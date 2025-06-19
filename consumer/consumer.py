# consumer/consumer.py
import json
import logging
import os
import sys
import time
import threading
import signal
from typing import Dict, List, Any, Optional
from collections import deque, defaultdict
from datetime import datetime, timedelta

# Add the project root to the Python path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from kafka import KafkaConsumer, KafkaProducer

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger("garmin-activity-consumer")

# Kafka configuration
KAFKA_BOOTSTRAP_SERVERS = os.environ.get('KAFKA_BOOTSTRAP_SERVERS', 'kafka:29092')
KAFKA_TOPIC = os.environ.get('KAFKA_TOPIC', 'garmin-activity-stream')
CONSUMER_GROUP = os.environ.get('CONSUMER_GROUP', 'garmin-analytics')
ANOMALY_TOPIC = os.environ.get('ANOMALY_TOPIC', 'garmin-anomalies')
BATCH_SIZE = int(os.environ.get('BATCH_SIZE', '100'))
POLL_TIMEOUT_MS = int(os.environ.get('POLL_TIMEOUT_MS', '1000'))

# Analytics configuration
HEART_RATE_ANOMALY_THRESHOLD = 190  # bpm
LOW_BATTERY_THRESHOLD = 15  # percentage
GPS_ACCURACY_THRESHOLD = 20  # meters
SPEED_ANOMALY_MULTIPLIER = 3  # times the average

# Real-time analytics tracking
analytics = {
    "events_processed": 0,
    "anomalies_detected": 0,
    "activity_summary": defaultdict(lambda: {
        "count": 0,
        "total_distance": 0,
        "avg_heart_rate": [],
        "avg_speed": [],
        "max_speed": 0,
        "total_duration": 0
    }),
    "device_health": defaultdict(lambda: {
        "last_seen": None,
        "battery_level": 100,
        "low_battery_alerts": 0
    }),
    "user_stats": defaultdict(lambda: {
        "activities": defaultdict(int),
        "total_distance": 0,
        "active_time": 0,
        "avg_heart_rate": []
    }),
    "processing_times": deque(maxlen=100),
    "start_time": time.time()
}

# Global shutdown event
shutdown_event = threading.Event()

def signal_handler(sig, frame):
    """Handle termination signals for graceful shutdown"""
    logger.info(f"Received signal {sig}, initiating graceful shutdown...")
    shutdown_event.set()

# Register signal handlers
signal.signal(signal.SIGTERM, signal_handler)
signal.signal(signal.SIGINT, signal_handler)

def create_kafka_consumer() -> KafkaConsumer:
    """Create and return a Kafka consumer instance"""
    max_retries = 30
    retries = 0
    
    while retries < max_retries:
        try:
            consumer = KafkaConsumer(
                KAFKA_TOPIC,
                bootstrap_servers=KAFKA_BOOTSTRAP_SERVERS,
                group_id=CONSUMER_GROUP,
                auto_offset_reset='earliest',
                enable_auto_commit=False,
                value_deserializer=lambda v: json.loads(v.decode('utf-8')),
                key_deserializer=lambda k: k.decode('utf-8') if k else None
            )
            logger.info(f"Successfully connected to Kafka at {KAFKA_BOOTSTRAP_SERVERS}")
            return consumer
        except Exception as e:
            retries += 1
            logger.warning(f"Failed to connect to Kafka (attempt {retries}/{max_retries}): {str(e)}")
            time.sleep(2)
    
    raise Exception(f"Failed to connect to Kafka after {max_retries} attempts")

def create_anomaly_producer() -> Optional[KafkaProducer]:
    """Create producer for anomaly detection alerts"""
    try:
        producer = KafkaProducer(
            bootstrap_servers=KAFKA_BOOTSTRAP_SERVERS,
            value_serializer=lambda v: json.dumps(v).encode('utf-8'),
            key_serializer=lambda k: k.encode('utf-8') if k else None
        )
        logger.info("Created anomaly alert producer")
        return producer
    except Exception as e:
        logger.error(f"Failed to create anomaly producer: {str(e)}")
        return None

