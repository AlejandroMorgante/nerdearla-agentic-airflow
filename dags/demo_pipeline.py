"""Ingesta de ventas: esperar un CSV en S3 y procesarlo con Glue y resumirlo con Athena."""

from airflow.providers.amazon.aws.operators.athena import AthenaOperator
from airflow.providers.amazon.aws.operators.bedrock import BedrockInvokeAgentRuntimeOperator
from airflow.providers.amazon.aws.operators.glue import GlueJobOperator
from airflow.providers.amazon.aws.sensors.s3 import S3KeySensor
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

    wait_for_sales = S3KeySensor(
        task_id="wait_for_sales",
        bucket_name="{{ var.value.sales_input_bucket }}",
        bucket_key="incoming/sales.csv",
        aws_conn_id=None,
        deferrable=False,
        mode="reschedule",
        poke_interval=30,
        timeout=300,
    )

    process_sales = GlueJobOperator(
        task_id="process_sales",
        job_name="{{ var.value.sales_glue_job }}",
        aws_conn_id=None,
        update_config=False,
        wait_for_completion=True,
        deferrable=False,
        verbose=False,
    )

    summarize_sales = AthenaOperator(
        task_id="summarize_sales",
        query="""
            SELECT product, SUM(quantity) AS units, SUM(amount) AS revenue
            FROM sales
            GROUP BY product
            ORDER BY revenue DESC
        """,
        database="{{ var.value.sales_database }}",
        workgroup="{{ var.value.sales_athena_workgroup }}",
        aws_conn_id=None,
        deferrable=False,
    )

    investigate_failure = BedrockInvokeAgentRuntimeOperator(
        task_id="investigate_failure",
        trigger_rule=TriggerRule.ONE_FAILED,
        agent_runtime_arn="{{ var.value.agentcore_runtime_arn }}",
        payload={
            "environment_name": "{{ var.value.mwaa_environment_name }}",
            "dag_id": "{{ dag.dag_id }}",
            "run_id": "{{ run_id }}",
            "task_id": "wait_for_sales",
        },
        invoke_agent_runtime_kwargs={"qualifier": "workshop"},
        aws_conn_id=None,
        do_xcom_push=False,
        botocore_config={"read_timeout": 120, "retries": {"total_max_attempts": 1}},
    )

    wait_for_sales >> process_sales >> summarize_sales
    wait_for_sales >> investigate_failure
