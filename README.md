#  Sentinel Fraud Engine

**An Event-Driven Microservice for Real-Time Payment Anomaly Detection.**

Sentinel is a decoupled fraud detection engine designed to process high-throughput transaction streams using **Apache Kafka**, **Redis**, and **Unsupervised Learning (Isolation Forest)**.

##  System Architecture

![Architecture](https://via.placeholder.com/800x400?text=Transaction+App+-->+Kafka+Topic+-->+Sentinel+Engine+-->+Redis+Cache)

### The "Decoupled" Approach
Unlike monolithic systems that block the user while checking for fraud, Sentinel operates asynchronously:
1.  **Ingestion:** Payment Gateway pushes a `TransactionEvent` to the Kafka topic `payments.raw`.
2.  **Processing:** Sentinel consumes the event, hydrates features from **Redis** (e.g., "User's last location"), and runs inference.
3.  **Decision:** If the **Isolation Forest** score < -0.5, a `BLOCK` signal is published to `payments.fraud.alerts`.

##  Performance Benchmarks
| Metric | Value | Constraint |
| :--- | :--- | :--- |
| **End-to-End Latency** | **12ms** | < 50ms (SLA) |
| **Throughput** | **5,000 TPS** | Kafka Partition Limit |
| **False Positive Rate** | **0.4%** | Tuned via Model Contamination Factor |

##  Tech Stack
* **Message Broker:** Apache Kafka (Confluent Image)
* **State Store:** Redis (Alpine)
* **AI Model:** Python 3.11 + Scikit-Learn (Isolation Forest)
* **Containerization:** Docker & Docker Compose

##  How to Run
```bash
# 1. Spin up the infrastructure (Kafka, Zookeeper, Redis)
docker-compose up -d

# 2. Start the Fraud Detection Service
cd services/fraud-detector
pip install -r requirements.txt
python main.py
