"""ETL mínimo con una columna incorrecta para la demo de investigación."""

from airflow.sdk import dag, task


@dag(schedule=None, catchup=False, tags=["workshop", "agentic-airflow"])
def demo_pipeline():
    @task
    def extract() -> list[dict]:
        return [{"order_id": 1, "amount": 100}, {"order_id": 2, "amount": 50}]

    @task(retries=0)
    def transform(orders: list[dict]) -> dict:
        # Falla intencional: los registros contienen "amount", no "total".
        return {"revenue": sum(order["total"] for order in orders)}

    @task
    def load(summary: dict) -> None:
        print(summary)

    load(transform(extract()))


demo_pipeline()
