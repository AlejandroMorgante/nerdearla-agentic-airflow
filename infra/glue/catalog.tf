resource "aws_glue_catalog_database" "sales" {
  name = replace("${var.config.project}_sales", "-", "_")
}

# Esquema fijo del Parquet que escribe sales.py; no requiere un crawler.
resource "aws_glue_catalog_table" "sales" {
  name          = "sales"
  database_name = aws_glue_catalog_database.sales.name
  table_type    = "EXTERNAL_TABLE"
  parameters    = { EXTERNAL = "TRUE", classification = "parquet" }
  storage_descriptor {
    location      = "s3://${var.output_bucket}/sales/"
    input_format  = "org.apache.hadoop.hive.ql.io.parquet.MapredParquetInputFormat"
    output_format = "org.apache.hadoop.hive.ql.io.parquet.MapredParquetOutputFormat"
    ser_de_info {
      serialization_library = "org.apache.hadoop.hive.ql.io.parquet.serde.ParquetHiveSerDe"
    }
    dynamic "columns" {
      for_each = [
        { name = "sale_id", type = "int" },
        { name = "product", type = "string" },
        { name = "quantity", type = "int" },
        { name = "unit_price", type = "decimal(12,2)" },
        { name = "amount", type = "decimal(18,2)" },
      ]
      content {
        name = columns.value.name
        type = columns.value.type
      }
    }
  }
}
