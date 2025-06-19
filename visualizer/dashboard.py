# visualizer/dashboard.py
import json
import time
import logging
import threading
import signal
import sys
import os
from datetime import datetime, timedelta
from collections import defaultdict, deque
from typing import Dict, List, Any, Tuple
import statistics

# Data visualization libraries
import matplotlib.pyplot as plt
import matplotlib.animation as animation
from matplotlib.backends.backend_pdf import PdfPages
import seaborn as sns
import pandas as pd
import numpy as np

# Add the project root to the Python path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from kafka import KafkaConsumer

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger("garmin-visualizer")

# Kafka configuration
KAFKA_BOOTSTRAP_SERVERS = os.environ.get('KAFKA_BOOTSTRAP_SERVERS', 'kafka:29092')
KAFKA_TOPIC = os.environ.get('KAFKA_TOPIC', 'garmin-activity-stream')
CONSUMER_GROUP = os.environ.get('CONSUMER_GROUP', 'garmin-visualizer')

# Visualization settings
DASHBOARD_UPDATE_INTERVAL = int(os.environ.get('DASHBOARD_UPDATE_INTERVAL', '10'))  # seconds
EXPORT_INTERVAL = int(os.environ.get('EXPORT_INTERVAL', '300'))  # 5 minutes
OUTPUT_DIR = os.environ.get('OUTPUT_DIR', '/app/visualizations')

# Create output directory if it doesn't exist
os.makedirs(OUTPUT_DIR, exist_ok=True)

