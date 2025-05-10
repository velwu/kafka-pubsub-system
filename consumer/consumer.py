# consumer/consumer.py
import json
import logging
import os
import sys
import time
import threading
import signal
from typing import Dict, List, Any, Optional
from collections import deque

# Add the project root to the Python path to enable importing from models
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from kafka import KafkaConsumer, KafkaProducer
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
# IMPROVEMENT 1: Add dead letter queue topic configuration
DEAD_LETTER_TOPIC = os.environ.get('DEAD_LETTER_TOPIC', 'policy-events-dlq')
# IMPROVEMENT 2: Add batch size configuration
BATCH_SIZE = int(os.environ.get('BATCH_SIZE', '100'))
POLL_TIMEOUT_MS = int(os.environ.get('POLL_TIMEOUT_MS', '1000'))

# Statistics tracking
# IMPROVEMENT 3: Enhanced Metrics - Added processing time metrics
stats = {
    "events_processed": 0,
    "events_failed": 0,
    "event_types": {},
    "policy_types": {},
    "start_time": time.time(),
    # Track last N processing times to calculate moving average
    "processing_times": deque(maxlen=100),
    "max_processing_time": 0,
    "min_processing_time": float('inf'),
    "avg_processing_time": 0,
    "batch_sizes": [],
    "avg_batch_size": 0
}

# Global shutdown event for graceful termination
shutdown_event = threading.Event()

def signal_handler(sig, frame):
    """
    Handle termination signals for graceful shutdown
    """
    logger.info(f"Received signal {sig}, initiating graceful shutdown...")
    shutdown_event.set()

# Register signal handlers
signal.signal(signal.SIGTERM, signal_handler)
signal.signal(signal.SIGINT, signal_handler)

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
                    # IMPROVEMENT 2: Enable auto-commit for batch processing
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
    except Exception as e:
        logger.error(f"Error creating Kafka consumer: {str(e)}")
        raise

# IMPROVEMENT 1: Create a function to set up the dead letter queue producer
def create_dlq_producer() -> Optional[KafkaProducer]:
    """Create and return a Kafka producer for the dead letter queue"""
    try:
        max_retries = 30
        retries = 0
        while retries < max_retries and not shutdown_event.is_set():
            try:
                producer = KafkaProducer(
                    bootstrap_servers=KAFKA_BOOTSTRAP_SERVERS,
                    value_serializer=lambda v: json.dumps(v).encode('utf-8'),
                    key_serializer=lambda k: k.encode('utf-8') if k else None
                )
                logger.info(f"Successfully created DLQ producer connected to {KAFKA_BOOTSTRAP_SERVERS}")
                return producer
            except Exception as e:
                retries += 1
                logger.warning(f"Failed to create DLQ producer (attempt {retries}/{max_retries}): {str(e)}")
                time.sleep(2)
        
        if shutdown_event.is_set():
            logger.info("Shutdown requested, abandoning DLQ producer creation")
            return None
            
        raise Exception(f"Failed to create DLQ producer after {max_retries} attempts")
    except Exception as e:
        logger.error(f"Error creating DLQ producer: {str(e)}")
        return None

def process_event(event_data: Dict[str, Any], dlq_producer: Optional[KafkaProducer] = None) -> bool:
    """
    Process a policy event
    
    Args:
        event_data: The event data to process
        dlq_producer: Optional KafkaProducer for dead letter queue
        
    Returns:
        bool: True if processing succeeded, False otherwise
    """
    # IMPROVEMENT 3: Add processing time tracking
    processing_start = time.time()
    
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
        
        # IMPROVEMENT 3: Track processing time
        processing_time = time.time() - processing_start
        update_processing_time_stats(processing_time)
        
        return True
            
    except Exception as e:
        stats["events_failed"] += 1
        logger.error(f"Error processing event: {str(e)}")
        
        # IMPROVEMENT 1: Send failed messages to dead letter queue
        if dlq_producer is not None:
            try:
                # Add error information to the message
                event_data['_error'] = {
                    'timestamp': time.time(),
                    'message': str(e),
                    'type': type(e).__name__
                }
                
                # Send to DLQ
                dlq_producer.send(
                    DEAD_LETTER_TOPIC,
                    key=event_data.get('customer_id', 'unknown'),
                    value=event_data
                )
                logger.info(f"Sent failed event to dead letter queue: {event_data.get('event_id', 'unknown')}")
            except Exception as dlq_error:
                logger.error(f"Failed to send to dead letter queue: {str(dlq_error)}")
        
        # IMPROVEMENT 3: Still track processing time even for failures
        processing_time = time.time() - processing_start
        update_processing_time_stats(processing_time)
        
        return False

