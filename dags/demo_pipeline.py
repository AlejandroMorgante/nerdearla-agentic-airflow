"""Ingesta de ventas: esperar un CSV en S3 y procesarlo con Glue y resumirlo con Athena."""

from airflow.providers.amazon.aws.operators.athena import AthenaOperator
from airflow.providers.amazon.aws.operators.bedrock import BedrockInvokeAgentRuntimeOperator
from airflow.providers.amazon.aws.operators.glue import GlueJobOperator
from airflow.providers.amazon.aws.sensors.s3 import S3KeySensor
from airflow.sdk import DAG
from airflow.task.trigger_rule import TriggerRule


def _record_failed_task(context):
    """on_failure_callback: deja el task_id real en XCom para investigate_failure."""
    context["ti"].xcom_push(key="failed_task_id", value=context["ti"].task_id)


with DAG(
    dag_id="demo_pipeline",
    schedule=None,
    catchup=False,
    max_active_runs=1,
    default_args={"retries": 0},
    tags=["workshop", "agentic-airflow"],
) as dag:

    wait_for_sales = S3KeySensor(
        task_id="wait_for_sales",
        bucket_name="{{ var.value.sales_input_bucket }}",
        bucket_key="incoming/sales.csv",
        aws_conn_id=None,
        mode="reschedule",
        poke_interval=30,
        timeout=300,
        on_failure_callback=_record_failed_task,
    )

    process_sales = GlueJobOperator(
        task_id="process_sales",
        job_name="sales-etl",
        aws_conn_id=None,
        on_failure_callback=_record_failed_task,
    )

    summarize_sales = AthenaOperator(
        task_id="summarize_sales",
        query="""
            SELECT product, SUM(quantity) AS units, SUM(amount) AS revenue
            FROM sales
            GROUP BY product
            ORDER BY revenue DESC
        """,
        database="sales",
        workgroup="sales-reports",
        aws_conn_id=None,
        on_failure_callback=_record_failed_task,
    )

    investigate_failure = BedrockInvokeAgentRuntimeOperator(
        task_id="investigate_failure",
        trigger_rule=TriggerRule.ONE_FAILED,
        agent_runtime_arn="{{ var.value.agentcore_runtime_arn }}",
        payload={
            "environment_name": "{{ var.value.mwaa_environment_name }}",
            "dag_id": "{{ dag.dag_id }}",
            "run_id": "{{ run_id }}",
            "task_id": "{{ ti.xcom_pull(key='failed_task_id') }}",
        },
        invoke_agent_runtime_kwargs={"qualifier": "workshop"},
        aws_conn_id=None,
        do_xcom_push=False,
        botocore_config={"read_timeout": 600, "retries": {"total_max_attempts": 1}},
    )

    wait_for_sales >> process_sales >> summarize_sales
    [wait_for_sales, process_sales, summarize_sales] >> investigate_failure
