# producer/producer.py
import json
import time
import random
import logging
import signal
import threading
import sys
import os
from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional, Tuple, Callable

# Add the project root to the Python path to enable importing from models
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from kafka import KafkaProducer
from kafka.errors import KafkaError
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

# IMPROVEMENT 3: Enhanced data generation configuration
# Allow configuration of data generation profiles through environment variables
DATA_PROFILE = os.environ.get('DATA_PROFILE', 'MIXED')  # Options: RETAIL, BUSINESS, MIXED
REALISTIC_DISTRIBUTION = os.environ.get('REALISTIC_DISTRIBUTION', 'TRUE').upper() == 'TRUE'

# Sample data for random generation
POLICY_TYPES = ["LIFE", "HOME", "AUTO", "HEALTH", "TRAVEL", "BUSINESS"]

# IMPROVEMENT 3: Add realistic policy type weights based on typical insurance distribution
POLICY_TYPE_WEIGHTS = {
    "RETAIL": {"LIFE": 0.3, "HOME": 0.25, "AUTO": 0.3, "HEALTH": 0.1, "TRAVEL": 0.05, "BUSINESS": 0.0},
    "BUSINESS": {"LIFE": 0.1, "HOME": 0.05, "AUTO": 0.1, "HEALTH": 0.15, "TRAVEL": 0.0, "BUSINESS": 0.6},
    "MIXED": {"LIFE": 0.25, "HOME": 0.2, "AUTO": 0.25, "HEALTH": 0.1, "TRAVEL": 0.05, "BUSINESS": 0.15}
}

EVENT_TYPES = ["POLICY_CREATED", "POLICY_UPDATED", "POLICY_RENEWED", "PREMIUM_PAID", "CLAIM_FILED"]

# IMPROVEMENT 3: Add realistic event type weights
EVENT_TYPE_WEIGHTS = {
    "POLICY_CREATED": 0.15,    # New policies are relatively common
    "POLICY_UPDATED": 0.3,     # Policy updates are very common
    "POLICY_RENEWED": 0.2,     # Renewals happen periodically
    "PREMIUM_PAID": 0.25,      # Premium payments are common
    "CLAIM_FILED": 0.1         # Claims are less frequent
}

SOURCE_SYSTEMS = ["online_portal", "agent_app", "batch_process", "partner_api"]
SOURCE_SYSTEM_WEIGHTS = {
    "online_portal": 0.4,      # Many customers use the online portal
    "agent_app": 0.3,          # Agents also create many policies
    "batch_process": 0.2,      # Some policies created via batch processes
    "partner_api": 0.1         # Fewer from partner integrations
}

PROCESSING_PRIORITIES = ["high", "standard", "low"]
PRIORITY_WEIGHTS = {"high": 0.1, "standard": 0.8, "low": 0.1}

# IMPROVEMENT 2: Add metrics tracking
metrics = {
    "events_generated": 0,
    "events_sent": 0,
    "events_failed": 0,
    "event_types": {},
    "policy_types": {},
    "send_latencies": [],
    "start_time": time.time()
}

# IMPROVEMENT 1: Add global shutdown event for graceful termination
shutdown_event = threading.Event()

def signal_handler(sig, frame):
    """
    Handle termination signals for graceful shutdown
    
    This ensures all pending messages are flushed to Kafka before the producer exits,
    preventing data loss during container restarts or system updates.
    """
    logger.info(f"Received signal {sig}, initiating graceful shutdown...")
    shutdown_event.set()

# Register signal handlers
signal.signal(signal.SIGTERM, signal_handler)
signal.signal(signal.SIGINT, signal_handler)

# IMPROVEMENT 3: Helper for weighted random selection
def weighted_choice(options: List[str], weights: Dict[str, float]) -> str:
    """
    Select a random option based on weights
    
    Args:
        options: List of options to choose from
        weights: Dictionary mapping options to their weights
        
    Returns:
        Selected option
    """
    # Ensure all options have weights
    option_weights = [weights.get(option, 1.0) for option in options]
    return random.choices(options, weights=option_weights, k=1)[0]

