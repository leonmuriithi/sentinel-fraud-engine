'use strict';

const { Kafka, logLevel } = require('kafkajs');
const { createApp } = require('./app');

const PORT = Number(process.env.PORT || 3000);
const BROKERS = (process.env.KAFKA_BROKERS || 'kafka:29092').split(',');
const TOPIC = process.env.INPUT_TOPIC || 'transaction-stream';

const kafka = new Kafka({
  clientId: 'sentinel-ingestor',
  brokers: BROKERS,
  logLevel: logLevel.WARN,
  retry: { retries: 10, initialRetryTime: 300 },
});
const producer = kafka.producer({ allowAutoTopicCreation: true });

async function connectWithRetry(attempts = 20) {
  for (let i = 1; i <= attempts; i += 1) {
    try {
      await producer.connect();
      return;
    } catch (err) {
      console.warn(`Kafka not ready (attempt ${i}/${attempts}): ${err.message}`);
      await new Promise((r) => setTimeout(r, 2000));
    }
  }
  throw new Error('Could not connect to Kafka');
}

async function main() {
  await connectWithRetry();
  const server = createApp({ producer, topic: TOPIC });
  server.listen(PORT, () => console.log(`Ingestor listening on :${PORT}, publishing to '${TOPIC}'`));

  const shutdown = async () => {
    console.log('Shutting down...');
    server.close();
    await producer.disconnect();
    process.exit(0);
  };
  process.on('SIGTERM', shutdown);
  process.on('SIGINT', shutdown);
}

main().catch((err) => {
  console.error(err);
  process.exit(1);
});
