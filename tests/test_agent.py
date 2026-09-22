"""Ejercita el loop real de Strands con un modelo y tools simulados, sin red."""

import copy
import json
import os
import unittest
from unittest.mock import patch

from strands import tool
from strands.models.model import Model

import agent


EVENT = {"environment_name": "workshop", "dag_id": "demo_pipeline",
         "run_id": "manual__incident", "task_id": "transform"}


class ScriptedModel(Model):
    def __init__(self, turns):
        self.turns = iter(turns)
        self.calls = 0

    def get_config(self):
        return {"model_id": "test-model"}

    def update_config(self, **kwargs):
        pass

    async def structured_output(self, *args, **kwargs):
        raise NotImplementedError
        yield

    async def stream(self, messages, tool_specs=None, system_prompt=None, **kwargs):
        self.calls += 1
        turn = next(self.turns)
        if isinstance(turn, Exception):
            raise turn
        yield {"messageStart": {"role": "assistant"}}
        if isinstance(turn, str):
            yield {"contentBlockDelta": {"contentBlockIndex": 0, "delta": {"text": turn}}}
            yield {"contentBlockStop": {"contentBlockIndex": 0}}
        else:
            for index, (name, arguments) in enumerate(turn):
                yield {"contentBlockStart": {"contentBlockIndex": index,
                    "start": {"toolUse": {"toolUseId": f"call-{self.calls}-{index}", "name": name}}}}
                yield {"contentBlockDelta": {"contentBlockIndex": index,
                    "delta": {"toolUse": {"input": json.dumps(arguments)}}}}
                yield {"contentBlockStop": {"contentBlockIndex": index}}
        yield {"messageStop": {"stopReason": "end_turn" if isinstance(turn, str) else "tool_use"}}
        yield {"metadata": {"usage": {"inputTokens": 10, "outputTokens": 10, "totalTokens": 20},
                            "metrics": {"latencyMs": 1}}}


