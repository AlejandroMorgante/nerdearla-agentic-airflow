"""Pruebas sin credenciales ni llamadas externas; ejecutar dentro de Docker."""

import base64
import io
import os
import unittest
from unittest.mock import MagicMock, patch

import boto3
import requests
from botocore.response import StreamingBody
from botocore.stub import Stubber

import tools


class ToolsTest(unittest.TestCase):
    def setUp(self):
        self.env = patch.dict(os.environ, {
            "MWAA_ENVIRONMENT_NAME": "workshop", "AIRFLOW_DAG_ID": "demo_pipeline",
            "GITHUB_REPO": "demo/workshop", "GITHUB_SECRET_ID": "github-secret",
            "SLACK_SECRET_ID": "slack-secret", "GITHUB_BASE_BRANCH": "main",
            "GITHUB_DAG_PATH": "dags/demo_pipeline.py", "ENABLE_DAG_RERUN": "false",
            "GITHUB_IAM_PATH": "infra/mwaa/sales-access.tf",
            "SALES_INPUT_BUCKET": "sales-input", "SALES_INPUT_KEY": "incoming/sales.csv",
        }, clear=True)
        self.env.start()
        self.addCleanup(self.env.stop)

    def aws(self, service):
        client = boto3.client(service, region_name="us-east-1",
                              aws_access_key_id="test", aws_secret_access_key="test")
        stub = Stubber(client)
        stub.activate()
        self.addCleanup(stub.deactivate)
        return client, stub

    def test_secrets_are_read_again_after_rotation(self):
        client, stub = self.aws("secretsmanager")
        for value in ("first", "rotated"):
            stub.add_response("get_secret_value", {"SecretString": '{"token":"' + value + '"}'},
                              {"SecretId": "github-secret"})
        with patch.object(tools, "_client", return_value=client):
            self.assertEqual(tools._secret("GITHUB_SECRET_ID", "token"), "first")
            self.assertEqual(tools._secret("GITHUB_SECRET_ID", "token"), "rotated")
        stub.assert_no_pending_responses()

    def test_malformed_secret_does_not_leak_value(self):
        client = MagicMock()
        client.get_secret_value.return_value = {"SecretString": "private-value"}
        with patch.object(tools, "_client", return_value=client):
            with self.assertRaises(ValueError) as error:
                tools._secret("GITHUB_SECRET_ID", "token")
        self.assertNotIn("private-value", str(error.exception))

    def test_mwaa_run_path_and_environment(self):
        client, stub = self.aws("mwaa")
        stub.add_response("invoke_rest_api", {
            "RestApiStatusCode": 200, "RestApiResponse": {"state": "failed"},
        }, {"Name": "workshop", "Path": "/dags/demo_pipeline/dagRuns/manual__a%2Bb",
            "Method": "GET"})
        with patch.object(tools, "_client", return_value=client):
            self.assertEqual(tools.get_dag_run("demo_pipeline", "manual__a+b"), {"state": "failed"})
        stub.assert_no_pending_responses()

    def test_other_dag_is_rejected_before_network(self):
        with patch.object(tools, "_client") as client:
            with self.assertRaises(ValueError):
                tools.get_dag_run("other", "run")
            client.assert_not_called()

    def test_airflow_http_error_is_not_success(self):
        client = MagicMock()
        client.invoke_rest_api.return_value = {"RestApiStatusCode": 403, "RestApiResponse": {}}
        with patch.object(tools, "_client", return_value=client):
            with self.assertRaisesRegex(RuntimeError, "403"):
                tools.get_dag_run("demo_pipeline", "run")

    def test_logs_preserve_paging_and_report_truncation(self):
        client, stub = self.aws("logs")
        prefix = "dag_id=demo_pipeline/run_id=run/task_id=transform/"
        stub.add_response("get_log_events", {
            "events": [{"timestamp": 1, "message": "x" * 4001}],
            "nextBackwardToken": "older", "nextForwardToken": "newer",
        }, {"logGroupName": "airflow-workshop-Task", "logStreamName": prefix + "attempt=1.log",
            "limit": 100, "startFromHead": False, "nextToken": "older"})
        with patch.object(tools, "_log_location", return_value=("airflow-workshop-Task", prefix)), \
                patch.object(tools, "_client", return_value=client):
            result = tools.read_task_logs("demo_pipeline", "run", "transform",
                                          prefix + "attempt=1.log", next_token="older")
        self.assertTrue(result["at_start"])
        self.assertTrue(result["messages_truncated"])
        stub.assert_no_pending_responses()

    def test_deployed_source_is_bounded_and_stream_closed(self):
        raw = io.BytesIO(b"amount = 150\n")
        body = StreamingBody(raw, 13)
        client = MagicMock()
        client.get_object.return_value = {"Body": body, "VersionId": "v1"}
        with patch.object(tools, "_environment", return_value={
            "SourceBucketArn": "arn:aws:s3:::workshop", "DagS3Path": "dags",
        }), patch.object(tools, "_client", return_value=client):
            result = tools.read_deployed_dag()
        self.assertEqual(result["content"], "amount = 150\n")
        self.assertTrue(raw.closed)
        client.get_object.assert_called_once_with(Bucket="workshop", Key="dags/demo_pipeline.py")
        with self.assertRaises(ValueError):
            tools.read_deployed_dag("../secret")

    @patch.object(tools, "_github")
    def test_existing_pr_is_reused_without_writes(self, github):
        github.return_value = [{"html_url": "https://github.com/demo/workshop/pull/1", "state": "open"}]
        result = tools.create_fix_pr("incident", "sha", "amount = 150\n", "Fix", "Diagnosis")
        self.assertTrue(result["reused"])
        self.assertEqual(github.call_count, 1)
        self.assertEqual(github.call_args.args[0], "GET")

    def test_stale_fix_is_rejected_before_branch_creation(self):
        with patch.object(tools, "_github", side_effect=[[], None, {"object": {"sha": "commit"}}]) as github, \
                patch.object(tools, "_repo_file", return_value={"sha": "new", "content": "old"}):
            with self.assertRaisesRegex(ValueError, "cambió"):
                tools.create_fix_pr("incident", "old", "amount = 150\n", "Fix", "Diagnosis")
        self.assertTrue(all(call.args[0] == "GET" for call in github.call_args_list))

    def test_pr_is_draft_and_modifies_only_configured_file(self):
        with patch.object(tools, "_github", side_effect=[
            [], None, {"object": {"sha": "commit"}}, {}, {},
            {"html_url": "https://github.com/demo/workshop/pull/1", "state": "open"},
        ]) as github, patch.object(tools, "_repo_file", return_value={"sha": "original", "content": "old"}):
            result = tools.create_fix_pr("incident", "original", "amount = 150\n", "Fix", "Diagnosis")
        self.assertFalse(result["reused"])
        update = github.call_args_list[-2]
        self.assertEqual(update.args, ("PUT", "/contents/dags/demo_pipeline.py"))
        self.assertEqual(base64.b64decode(update.kwargs["json"]["content"]), b"amount = 150\n")
        self.assertTrue(github.call_args.kwargs["json"]["draft"])

    def test_pr_rejects_unconfigured_terraform_path_before_network(self):
        with patch.object(tools, "_github") as github:
            with self.assertRaisesRegex(ValueError, "habilitado"):
                tools.create_fix_pr("incident", "sha", "content", "Fix", "Why", path="infra/main.tf")
            github.assert_not_called()

    def test_pr_accepts_configured_iam_file_as_draft(self):
        content = 'resource "aws_iam_role_policy" "sales" {}'
        with patch.object(tools, "_github", side_effect=[
            [], None, {"object": {"sha": "commit"}}, {}, {},
            {"html_url": "https://github.com/demo/workshop/pull/2", "state": "open"},
        ]) as github, patch.object(tools, "_repo_file", return_value={"sha": "original", "content": "old"}):
            tools.create_fix_pr("incident", "original", content, "Fix", "Why", path="infra/mwaa/sales-access.tf")
        self.assertEqual(github.call_args_list[-2].args, ("PUT", "/contents/infra/mwaa/sales-access.tf"))
        self.assertTrue(github.call_args.kwargs["json"]["draft"])

    def test_file_inspection_uses_only_configured_location(self):
        client, stub = self.aws("s3")
        stub.add_response("head_object", {"ContentLength": 120},
                          {"Bucket": "sales-input", "Key": "incoming/sales.csv"})
        with stub, patch.object(tools, "_client", return_value=client):
            self.assertEqual(tools.inspect_sales_file()["checked_as"], "agent_runtime_role")
        stub.assert_no_pending_responses()

    def test_permission_inspection_targets_mwaa_role_and_pipeline_resources(self):
        iam = MagicMock()
        arn = "arn:aws:iam::000000000000:role/workshop-mwaa"
        iam.get_role.return_value = {"Role": {"Arn": arn}}
        iam.get_paginator.return_value.paginate.side_effect = [
            [{"PolicyNames": ["sales"]}], [{"AttachedPolicies": []}],
        ]
        iam.get_role_policy.return_value = {"PolicyDocument": {"Statement": []}}
        iam.simulate_principal_policy.return_value = {"EvaluationResults": []}
        with patch.object(tools, "_environment", return_value={"ExecutionRoleArn": arn}), \
                patch.object(tools, "_client", return_value=iam):
            result = tools.inspect_mwaa_permissions()
        self.assertEqual(result["role_arn"], arn)
        checks = iam.simulate_principal_policy.call_args_list
        self.assertEqual(len(checks), 1)
        self.assertEqual(checks[0].kwargs["PolicySourceArn"], arn)
        self.assertEqual(checks[0].kwargs["ResourceArns"], ["arn:aws:s3:::sales-input/incoming/sales.csv"])

    def test_invalid_python_never_reaches_github(self):
        with patch.object(tools, "_github") as github:
            with self.assertRaises(SyntaxError):
                tools.create_fix_pr("incident", "sha", "def broken(", "Fix", "Diagnosis")
            github.assert_not_called()

    def test_github_token_is_header_only(self):
        response = MagicMock(status_code=200)
        response.json.return_value = {"ok": True}
        with patch.object(tools, "_secret", return_value="private-token"), \
                patch.object(requests, "request", return_value=response) as request:
            tools._github("GET", "/pulls")
        self.assertEqual(request.call_args.kwargs["headers"]["Authorization"], "Bearer private-token")
        self.assertNotIn("private-token", request.call_args.args[1])

    def test_slack_success_and_network_error_redaction(self):
        webhook = "https://hooks.slack.com/services/private/path/token"
        with patch.object(tools, "_secret", return_value=webhook), \
                patch.object(requests, "post", return_value=MagicMock(status_code=200, text="ok")) as post:
            self.assertEqual(tools.send_slack_message("Diagnosis"), {"sent": True})
            post.assert_called_once()
            post.side_effect = requests.Timeout(webhook)
            with self.assertRaises(RuntimeError) as error:
                tools.send_slack_message("Diagnosis")
            self.assertNotIn(webhook, str(error.exception))

    def test_rerun_disabled_by_default(self):
        self.assertNotIn(tools.rerun_dag, tools.get_tools())
        with patch.object(tools, "_airflow") as airflow:
            with self.assertRaises(ValueError):
                tools.rerun_dag("demo_pipeline", "run")
            airflow.assert_not_called()

    def test_rerun_stable_id_and_no_recovery_chain(self):
        os.environ["ENABLE_DAG_RERUN"] = "true"
        with patch.object(tools, "_airflow", return_value={"state": "failed", "conf": {"date": "2026-09-21"}}) as airflow:
            tools.rerun_dag("demo_pipeline", "run")
            body = airflow.call_args.kwargs["Body"]
            tools.rerun_dag("demo_pipeline", "run")
            self.assertEqual(body, airflow.call_args.kwargs["Body"])
            self.assertEqual(body["conf"], {"date": "2026-09-21"})
            self.assertTrue(body["dag_run_id"].startswith("agent_recovery__"))
            with self.assertRaises(ValueError):
                tools.rerun_dag("demo_pipeline", body["dag_run_id"])

    def test_tools_have_strands_schemas_without_loading_secrets(self):
        with patch.object(tools, "_client") as client:
            schemas = [t.tool_spec for t in tools.get_tools()]
            self.assertEqual(len(schemas), 12)
            self.assertTrue(all(s["inputSchema"]["json"]["type"] == "object" for s in schemas))
            client.assert_not_called()


if __name__ == "__main__":
    unittest.main()
