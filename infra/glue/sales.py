"""Valida ventas y genera Parquet con el importe de cada venta."""
import sys

from awsglue.context import GlueContext
from awsglue.job import Job
from awsglue.utils import getResolvedOptions
from pyspark.context import SparkContext
from pyspark.sql import functions as F

args = getResolvedOptions(sys.argv, ["JOB_NAME", "INPUT_URI", "OUTPUT_URI"])
context = GlueContext(SparkContext.getOrCreate())
job = Job(context)
job.init(args["JOB_NAME"], args)

sales = (context.spark_session.read.option("header", True).option("mode", "FAILFAST")
         .schema("sale_id INT, product STRING, quantity INT, unit_price DECIMAL(12,2)")
         .csv(args["INPUT_URI"]))
sales = sales.withColumn("product", F.trim("product"))
invalid = sales.filter(
    F.col("sale_id").isNull() | F.col("product").isNull() | (F.col("product") == "")
    | F.col("quantity").isNull() | (F.col("quantity") <= 0)
    | F.col("unit_price").isNull() | (F.col("unit_price") < 0)
)
if not sales.take(1) or invalid.take(1):
    raise ValueError("El archivo está vacío o contiene ventas inválidas.")

(sales.withColumn("amount", (F.col("quantity") * F.col("unit_price")).cast("decimal(18,2)"))
 .write.mode("overwrite").parquet(args["OUTPUT_URI"]))
job.commit()