# Global data store for accumulating metrics
class DataStore:
    def __init__(self):
        self.lock = threading.Lock()
        
        # User-centric data
        self.user_data = defaultdict(lambda: {
            'total_distance': 0,
            'total_time': 0,
            'activities': defaultdict(int),
            'avg_heart_rate': [],
            'avg_speed': [],
            'max_heart_rate': 0,
            'calories_burned': 0,
            'recent_activities': deque(maxlen=100),
            'daily_distance': defaultdict(float),
            'performance_trend': []
        })
        
        # Device analytics
        self.device_data = defaultdict(lambda: {
            'usage_count': 0,
            'battery_samples': deque(maxlen=100),
            'gps_accuracy_samples': deque(maxlen=100),
            'last_seen': None,
            'activities': defaultdict(int)
        })
        
        # Activity patterns
        self.activity_patterns = {
            'hourly_distribution': defaultdict(int),
            'daily_distribution': defaultdict(int),
            'activity_types': defaultdict(int),
            'location_heatmap': defaultdict(int),
            'speed_by_activity': defaultdict(list),
            'heart_rate_zones': defaultdict(int)
        }
        
        # Time series data for real-time charts
        self.time_series = {
            'timestamps': deque(maxlen=1000),
            'active_users': deque(maxlen=1000),
            'avg_heart_rate': deque(maxlen=1000),
            'events_per_minute': deque(maxlen=60)
        }
        
        # Leaderboards
        self.leaderboards = {
            'distance_today': {},
            'distance_week': {},
            'longest_activity': {},
            'most_active': {}
        }
        
    def add_event(self, event: Dict[str, Any]):
        """Process and store incoming event data"""
        with self.lock:
            user_id = event['user_id']
            device_id = event['device_id']
            activity_type = event['activity_type']
            timestamp = datetime.fromisoformat(event['timestamp'])
            
            # Update user data
            user = self.user_data[user_id]
            user['total_distance'] += event['distance']
            user['total_time'] += 5  # Assuming 5-second intervals
            user['activities'][activity_type] += 1
            user['avg_heart_rate'].append(event['heart_rate'])
            user['avg_speed'].append(event['speed'])
            user['max_heart_rate'] = max(user['max_heart_rate'], event['heart_rate'])
            user['recent_activities'].append(event)
            
            # Daily distance tracking
            date_key = timestamp.strftime('%Y-%m-%d')
            user['daily_distance'][date_key] += event['distance']
            
            # Calories estimation (simplified)
            calories = self._estimate_calories(event)
            user['calories_burned'] += calories
            
            # Update device data
            device = self.device_data[device_id]
            device['usage_count'] += 1
            device['battery_samples'].append(event['battery_level'])
            device['gps_accuracy_samples'].append(event['gps_accuracy'])
            device['last_seen'] = timestamp
            device['activities'][activity_type] += 1
            
            # Update activity patterns
            hour = timestamp.hour
            weekday = timestamp.strftime('%A')
            self.activity_patterns['hourly_distribution'][hour] += 1
            self.activity_patterns['daily_distribution'][weekday] += 1
            self.activity_patterns['activity_types'][activity_type] += 1
            
            # Location heatmap (grid-based)
            lat_grid = int(event['latitude'] * 100)
            lon_grid = int(event['longitude'] * 100)
            self.activity_patterns['location_heatmap'][(lat_grid, lon_grid)] += 1
            
            # Speed by activity
            self.activity_patterns['speed_by_activity'][activity_type].append(event['speed'])
            
            # Heart rate zones
            hr_zone = self._get_heart_rate_zone(event['heart_rate'])
            self.activity_patterns['heart_rate_zones'][hr_zone] += 1
            
            # Update time series
            self.time_series['timestamps'].append(timestamp)
            self.time_series['active_users'].append(len(self.user_data))
            self.time_series['avg_heart_rate'].append(event['heart_rate'])
            
            # Events per minute
            current_minute = timestamp.strftime('%Y-%m-%d %H:%M')
            if not hasattr(self, '_current_minute'):
                self._current_minute = current_minute
                self._minute_count = 0
            
            if current_minute == self._current_minute:
                self._minute_count += 1
            else:
                self.time_series['events_per_minute'].append(self._minute_count)
                self._current_minute = current_minute
                self._minute_count = 1
    
    def _estimate_calories(self, event: Dict[str, Any]) -> float:
        """Estimate calories burned based on activity data"""
        # Simplified calorie calculation
        met_values = {
            'RUNNING': 9.8,
            'CYCLING': 7.5,
            'SWIMMING': 8.0,
            'HIKING': 6.0,
            'WALKING': 3.5
        }
        met = met_values.get(event['activity_type'], 5.0)
        # Assuming 70kg user, 5 second interval
        calories = (met * 70 * (5/3600))
        return calories
    
    def _get_heart_rate_zone(self, heart_rate: int) -> str:
        """Categorize heart rate into training zones"""
        if heart_rate < 100:
            return 'Rest'
        elif heart_rate < 120:
            return 'Light'
        elif heart_rate < 140:
            return 'Moderate'
        elif heart_rate < 160:
            return 'Hard'
        elif heart_rate < 180:
            return 'Maximum'
        else:
            return 'Peak'
    
    def update_leaderboards(self):
        """Update various leaderboards"""
        with self.lock:
            today = datetime.now().strftime('%Y-%m-%d')
            
            # Distance leaderboards
            distance_today = {}
            distance_week = {}
            
            for user_id, data in self.user_data.items():
                # Today's distance
                distance_today[user_id] = data['daily_distance'].get(today, 0)
                
                # This week's distance
                week_distance = 0
                for i in range(7):
                    date = (datetime.now() - timedelta(days=i)).strftime('%Y-%m-%d')
                    week_distance += data['daily_distance'].get(date, 0)
                distance_week[user_id] = week_distance
            
            # Sort and store top 10
            self.leaderboards['distance_today'] = dict(
                sorted(distance_today.items(), key=lambda x: x[1], reverse=True)[:10]
            )
            self.leaderboards['distance_week'] = dict(
                sorted(distance_week.items(), key=lambda x: x[1], reverse=True)[:10]
            )
            
            # Most active users (by activity count)
            activity_counts = {
                user_id: sum(data['activities'].values()) 
                for user_id, data in self.user_data.items()
            }
            self.leaderboards['most_active'] = dict(
                sorted(activity_counts.items(), key=lambda x: x[1], reverse=True)[:10]
            )

# Global data store instance
data_store = DataStore()

# Global shutdown event
shutdown_event = threading.Event()

def signal_handler(sig, frame):
    """Handle termination signals"""
    logger.info(f"Received signal {sig}, initiating graceful shutdown...")
    shutdown_event.set()

signal.signal(signal.SIGTERM, signal_handler)
signal.signal(signal.SIGINT, signal_handler)

def create_kafka_consumer() -> KafkaConsumer:
    """Create and return a Kafka consumer instance"""
    max_retries = 30
    retries = 0
    
    while retries < max_retries and not shutdown_event.is_set():
        try:
            consumer = KafkaConsumer(
                KAFKA_TOPIC,
                bootstrap_servers=KAFKA_BOOTSTRAP_SERVERS,
                group_id=CONSUMER_GROUP,
                auto_offset_reset='earliest',
                value_deserializer=lambda v: json.loads(v.decode('utf-8'))
            )
            logger.info(f"Connected to Kafka at {KAFKA_BOOTSTRAP_SERVERS}")
            return consumer
        except Exception as e:
            retries += 1
            logger.warning(f"Failed to connect (attempt {retries}/{max_retries}): {str(e)}")
            time.sleep(2)
    
    raise Exception("Failed to connect to Kafka")

