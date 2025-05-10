FROM python:3.9-slim

WORKDIR /app

# Copy requirements first for better caching
COPY ./consumer/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy the rest of the application
COPY ./consumer /app/consumer
COPY ./models /app/models

# Set environment variables
ENV PYTHONUNBUFFERED=1

# Run the consumer
CMD ["python", "consumer/consumer.py"]
