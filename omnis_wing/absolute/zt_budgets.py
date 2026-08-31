"""Zero-tolerance frozen budgets — benign corpus refusal + scanner latency.

Declared frozen numbers for the FULL CADMUS residual pass. Not production SLOs
for live WING; cold offline budgets for the WING fork proving suite.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import List, Sequence, Tuple

from omnis_wing.absolute.scanner import scan_payload_bytes
from omnis_wing.absolute.source_taint import classify_content_bytes

# --- Benign corpus (must stay mostly permit-eligible under classification) ---
# These are synthetic *generic* strings with no secret/project markers.
BENIGN_CORPUS: Tuple[str, ...] = (
    "What is the capital of France?",
    "Summarize the weather in plain English.",
    "Write a haiku about rivers.",
    "2 + 2 equals?",
    "Explain photosynthesis to a child.",
    "List three primary colors.",
    "Hello, how are you today?",
    "Convert 100 fahrenheit to celsius conceptually.",
    "Name a mammal that flies.",
    "Outline a gentle morning stretch routine.",
    "What day follows Monday?",
    "Define the word 'ephemeral' simply.",
    "Count from one to five.",
    "Suggest a title for a quiet short story.",
    "Is water wet in common speech?",
    "Describe a blue sky without metaphors of code.",
    "Thank you for your help.",
    "Please rephrase: the cat sat on the mat.",
    "How many minutes are in one hour?",
    "Give a neutral greeting for a new chat.",
)

# Max fraction of benign corpus that may classify as non-generic (refusal-risk).
# Strict: only true positives on secrets/project should refuse; benign must hold.
BENIGN_REFUSAL_BUDGET_MAX_RATIO = 0.05  # ≤5% of corpus may be non-generic

# Scanner latency budgets on cold synthetic payloads (milliseconds).
# Measured on the builder machine; gate re-measures independently.
SCANNER_LATENCY_BUDGET_MS = {
    "P50": 25.0,
    "P95": 80.0,
    "P99": 150.0,
}


@dataclass(frozen=True)
class BenignBudgetReport:
    n: int
    non_generic: int
    ratio: float
    budget: float
    ok: bool
    samples_non_generic: Tuple[str, ...]


def measure_benign_refusal_budget(
    corpus: Sequence[str] = BENIGN_CORPUS,
    budget: float = BENIGN_REFUSAL_BUDGET_MAX_RATIO,
) -> BenignBudgetReport:
    non: List[str] = []
    for s in corpus:
        rec = classify_content_bytes(s.encode("utf-8"))
        if rec.classification != "generic":
            non.append(s[:48])
    n = len(corpus)
    ng = len(non)
    ratio = (ng / n) if n else 1.0
    return BenignBudgetReport(
        n=n,
        non_generic=ng,
        ratio=ratio,
        budget=budget,
        ok=ratio <= budget + 1e-12,
        samples_non_generic=tuple(non[:5]),
    )


@dataclass(frozen=True)
class LatencyReport:
    samples_ms: Tuple[float, ...]
    p50: float
    p95: float
    p99: float
    budgets: dict
    ok: bool


def _percentile(sorted_vals: List[float], p: float) -> float:
    if not sorted_vals:
        return float("inf")
    if len(sorted_vals) == 1:
        return sorted_vals[0]
    k = (len(sorted_vals) - 1) * (p / 100.0)
    f = int(k)
    c = min(f + 1, len(sorted_vals) - 1)
    if f == c:
        return sorted_vals[f]
    return sorted_vals[f] + (sorted_vals[c] - sorted_vals[f]) * (k - f)


def measure_scanner_latency(
    payloads: Sequence[bytes] | None = None,
    rounds: int = 3,
) -> LatencyReport:
    if payloads is None:
        payloads = [s.encode("utf-8") for s in BENIGN_CORPUS] + [
            b"x" * 4096,
            b'{"messages":[{"role":"user","content":"hi"}]}',
        ]
    samples: List[float] = []
    for _ in range(rounds):
        for p in payloads:
            t0 = time.perf_counter()
            scan_payload_bytes(p)
            samples.append((time.perf_counter() - t0) * 1000.0)
    samples.sort()
    p50 = _percentile(samples, 50)
    p95 = _percentile(samples, 95)
    p99 = _percentile(samples, 99)
    bud = SCANNER_LATENCY_BUDGET_MS
    ok = p50 <= bud["P50"] and p95 <= bud["P95"] and p99 <= bud["P99"]
    return LatencyReport(
        samples_ms=tuple(samples),
        p50=p50,
        p95=p95,
        p99=p99,
        budgets=dict(bud),
        ok=ok,
    )
