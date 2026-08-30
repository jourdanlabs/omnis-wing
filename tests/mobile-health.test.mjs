import test from 'node:test';
import assert from 'node:assert/strict';
import { parseHealthReport, summarizeHealth } from '../mobile/health-parse.mjs';

test('parseHealthReport extracts ready + chain fields', () => {
  const summary = parseHealthReport({
    ready: true,
    chain: { valid: true, head: 'abc123' },
    signer: { algorithm: 'ed25519', fingerprint: 'fp-deadbeef' },
    anchor_configured: false,
  });
  assert.equal(summary.ready, true);
  assert.equal(summary.chainValid, true);
  assert.equal(summary.chainHead, 'abc123');
  assert.equal(summary.signerFingerprint, 'fp-deadbeef');
});

test('parseHealthReport rejects invalid JSON string', () => {
  assert.throws(() => parseHealthReport('{not json'), SyntaxError);
});

test('summarizeHealth returns label rows', () => {
  const rows = summarizeHealth({
    ready: false,
    chainValid: false,
    chainHead: null,
    signerAlgorithm: null,
    signerFingerprint: null,
    anchorConfigured: false,
  });
  assert.ok(rows.some(([k]) => k === 'Ready'));
  assert.equal(rows[0][1], 'false');
});
