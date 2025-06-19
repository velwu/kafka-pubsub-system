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
from typing import Dict, List, Any, Optional, Tuple
from dataclasses import dataclass, asdict

# Add the project root to the Python path to enable importing from models
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from kafka import KafkaProducer
from kafka.errors import KafkaError

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger("garmin-activity-producer")

# Kafka configuration
KAFKA_BOOTSTRAP_SERVERS = os.environ.get('KAFKA_BOOTSTRAP_SERVERS', 'kafka:29092')
KAFKA_TOPIC = os.environ.get('KAFKA_TOPIC', 'garmin-activity-stream')
BATCH_SIZE = int(os.environ.get('BATCH_SIZE', '10'))
INTERVAL_SECONDS = int(os.environ.get('INTERVAL_SECONDS', '5'))

# Data generation configuration
DATA_PROFILE = os.environ.get('DATA_PROFILE', 'MIXED')  # Options: RUNNER, CYCLIST, MIXED
REALISTIC_DISTRIBUTION = os.environ.get('REALISTIC_DISTRIBUTION', 'TRUE').upper() == 'TRUE'

# Garmin device types and their typical activities
DEVICE_TYPES = {
    "Forerunner": ["RUNNING", "TRAIL_RUNNING", "TREADMILL", "TRACK"],
    "Edge": ["CYCLING", "INDOOR_CYCLING", "MOUNTAIN_BIKING"],
    "Fenix": ["RUNNING", "CYCLING", "HIKING", "SWIMMING", "TRIATHLON"],
    "Venu": ["RUNNING", "CYCLING", "YOGA", "STRENGTH", "CARDIO"],
    "Instinct": ["HIKING", "TRAIL_RUNNING", "MOUNTAIN_BIKING", "CLIMBING"],
    "Swim": ["POOL_SWIMMING", "OPEN_WATER_SWIMMING"]
}

ACTIVITY_TYPES = ["RUNNING", "CYCLING", "SWIMMING", "HIKING", "STRENGTH", 
                  "YOGA", "CARDIO", "TRAIL_RUNNING", "MOUNTAIN_BIKING", 
                  "TREADMILL", "INDOOR_CYCLING", "TRIATHLON"]

# Realistic activity type weights
ACTIVITY_TYPE_WEIGHTS = {
    "RUNNER": {"RUNNING": 0.5, "TRAIL_RUNNING": 0.2, "TREADMILL": 0.15, 
               "STRENGTH": 0.1, "YOGA": 0.05},
    "CYCLIST": {"CYCLING": 0.5, "INDOOR_CYCLING": 0.2, "MOUNTAIN_BIKING": 0.15,
                "RUNNING": 0.1, "STRENGTH": 0.05},
    "MIXED": {"RUNNING": 0.3, "CYCLING": 0.25, "SWIMMING": 0.1, "HIKING": 0.1,
              "STRENGTH": 0.1, "YOGA": 0.05, "CARDIO": 0.05, "OTHER": 0.05}
}

