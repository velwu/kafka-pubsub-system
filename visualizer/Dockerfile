# visualizer/Dockerfile
FROM python:3.9-slim

WORKDIR /app

# Install system dependencies for matplotlib
RUN apt-get update && apt-get install -y \
    gcc \
    g++ \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements
COPY visualizer/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY models/ ./models/
COPY visualizer/dashboard.py ./visualizer/

# Create output directory
RUN mkdir -p /app/visualizations

CMD ["python", "visualizer/dashboard.py"]