# IMPROVEMENT 3: Add helper function for updating processing time stats
def update_processing_time_stats(processing_time: float) -> None:
    """Update the processing time statistics"""
    stats["processing_times"].append(processing_time)
    stats["max_processing_time"] = max(stats["max_processing_time"], processing_time)
    
    # Handle the case where this is the first message processed
    if stats["min_processing_time"] == float('inf'):
        stats["min_processing_time"] = processing_time
    else:
        stats["min_processing_time"] = min(stats["min_processing_time"], processing_time)
        
    # Calculate average processing time
    if stats["processing_times"]:
        stats["avg_processing_time"] = sum(stats["processing_times"]) / len(stats["processing_times"])

def print_statistics() -> None:
    """Print current processing statistics"""
    elapsed_time = time.time() - stats["start_time"]
    events_per_second = stats["events_processed"] / elapsed_time if elapsed_time > 0 else 0
    
    # IMPROVEMENT 3: Enhanced statistics reporting
    logger.info("--- Processing Statistics ---")
    logger.info(f"Total events processed: {stats['events_processed']}")
    logger.info(f"Failed events: {stats['events_failed']}")
    logger.info(f"Success rate: {(stats['events_processed'] - stats['events_failed']) / stats['events_processed'] * 100:.2f}% if stats['events_processed'] > 0 else 'N/A'")
    logger.info(f"Events per second: {events_per_second:.2f}")
    
    # Processing time metrics
    if stats["processing_times"]:
        logger.info(f"Processing time (min/avg/max): {stats['min_processing_time']*1000:.2f}/{stats['avg_processing_time']*1000:.2f}/{stats['max_processing_time']*1000:.2f} ms")
    
    # Batch size metrics
    if stats["batch_sizes"]:
        avg_batch = sum(stats["batch_sizes"]) / len(stats["batch_sizes"])
        logger.info(f"Average batch size: {avg_batch:.2f}")
    
    logger.info(f"Event type distribution: {stats['event_types']}")
    logger.info(f"Policy type distribution: {stats['policy_types']}")
    logger.info("----------------------------")

def main():
    """Main function to run the consumer"""
    logger.info("Starting Policy Event Consumer")
    logger.info(f"Connecting to Kafka at {KAFKA_BOOTSTRAP_SERVERS}")
    logger.info(f"Subscribing to topic: {KAFKA_TOPIC}")
    logger.info(f"Consumer group: {CONSUMER_GROUP}")
    logger.info(f"Dead Letter Queue topic: {DEAD_LETTER_TOPIC}")
    logger.info(f"Batch size: {BATCH_SIZE}")
    
    consumer = None
    dlq_producer = None
    
    try:
        consumer = create_kafka_consumer()
        
        # IMPROVEMENT 1: Create DLQ producer
        dlq_producer = create_dlq_producer()
        if dlq_producer is None:
            logger.warning("Dead Letter Queue producer creation failed, continuing without DLQ functionality")
        
        logger.info("Consumer started. Waiting for messages...")
        
        # IMPROVEMENT 2: Batch Processing Implementation
        while not shutdown_event.is_set():
            # Poll for a batch of messages
            message_batch = consumer.poll(timeout_ms=POLL_TIMEOUT_MS, max_records=BATCH_SIZE)
            
            # Process the batch if any messages were received
            total_messages = sum(len(messages) for messages in message_batch.values())
            
            if total_messages > 0:
                logger.info(f"Received batch of {total_messages} messages")
                stats["batch_sizes"].append(total_messages)
                
                # Process all messages in the batch
                for tp, messages in message_batch.items():
                    logger.debug(f"Processing {len(messages)} messages from {tp.topic}-{tp.partition}")
                    
                    for message in messages:
                        if shutdown_event.is_set():
                            break
                        process_event(message.value, dlq_producer)
                
                # Commit offsets after processing the batch
                try:
                    consumer.commit()
                    logger.debug("Successfully committed offsets")
                except Exception as e:
                    logger.error(f"Failed to commit offsets: {str(e)}")
                
                # Print statistics every 50 events or when batch contains at least 50 messages
                if (stats["events_processed"] % 50 == 0) or (total_messages >= 50):
                    print_statistics()
            
            # If no messages, just log at debug level
            else:
                logger.debug("No messages received in polling interval")
                
    except KeyboardInterrupt:
        logger.info("Consumer stopped by user")
    except Exception as e:
        logger.error(f"Unexpected error: {str(e)}")
    finally:
        logger.info("Shutting down consumer")
        print_statistics()
        
        # Cleanup resources
        if dlq_producer is not None:
            try:
                dlq_producer.flush()  # Ensure any buffered messages are sent
                dlq_producer.close(timeout=5)
                logger.info("DLQ producer closed")
            except Exception as e:
                logger.error(f"Error closing DLQ producer: {str(e)}")
                
        if consumer is not None:
            try:
                consumer.close()
                logger.info("Consumer closed")
            except Exception as e:
                logger.error(f"Error closing consumer: {str(e)}")

if __name__ == "__main__":
    main()
