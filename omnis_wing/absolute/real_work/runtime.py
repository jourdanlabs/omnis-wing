"""Real WING host join for TERMINUS_REAL_WORK_V1.

Production always takes this path.  The legacy in-process provider broker is
retained only for explicit cold tests that set ``OMNIS_WING_SIGNER_MODE=test``
without a real-work config.
"""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
from typing import Any, Mapping, Optional, Sequence

from omnis_wing.absolute.envelope import SourceProvenance
from omnis_wing.absolute.evaluator import TransmissionReceipt
from omnis_wing.absolute.hermes_chat_join import (
    EvidenceSession,
    OutcomeUnknownError,
    WingEgressContext,
    WingRefusal,
)
from omnis_wing.absolute.receipt_spine import (
    EvidencePersistError,
    SignerUnavailable,
    build_signed_receipt,
)

from .caduceus_client import (
    CaduceusBoundaryError,
    CaduceusOutcomeUnknown,
    CaduceusRealWorkClient,
)
from .config import (
    RealWorkConfigError,
    assert_pinned_caduceus_tree,
    load_real_work_config,
)
from .contract import REAL_WORK_POLICY_ID

REAL_WORK_COVERAGE = "WING_PRIMARY_CHAT_TO_CADUCEUS_TERMINUS_REAL_WORK_V1"


def real_work_required() -> bool:
    """Primary chat uses CADUCEUS only when operator supplied real-work config.

    Cold tests keep the legacy in-process join when ``OMNIS_WING_REAL_WORK_CONFIG``
    is unset. Dogfood launcher sets the config path explicitly.
    """
    return bool(str(os.environ.get("OMNIS_WING_REAL_WORK_CONFIG") or "").strip())


def _refusal_receipt(*, digest: str, decision: str, reason: str, provider_calls: int = 0) -> TransmissionReceipt:
    return TransmissionReceipt(
        envelope_id="wing-real-work",
        envelope_digest=digest,
        payload_digest=digest,
        decision=decision,  # type: ignore[arg-type]
        phase="NONE",
        reason=reason,
        finding_ids=(),
        provider_calls=provider_calls,
        delivered_payload_digest=None,
        destination={},
        policy_version=REAL_WORK_POLICY_ID,
        coverage_class=REAL_WORK_COVERAGE,
        phases_observed=(),
    )