# Metrics tracking
metrics = {
    "events_generated": 0,
    "events_sent": 0,
    "events_failed": 0,
    "activity_types": {},
    "device_types": {},
    "avg_heart_rate": [],
    "total_distance": 0,
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

@dataclass
class GarminActivityData:
    """Data structure for Garmin activity streaming data"""
    event_id: str
    timestamp: str
    device_id: str
    device_type: str
    user_id: str
    activity_type: str
    latitude: float
    longitude: float
    altitude: float
    heart_rate: int
    speed: float  # m/s
    distance: float  # meters
    cadence: Optional[int]  # steps/min or pedal rpm
    power: Optional[int]  # watts (for cycling)
    temperature: float  # celsius
    battery_level: int  # percentage
    gps_accuracy: float  # meters
    
    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

def generate_device_id() -> Tuple[str, str]:
    """Generate a device ID and type"""
    device_type = random.choice(list(DEVICE_TYPES.keys()))
    device_id = f"{device_type}-{random.randint(100000, 999999)}"
    return device_id, device_type

def generate_user_id() -> str:
    """Generate a user ID"""
    return f"USER-{random.randint(1000, 9999)}"

def weighted_choice(options: List[str], weights: Dict[str, float]) -> str:
    """Select a random option based on weights"""
    if not weights:
        return random.choice(options)
    
    # Filter options to only those with weights
    available_options = [opt for opt in options if opt in weights]
    if not available_options:
        return random.choice(options)
    
    option_weights = [weights[option] for option in available_options]
    return random.choices(available_options, weights=option_weights, k=1)[0]

def generate_realistic_activity_data(
    activity_type: str, 
    prev_lat: float = None, 
    prev_lon: float = None
) -> Dict[str, Any]:
    """Generate realistic activity metrics based on activity type"""
    
    # Base coordinates (Taiwan area - near Keelung)
    if prev_lat is None:
        base_lat = 25.1276 + random.uniform(-0.1, 0.1)
        base_lon = 121.7392 + random.uniform(-0.1, 0.1)
    else:
        # Simulate movement
        base_lat = prev_lat + random.uniform(-0.0005, 0.0005)
        base_lon = prev_lon + random.uniform(-0.0005, 0.0005)
    
    # Activity-specific parameters
    activity_params = {
        "RUNNING": {
            "speed": (2.5, 5.5),  # m/s (9-20 km/h)
            "heart_rate": (140, 170),
            "cadence": (160, 180),
            "altitude_change": (-2, 2)
        },
        "CYCLING": {
            "speed": (5.0, 12.0),  # m/s (18-43 km/h)
            "heart_rate": (130, 160),
            "cadence": (70, 95),
            "altitude_change": (-5, 5),
            "power": (150, 300)
        },
        "SWIMMING": {
            "speed": (0.5, 2.0),  # m/s
            "heart_rate": (120, 150),
            "cadence": (50, 70),  # strokes/min
            "altitude_change": (0, 0)
        },
        "HIKING": {
            "speed": (0.8, 1.5),  # m/s (3-5.5 km/h)
            "heart_rate": (110, 140),
            "cadence": (100, 120),
            "altitude_change": (-10, 15)
        },
        "STRENGTH": {
            "speed": (0, 0),
            "heart_rate": (90, 140),
            "cadence": None,
            "altitude_change": (0, 0)
        }
    }
    
    # Get parameters for activity type
    params = activity_params.get(activity_type, activity_params["RUNNING"])
    
    # Generate metrics
    speed = random.uniform(*params["speed"])
    heart_rate = int(random.gauss(
        (params["heart_rate"][0] + params["heart_rate"][1]) / 2, 10
    ))
    heart_rate = max(min(heart_rate, 200), 60)  # Clamp to realistic range
    
    cadence = None
    if params["cadence"]:
        cadence = int(random.uniform(*params["cadence"]))
    
    power = None
    if "power" in params:
        power = int(random.uniform(*params["power"]))
    
    altitude = 100 + random.uniform(*params["altitude_change"])
    
    return {
        "latitude": round(base_lat, 6),
        "longitude": round(base_lon, 6),
        "altitude": round(altitude, 1),
        "heart_rate": heart_rate,
        "speed": round(speed, 2),
        "distance": round(speed * INTERVAL_SECONDS, 1),  # distance covered in interval
        "cadence": cadence,
        "power": power,
        "temperature": round(25 + random.uniform(-5, 5), 1),
        "battery_level": max(10, 100 - int(metrics["events_generated"] * 0.01)),
        "gps_accuracy": round(random.uniform(2, 10), 1)
    }

def generate_activity_event(
    prev_lat: float = None,
    prev_lon: float = None
) -> GarminActivityData:
    """Generate a Garmin activity data event"""
    
    device_id, device_type = generate_device_id()
    user_id = generate_user_id()
    
    # Select activity type based on device capabilities and profile
    if REALISTIC_DISTRIBUTION:
        # Get activities supported by this device
        supported_activities = DEVICE_TYPES.get(device_type, ACTIVITY_TYPES)
        
        # Use profile weights if available
        profile_weights = ACTIVITY_TYPE_WEIGHTS.get(DATA_PROFILE, {})
        
        # Filter weights to only supported activities
        activity_weights = {
            act: profile_weights.get(act, 0.1) 
            for act in supported_activities 
            if act in profile_weights
        }
        
        if activity_weights:
            activity_type = weighted_choice(supported_activities, activity_weights)
        else:
            activity_type = random.choice(supported_activities)
    else:
        # Random selection from device-supported activities
        activity_type = random.choice(DEVICE_TYPES.get(device_type, ACTIVITY_TYPES))
    
    # Generate activity data
    activity_data = generate_realistic_activity_data(activity_type, prev_lat, prev_lon)
    
    # Update metrics
    metrics["events_generated"] += 1
    metrics["activity_types"][activity_type] = metrics["activity_types"].get(activity_type, 0) + 1
    metrics["device_types"][device_type] = metrics["device_types"].get(device_type, 0) + 1
    metrics["avg_heart_rate"].append(activity_data["heart_rate"])
    metrics["total_distance"] += activity_data["distance"]
    
    return GarminActivityData(
        event_id=f"EVT-{int(time.time() * 1000)}-{random.randint(100, 999)}",
        timestamp=datetime.now().isoformat(),
        device_id=device_id,
        device_type=device_type,
        user_id=user_id,
        activity_type=activity_type,
        **activity_data
    )

def create_kafka_producer() -> KafkaProducer:
    """Create and return a Kafka producer instance"""
    max_retries = 30
    retries = 0
    
    while retries < max_retries and not shutdown_event.is_set():
        try:
            producer = KafkaProducer(
                bootstrap_servers=KAFKA_BOOTSTRAP_SERVERS,
                value_serializer=lambda v: json.dumps(v).encode('utf-8'),
                key_serializer=lambda k: k.encode('utf-8') if k else None,
                acks='all',
                retries=5,
                retry_backoff_ms=100,
                request_timeout_ms=30000,
                linger_ms=5,
                batch_size=16384,
                compression_type='gzip'
            )
            logger.info(f"Successfully connected to Kafka at {KAFKA_BOOTSTRAP_SERVERS}")
            return producer
        except Exception as e:
            retries += 1
            logger.warning(f"Failed to connect to Kafka (attempt {retries}/{max_retries}): {str(e)}")
            time.sleep(2)
    
    if shutdown_event.is_set():
        raise Exception("Shutdown requested during producer creation")
    
    raise Exception(f"Failed to connect to Kafka after {max_retries} attempts")

def generate_and_send_events(producer: KafkaProducer, num_events: int) -> None:
    """Generate and send a batch of activity events"""
    logger.info(f"Generating batch of {num_events} activity events")
    
    # Track position for continuous movement simulation
    prev_lat, prev_lon = None, None
    
    for _ in range(num_events):
        if shutdown_event.is_set():
            logger.info("Shutdown in progress, stopping event generation")
            break
        
        event = generate_activity_event(prev_lat, prev_lon)
        prev_lat, prev_lon = event.latitude, event.longitude
        
        # Use user_id as partition key for consistent user data routing
        producer.send(
            KAFKA_TOPIC,
            key=event.user_id,
            value=event.to_dict()
        ).add_callback(
            lambda metadata, e=event: logger.info(
                f"Sent: {e.event_id} - {e.activity_type} from {e.device_type} "
                f"(HR: {e.heart_rate}, Speed: {e.speed}m/s) "
                f"to partition {metadata.partition}"
            )
        ).add_errback(
            lambda err, e=event: logger.error(f"Failed to send {e.event_id}: {err}")
        )
    
    producer.flush()
    logger.info(f"Successfully sent batch of {num_events} events")
    
    if metrics["events_generated"] % 50 == 0:
        print_metrics()

def print_metrics() -> None:
    """Print current producer metrics"""
    elapsed_time = time.time() - metrics["start_time"]
    events_per_second = metrics["events_generated"] / elapsed_time if elapsed_time > 0 else 0
    
    avg_hr = sum(metrics["avg_heart_rate"]) / len(metrics["avg_heart_rate"]) if metrics["avg_heart_rate"] else 0
    
    logger.info("--- Garmin Activity Producer Metrics ---")
    logger.info(f"Events generated: {metrics['events_generated']}")
    logger.info(f"Generation rate: {events_per_second:.2f} events/second")
    logger.info(f"Total distance tracked: {metrics['total_distance']/1000:.2f} km")
    logger.info(f"Average heart rate: {avg_hr:.1f} bpm")
    logger.info(f"Activity distribution: {metrics['activity_types']}")
    logger.info(f"Device distribution: {metrics['device_types']}")
    logger.info("---------------------------------------")

def main():
    """Main function to run the producer"""
    logger.info("Starting Garmin Activity Data Producer")
    logger.info(f"Connecting to Kafka at {KAFKA_BOOTSTRAP_SERVERS}")
    logger.info(f"Publishing to topic: {KAFKA_TOPIC}")
    logger.info(f"Activity profile: {DATA_PROFILE}")
    
    producer = None
    
    try:
        producer = create_kafka_producer()
        logger.info(f"Streaming {BATCH_SIZE} activity events every {INTERVAL_SECONDS} seconds")
        
        while not shutdown_event.is_set():
            generate_and_send_events(producer, BATCH_SIZE)
            
            # Sleep with shutdown check
            for _ in range(INTERVAL_SECONDS * 10):
                if shutdown_event.is_set():
                    break
                time.sleep(0.1)
    
    except KeyboardInterrupt:
        logger.info("Producer stopped by user")
    except Exception as e:
        logger.error(f"Unexpected error: {str(e)}")
    finally:
        logger.info("Shutting down producer")
        if producer:
            try:
                producer.flush(timeout=10)
                producer.close(timeout=5)
                logger.info("Producer closed successfully")
                print_metrics()
            except Exception as e:
                logger.error(f"Error during shutdown: {str(e)}")

if __name__ == "__main__":
    main()