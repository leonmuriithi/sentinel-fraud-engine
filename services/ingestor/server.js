/**
 * SENTINEL INGESTOR SERVICE
 * Responsibility: Accept high-volume transactions via HTTP and buffer to Kafka.
 * Performance: Non-blocking I/O to handle 10k+ TPS.
 */

const express = require('express');
const { Kafka, CompressionTypes } = require('kafkajs');
const { v4: uuidv4 } = require('uuid');
const helmet = require('helmet');
const morgan = require('morgan');

const app = express();
const PORT = process.env.PORT || 3000;

// Security & Logging Middlewares
app.use(helmet());
app.use(express.json());
app.use(morgan('combined')); // Production logging

// Kafka Configuration
const kafka = new Kafka({
  clientId: 'sentinel-ingest-node',
  brokers: [process.env.KAFKA_BROKER || 'localhost:29092'],
  retry: {
    initialRetryTime: 100,
    retries: 8
  }
});

const producer = kafka.producer();

const initKafka = async () => {
  try {
    await producer.connect();
    console.log(">>> [KAFKA] Producer Connected & Ready");
  } catch (err) {
    console.error("!!! [KAFKA CRITICAL] Connection Failed:", err);
    process.exit(1); // Fail fast so Docker restarts the container
  }
};

// --- API ENDPOINTS ---

/**
 * POST /api/v1/transaction
 * Receives raw payment payload.
 * Returns 202 Accepted immediately (Async Processing).
 */
app.post('/api/v1/transaction', async (req, res) => {
  const { userId, amount, merchantId, location, currency } = req.body;
  
  // 1. Generate unique Trace ID for Distributed Tracing
  const traceId = uuidv4();
  const timestamp = Date.now();

  // 2. Validate Payload (Basic Schema Check)
  if (!userId || !amount) {
    return res.status(400).json({ error: "Invalid payload structure" });
  }

  // 3. Serialize Event
  const eventPayload = {
    traceId,
    userId,
    amount,
    merchantId,
    location,
    currency,
    timestamp,
    metadata: { source: 'MOBILE_APP', version: '2.4.1' }
  };

  try {
    // 4. Push to Kafka (Topic: 'transaction-stream')
    // Using GZIP compression for network efficiency
    await producer.send({
      topic: 'transaction-stream',
      compression: CompressionTypes.GZIP,
      messages: [
        { 
          key: userId, // Partition by UserID to ensure order guarantees
          value: JSON.stringify(eventPayload) 
        }
      ],
    });

    // 5. Response: 202 Accepted
    return res.status(202).json({ 
      status: 'QUEUED', 
      traceId, 
      message: 'Transaction accepted for risk analysis.' 
    });

  } catch (error) {
    console.error(`[ERROR] TraceID: ${traceId} - Kafka Publish Failed`, error);
    return res.status(503).json({ error: "Service Unavailable - Event Bus Down" });
  }
});

// Start Server
initKafka().then(() => {
  app.listen(PORT, () => console.log(`>>> Sentinel Ingestor listening on port ${PORT}`));
});