def _stable(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def _append(
    evidence: EvidenceSession,
    *,
    envelope_digest: str,
    decision: str,
    phase: str,
    finding_ids: Sequence[str] = (),
) -> object:
    destination = {
        "provider": "caduceus-local",
        "scheme": "http",
        "hostname": "loopback",
        "port": 0,
        "path_class": "omnis.broker.chat",
        "residency": "LOCAL",
    }
    tr = TransmissionReceipt(
        envelope_id=envelope_digest[:32],
        envelope_digest=envelope_digest,
        payload_digest=envelope_digest,
        decision=decision,  # type: ignore[arg-type]
        phase=phase,
        reason="wing_to_caduceus_real_work",
        finding_ids=tuple(finding_ids),
        provider_calls=0,
        delivered_payload_digest=None,
        destination=destination,
        policy_version=REAL_WORK_POLICY_ID,
        coverage_class=REAL_WORK_COVERAGE,
        phases_observed=(phase,) if phase != "NONE" else (),
    )
    signed = build_signed_receipt(
        tr,
        signer=evidence.signer,
        previous_digest=evidence.ledger.head_digest(),
        sequence=evidence.ledger.next_sequence(),
    )
    evidence.ledger.append(signed)
    evidence.last_signed = signed
    return signed


def _evidence(ctx: Optional[WingEgressContext]) -> EvidenceSession:
    evidence = getattr(ctx, "evidence", None) if ctx is not None else None
    if evidence is None or evidence.signer is None or not evidence.signer.available():
        raise WingRefusal(
            TransmissionReceipt(
                envelope_id="wing-real-work",
                envelope_digest="0" * 64,
                payload_digest="0" * 64,
                decision="REFUSE_POLICY_INVALID",
                phase="NONE",
                reason="signer_unavailable",
                finding_ids=(),
                provider_calls=0,
                delivered_payload_digest=None,
                destination={},
                policy_version=REAL_WORK_POLICY_ID,
                coverage_class=REAL_WORK_COVERAGE,
                phases_observed=(),
            )
        )
    try:
        evidence.ledger.ensure_appendable()
    except EvidencePersistError as exc:
        raise WingRefusal(
            TransmissionReceipt(
                envelope_id="wing-real-work",
                envelope_digest="0" * 64,
                payload_digest="0" * 64,
                decision="REFUSE_POLICY_INVALID",
                phase="NONE",
                reason="ledger_not_appendable",
                finding_ids=(),
                provider_calls=0,
                delivered_payload_digest=None,
                destination={},
                policy_version=REAL_WORK_POLICY_ID,
                coverage_class=REAL_WORK_COVERAGE,
                phases_observed=(),
            )
        ) from exc
    return evidence


def _messages(api_kwargs: Mapping[str, Any]) -> list[dict[str, Any]]:
    raw = api_kwargs.get("messages")
    if not isinstance(raw, list) or not raw:
        raise CaduceusBoundaryError("messages_missing")
    out: list[dict[str, Any]] = []
    for item in raw:
        if not isinstance(item, dict):
            raise CaduceusBoundaryError("message_not_object")
        role = item.get("role")
        content = item.get("content")
        if role not in ("system", "user", "assistant", "tool") or not isinstance(content, str):
            raise CaduceusBoundaryError("message_shape_unsupported")
        # Preserve tool-call correlation fields in the final composed message.
        msg = {"role": role, "content": content}
        for key in ("name", "tool_call_id", "tool_calls"):
            if key in item:
                msg[key] = item[key]
        out.append(msg)

    # The frozen broker contract is messages-only.  Do not silently discard
    # WING's real tool schema: include a canonical local-tool description as a
    # final system message. It is context, not a provider-side executable tool.
    tools = api_kwargs.get("tools")
    if tools:
        if not isinstance(tools, list):
            raise CaduceusBoundaryError("tools_shape_unsupported")
        out.append(
            {
                "role": "system",
                "content": (
                    "OMNIS WING LOCAL TOOL CONTRACT (descriptive only; direct "
                    "provider tool execution is disabled on this governed request):\n"
                    + _stable(tools).decode("utf-8")
                ),
            }
        )
    # Unknown payload-bearing fields cannot ride outside the registered body.
    allowed_control = {
        "model",
        "messages",
        "tools",
        "tool_choice",
        "parallel_tool_calls",
        "temperature",
        "top_p",
        "max_tokens",
        "max_completion_tokens",
        "reasoning_effort",
        "stream",
        "stream_options",
        "timeout",
    }
    unknown = sorted(str(k) for k in api_kwargs if k not in allowed_control)
    if unknown:
        raise CaduceusBoundaryError("provider_body_contains_unsupported_fields")
    return out


def _workspace_identity(agent: Any) -> str:
    root = Path(
        os.environ.get("OMNIS_WING_WORKSPACE")
        or os.environ.get("HERMES_WORKSPACE")
        or os.getcwd()
    ).expanduser()
    # This stays local and is hashed before registration. Include the repo head
    # when available so a different checkout is a different public identity.
    head = "no-git"
    try:
        import subprocess

        head = subprocess.run(
            ["git", "-C", str(root), "rev-parse", "HEAD"],
            check=True,
            capture_output=True,
            text=True,
            timeout=3,
        ).stdout.strip()
    except Exception:
        pass
    profile = str(getattr(agent, "profile_name", "wing") or "wing")
    return f"{root}|{head}|{profile}"


def _client_for(agent: Any) -> CaduceusRealWorkClient:
    planted = getattr(agent, "_wing_caduceus_client", None)
    mode = (os.environ.get("OMNIS_WING_SIGNER_MODE") or "production").strip().lower()
    if planted is not None and mode == "test":
        return planted
    cfg = load_real_work_config(require=True)
    assert cfg is not None
    assert_pinned_caduceus_tree(cfg)
    return CaduceusRealWorkClient(cfg)


def transmit_primary_chat(
    *,
    agent: Any,
    api_kwargs: Mapping[str, Any],
    wing_ctx: Optional[WingEgressContext],
) -> Any:
    evidence = _evidence(wing_ctx)
    try:
        messages = _messages(api_kwargs)
    except CaduceusBoundaryError as exc:
        try:
            _append(
                evidence,
                envelope_digest=hashlib.sha256(b"local-refusal").hexdigest(),
                decision="REFUSE_UNSUPPORTED",
                phase="NONE",
                finding_ids=(exc.reason,),
            )
        except Exception:
            pass
        setattr(
            agent,
            "wing_real_work_status",
            {"state": "LOCAL_ONLY", "reason": exc.reason, "provider_calls": 0},
        )
        raise WingRefusal(
            _refusal_receipt(
                digest="0" * 64,
                decision="REFUSE_UNSUPPORTED",
                reason=exc.reason,
            )
        ) from exc

    digest = hashlib.sha256(_stable(messages)).hexdigest()
    # Resolve and authenticate the exact local authority before writing a
    # STARTED row. A config/pin/capability failure is a local refusal, not an
    # uncertain transmission.
    try:
        client = _client_for(agent)
    except RealWorkConfigError as exc:
        reason = f"real_work_config:{exc}"
        setattr(
            agent,
            "wing_real_work_status",
            {"state": "LOCAL_ONLY", "reason": reason, "provider_calls": 0},
        )
        raise WingRefusal(
            _refusal_receipt(
                digest=digest,
                decision="REFUSE_POLICY_INVALID",
                reason=reason,
            )
        ) from exc

    try:
        _append(
            evidence,
            envelope_digest=digest,
            decision="PERMIT",
            phase="TRANSMISSION_STARTED",
        )
    except Exception as exc:
        setattr(
            agent,
            "wing_real_work_status",
            {"state": "LOCAL_ONLY", "reason": "wing_pre_send_evidence_failed", "provider_calls": 0},
        )
        raise WingRefusal(
            _refusal_receipt(
                digest=digest,
                decision="REFUSE_POLICY_INVALID",
                reason="wing_pre_send_evidence_failed",
            )
        ) from exc

    sources: tuple[SourceProvenance, ...] = tuple(getattr(wing_ctx, "sources", ()) or ())
    try:
        result = client.call(
            messages=messages,
            sources=sources,
            workspace_identity=_workspace_identity(agent),
            lane=getattr(getattr(client, "cfg", None), "lane", "codegen"),
        )
    except CaduceusBoundaryError as exc:
        decision = "REFUSE_SOURCE_POLICY"
        # WING has already durably recorded STARTED for its local CADUCEUS
        # request, even when CADUCEUS correctly kept the external provider at
        # zero calls. Therefore its terminal is always the after-start failure
        # phase from WING's own two-phase grammar.
        phase = "FAILED_AFTER_TRANSMISSION_STARTED"
        try:
            _append(
                evidence,
                envelope_digest=digest,
                decision=decision,
                phase=phase,
                finding_ids=(exc.reason,),
            )
        except Exception as evidence_exc:
            setattr(
                agent,
                "wing_real_work_status",
                {
                    "state": "OUTCOME_UNKNOWN",
                    "reason": "wing_refusal_terminal_evidence_failed",
                    "provider_calls": exc.provider_calls,
                },
            )
            raise OutcomeUnknownError(
                receipt=_refusal_receipt(
                    digest=digest,
                    decision="REFUSE_POLICY_INVALID",
                    reason="wing_refusal_terminal_evidence_failed",
                    provider_calls=exc.provider_calls,
                ),
                pre_send_signed=evidence.last_signed,
                client_calls=exc.provider_calls,
                response=None,
                reason="wing_refusal_terminal_evidence_failed",
            ) from evidence_exc
        setattr(
            agent,
            "wing_real_work_status",
            {
                "state": "LOCAL_ONLY" if exc.provider_calls == 0 else "REFUSED",
                "reason": exc.reason,
                "delivery_mode": exc.delivery_mode,
                "provider_calls": exc.provider_calls,
            },
        )
        raise WingRefusal(
            _refusal_receipt(
                digest=digest,
                decision=decision,
                reason=exc.reason,
                provider_calls=exc.provider_calls,
            )
        ) from exc
    except CaduceusOutcomeUnknown as exc:
        setattr(
            agent,
            "wing_real_work_status",
            {"state": "OUTCOME_UNKNOWN", "reason": str(exc), "provider_calls": getattr(client, "calls", 0)},
        )
        raise OutcomeUnknownError(
            receipt=TransmissionReceipt(
                envelope_id="wing-real-work",
                envelope_digest=digest,
                payload_digest=digest,
                decision="PERMIT",
                phase="OUTCOME_UNKNOWN",
                reason=str(exc),
                finding_ids=(),
                provider_calls=getattr(client, "calls", 0),
                delivered_payload_digest=None,
                destination={},
                policy_version=REAL_WORK_POLICY_ID,
                coverage_class=REAL_WORK_COVERAGE,
                phases_observed=("TRANSMISSION_STARTED", "OUTCOME_UNKNOWN"),
            ),
            pre_send_signed=evidence.last_signed,
            client_calls=getattr(client, "calls", 0),
            response=None,
            reason=str(exc),
        ) from exc

    try:
        _append(
            evidence,
            envelope_digest=digest,
            decision="PERMIT",
            phase="TRANSMISSION_COMPLETED",
        )
    except Exception as exc:
        setattr(
            agent,
            "wing_real_work_status",
            {"state": "OUTCOME_UNKNOWN", "reason": "wing_terminal_evidence_failed", "provider_calls": 1},
        )
        raise OutcomeUnknownError(
            receipt=TransmissionReceipt(
                envelope_id="wing-real-work",
                envelope_digest=digest,
                payload_digest=digest,
                decision="PERMIT",
                phase="OUTCOME_UNKNOWN",
                reason="wing_terminal_evidence_failed",
                finding_ids=(),
                provider_calls=1,
                delivered_payload_digest=None,
                destination={},
                policy_version=REAL_WORK_POLICY_ID,
                coverage_class=REAL_WORK_COVERAGE,
                phases_observed=("TRANSMISSION_STARTED", "OUTCOME_UNKNOWN"),
            ),
            pre_send_signed=evidence.last_signed,
            client_calls=1,
            response=result.response,
            reason="wing_terminal_evidence_failed",
        ) from exc

    status = dict(result.public_evidence)
    status["state"] = f"{result.delivery_mode} · DELIVERED"
    status["provider_calls"] = result.provider_calls
    setattr(agent, "wing_real_work_status", status)
    return result.response


def refuse_non_primary_route(agent: Any, route_id: str) -> None:
    setattr(
        agent,
        "wing_real_work_status",
        {"state": "LOCAL_ONLY", "reason": f"route_disabled:{route_id}", "provider_calls": 0},
    )
    from omnis_wing.completion.product_disable import WingRouteDisabled

    raise WingRouteDisabled(
        route_id,
        "route disabled in OMNIS WING real-work dogfood launcher; primary CADUCEUS chat only",
    )


class BufferedCaduceusStream:
    """One safe, response-gated CADUCEUS answer exposed as a stream-shaped object.

    CADUCEUS owns the external non-stream request and response gate. WING emits
    the already-cleared answer as one local chunk; no provider streaming socket
    exists in WING and no unscanned partial response can reach the user.
    """

    def __init__(self, response: Any):
        self.response = None
        self._response = response

    def __iter__(self):
        choice = self._response.choices[0]
        message = choice.message
        delta = type(
            "WingBufferedDelta",
            (),
            {
                "content": getattr(message, "content", None),
                "role": getattr(message, "role", "assistant"),
                "tool_calls": getattr(message, "tool_calls", None),
                "reasoning": getattr(message, "reasoning", None),
                "reasoning_content": getattr(message, "reasoning_content", None),
            },
        )()
        yield type(
            "WingBufferedChunk",
            (),
            {
                "id": getattr(self._response, "id", "wing-caduceus"),
                "model": getattr(self._response, "model", "caduceus"),
                "choices": [
                    type(
                        "WingBufferedChoice",
                        (),
                        {"index": 0, "delta": delta, "finish_reason": "stop"},
                    )()
                ],
                "usage": getattr(self._response, "usage", None),
            },
        )()


def transmit_primary_stream(
    *, agent: Any, api_kwargs: Mapping[str, Any], wing_ctx: Optional[WingEgressContext]
) -> BufferedCaduceusStream:
    body = dict(api_kwargs)
    body["stream"] = False
    body.pop("stream_options", None)
    return BufferedCaduceusStream(
        transmit_primary_chat(agent=agent, api_kwargs=body, wing_ctx=wing_ctx)
    )
