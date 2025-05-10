# Kafka Pub/Sub System for Insurance Policy Events

A containerized pub/sub system using Kafka and Python, designed to simulate an insurance company's policy event processing pipeline.

- 🔄 Event-driven architecture showcasing real-time insurance data processing

- 🐳 Fully containerized with Docker and Docker Compose

- 🐍 Clean Python implementation with proper error handling

- 📊 Includes statistics tracking and monitoring capabilities

- 📝 Realistic insurance policy data model

## System Overview

This system demonstrates a simple but realistic pub/sub architecture for processing insurance policy events:

- **Producer**: Generates random insurance policy events (creation, updates, claims, etc.) and publishes them to a Kafka topic.
- **Consumer**: Subscribes to the Kafka topic, processes the events, and displays statistics.

## Architecture

- **Kafka**: Message broker for reliable event streaming
- **Zookeeper**: Required for Kafka cluster management
- **Kafka UI**: Web interface for monitoring Kafka topics and messages
- **Policy Producer**: Python application that generates and publishes policy events
- **Policy Consumer**: Python application that consumes and processes policy events

## Data Model

The system processes insurance policy events with the following structure:

```json
{
  "event_id": "uuid-string",
  "event_timestamp": "2025-05-10T14:30:00Z",
  "event_type": "POLICY_CREATED",
  "customer_id": "CUS123456",
  "policy_details": {
    "policy_id": "POL987654",
    "policy_type": "LIFE",
    "premium_amount": 1250.00,
    "coverage_amount": 500000.00,
    "start_date": "2025-06-01",
    "end_date": "2026-06-01",
    "risk_score": 85.7
  },
  "metadata": {
    "source_system": "online_portal",
    "processing_priority": "standard"
  }
}
```

## Getting Started

### Prerequisites
Docker and Docker Compose
Git

### Running the System

1. Clone the repository:
```sh
git clone https://github.com/velwu/kafka-pubsub-system.git
cd kafka-pubsub-system
```

2. Start the system:
```sh
docker-compose up --build
```

3. Access the Kafka UI at http://localhost:8080 to monitor topics and messages.

4. To stop the system:
```sh
docker-compose down
```

### Day-to-day Operations

For ongoing development and maintenance, these commands will be useful:

Start the system (after initial build). Add -d flag to run in detached mode (background):

```sh
docker-compose up -d
```

View logs (when running in detached mode):
```sh
docker-compose logs -f
```

To view logs for a specific service:
```sh
docker-compose logs -f policy-producer
```

Stop containers (without removing them):
```sh
docker-compose stop
```

Restart stopped containers:
```sh
docker-compose start
```

Pause data generation (while keeping Kafka running):
```sh
docker stop policy-producer
```

And to resume:
```sh
docker start policy-producer
```

Rebuild and restart a specific service (after code changes):
```sh
docker-compose up --build policy-producer
```

Stop and remove containers:
```sh
docker-compose down
```

⚠️ Warning: This action below will delete all stored data.
Full cleanup (remove all data, including volumes):
```sh
docker-compose down -v
```

---

## Configuration
The system can be configured using environment variables in the docker-compose.yml file:

### Producer Configuration
- KAFKA_BOOTSTRAP_SERVERS: Kafka broker address (default: kafka:29092)
- KAFKA_TOPIC: Topic to publish events to (default: policy-events)
- BATCH_SIZE: Number of events to generate in each batch (default: 10)
- INTERVAL_SECONDS: Seconds between each batch (default: 5)

### Consumer Configuration
- KAFKA_BOOTSTRAP_SERVERS: Kafka broker address (default: kafka:29092)
- KAFKA_TOPIC: Topic to consume events from (default: policy-events)
- CONSUMER_GROUP: Consumer group ID (default: policy-processor)

### Real-world Example
In a real production environment, we might have:
- `docker-compose.dev.yml` - Development config with verbose logging, small batch sizes
- `docker-compose.test.yml` - Testing config with test topics
- `docker-compose.prod.yml` - Production config with optimized settings

We would then run with: `docker-compose -f docker-compose.prod.yml up`

### Design Decisions
1. Docker Containerization: All components are containerized for isolation and ease of deployment.
2. Schema Design: The event schema is designed to be realistic for an insurance company, with policy details and metadata.
3. Error Handling: Both producer and consumer include robust error handling and retries for Kafka connection issues.
4. Statistics Tracking: The consumer tracks and displays event processing statistics periodically.
5. Message Partitioning: Events are partitioned by customer_id to ensure related events are processed sequentially.

### Potential Enhancements
- Add schema validation using Avro or JSON Schema
- Implement a more sophisticated consumer with filtering capabilities
- Add a REST API for querying event statistics
- Implement multiple consumer groups for different processing needs
- Add monitoring and alerting for system health
