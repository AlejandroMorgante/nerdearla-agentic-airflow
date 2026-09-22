"""Pruebas del DAG con Airflow instalado, sin AWS ni base de datos."""
import importlib.util
from pathlib import Path
import unittest
from unittest.mock import MagicMock

from airflow.providers.amazon.aws.operators.bedrock import BedrockInvokeAgentRuntimeOperator
from airflow.task.trigger_rule import TriggerRule

spec = importlib.util.spec_from_file_location(
    "demo_pipeline", Path(__file__).resolve().parents[2] / "dags/demo_pipeline.py"
)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class DemoPipelineTests(unittest.TestCase):
    def test_failure_is_not_hidden_by_successful_investigation(self):
        dag = module.dag
        self.assertEqual({t.task_id for t in dag.leaves}, {"load", "investigate_failure"})
        self.assertEqual(dag.get_task("load").trigger_rule, TriggerRule.ALL_SUCCESS)
        investigation = dag.get_task("investigate_failure")
        self.assertIsInstance(investigation, BedrockInvokeAgentRuntimeOperator)
        self.assertEqual(investigation.upstream_task_ids, {"transform"})
        self.assertEqual(investigation.trigger_rule, TriggerRule.ONE_FAILED)
        self.assertEqual(investigation.retries, 0)

    def test_incident_is_rendered_and_sent_to_runtime(self):
        # Copia de la tarea: render_template_fields modifica la instancia.
        import copy
        task = copy.deepcopy(module.dag.get_task("investigate_failure"))
        task.render_template_fields({
            "var": {"value": {"agentcore_runtime_arn": "test-runtime", "mwaa_environment_name": "test-mwaa"}},
            "dag": module.dag, "run_id": "manual__incident",
        })
        task.hook = MagicMock()
        task.hook.conn.invoke_agent_runtime.return_value = {
            "contentType": "application/json", "response": b'{"status":"accepted"}'
        }
        result = task.execute({})
        import json
        call = task.hook.conn.invoke_agent_runtime.call_args.kwargs
        self.assertEqual(call["agentRuntimeArn"], "test-runtime")
        self.assertEqual(call["qualifier"], "workshop")
        self.assertEqual(json.loads(call["payload"]), {
            "environment_name": "test-mwaa", "dag_id": "demo_pipeline",
            "run_id": "manual__incident", "task_id": "transform",
        })
        self.assertEqual(result["response"]["status"], "accepted")

    def test_shell_demo_fails_on_total_and_recovers_with_amount(self):
        import os
        import subprocess
        import json
        extracted = subprocess.check_output(module.extract.bash_command, shell=True, text=True)
        env = dict(os.environ, ORDERS=extracted)
        failed = subprocess.run(module.transform.bash_command, shell=True, env=env, capture_output=True, text=True)
        self.assertNotEqual(failed.returncode, 0)
        self.assertIn("KeyError: 'total'", failed.stderr)
        fixed = subprocess.check_output(module.transform.bash_command.replace('order["total"]', 'order["amount"]'), shell=True, env=env, text=True)
        self.assertEqual(json.loads(fixed), {"revenue": 150})
