# HW8 image for the Kafka worker and the FastAPI wrapper (build context: code/)
FROM python:3.11-slim
WORKDIR /app
RUN pip install --no-cache-dir confluent-kafka==2.5.3 fastapi==0.115.0 uvicorn==0.30.6
COPY kafka_service /app/kafka_service
ENV PYTHONUNBUFFERED=1
