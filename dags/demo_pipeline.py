"""ETL mínimo: si transform falla, AgentCore recibe el incidente y hace el triage."""

from airflow.providers.amazon.aws.operators.bedrock import BedrockInvokeAgentRuntimeOperator
from airflow.providers.standard.operators.bash import BashOperator
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
    extract = BashOperator(
        task_id="extract",
        bash_command='echo \'[{"order_id": 1, "amount": 100}, {"order_id": 2, "amount": 50}]\'',
    )

    transform = BashOperator(
        task_id="transform",
        env={"ORDERS": "{{ ti.xcom_pull(task_ids='extract') }}"},
        append_env=True,
        # Falla intencional: los registros contienen "amount", no "total".
        bash_command="""python - <<'PY'
import json, os
orders = json.loads(os.environ["ORDERS"])
print(json.dumps({"revenue": sum(order["total"] for order in orders)}))
PY""",
    )

    load = BashOperator(
        task_id="load",
        env={"SUMMARY": "{{ ti.xcom_pull(task_ids='transform') }}"},
        append_env=True,
        bash_command='echo "Resultado: $SUMMARY"',
    )

    investigate_failure = BedrockInvokeAgentRuntimeOperator(
        task_id="investigate_failure",
        trigger_rule=TriggerRule.ONE_FAILED,
        agent_runtime_arn="{{ var.value.agentcore_runtime_arn }}",
        payload={
            "environment_name": "{{ var.value.mwaa_environment_name }}",
            "dag_id": "{{ dag.dag_id }}",
            "run_id": "{{ run_id }}",
            "task_id": "transform",
        },
        invoke_agent_runtime_kwargs={"qualifier": "workshop"},
        aws_conn_id=None,
        do_xcom_push=False,
        botocore_config={"read_timeout": 120, "retries": {"total_max_attempts": 1}},
    )

    extract >> transform >> load
    transform >> investigate_failure
    # load queda upstream_failed: aceptar el incidente no vuelve exitoso al DAG.
