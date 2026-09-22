"""Una división por cero dispara el triage asíncrono en AgentCore."""

from airflow.providers.amazon.aws.operators.bedrock import BedrockInvokeAgentRuntimeOperator
from airflow.providers.standard.operators.bash import BashOperator
from airflow.providers.standard.operators.empty import EmptyOperator
from airflow.sdk import DAG
from airflow.task.trigger_rule import TriggerRule


with DAG(
    dag_id="demo_pipeline",
    schedule=None,
    catchup=False,
    max_active_runs=1,
    default_args={"retries": 0},
    tags=["workshop", "agentic-airflow"],
) as dag:
    divide_numbers = BashOperator(
        task_id="divide_numbers",
        bash_command="python -c 'print(10 / 0)'",
    )

    finish = EmptyOperator(task_id="finish")

    investigate_failure = BedrockInvokeAgentRuntimeOperator(
        task_id="investigate_failure",
        trigger_rule=TriggerRule.ONE_FAILED,
        agent_runtime_arn="{{ var.value.agentcore_runtime_arn }}",
        payload={
            "environment_name": "{{ var.value.mwaa_environment_name }}",
            "dag_id": "{{ dag.dag_id }}",
            "run_id": "{{ run_id }}",
            "task_id": "divide_numbers",
        },
        invoke_agent_runtime_kwargs={"qualifier": "workshop"},
        aws_conn_id=None,
        do_xcom_push=False,
        botocore_config={"read_timeout": 120, "retries": {"total_max_attempts": 1}},
    )

    divide_numbers >> [finish, investigate_failure]
