FROM python:3.9-slim

WORKDIR /app

# Copy requirements first for better caching
COPY ./producer/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy the rest of the application
COPY ./producer /app/producer
COPY ./models /app/models

# Set environment variables
ENV PYTHONUNBUFFERED=1

# Run the producer
CMD ["python", "producer/producer.py"]
