FROM python:3.12-slim@sha256:2f17fc044b579bab302c2e8054d3a686e2cb9a83de48e70534b94cd8ebbe06a9 AS builder
WORKDIR /app
COPY container/requirements.txt .
RUN pip install --no-cache-dir --prefix=/install -r requirements.txt

FROM python:3.12-slim@sha256:2f17fc044b579bab302c2e8054d3a686e2cb9a83de48e70534b94cd8ebbe06a9
WORKDIR /app
RUN useradd --uid 10001 --create-home agent
COPY --from=builder /install /usr/local
COPY agent.py tools.py config.yaml ./
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1
USER agent
EXPOSE 8080
CMD ["python", "agent.py"]