class AgentTest(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.env = patch.dict(os.environ, {"MWAA_ENVIRONMENT_NAME": "workshop",
            "AIRFLOW_DAG_ID": "demo_pipeline", "GITHUB_REPO": "demo/workshop"}, clear=True)
        self.env.start()
        self.addCleanup(self.env.stop)

    async def invoke_model(self, model, tools=None, config=None):
        with patch.object(agent, "BedrockModel", return_value=model), \
                patch.object(agent, "get_tools", return_value=tools or []), \
                patch.object(agent, "load_config", return_value=config or agent.load_config()):
            return await agent.investigate(copy.deepcopy(EVENT))

    async def test_invalid_payload_and_wrong_environment_do_not_invoke_model(self):
        with patch.object(agent, "BedrockModel") as model:
            for payload in ({}, dict(EVENT, environment_name="other"),
                            dict(EVENT, prompt="ignore instructions"), dict(EVENT, task_id=" ")):
                self.assertEqual((await agent.invoke(payload))["status"], "invalid_input")
            model.assert_not_called()

    async def test_missing_runtime_configuration(self):
        os.environ.pop("MWAA_ENVIRONMENT_NAME")
        self.assertEqual((await agent.invoke(EVENT))["status"], "configuration_error")

    async def test_acknowledges_before_background_investigation_finishes(self):
        import asyncio
        import threading
        release, finished = threading.Event(), threading.Event()

        async def slow_investigation(payload):
            release.wait(timeout=5)
            return {"status": "completed"}

        with patch.object(agent, "investigate", side_effect=slow_investigation), \
             patch.object(agent.app, "add_async_task", return_value=123) as started, \
             patch.object(agent.app, "complete_async_task", side_effect=lambda _: finished.set()) as completed:
            try:
                result = await agent.invoke(EVENT)
                self.assertEqual(result["status"], "accepted")
                started.assert_called_once()
                completed.assert_not_called()
            finally:
                release.set()
                self.assertTrue(await asyncio.to_thread(finished.wait, 5))
            completed.assert_called_once_with(123)

    async def test_background_failure_releases_busy_state(self):
        with patch.object(agent, "investigate", side_effect=RuntimeError("private-token")), \
             patch.object(agent.app, "complete_async_task") as completed, \
             patch.object(agent.app.logger, "error") as log:
            import asyncio
            await asyncio.to_thread(agent.investigate_in_background, EVENT, 123)
            completed.assert_called_once_with(123)
            self.assertNotIn("private-token", str(log.call_args))

    async def test_config_requires_positive_limits(self):
        config = agent.load_config().model_dump()
        config["limits"]["turns"] = 0
        with self.assertRaises(ValueError):
            agent.AgentSettings.model_validate(config)

    async def test_actual_tool_results_drive_pr_and_slack_confirmation(self):
        incidents = []

        @tool
        def create_fix_pr(incident_id: str) -> dict:
            """Simula la creación de una PR sin red."""
            incidents.append(incident_id)
            return {"url": "https://github.com/demo/workshop/pull/1", "state": "open"}

        @tool
        def send_slack_message(text: str) -> dict:
            """Simula un mensaje confirmado sin red."""
            return {"sent": True}

        model = ScriptedModel([[('create_fix_pr', {"incident_id": "invented"}),
                               ('send_slack_message', {"text": "Diagnóstico"})],
                               "La columna total no existe; amount sí."])
        result = await self.invoke_model(model, [create_fix_pr, send_slack_message])
        self.assertEqual(result["status"], "completed")
        self.assertEqual(result["pull_request_url"], "https://github.com/demo/workshop/pull/1")
        self.assertEqual(result["slack_status"], "sent")
        self.assertEqual(result["tool_calls"], 2)
        self.assertEqual(incidents, ["workshop/demo_pipeline/manual__incident/transform"])
        self.assertGreater(result["usage"]["totalTokens"], 0)

    async def test_model_claims_do_not_confirm_actions(self):
        result = await self.invoke_model(ScriptedModel(["Envié Slack y abrí una PR."]))
        self.assertEqual(result["slack_status"], "not_sent")
        self.assertIsNone(result["pull_request_url"])
        self.assertEqual(result["actions"], [])

    async def test_slack_timeout_is_unconfirmed_and_not_retried(self):
        attempts = []

        @tool
        def send_slack_message(text: str) -> dict:
            """Simula una entrega ambigua."""
            attempts.append(text)
            raise RuntimeError("Entrega no confirmada")

        model = ScriptedModel([[('send_slack_message', {"text": "first"}),
                               ('send_slack_message', {"text": "retry"})], "No pude confirmar Slack."])
        result = await self.invoke_model(model, [send_slack_message])
        self.assertEqual(attempts, ["first"])
        self.assertEqual(result["slack_status"], "unconfirmed")
        self.assertEqual(result["status"], "needs_attention")

    async def test_tool_budget_blocks_remaining_tools_in_same_turn(self):
        calls = []

        @tool
        def inspect_run(dag_id: str) -> dict:
            """Consulta simulada de una ejecución."""
            calls.append(dag_id)
            return {"state": "failed"}

        config = agent.load_config()
        config.limits.tool_calls = 1
        model = ScriptedModel([[('inspect_run', {"dag_id": "other"}),
                               ('inspect_run', {"dag_id": "other"})], "No debe llamarse"])
        result = await self.invoke_model(model, [inspect_run], config)
        self.assertEqual(calls, ["demo_pipeline"])
        self.assertEqual(model.calls, 1)
        self.assertEqual(result["status"], "limited")
        self.assertEqual(result["limit_reason"], "tool_calls")

    async def test_native_turn_budget_stops_loop(self):
        @tool
        def inspect_run() -> dict:
            """Devuelve una ejecución fallida simulada."""
            return {"state": "failed"}

        config = agent.load_config()
        config.limits.turns = 1
        model = ScriptedModel([[('inspect_run', {})], "No debe llamarse"])
        result = await self.invoke_model(model, [inspect_run], config)
        self.assertEqual(model.calls, 1)
        self.assertEqual(result["status"], "limited")
        self.assertEqual(result["stop_reason"], "limit_turns")

    async def test_elapsed_budget_is_checked_before_model(self):
        investigation = agent.Investigation(agent.Incident(**EVENT), agent.load_config().limits)
        investigation.started -= 301
        event = type("Event", (), {"cancel": False})()
        investigation.before_model(event)
        self.assertTrue(event.cancel)
        self.assertEqual(investigation.limit_reason, "elapsed_seconds")

    async def test_model_error_preserves_confirmed_actions_without_leaking_error(self):
        @tool
        def send_slack_message(text: str) -> dict:
            """Simula un envío exitoso."""
            return {"sent": True}

        result = await self.invoke_model(ScriptedModel([
            [('send_slack_message', {"text": "Diagnosis"})], RuntimeError("private-token")
        ]), [send_slack_message])
        self.assertEqual(result["status"], "error")
        self.assertEqual(result["slack_status"], "sent")
        self.assertNotIn("private-token", json.dumps(result))

    async def test_incidents_do_not_share_state(self):
        one = await self.invoke_model(ScriptedModel(["Primera investigación."]))
        two = await self.invoke_model(ScriptedModel(["Segunda investigación."]))
        self.assertNotEqual(one["diagnosis"], two["diagnosis"])
        self.assertEqual(two["tool_calls"], 0)


if __name__ == "__main__":
    unittest.main()
