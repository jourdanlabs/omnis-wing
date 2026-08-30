/**
 * Parse operator_cli health JSON (offline — no live wire from mobile browser).
 */

export function parseHealthReport(raw) {
  const data = typeof raw === 'string' ? JSON.parse(raw) : raw;
  if (!data || typeof data !== 'object') {
    throw new Error('health JSON must be an object');
  }
  const ready = Boolean(data.ready ?? data.ok ?? false);
  const chain = data.chain ?? data.ledger ?? {};
  const signer = data.signer ?? {};
  return {
    ready,
    chainValid: chain.valid ?? chain.ok ?? null,
    chainHead: chain.head ?? chain.head_sha ?? null,
    signerAlgorithm: signer.algorithm ?? signer.alg ?? null,
    signerFingerprint: signer.fingerprint ?? signer.fp ?? null,
    anchorConfigured: data.anchor_configured ?? data.anchor?.configured ?? null,
    raw: data,
  };
}

export function summarizeHealth(summary) {
  const lines = [
    ['Ready', String(summary.ready)],
    ['Chain valid', String(summary.chainValid)],
    ['Chain head', summary.chainHead ?? '—'],
    ['Signer', summary.signerAlgorithm ?? '—'],
    ['Fingerprint', summary.signerFingerprint ?? '—'],
    ['Anchor configured', String(summary.anchorConfigured)],
  ];
  return lines;
}
