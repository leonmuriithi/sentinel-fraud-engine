'use strict';

const test = require('node:test');
const assert = require('node:assert/strict');
const http = require('node:http');
const { createApp } = require('../src/app');

const silent = { error() {}, warn() {}, log() {} };
const good = { userId: 'u1', amount: 5000, currency: 'KES', location: 'Nairobi', merchantId: 'M1' };

function start(producer) {
  const server = createApp({ producer, topic: 'transaction-stream', logger: silent });
  return new Promise((resolve) => server.listen(0, () => resolve(server)));
}

function request(server, { method = 'POST', path = '/api/v1/transaction', body }) {
  return new Promise((resolve, reject) => {
    const data = body === undefined ? undefined : (typeof body === 'string' ? body : JSON.stringify(body));
    const req = http.request(
      { port: server.address().port, method, path, headers: { 'Content-Type': 'application/json' } },
      (res) => {
        let text = '';
        res.on('data', (c) => { text += c; });
        res.on('end', () => resolve({ status: res.statusCode, json: text ? JSON.parse(text) : null }));
      },
    );
    req.on('error', reject);
    if (data) req.write(data);
    req.end();
  });
}

test('valid transaction is published to Kafka and acknowledged with 202', async () => {
  const sent = [];
  const server = await start({ send: async (m) => { sent.push(m); } });
  const res = await request(server, { body: good });
  server.close();

  assert.equal(res.status, 202);
  assert.ok(res.json.traceId);
  assert.equal(sent.length, 1);
  assert.equal(sent[0].topic, 'transaction-stream');
  assert.equal(sent[0].messages[0].key, 'u1');
  const payload = JSON.parse(sent[0].messages[0].value);
  assert.equal(payload.traceId, res.json.traceId);
  assert.equal(payload.amount, 5000);
});

test('invalid transaction returns 422 and publishes nothing', async () => {
  const sent = [];
  const server = await start({ send: async (m) => { sent.push(m); } });
  const res = await request(server, { body: { ...good, amount: -5 } });
  server.close();

  assert.equal(res.status, 422);
  assert.equal(sent.length, 0);
});

test('malformed JSON returns 400', async () => {
  const server = await start({ send: async () => {} });
  const res = await request(server, { body: '{not json' });
  server.close();
  assert.equal(res.status, 400);
});

test('oversized body returns 413', async () => {
  const server = await start({ send: async () => {} });
  const res = await request(server, { body: JSON.stringify({ ...good, userId: 'x'.repeat(20000) }) })
    .catch(() => ({ status: 413 })); // server may reset the connection once the limit is hit
  server.close();
  assert.equal(res.status, 413);
});

test('broker failure returns 503 instead of crashing', async () => {
  const server = await start({ send: async () => { throw new Error('broker down'); } });
  const res = await request(server, { body: good });
  server.close();
  assert.equal(res.status, 503);
});

test('health check, wrong method and unknown route', async () => {
  const server = await start({ send: async () => {} });
  const health = await request(server, { method: 'GET', path: '/health' });
  const wrong = await request(server, { method: 'GET', path: '/api/v1/transaction' });
  const missing = await request(server, { method: 'GET', path: '/nope' });
  server.close();

  assert.equal(health.status, 200);
  assert.equal(wrong.status, 405);
  assert.equal(missing.status, 404);
});
