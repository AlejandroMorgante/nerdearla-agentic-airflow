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
        self.assertEqual({t.task_id for t in dag.leaves}, {"process_sales", "investigate_failure"})
        self.assertEqual(dag.get_task("process_sales").trigger_rule, TriggerRule.ALL_SUCCESS)
        investigation = dag.get_task("investigate_failure")
        self.assertIsInstance(investigation, BedrockInvokeAgentRuntimeOperator)
        self.assertEqual(investigation.upstream_task_ids, {"wait_for_sales"})
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
            "run_id": "manual__incident", "task_id": "wait_for_sales",
        })
        self.assertEqual(result["response"]["status"], "accepted")

    def test_sensor_propagates_access_denied_instead_of_waiting(self):
        from botocore.exceptions import ClientError
        sensor, client, stub = self.sales_sensor()
        stub.add_client_error("head_object", service_error_code="403", http_status_code=403,
                              expected_params={"Bucket": "sales-input", "Key": "incoming/sales.csv"})
        with stub, self.assertRaises(ClientError):
            sensor.poke({})
        stub.assert_no_pending_responses()

    def test_sensor_waits_only_when_file_is_missing(self):
        sensor, client, stub = self.sales_sensor()
        stub.add_client_error("head_object", service_error_code="404", http_status_code=404,
                              expected_params={"Bucket": "sales-input", "Key": "incoming/sales.csv"})
        with stub:
            self.assertFalse(sensor.poke({}))

    def test_sensor_accepts_existing_file(self):
        sensor, client, stub = self.sales_sensor()
        stub.add_response("head_object", {"ContentLength": 120},
                          {"Bucket": "sales-input", "Key": "incoming/sales.csv"})
        with stub:
            self.assertTrue(sensor.poke({}))

    def sales_sensor(self):
        import copy
        import boto3
        from botocore.stub import Stubber
        from airflow.providers.amazon.aws.hooks.s3 import S3Hook
        sensor = copy.deepcopy(module.wait_for_sales)
        sensor.bucket_name = "sales-input"
        client = boto3.client("s3", region_name="us-east-1",
                              aws_access_key_id="test", aws_secret_access_key="test")
        sensor.hook = S3Hook(aws_conn_id=None)
        sensor.hook.conn = client
        return sensor, client, Stubber(client)
