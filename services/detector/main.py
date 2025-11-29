import os
import json
import time
import logging
import redis
import numpy as np
from kafka import KafkaConsumer, KafkaProducer
from sklearn.ensemble import IsolationForest

# --- CONFIGURATION ---
KAFKA_BROKER = os.getenv('KAFKA_BROKER', 'localhost:9092')
REDIS_HOST = os.getenv('REDIS_HOST', 'localhost')
TOPIC_INPUT = 'transaction-stream'
TOPIC_ALERTS = 'fraud-alerts'

# Setup Logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s | %(levelname)s | %(message)s')
logger = logging.getLogger("Sentinel-Detector")

# --- INITIALIZATION ---
logger.info(">>> INITIALIZING SENTINEL AI CORE...")

# 1. Connect to Redis (State Store)
try:
    cache = redis.Redis(host=REDIS_HOST, port=6379, db=0)
    cache.ping()
    logger.info(">>> [REDIS] Connection Established.")
except Exception as e:
    logger.error(f">>> [REDIS] Failed: {e}")

# 2. Load/Train AI Model (Simulated Pre-trained Model)
# In production, this would load a .pkl file from S3
logger.info(">>> [AI] Loading Isolation Forest Model...")
rng = np.random.RandomState(42)
# Simulate training data (Normal vs Anomaly)
X_train = 0.3 * rng.randn(100, 2)
X_train = np.r_[X_train + 2, X_train - 2]
clf = IsolationForest(max_samples=100, random_state=rng)
clf.fit(X_train)
logger.info(">>> [AI] Model Loaded Successfully.")

# 3. Connect to Kafka
consumer = KafkaConsumer(
    TOPIC_INPUT,
    bootstrap_servers=[KAFKA_BROKER],
    auto_offset_reset='latest',
    value_deserializer=lambda x: json.loads(x.decode('utf-8'))
)
producer = KafkaProducer(
    bootstrap_servers=[KAFKA_BROKER],
    value_serializer=lambda x: json.dumps(x).encode('utf-8')
)

# --- FRAUD LOGIC ---
def check_velocity_rules(tx):
    """
    Rule-based check: Did the user move too fast?
    """
    user_id = tx['userId']
    current_loc = tx.get('location', 'UNKNOWN')
    
    last_loc = cache.get(f"loc:{user_id}")
    
    if last_loc:
        last_loc = last_loc.decode('utf-8')
        if last_loc != current_loc:
            # Simple simulation: If location changed instantly, flag it.
            return True, f"VELOCITY_VIOLATION: JUMPED FROM {last_loc} TO {current_loc}"
            
    # Update Cache with TTL (Time To Live)
    cache.setex(f"loc:{user_id}", 300, current_loc) # Expire in 5 mins
    return False, None

def check_ai_model(tx):
    """
    AI-based check: Is the amount/pattern anomalous?
    """
    # Feature Engineering (Simulated)
    features = [[tx['amount'] / 1000, 1.0]] # Normalize inputs
    score = clf.decision_function(features)[0]
    
    if score < -0.15: # Anomaly threshold
        return True, f"AI_ANOMALY_SCORE: {score:.4f}"
    return False, None

# --- MAIN LOOP ---
logger.info(">>> SYSTEM LIVE. PROCESSING STREAM...")

for message in consumer:
    tx = message.value
    tx_id = tx.get('traceId', 'N/A')
    
    # 1. Run Rules Engine
    is_fraud, reason = check_velocity_rules(tx)
    
    # 2. Run AI Engine (if rules pass)
    if not is_fraud:
        is_fraud, reason = check_ai_model(tx)
    
    if is_fraud:
        logger.warning(f"🚨 FRAUD DETECTED [{tx_id}]: {reason}")
        
        # Publish Alert
        alert_payload = {
            "traceId": tx_id,
            "reason": reason,
            "userId": tx['userId'],
            "status": "BLOCKED",
            "timestamp": time.time()
        }
        producer.send(TOPIC_ALERTS, value=alert_payload)
    else:
        logger.info(f"✅ CLEAN TRANSACTION [{tx_id}]")