def generate_visualizations():
    """Generate and save visualization charts"""
    logger.info("Generating visualizations...")
    
    try:
        # Set style
        plt.style.use('seaborn-v0_8-darkgrid')
        sns.set_palette("husl")
        
        # Create figure with subplots
        fig = plt.figure(figsize=(20, 24))
        
        # 1. User Activity Distribution (Top 10 Users)
        ax1 = plt.subplot(5, 2, 1)
        if data_store.leaderboards['distance_week']:
            users = list(data_store.leaderboards['distance_week'].keys())[:10]
            distances = [data_store.leaderboards['distance_week'][u]/1000 for u in users]
            ax1.bar(range(len(users)), distances)
            ax1.set_xticks(range(len(users)))
            ax1.set_xticklabels(users, rotation=45)
            ax1.set_title('Top 10 Users by Weekly Distance')
            ax1.set_ylabel('Distance (km)')
        
        # 2. Activity Type Distribution
        ax2 = plt.subplot(5, 2, 2)
        if data_store.activity_patterns['activity_types']:
            activities = list(data_store.activity_patterns['activity_types'].keys())
            counts = list(data_store.activity_patterns['activity_types'].values())
            ax2.pie(counts, labels=activities, autopct='%1.1f%%')
            ax2.set_title('Activity Type Distribution')
        
        # 3. Hourly Activity Pattern
        ax3 = plt.subplot(5, 2, 3)
        hours = list(range(24))
        hourly_counts = [data_store.activity_patterns['hourly_distribution'].get(h, 0) for h in hours]
        ax3.plot(hours, hourly_counts, marker='o')
        ax3.set_title('Activity Distribution by Hour')
        ax3.set_xlabel('Hour of Day')
        ax3.set_ylabel('Activity Count')
        ax3.set_xticks(range(0, 24, 2))
        
        # 4. Heart Rate Zone Distribution
        ax4 = plt.subplot(5, 2, 4)
        if data_store.activity_patterns['heart_rate_zones']:
            zones = list(data_store.activity_patterns['heart_rate_zones'].keys())
            zone_counts = list(data_store.activity_patterns['heart_rate_zones'].values())
            colors = ['green', 'yellow', 'orange', 'red', 'darkred', 'purple']
            ax4.bar(zones, zone_counts, color=colors[:len(zones)])
            ax4.set_title('Heart Rate Training Zones')
            ax4.set_ylabel('Time in Zone')
        
        # 5. Speed by Activity Type (Box Plot)
        ax5 = plt.subplot(5, 2, 5)
        speed_data = []
        labels = []
        for activity, speeds in data_store.activity_patterns['speed_by_activity'].items():
            if speeds:
                speed_data.append(speeds[-100:])  # Last 100 samples
                labels.append(activity)
        if speed_data:
            ax5.boxplot(speed_data, labels=labels)
            ax5.set_title('Speed Distribution by Activity')
            ax5.set_ylabel('Speed (m/s)')
            plt.setp(ax5.xaxis.get_majorticklabels(), rotation=45)
        
        # 6. Device Battery Health
        ax6 = plt.subplot(5, 2, 6)
        battery_data = []
        device_labels = []
        for device_id, data in list(data_store.device_data.items())[:10]:
            if data['battery_samples']:
                battery_data.append(list(data['battery_samples']))
                device_labels.append(device_id.split('-')[0])
        if battery_data:
            positions = range(len(battery_data))
            ax6.violinplot(battery_data, positions=positions, showmeans=True)
            ax6.set_xticks(positions)
            ax6.set_xticklabels(device_labels, rotation=45)
            ax6.set_title('Device Battery Level Distribution')
            ax6.set_ylabel('Battery %')
        
        # 7. Daily Activity Trend
        ax7 = plt.subplot(5, 2, 7)
        days = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday']
        daily_counts = [data_store.activity_patterns['daily_distribution'].get(d, 0) for d in days]
        ax7.bar(days, daily_counts)
        ax7.set_title('Activity Distribution by Day of Week')
        plt.setp(ax7.xaxis.get_majorticklabels(), rotation=45)
        
        # 8. Real-time Event Rate
        ax8 = plt.subplot(5, 2, 8)
        if data_store.time_series['events_per_minute']:
            minutes = list(range(len(data_store.time_series['events_per_minute'])))
            ax8.plot(minutes[-60:], list(data_store.time_series['events_per_minute'])[-60:])
            ax8.set_title('Events Per Minute (Last Hour)')
            ax8.set_xlabel('Minutes Ago')
            ax8.set_ylabel('Event Count')
        
        # 9. GPS Accuracy Analysis
        ax9 = plt.subplot(5, 2, 9)
        accuracy_data = []
        for device_id, data in data_store.device_data.items():
            if data['gps_accuracy_samples']:
                accuracy_data.extend(list(data['gps_accuracy_samples']))
        if accuracy_data:
            ax9.hist(accuracy_data, bins=20, edgecolor='black')
            ax9.set_title('GPS Accuracy Distribution')
            ax9.set_xlabel('Accuracy (meters)')
            ax9.set_ylabel('Frequency')
            ax9.axvline(x=20, color='red', linestyle='--', label='Threshold')
            ax9.legend()
        
        # 10. Calories Burned Leaderboard
        ax10 = plt.subplot(5, 2, 10)
        calories_data = [(uid, data['calories_burned']) for uid, data in data_store.user_data.items()]
        calories_data.sort(key=lambda x: x[1], reverse=True)
        top_calories = calories_data[:10]
        if top_calories:
            users, calories = zip(*top_calories)
            ax10.barh(range(len(users)), calories)
            ax10.set_yticks(range(len(users)))
            ax10.set_yticklabels(users)
            ax10.set_title('Top 10 Users by Calories Burned')
            ax10.set_xlabel('Calories')
        
        plt.tight_layout()
        
        # Save to file
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        filename = os.path.join(OUTPUT_DIR, f'garmin_analytics_{timestamp}.png')
        plt.savefig(filename, dpi=300, bbox_inches='tight')
        plt.close()
        
        logger.info(f"Saved visualization to {filename}")
        
        # Also create a PDF report
        create_pdf_report(timestamp)
        
    except Exception as e:
        logger.error(f"Error generating visualizations: {str(e)}")