def generate_customer_id() -> str:
    """Generate a random customer ID"""
    # IMPROVEMENT 3: Different prefixes for business vs retail customers
    if DATA_PROFILE == "BUSINESS" or (DATA_PROFILE == "MIXED" and random.random() < 0.2):
        return f"BUS{random.randint(100000, 999999)}"
    else:
        return f"CUS{random.randint(100000, 999999)}"

def generate_policy_id() -> str:
    """Generate a random policy ID"""
    return f"POL{random.randint(100000, 999999)}"

def generate_date_range() -> tuple:
    """
    Generate start and end dates for a policy
    
    Returns:
        Tuple of (start_date, end_date) as strings
    """
    # IMPROVEMENT 3: More realistic date patterns
    # Most policies start within 1-30 days from now
    start_date = datetime.now() + timedelta(days=random.randint(1, 30))
    
    # Most policies are annual, but some have different terms
    policy_term_days = random.choices(
        [180, 365, 730, 1095],  # 6 months, 1 year, 2 years, 3 years
        weights=[0.1, 0.7, 0.15, 0.05],
        k=1
    )[0]
    
    end_date = start_date + timedelta(days=policy_term_days)
    return start_date.strftime('%Y-%m-%d'), end_date.strftime('%Y-%m-%d')

# IMPROVEMENT 3: Enhanced policy event generation with more realistic values
def generate_random_policy_event() -> PolicyEvent:
    """
    Generate a random policy event with realistic data based on the configured profile
    
    Returns:
        PolicyEvent: A randomly generated policy event
    """
    start_date, end_date = generate_date_range()
    customer_id = generate_customer_id()
    is_business = customer_id.startswith("BUS")
    
    # Select policy type with realistic distribution
    if REALISTIC_DISTRIBUTION:
        profile = "BUSINESS" if is_business else "RETAIL"
        if DATA_PROFILE == "MIXED":
            profile_weights = POLICY_TYPE_WEIGHTS["MIXED"]
        else:
            profile_weights = POLICY_TYPE_WEIGHTS[profile]
            
        policy_type = weighted_choice(POLICY_TYPES, profile_weights)
        event_type = weighted_choice(EVENT_TYPES, EVENT_TYPE_WEIGHTS)
        source_system = weighted_choice(SOURCE_SYSTEMS, SOURCE_SYSTEM_WEIGHTS)
        processing_priority = weighted_choice(PROCESSING_PRIORITIES, PRIORITY_WEIGHTS)
    else:
        policy_type = random.choice(POLICY_TYPES)
        event_type = random.choice(EVENT_TYPES)
        source_system = random.choice(SOURCE_SYSTEMS)
        processing_priority = random.choice(PROCESSING_PRIORITIES)
    
    # Premium and coverage amounts based on policy type and business vs retail
    premium_multiplier = 2.5 if is_business else 1.0
    
    # Different policy types have different typical premiums
    base_premium_ranges = {
        "LIFE": (800, 3000),
        "HOME": (600, 2000),
        "AUTO": (500, 1500),
        "HEALTH": (1000, 5000),
        "TRAVEL": (200, 800),
        "BUSINESS": (2000, 10000)
    }
    
    # Different policy types have different typical coverage amounts
    coverage_ranges = {
        "LIFE": (100000, 1000000),
        "HOME": (150000, 750000),
        "AUTO": (30000, 150000),
        "HEALTH": (50000, 300000),
        "TRAVEL": (10000, 100000),
        "BUSINESS": (500000, 5000000)
    }
    
    premium_range = base_premium_ranges.get(policy_type, (500, 3000))
    premium_amount = round(random.uniform(premium_range[0], premium_range[1]) * premium_multiplier, 2)
    
    coverage_range = coverage_ranges.get(policy_type, (100000, 1000000))
    coverage_amount = round(random.uniform(coverage_range[0], coverage_range[1]) * premium_multiplier, 2)
    
    # Risk scores tend to cluster around certain values
    if event_type == "CLAIM_FILED":
        # Claims tend to be for higher risk policies
        risk_score = round(random.normalvariate(75, 10), 1)
    else:
        # Other policies have a wider distribution
        risk_score = round(random.normalvariate(65, 15), 1)
    
    # Ensure risk score is within bounds
    risk_score = max(min(risk_score, 99.9), 1.0)
    
    # IMPROVEMENT 2: Track metrics for generated events
    metrics["events_generated"] += 1
    metrics["event_types"][event_type] = metrics["event_types"].get(event_type, 0) + 1
    metrics["policy_types"][policy_type] = metrics["policy_types"].get(policy_type, 0) + 1
    
    return PolicyEvent(
        event_type=event_type,
        customer_id=customer_id,
        policy_id=generate_policy_id(),
        policy_type=policy_type,
        premium_amount=premium_amount,
        coverage_amount=coverage_amount,
        start_date=start_date,
        end_date=end_date,
        risk_score=risk_score,
        source_system=source_system,
        processing_priority=processing_priority
    )

