'use strict';

const MAX_AMOUNT = 1e9;

function isText(value, max = 64) {
  return typeof value === 'string' && value.trim().length > 0 && value.length <= max;
}

/**
 * Validate a transaction payload.
 * @returns {{valid: boolean, errors: string[], value?: object}}
 */
function validateTransaction(body) {
  const errors = [];
  if (body === null || typeof body !== 'object' || Array.isArray(body)) {
    return { valid: false, errors: ['body must be a JSON object'] };
  }

  if (!isText(body.userId)) errors.push('userId must be a non-empty string (max 64 chars)');
  if (!isText(body.merchantId)) errors.push('merchantId must be a non-empty string (max 64 chars)');
  if (!isText(body.location)) errors.push('location must be a non-empty string (max 64 chars)');
  if (typeof body.currency !== 'string' || !/^[A-Z]{3}$/.test(body.currency)) {
    errors.push('currency must be a 3-letter uppercase code, e.g. KES');
  }
  if (typeof body.amount !== 'number' || !Number.isFinite(body.amount) ||
      body.amount <= 0 || body.amount > MAX_AMOUNT) {
    errors.push(`amount must be a number greater than 0 and at most ${MAX_AMOUNT}`);
  }

  if (errors.length > 0) return { valid: false, errors };

  return {
    valid: true,
    errors: [],
    value: {
      userId: body.userId.trim(),
      merchantId: body.merchantId.trim(),
      location: body.location.trim(),
      currency: body.currency,
      amount: body.amount,
    },
  };
}

module.exports = { validateTransaction };
