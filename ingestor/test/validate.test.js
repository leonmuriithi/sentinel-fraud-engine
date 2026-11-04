'use strict';

const test = require('node:test');
const assert = require('node:assert/strict');
const { validateTransaction } = require('../src/validate');

const good = { userId: 'u1', amount: 5000, currency: 'KES', location: 'Nairobi', merchantId: 'M1' };

test('accepts a valid transaction and trims strings', () => {
  const r = validateTransaction({ ...good, userId: '  u1  ' });
  assert.equal(r.valid, true);
  assert.equal(r.value.userId, 'u1');
});

test('rejects non-objects', () => {
  for (const bad of [null, 'text', 42, [1, 2]]) {
    assert.equal(validateTransaction(bad).valid, false);
  }
});

test('rejects missing or empty strings', () => {
  for (const field of ['userId', 'merchantId', 'location']) {
    assert.equal(validateTransaction({ ...good, [field]: '' }).valid, false, field);
    const { [field]: _omit, ...rest } = good;
    assert.equal(validateTransaction(rest).valid, false, field);
  }
});

test('rejects bad amounts', () => {
  for (const amount of [0, -1, NaN, Infinity, '100', null, 2e9]) {
    assert.equal(validateTransaction({ ...good, amount }).valid, false, String(amount));
  }
});

test('rejects malformed currency codes', () => {
  for (const currency of ['kes', 'KE', 'KESS', 7, undefined]) {
    assert.equal(validateTransaction({ ...good, currency }).valid, false, String(currency));
  }
});

test('reports every problem at once', () => {
  const r = validateTransaction({});
  assert.equal(r.errors.length, 5);
});