def create_kafka_producer() -> KafkaProducer:
    """
    Create and return a Kafka producer instance with retry logic
    
    Returns:
        KafkaProducer: Configured Kafka producer instance
    
    Raises:
        Exception: If connection to Kafka fails after maximum retries
    """
    try:
        # Wait for Kafka to be ready
        max_retries = 30
        retries = 0
        while retries < max_retries and not shutdown_event.is_set():
            try:
                # IMPROVEMENT 2: Add producer configuration for better reliability and metrics
                producer = KafkaProducer(
                    bootstrap_servers=KAFKA_BOOTSTRAP_SERVERS,
                    value_serializer=lambda v: json.dumps(v).encode('utf-8'),
                    key_serializer=lambda k: k.encode('utf-8') if k else None,
                    acks='all',               # Wait for all replicas to acknowledge
                    retries=5,                # Retry delivery if it fails
                    retry_backoff_ms=100,     # Time between retries
                    request_timeout_ms=30000, # How long to wait for acks
                    linger_ms=5,              # Wait a few ms to batch messages
                    batch_size=16384,         # Default batch size in bytes
                    compression_type='gzip'   # Compress messages for efficiency
                )
                logger.info(f"Successfully connected to Kafka at {KAFKA_BOOTSTRAP_SERVERS}")
                return producer
            except Exception as e:
                retries += 1
                logger.warning(f"Failed to connect to Kafka (attempt {retries}/{max_retries}): {str(e)}")
                time.sleep(2)
        
        if shutdown_event.is_set():
            logger.info("Shutdown requested, abandoning producer creation")
            raise Exception("Shutdown requested during producer creation")
            
        raise Exception(f"Failed to connect to Kafka after {max_retries} attempts")
    except Exception as e:
        logger.error(f"Error creating Kafka producer: {str(e)}")
        raise

# IMPROVEMENT 2: Callback for tracking message delivery success/failure
def delivery_callback(record_metadata: Any, exception: Any) -> None:
    """
    Callback for tracking Kafka message delivery status
    
    Args:
        record_metadata: Metadata for the record if successful
        exception: Exception if delivery failed
    """
    if exception is not None:
        logger.error(f"Failed to deliver message: {exception}")
        metrics["events_failed"] += 1
    else:
        # Message was delivered successfully
        metrics["events_sent"] += 1
        latency = time.time() - record_metadata._created_time / 1000.0
        metrics["send_latencies"].append(latency)

