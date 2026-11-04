'use strict';

const http = require('node:http');
const { randomUUID } = require('node:crypto');
const { validateTransaction } = require('./validate');

const MAX_BODY_BYTES = 10 * 1024;

function send(res, status, payload) {
  const body = JSON.stringify(payload);
  res.writeHead(status, { 'Content-Type': 'application/json', 'Content-Length': Buffer.byteLength(body) });
  res.end(body);
}

function readBody(req, limit) {
  return new Promise((resolve, reject) => {
    const chunks = [];
    let size = 0;
    req.on('data', (chunk) => {
      size += chunk.length;
      if (size > limit) {
        reject(Object.assign(new Error('payload too large'), { status: 413 }));
        req.destroy();
        return;
      }
      chunks.push(chunk);
    });
    req.on('end', () => resolve(Buffer.concat(chunks).toString('utf8')));
    req.on('error', reject);
  });
}

/**
 * Build the HTTP server. The Kafka producer is injected so the app can be
 * tested without a broker.
 * @param {{producer: {send: Function}, topic: string, logger?: Console}} deps
 */
function createApp({ producer, topic, logger = console }) {
  return http.createServer(async (req, res) => {
    try {
      if (req.url === '/health' && req.method === 'GET') {
        return send(res, 200, { status: 'ok' });
      }

      if (req.url === '/api/v1/transaction') {
        if (req.method !== 'POST') return send(res, 405, { error: 'method not allowed' });

        let parsed;
        try {
          parsed = JSON.parse(await readBody(req, MAX_BODY_BYTES));
        } catch (err) {
          if (err.status === 413) return send(res, 413, { error: 'payload too large' });
          return send(res, 400, { error: 'request body is not valid JSON' });
        }

        const result = validateTransaction(parsed);
        if (!result.valid) return send(res, 422, { error: 'validation failed', details: result.errors });

        const traceId = randomUUID();
        const message = { traceId, ...result.value, receivedAt: Date.now() / 1000 };
        try {
          await producer.send({
            topic,
            messages: [{ key: message.userId, value: JSON.stringify(message) }],
          });
        } catch (err) {
          logger.error(`[${traceId}] Kafka publish failed: ${err.message}`);
          return send(res, 503, { error: 'message broker unavailable, retry later' });
        }
        return send(res, 202, { status: 'queued', traceId });
      }

      return send(res, 404, { error: 'not found' });
    } catch (err) {
      logger.error(`Unhandled error: ${err.stack || err}`);
      return send(res, 500, { error: 'internal error' });
    }
  });
}

module.exports = { createApp };
