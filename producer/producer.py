# producer/producer.py
import json
import time
import random
import logging
from datetime import datetime, timedelta
from typing import List
import sys
import os

# Add the project root to the Python path to enable importing from models
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from kafka import KafkaProducer
from models.schemas import PolicyEvent

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger("policy-producer")

# Kafka configuration
KAFKA_BOOTSTRAP_SERVERS = os.environ.get('KAFKA_BOOTSTRAP_SERVERS', 'kafka:29092')
KAFKA_TOPIC = os.environ.get('KAFKA_TOPIC', 'policy-events')
BATCH_SIZE = int(os.environ.get('BATCH_SIZE', '10'))
INTERVAL_SECONDS = int(os.environ.get('INTERVAL_SECONDS', '5'))

# Sample data for random generation
POLICY_TYPES = ["LIFE", "HOME", "AUTO", "HEALTH", "TRAVEL", "BUSINESS"]
EVENT_TYPES = ["POLICY_CREATED", "POLICY_UPDATED", "POLICY_RENEWED", "PREMIUM_PAID", "CLAIM_FILED"]
SOURCE_SYSTEMS = ["online_portal", "agent_app", "batch_process", "partner_api"]
PROCESSING_PRIORITIES = ["high", "standard", "low"]

def generate_customer_id() -> str:
    """Generate a random customer ID"""
    return f"CUS{random.randint(100000, 999999)}"

def generate_policy_id() -> str:
    """Generate a random policy ID"""
    return f"POL{random.randint(100000, 999999)}"

def generate_date_range() -> tuple:
    """Generate start and end dates for a policy"""
    start_date = datetime.now() + timedelta(days=random.randint(1, 30))
    end_date = start_date + timedelta(days=random.randint(180, 365))
    return start_date.strftime('%Y-%m-%d'), end_date.strftime('%Y-%m-%d')

def generate_random_policy_event() -> PolicyEvent:
    """Generate a random policy event"""
    start_date, end_date = generate_date_range()
    
    return PolicyEvent(
        event_type=random.choice(EVENT_TYPES),
        customer_id=generate_customer_id(),
        policy_id=generate_policy_id(),
        policy_type=random.choice(POLICY_TYPES),
        premium_amount=round(random.uniform(500, 5000), 2),
        coverage_amount=round(random.uniform(10000, 2000000), 2),
        start_date=start_date,
        end_date=end_date,
        risk_score=round(random.uniform(50, 99), 1),
        source_system=random.choice(SOURCE_SYSTEMS),
        processing_priority=random.choice(PROCESSING_PRIORITIES)
    )

def create_kafka_producer() -> KafkaProducer:
    """Create and return a Kafka producer instance"""
    try:
        # Wait for Kafka to be ready
        max_retries = 30
        retries = 0
        while retries < max_retries:
            try:
                producer = KafkaProducer(
                    bootstrap_servers=KAFKA_BOOTSTRAP_SERVERS,
                    value_serializer=lambda v: json.dumps(v).encode('utf-8'),
                    key_serializer=lambda k: k.encode('utf-8') if k else None
                )
                logger.info(f"Successfully connected to Kafka at {KAFKA_BOOTSTRAP_SERVERS}")
                return producer
            except Exception as e:
                retries += 1
                logger.warning(f"Failed to connect to Kafka (attempt {retries}/{max_retries}): {str(e)}")
                time.sleep(2)
        
        raise Exception(f"Failed to connect to Kafka after {max_retries} attempts")
    except Exception as e:
        logger.error(f"Error creating Kafka producer: {str(e)}")
        raise

def generate_and_send_events(producer: KafkaProducer, num_events: int) -> None:
    """Generate and send a batch of policy events to Kafka"""
    try:
        logger.info(f"Generating batch of {num_events} policy events")
        
        for _ in range(num_events):
            event = generate_random_policy_event()
            
            # Use customer_id as the message key for partitioning
            producer.send(
                KAFKA_TOPIC,
                key=event.customer_id,
                value=event.to_dict()
            )
            
            logger.info(f"Sent event: {event.event_id} - {event.event_type} for policy {event.policy_details['policy_id']}")
        
        # Ensure all messages are sent
        producer.flush()
        logger.info(f"Successfully sent batch of {num_events} events")
    
    except Exception as e:
        logger.error(f"Error generating and sending events: {str(e)}")

def main():
    """Main function to run the producer"""
    logger.info("Starting Policy Event Producer")
    logger.info(f"Connecting to Kafka at {KAFKA_BOOTSTRAP_SERVERS}")
    logger.info(f"Publishing to topic: {KAFKA_TOPIC}")
    
    try:
        producer = create_kafka_producer()
        
        logger.info(f"Producer started. Sending {BATCH_SIZE} events every {INTERVAL_SECONDS} seconds")
        
        while True:
            generate_and_send_events(producer, BATCH_SIZE)
            time.sleep(INTERVAL_SECONDS)
            
    except KeyboardInterrupt:
        logger.info("Producer stopped by user")
    except Exception as e:
        logger.error(f"Unexpected error: {str(e)}")
    finally:
        logger.info("Shutting down producer")
        if 'producer' in locals():
            producer.close()

if __name__ == "__main__":
    main()
