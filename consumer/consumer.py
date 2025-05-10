# consumer/consumer.py
import json
import logging
import os
import sys
import time
from typing import Dict, List, Any

# Add the project root to the Python path to enable importing from models
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from kafka import KafkaConsumer
from models.schemas import PolicyEvent

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger("policy-consumer")

# Kafka configuration
KAFKA_BOOTSTRAP_SERVERS = os.environ.get('KAFKA_BOOTSTRAP_SERVERS', 'kafka:29092')
KAFKA_TOPIC = os.environ.get('KAFKA_TOPIC', 'policy-events')
CONSUMER_GROUP = os.environ.get('CONSUMER_GROUP', 'policy-processor')

# Statistics tracking
stats = {
    "events_processed": 0,
    "event_types": {},
    "policy_types": {},
    "start_time": time.time()
}

def create_kafka_consumer() -> KafkaConsumer:
    """Create and return a Kafka consumer instance"""
    try:
        # Wait for Kafka to be ready
        max_retries = 30
        retries = 0
        while retries < max_retries:
            try:
                consumer = KafkaConsumer(
                    KAFKA_TOPIC,
                    bootstrap_servers=KAFKA_BOOTSTRAP_SERVERS,
                    group_id=CONSUMER_GROUP,
                    auto_offset_reset='earliest',
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
    except Exception as e:
        logger.error(f"Error creating Kafka consumer: {str(e)}")
        raise

def process_event(event_data: Dict[str, Any]) -> None:
    """Process a policy event"""
    try:
        event = PolicyEvent.from_dict(event_data)
        
        # Update statistics
        stats["events_processed"] += 1
        stats["event_types"][event.event_type] = stats["event_types"].get(event.event_type, 0) + 1
        stats["policy_types"][event.policy_details["policy_type"]] = stats["policy_types"].get(event.policy_details["policy_type"], 0) + 1
        
        # In a real system, we might:
        # - Store the event in a database
        # - Trigger notifications or alerts
        # - Update dashboards
        # - Forward to another system
        
        # For now, we'll just log the event details
        logger.info(f"Processed event: {event.event_id} - {event.event_type} for policy {event.policy_details['policy_id']}")
        
        # Print statistics every 50 events
        if stats["events_processed"] % 50 == 0:
            print_statistics()
            
    except Exception as e:
        logger.error(f"Error processing event: {str(e)}")

def print_statistics() -> None:
    """Print current processing statistics"""
    elapsed_time = time.time() - stats["start_time"]
    events_per_second = stats["events_processed"] / elapsed_time if elapsed_time > 0 else 0
    
    logger.info("--- Processing Statistics ---")
    logger.info(f"Total events processed: {stats['events_processed']}")
    logger.info(f"Events per second: {events_per_second:.2f}")
    logger.info(f"Event type distribution: {stats['event_types']}")
    logger.info(f"Policy type distribution: {stats['policy_types']}")
    logger.info("----------------------------")

def main():
    """Main function to run the consumer"""
    logger.info("Starting Policy Event Consumer")
    logger.info(f"Connecting to Kafka at {KAFKA_BOOTSTRAP_SERVERS}")
    logger.info(f"Subscribing to topic: {KAFKA_TOPIC}")
    logger.info(f"Consumer group: {CONSUMER_GROUP}")
    
    try:
        consumer = create_kafka_consumer()
        
        logger.info("Consumer started. Waiting for messages...")
        
        for message in consumer:
            logger.debug(f"Received message: {message.value}")
            process_event(message.value)
            
    except KeyboardInterrupt:
        logger.info("Consumer stopped by user")
    except Exception as e:
        logger.error(f"Unexpected error: {str(e)}")
    finally:
        logger.info("Shutting down consumer")
        print_statistics()
        if 'consumer' in locals():
            consumer.close()

if __name__ == "__main__":
    main()
