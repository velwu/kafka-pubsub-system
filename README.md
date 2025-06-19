# Kafka Real-Time Activity Data Streaming Pipeline

A high-performance, containerized streaming data pipeline using Apache Kafka and Python, designed to demonstrate real-time processing of GPS and fitness data from Garmin devices.

- 🚴 Real-time activity data streaming from multiple device types
- 📍 GPS tracking with movement simulation and anomaly detection
- 💓 Health metrics monitoring (heart rate, cadence, power)
- 📊 Live analytics dashboard with performance insights
- 🐳 Production-ready containerized architecture

## System Overview

This system demonstrates a scalable streaming architecture for processing real-time activity data from Garmin devices:

- **Producer**: Simulates multiple Garmin devices (Forerunner, Edge, Fenix, etc.) streaming GPS coordinates, heart rate, speed, and other fitness metrics
- **Consumer**: Processes streams in real-time, performs anomaly detection, and generates analytics dashboards
- **Anomaly Detection**: Identifies unusual patterns like abnormal heart rates, GPS accuracy issues, or unrealistic speeds

## Architecture

- **Kafka**: High-throughput message broker for streaming fitness data
- **Zookeeper**: Kafka cluster coordination and management
- **Kafka UI**: Web interface for monitoring data streams and system health
- **Activity Producer**: Python application simulating Garmin device data streams
- **Activity Consumer**: Real-time analytics engine with anomaly detection

## Data Model

The system processes real-time activity data with the following structure:

```json
{
  "event_id": "EVT-1736404521234-789",
  "timestamp": "2025-01-09T10:15:21.234567",
  "device_id": "Forerunner-945123",
  "device_type": "Forerunner",
  "user_id": "USER-4567",
  "activity_type": "RUNNING",
  "latitude": 25.1276,
  "longitude": 121.7392,
  "altitude": 105.5,
  "heart_rate": 145,
  "speed": 3.5,
  "distance": 17.5,
  "cadence": 170,
  "power": null,
  "temperature": 22.5,
  "battery_level": 78,
  "gps_accuracy": 3.2
}
```

### Supported Activity Types
- **Running**: RUNNING, TRAIL_RUNNING, TREADMILL, TRACK
- **Cycling**: CYCLING, INDOOR_CYCLING, MOUNTAIN_BIKING  
- **Swimming**: POOL_SWIMMING, OPEN_WATER_SWIMMING
- **Other**: HIKING, STRENGTH, YOGA, CARDIO, TRIATHLON

## Real-Time Analytics Features

### Activity Monitoring
- Live tracking of distance, speed, and heart rate metrics
- Activity type distribution and user performance statistics
- Device health monitoring with battery level alerts

### Anomaly Detection
- **High Heart Rate**: Alerts when HR exceeds 190 bpm
- **Speed Anomalies**: Detects unrealistic speeds for activity type
- **Low Battery**: Warnings when device battery < 15%
- **GPS Issues**: Identifies poor GPS accuracy (> 20m)

## Getting Started

### Prerequisites
- Docker and Docker Compose
- Git

### Running the System

1. Clone the repository:
```bash
git clone https://github.com/velwu/kafka-pubsub-system.git
cd kafka-pubsub-system
```

2. Start the entire system:
```bash
docker-compose up -d --build
```

3. Monitor the data streams:
   - Kafka UI: http://localhost:8080
   - View real-time logs: `docker-compose logs -f`

4. Stop the system:
```bash
docker-compose down
```

## Configuration

### Producer Settings (Environment Variables)
```yaml
KAFKA_TOPIC: garmin-activity-stream  # Override default topic name
DATA_PROFILE: MIXED  # Options: RUNNER, CYCLIST, MIXED
BATCH_SIZE: 10  # Events per batch
INTERVAL_SECONDS: 5  # Time between batches
```

### Consumer Settings
```yaml
CONSUMER_GROUP: garmin-analytics
ANOMALY_TOPIC: garmin-anomalies  # For anomaly alerts
BATCH_SIZE: 100  # Processing batch size
```

### Performance Optimization
The system is pre-configured for high-performance operation:
- **Kafka**: 12 partitions for parallel processing
- **Producer**: Multiprocessing support with 4 parallel processes
- **Consumer**: Thread pool for I/O operations
- **Compression**: GZIP for efficient data transfer

## Operational Commands

### Daily Operations
```bash
# View activity stream analytics
docker-compose logs -f policy-consumer

# Monitor specific device types
docker-compose logs policy-producer | grep "Fenix"

# Scale consumers for higher throughput (up to 12)
docker-compose up -d --scale policy-consumer=6

# Pause data generation
docker stop policy-producer

# Resume data generation
docker start policy-producer
```

### Performance Monitoring
```bash
# Check processing rate
docker logs policy-consumer | grep "events/second"

# Monitor anomalies
docker logs policy-consumer | grep "Anomaly detected"

# View Kafka topic statistics
docker exec -it kafka kafka-topics --describe --topic garmin-activity-stream --bootstrap-server localhost:9092
```

## Design Highlights

### 1. **Realistic Data Simulation**
- Multiple device types with appropriate activity profiles
- GPS movement patterns based on activity type
- Realistic heart rate and performance metrics

### 2. **Production-Ready Architecture**
- Health checks ensure service dependencies
- Persistent volumes for data retention
- Resource limits prevent container overload
- Automatic restart policies

### 3. **Scalability**
- Horizontal scaling via Docker Compose replicas
- 12 Kafka partitions support up to 12 parallel consumers
- Multiprocessing producer for high-throughput data generation

### 4. **Real-Time Analytics**
- Sub-second latency for anomaly detection
- Aggregated metrics dashboard
- User and device performance tracking

## Demonstration Scenarios

### For Garmin Interview
1. **High-Volume Processing**: Show system handling 1000+ events/second
2. **Anomaly Detection**: Demonstrate real-time alerts for safety-critical events
3. **Analytics Dashboard**: Display user performance insights
4. **Scaling Demo**: Scale consumers dynamically based on load

### Business Value Points
- **User Safety**: Real-time heart rate monitoring could alert users to potential health issues
- **Device Quality**: GPS accuracy tracking helps identify hardware issues
- **User Engagement**: Performance analytics drive Garmin Connect features
- **Data Quality**: Anomaly detection ensures reliable fitness tracking

## Future Enhancements

### Technical Improvements
- Implement Apache Avro for schema evolution
- Add Kafka Streams for complex event processing
- Integrate with time-series databases (InfluxDB/TimescaleDB)
- Implement WebSocket API for live dashboard updates

### Business Features
- Machine learning for personalized training recommendations
- Social features for activity sharing and competitions
- Integration with weather data for context-aware insights
- Export capabilities for third-party fitness platforms

## Troubleshooting

### Common Issues
```bash
# Kafka connection issues
docker-compose restart kafka

# Clear all data and restart fresh
docker-compose down -v
docker-compose up -d --build

# Check Kafka topic health
docker exec -it kafka kafka-topics --list --bootstrap-server localhost:9092
```

### Performance Tuning
- Increase `BATCH_SIZE` for higher throughput
- Adjust `MAX_POLL_RECORDS` for consumer optimization
- Scale consumers horizontally for parallel processing

---

*This project demonstrates production-ready streaming data architecture with real-world applicability to Garmin's ecosystem of fitness devices and analytics platforms.*