def generate_and_send_events(producer: KafkaProducer, num_events: int) -> None:
    """
    Generate and send a batch of policy events to Kafka
    
    Args:
        producer: Kafka producer instance
        num_events: Number of events to generate and send
    """
    try:
        logger.info(f"Generating batch of {num_events} policy events")
        
        for _ in range(num_events):
            if shutdown_event.is_set():
                logger.info("Shutdown in progress, stopping event generation")
                break
                
            event = generate_random_policy_event()
            
            # IMPROVEMENT 2: Record timestamp for latency calculation
            event_metadata = {
                "_created_time": time.time() * 1000  # Convert to ms for Kafka
            }
            
            # Use customer_id as the message key for partitioning
            producer.send(
                KAFKA_TOPIC,
                key=event.customer_id,
                value=event.to_dict()
            ).add_callback(
                lambda metadata, event_data=event: logger.info(
                    f"Successfully sent event: {event_data.event_id} - {event_data.event_type} "
                    f"for policy {event_data.policy_details['policy_id']} "
                    f"to {metadata.topic}-{metadata.partition} @ offset {metadata.offset}"
                )
            ).add_errback(
                lambda err, event_data=event: logger.error(
                    f"Failed to send event {event_data.event_id}: {err}"
                )
            )
        
        # Ensure all messages are sent
        producer.flush()
        logger.info(f"Successfully sent batch of {num_events} events")
        
        # IMPROVEMENT 2: Print metrics periodically
        if metrics["events_generated"] % 50 == 0:
            print_metrics()
    
    except Exception as e:
        logger.error(f"Error generating and sending events: {str(e)}")

# IMPROVEMENT 2: Function to print collected metrics
def print_metrics() -> None:
    """Print current producer metrics"""
    elapsed_time = time.time() - metrics["start_time"]
    events_per_second = metrics["events_generated"] / elapsed_time if elapsed_time > 0 else 0
    
    # Calculate latency statistics if we have data
    avg_latency = "N/A"
    if metrics["send_latencies"]:
        avg_latency = f"{sum(metrics['send_latencies']) / len(metrics['send_latencies']) * 1000:.2f} ms"
    
    logger.info("--- Producer Metrics ---")
    logger.info(f"Events generated: {metrics['events_generated']}")
    logger.info(f"Events successfully sent: {metrics['events_sent']}")
    logger.info(f"Events failed: {metrics['events_failed']}")
    logger.info(f"Generation rate: {events_per_second:.2f} events/second")
    logger.info(f"Average send latency: {avg_latency}")
    logger.info(f"Event type distribution: {metrics['event_types']}")
    logger.info(f"Policy type distribution: {metrics['policy_types']}")
    logger.info("-----------------------")

def main():
    """Main function to run the producer"""
    logger.info("Starting Policy Event Producer")
    logger.info(f"Connecting to Kafka at {KAFKA_BOOTSTRAP_SERVERS}")
    logger.info(f"Publishing to topic: {KAFKA_TOPIC}")
    logger.info(f"Data profile: {DATA_PROFILE}")
    logger.info(f"Using realistic distribution: {REALISTIC_DISTRIBUTION}")
    
    producer = None
    
    try:
        producer = create_kafka_producer()
        
        logger.info(f"Producer started. Sending {BATCH_SIZE} events every {INTERVAL_SECONDS} seconds")
        
        # IMPROVEMENT 1: Check shutdown flag in the main loop
        while not shutdown_event.is_set():
            generate_and_send_events(producer, BATCH_SIZE)
            
            # Sleep but check for shutdown during sleep
            for _ in range(INTERVAL_SECONDS * 10):  # Check 10 times per second
                if shutdown_event.is_set():
                    break
                time.sleep(0.1)
            
    except KeyboardInterrupt:
        logger.info("Producer stopped by user")
    except Exception as e:
        logger.error(f"Unexpected error: {str(e)}")
    finally:
        # IMPROVEMENT 1: Enhanced shutdown process
        logger.info("Shutting down producer")
        if producer is not None:
            try:
                # Ensure any buffered messages are sent before shutting down
                logger.info("Flushing remaining messages...")
                producer.flush(timeout=10)
                logger.info("All messages flushed successfully")
                
                # Close the producer
                producer.close(timeout=5)
                logger.info("Producer closed")
                
                # Print final metrics
                print_metrics()
            except Exception as e:
                logger.error(f"Error during shutdown: {str(e)}")

if __name__ == "__main__":
    main()