def create_pdf_report(timestamp: str):
    """Create a comprehensive PDF report"""
    try:
        filename = os.path.join(OUTPUT_DIR, f'garmin_report_{timestamp}.pdf')
        
        with PdfPages(filename) as pdf:
            # Page 1: Executive Summary
            fig = plt.figure(figsize=(8.5, 11))
            fig.suptitle('Garmin Activity Analytics Report', fontsize=16, fontweight='bold')
            
            # Summary text
            ax = fig.add_subplot(111)
            ax.axis('off')
            
            summary_text = f"""
Executive Summary
Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}

Total Users: {len(data_store.user_data)}
Total Activities: {sum(data_store.activity_patterns['activity_types'].values())}
Total Distance: {sum(u['total_distance'] for u in data_store.user_data.values())/1000:.2f} km

Top Activity Types:
"""
            for activity, count in sorted(
                data_store.activity_patterns['activity_types'].items(), 
                key=lambda x: x[1], 
                reverse=True
            )[:5]:
                summary_text += f"  - {activity}: {count} events\n"
            
            ax.text(0.1, 0.9, summary_text, transform=ax.transAxes, 
                   fontsize=12, verticalalignment='top', fontfamily='monospace')
            
            pdf.savefig(bbox_inches='tight')
            plt.close()
            
            # Additional pages with detailed charts would go here
            
        logger.info(f"Saved PDF report to {filename}")
        
    except Exception as e:
        logger.error(f"Error creating PDF report: {str(e)}")

def visualization_thread():
    """Background thread for periodic visualization generation"""
    while not shutdown_event.is_set():
        time.sleep(DASHBOARD_UPDATE_INTERVAL)
        data_store.update_leaderboards()
        
        # Generate visualizations every EXPORT_INTERVAL
        if int(time.time()) % EXPORT_INTERVAL < DASHBOARD_UPDATE_INTERVAL:
            generate_visualizations()

def main():
    """Main function to run the visualizer"""
    logger.info("Starting Garmin Analytics Visualizer")
    
    consumer = None
    vis_thread = None
    
    try:
        consumer = create_kafka_consumer()
        
        # Start visualization thread
        vis_thread = threading.Thread(target=visualization_thread)
        vis_thread.start()
        
        logger.info("Visualizer started. Accumulating activity data...")
        
        # Consume events
        for message in consumer:
            if shutdown_event.is_set():
                break
            
            try:
                event = message.value
                data_store.add_event(event)
                
                # Log progress every 100 events
                total_events = sum(data_store.activity_patterns['activity_types'].values())
                if total_events % 100 == 0:
                    logger.info(f"Processed {total_events} events, {len(data_store.user_data)} users")
                    
            except Exception as e:
                logger.error(f"Error processing event: {str(e)}")
        
    except KeyboardInterrupt:
        logger.info("Visualizer stopped by user")
    except Exception as e:
        logger.error(f"Unexpected error: {str(e)}")
    finally:
        logger.info("Shutting down visualizer")
        shutdown_event.set()
        
        # Generate final visualization
        generate_visualizations()
        
        if vis_thread:
            vis_thread.join(timeout=5)
        
        if consumer:
            consumer.close()

if __name__ == "__main__":
    main()