def detect_anomalies(event: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Detect anomalies in activity data"""
    anomalies = []
    
    # Heart rate anomaly
    if event.get("heart_rate", 0) > HEART_RATE_ANOMALY_THRESHOLD:
        anomalies.append({
            "type": "HIGH_HEART_RATE",
            "severity": "HIGH",
            "value": event["heart_rate"],
            "threshold": HEART_RATE_ANOMALY_THRESHOLD,
            "message": f"Abnormally high heart rate detected: {event['heart_rate']} bpm"
        })
    
    # Low battery alert
    if event.get("battery_level", 100) < LOW_BATTERY_THRESHOLD:
        anomalies.append({
            "type": "LOW_BATTERY",
            "severity": "MEDIUM",
            "value": event["battery_level"],
            "threshold": LOW_BATTERY_THRESHOLD,
            "message": f"Low battery on device {event['device_id']}: {event['battery_level']}%"
        })
    
    # GPS accuracy issue
    if event.get("gps_accuracy", 0) > GPS_ACCURACY_THRESHOLD:
        anomalies.append({
            "type": "POOR_GPS_SIGNAL",
            "severity": "LOW",
            "value": event["gps_accuracy"],
            "threshold": GPS_ACCURACY_THRESHOLD,
            "message": f"Poor GPS accuracy: {event['gps_accuracy']}m"
        })
    
    # Speed anomaly based on activity type
    activity_type = event.get("activity_type", "")
    speed = event.get("speed", 0)
    
    max_speeds = {
        "RUNNING": 8.0,  # ~29 km/h (world record pace)
        "CYCLING": 20.0,  # ~72 km/h (professional sprint)
        "SWIMMING": 2.5,  # ~9 km/h (world record pace)
        "HIKING": 2.0,   # ~7.2 km/h (fast hiking)
    }
    
    if activity_type in max_speeds and speed > max_speeds[activity_type]:
        anomalies.append({
            "type": "SPEED_ANOMALY",
            "severity": "MEDIUM",
            "value": speed,
            "threshold": max_speeds[activity_type],
            "activity_type": activity_type,
            "message": f"Unrealistic speed for {activity_type}: {speed:.2f} m/s"
        })
    
    return anomalies

def process_event(event_data: Dict[str, Any], anomaly_producer: Optional[KafkaProducer] = None) -> bool:
    """Process a Garmin activity event with real-time analytics"""
    processing_start = time.time()
    
    try:
        # Extract key fields
        user_id = event_data.get("user_id", "unknown")
        device_id = event_data.get("device_id", "unknown")
        device_type = event_data.get("device_type", "unknown")
        activity_type = event_data.get("activity_type", "unknown")
        
        # Update analytics
        analytics["events_processed"] += 1
        
        # Activity summary
        activity_stats = analytics["activity_summary"][activity_type]
        activity_stats["count"] += 1
        activity_stats["total_distance"] += event_data.get("distance", 0)
        activity_stats["avg_heart_rate"].append(event_data.get("heart_rate", 0))
        activity_stats["avg_speed"].append(event_data.get("speed", 0))
        activity_stats["max_speed"] = max(activity_stats["max_speed"], event_data.get("speed", 0))
        
        # Device health tracking
        device_health = analytics["device_health"][device_id]
        device_health["last_seen"] = datetime.now()
        device_health["battery_level"] = event_data.get("battery_level", 100)
        
        # User statistics
        user_stats = analytics["user_stats"][user_id]
        user_stats["activities"][activity_type] += 1
        user_stats["total_distance"] += event_data.get("distance", 0)
        user_stats["avg_heart_rate"].append(event_data.get("heart_rate", 0))
        
        # Anomaly detection
        anomalies = detect_anomalies(event_data)
        if anomalies and anomaly_producer:
            analytics["anomalies_detected"] += len(anomalies)
            
            for anomaly in anomalies:
                anomaly_event = {
                    "timestamp": event_data.get("timestamp"),
                    "event_id": event_data.get("event_id"),
                    "user_id": user_id,
                    "device_id": device_id,
                    "anomaly": anomaly
                }
                
                anomaly_producer.send(
                    ANOMALY_TOPIC,
                    key=user_id,
                    value=anomaly_event
                )
                
                logger.warning(f"Anomaly detected: {anomaly['message']}")
        
        # Log high-value events
        if event_data.get("speed", 0) > 10.0:  # Fast activity
            logger.info(
                f"High-speed activity: {activity_type} at {event_data['speed']:.2f} m/s "
                f"by {user_id} on {device_type}"
            )
        
        # Track processing time
        processing_time = time.time() - processing_start
        analytics["processing_times"].append(processing_time)
        
        return True
        
    except Exception as e:
        logger.error(f"Error processing event: {str(e)}")
        return False

def print_analytics() -> None:
    """Print real-time analytics dashboard"""
    elapsed_time = time.time() - analytics["start_time"]
    events_per_second = analytics["events_processed"] / elapsed_time if elapsed_time > 0 else 0
    
    logger.info("=== Garmin Real-Time Analytics Dashboard ===")
    logger.info(f"Events processed: {analytics['events_processed']}")
    logger.info(f"Processing rate: {events_per_second:.2f} events/second")
    logger.info(f"Anomalies detected: {analytics['anomalies_detected']}")
    
    # Processing performance
    if analytics["processing_times"]:
        avg_time = sum(analytics["processing_times"]) / len(analytics["processing_times"])
        logger.info(f"Avg processing time: {avg_time*1000:.2f} ms")
    
    # Activity summary
    logger.info("\n--- Activity Summary ---")
    for activity, stats in analytics["activity_summary"].items():
        if stats["count"] > 0:
            avg_hr = sum(stats["avg_heart_rate"]) / len(stats["avg_heart_rate"]) if stats["avg_heart_rate"] else 0
            avg_speed = sum(stats["avg_speed"]) / len(stats["avg_speed"]) if stats["avg_speed"] else 0
            
            logger.info(
                f"{activity}: {stats['count']} activities, "
                f"{stats['total_distance']/1000:.2f} km, "
                f"avg HR: {avg_hr:.0f} bpm, "
                f"avg speed: {avg_speed:.2f} m/s, "
                f"max speed: {stats['max_speed']:.2f} m/s"
            )
    
    # Top users by distance
    logger.info("\n--- Top Users by Distance ---")
    top_users = sorted(
        analytics["user_stats"].items(),
        key=lambda x: x[1]["total_distance"],
        reverse=True
    )[:5]
    
    for user_id, stats in top_users:
        logger.info(
            f"{user_id}: {stats['total_distance']/1000:.2f} km, "
            f"{sum(stats['activities'].values())} activities"
        )
    
    # Device health summary
    low_battery_devices = [
        (device_id, health["battery_level"])
        for device_id, health in analytics["device_health"].items()
        if health["battery_level"] < 20
    ]
    
    if low_battery_devices:
        logger.info("\n--- Low Battery Devices ---")
        for device_id, battery in low_battery_devices:
            logger.info(f"{device_id}: {battery}%")
    
    logger.info("==========================================\n")

def main():
    """Main function to run the consumer"""
    logger.info("Starting Garmin Activity Data Consumer")
    logger.info(f"Connecting to Kafka at {KAFKA_BOOTSTRAP_SERVERS}")
    logger.info(f"Consuming from topic: {KAFKA_TOPIC}")
    logger.info(f"Consumer group: {CONSUMER_GROUP}")
    
    consumer = None
    anomaly_producer = None
    
    try:
        consumer = create_kafka_consumer()
        anomaly_producer = create_anomaly_producer()
        
        logger.info("Consumer started. Processing real-time activity data...")
        
        while not shutdown_event.is_set():
            # Poll for messages
            message_batch = consumer.poll(timeout_ms=POLL_TIMEOUT_MS, max_records=BATCH_SIZE)
            
            total_messages = sum(len(messages) for messages in message_batch.values())
            
            if total_messages > 0:
                logger.debug(f"Processing batch of {total_messages} activity events")
                
                for tp, messages in message_batch.items():
                    for message in messages:
                        if shutdown_event.is_set():
                            break
                        process_event(message.value, anomaly_producer)
                
                # Commit offsets
                try:
                    consumer.commit()
                except Exception as e:
                    logger.error(f"Failed to commit offsets: {str(e)}")
                
                # Print analytics dashboard every 50 events
                if analytics["events_processed"] % 50 == 0:
                    print_analytics()
    
    except KeyboardInterrupt:
        logger.info("Consumer stopped by user")
    except Exception as e:
        logger.error(f"Unexpected error: {str(e)}")
    finally:
        logger.info("Shutting down consumer")
        print_analytics()
        
        # Cleanup
        if anomaly_producer:
            try:
                anomaly_producer.flush()
                anomaly_producer.close(timeout=5)
                logger.info("Anomaly producer closed")
            except Exception as e:
                logger.error(f"Error closing anomaly producer: {str(e)}")
        
        if consumer:
            try:
                consumer.close()
                logger.info("Consumer closed")
            except Exception as e:
                logger.error(f"Error closing consumer: {str(e)}")

if __name__ == "__main__":
    main()
