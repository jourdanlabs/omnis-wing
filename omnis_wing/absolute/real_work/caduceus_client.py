"""The sole WING client for the pinned local CADUCEUS real-work broker.

This module owns WING's only payload-bearing network operation in the dogfood
launcher.  It can contact one exact loopback CADUCEUS origin.  CADUCEUS, not
WING, owns every provider socket and the TERMINUS transform/response gate.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import secrets
import ssl
import urllib.error
import urllib.request
import uuid
from dataclasses import dataclass
from types import SimpleNamespace
from typing import Any, Callable, Mapping, Optional, Sequence

from omnis_wing.absolute.envelope import SourceProvenance

from .config import RealWorkConfig, RealWorkConfigError, service_capability
from .contract import DELIVERY_MODE, REAL_WORK_POLICY_ID

SERVICE_AUTH_CONTEXT = "CADUCEUS-SERVICE-AUTH-V1"
BROKER_REQUEST_VERSION = "OMNIS-BROKER-REQUEST-V1"
WORKSPACE_DIGEST_CONTEXT = "OMNIS-WORKSPACE-POLICY-V1"
SOURCE_REF_CONTEXT = "OMNIS-SOURCE-REF-V1"
ALLOWED_LANES = frozenset({"plan", "codegen", "validation"})
ALLOWED_ORIGINS = frozenset(
    {"generic", "internal", "confidential", "crown_jewel", "credential", "project", "unknown"}
)


class CaduceusBoundaryError(RuntimeError):
    """Typed local boundary refusal. No raw submitted material in the message."""

    def __init__(self, reason: str, *, provider_calls: int = 0, mode: str = "LOCAL_ONLY"):
        self.reason = reason
        self.provider_calls = provider_calls
        self.delivery_mode = mode
        super().__init__(f"OMNIS_WING_CADUCEUS_REFUSED:{reason}")


class CaduceusOutcomeUnknown(RuntimeError):
    def __init__(self, reason: str, *, provider_may_have_run: bool):
        self.reason = reason
        self.provider_may_have_run = provider_may_have_run
        super().__init__(f"OMNIS_WING_CADUCEUS_OUTCOME_UNKNOWN:{reason}")


@dataclass(frozen=True)
class HttpResult:
    status: int
    headers: Mapping[str, str]
    body: bytes


@dataclass(frozen=True)
class CaduceusResult:
    response: Any
    request_id: str
    delivery_mode: str
    terminal: str
    receipt: str
    chain_head: str
    chain_count: int
    body_digest: str
    answer_digest: str
    provider_calls: int
    public_evidence: Mapping[str, Any]


HttpRequest = Callable[[str, str, Mapping[str, str], Optional[bytes], float], HttpResult]


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):  # noqa: ANN001
        raise CaduceusBoundaryError("local_caduceus_redirect_refused")


def _default_http_request(
    method: str,
    url: str,
    headers: Mapping[str, str],
    body: Optional[bytes],
    timeout: float,
) -> HttpResult:
    # No proxy and no redirect.  The only allowed target is validated loopback.
    opener = urllib.request.build_opener(
        urllib.request.ProxyHandler({}),
        _NoRedirect(),
        urllib.request.HTTPSHandler(context=ssl.create_default_context()),
    )
    req = urllib.request.Request(url, data=body, headers=dict(headers), method=method)
    try:
        with opener.open(req, timeout=timeout) as res:
            return HttpResult(
                status=int(res.status),
                headers={k.lower(): v for k, v in res.headers.items()},
                body=res.read(2 * 1024 * 1024 + 1),
            )
    except urllib.error.HTTPError as exc:
        return HttpResult(
            status=int(exc.code),
            headers={k.lower(): v for k, v in exc.headers.items()},
            body=exc.read(2 * 1024 * 1024 + 1),
        )
    except CaduceusBoundaryError:
        raise
    except Exception as exc:
        raise CaduceusBoundaryError(f"local_caduceus_unreachable:{type(exc).__name__}") from exc


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _canonical_bytes(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def _wire_bytes(value: Any) -> bytes:
    # JS JSON.stringify shape for the closed broker body: compact, insertion ordered.
    return json.dumps(value, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def _b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode("ascii").rstrip("=")


def _json_object(result: HttpResult, *, boundary: str) -> dict[str, Any]:
    if len(result.body) > 2 * 1024 * 1024:
        raise CaduceusBoundaryError(f"{boundary}_response_too_large")
    try:
        value = json.loads(result.body.decode("utf-8", errors="strict"))
    except Exception as exc:
        raise CaduceusBoundaryError(f"{boundary}_invalid_json") from exc
    if not isinstance(value, dict):
        raise CaduceusBoundaryError(f"{boundary}_not_object")
    return value


def _namespace(value: Any) -> Any:
    if isinstance(value, dict):
        return SimpleNamespace(**{str(k): _namespace(v) for k, v in value.items()})
    if isinstance(value, list):
        return [_namespace(v) for v in value]
    return value


def _map_classification(source: SourceProvenance) -> str:
    cls = str(source.classification or "unknown")
    if bool(source.crown_jewel):
        return "crown_jewel"
    if cls == "protected":
        return "confidential"
    if cls in ALLOWED_ORIGINS:
        return cls
    return "unknown"


def request_scoped_source_ref(request_id: str, seed: str) -> str:
    return _sha(f"{SOURCE_REF_CONTEXT}\n{request_id}\n{seed}".encode("utf-8"))


def workspace_policy_digest(workspace_identity: str) -> str:
    # Public path-hiding identity, not an authentication tag.
    return _sha(f"{WORKSPACE_DIGEST_CONTEXT}\n{workspace_identity}".encode("utf-8"))


def _source_fragments(
    request_id: str,
    messages: Sequence[Mapping[str, Any]],
    sources: Sequence[SourceProvenance],
) -> tuple[list[dict[str, Any]], list[str]]:
    fragments: list[dict[str, Any]] = []
    refs: list[str] = []
    classes: list[str] = []
    for index, source in enumerate(sources):
        classification = _map_classification(source)
        path_digest = _sha(str(source.path or "source").encode("utf-8"))
        ref = request_scoped_source_ref(
            request_id, f"source|{index}|{path_digest}|{source.content_digest}"
        )
        refs.append(ref)
        classes.append(classification)
        fragments.append(
            {
                "kind": "wing_source",
                "field_path": f"source[{index}]",
                "content_digest": source.content_digest,
                "classification": classification,
                "relative_path_digest": path_digest,
                "source_ref": ref,
            }
        )
    # Completeness records bind every final composed message digest. When no
    # explicit SourceProvenance list is provided, messages themselves are the
    # provenance (automatic content classification at CADUCEUS).
    if not fragments:
        if not messages:
            raise CaduceusBoundaryError("provenance_missing")
        for index, message in enumerate(messages):
            content = message.get("content")
            if not isinstance(content, str):
                raise CaduceusBoundaryError("message_content_unsupported")
            dig = _sha(content.encode("utf-8"))
            ref = request_scoped_source_ref(request_id, f"message|{index}|{dig}")
            refs.append(ref)
            classes.append("unknown")
            fragments.append(
                {
                    "kind": "prompt",
                    "field_path": f"message[{index}]",
                    "content_digest": dig,
                    "byte_length": len(content.encode("utf-8")),
                    "classification": "unknown",
                    "relative_path_digest": None,
                    "source_ref": ref,
                }
            )
        return fragments, classes

    # Explicit sources present: bind messages to first source identity so
    # breadth is not inflated by double-counting.
    for index, message in enumerate(messages):
        content = message.get("content")
        if not isinstance(content, str):
            raise CaduceusBoundaryError("message_content_unsupported")
        fragments.insert(
            index,
            {
                "kind": "prompt",
                "field_path": f"message[{index}]",
                "content_digest": _sha(content.encode("utf-8")),
                "byte_length": len(content.encode("utf-8")),
                "classification": classes[0],
                "relative_path_digest": None,
                "source_ref": refs[0],
            },
        )
    return fragments, sorted(set(classes))


def _service_auth_message(instance_id: str, nonce: str) -> bytes:
    return f"{SERVICE_AUTH_CONTEXT}\n{instance_id}\n{nonce}".encode("utf-8")


def _request_binding_bytes(
    *, origin: str, instance_id: str, nonce: str, request_id: str, lane: str, body_digest: str
) -> bytes:
    return "\n".join(
        (
            SERVICE_AUTH_CONTEXT,
            BROKER_REQUEST_VERSION,
            origin,
            instance_id,
            nonce,
            request_id,
            lane,
            lane,
            body_digest,
        )
    ).encode("utf-8")


class CaduceusRealWorkClient:
    def __init__(
        self,
        cfg: RealWorkConfig,
        *,
        token: Optional[str] = None,
        http_request: Optional[HttpRequest] = None,
    ):
        self.cfg = cfg
        self.token = token if token is not None else service_capability(cfg)
        if not self.token or len(self.token) != 43:
            raise RealWorkConfigError("caduceus_service_capability_unavailable")
        self.http_request = http_request or _default_http_request
        self.calls = 0
        self.last_wire_body: Optional[bytes] = None

    def _request(
        self, method: str, suffix: str, *, headers: Optional[Mapping[str, str]] = None, body: Optional[bytes] = None
    ) -> HttpResult:
        if not suffix.startswith("/") or "?" in suffix and not suffix.startswith("/auth/challenge?"):
            raise CaduceusBoundaryError("local_endpoint_invalid")
        return self.http_request(
            method,
            f"{self.cfg.caduceus_base}{suffix}",
            dict(headers or {}),
            body,
            self.cfg.timeout_seconds,
        )

    def health(self) -> dict[str, Any]:
        result = self._request("GET", "/health")
        if result.status != 200:
            raise CaduceusBoundaryError(f"caduceus_health_http_{result.status}")
        body = _json_object(result, boundary="health")
        if (
            body.get("ok") is not True
            or body.get("terminus") is not True
            or body.get("service_auth") != "required"
            or body.get("instance_id") != self.cfg.caduceus_instance_id
        ):
            raise CaduceusBoundaryError("caduceus_health_identity_mismatch")
        chain = body.get("chain")
        if not isinstance(chain, dict) or chain.get("ok") is not True:
            raise CaduceusBoundaryError("caduceus_chain_not_verified")
        return body

    def _challenge(self) -> str:
        nonce = _b64url(secrets.token_bytes(32))
        result = self._request("GET", f"/auth/challenge?nonce={nonce}")
        if result.status != 200:
            raise CaduceusBoundaryError(f"challenge_http_{result.status}")
        data = _json_object(result, boundary="challenge")
        if (
            data.get("instance_id") != self.cfg.caduceus_instance_id
            or data.get("nonce") != nonce
            or data.get("algorithm") != "hmac-sha256"
            or not isinstance(data.get("proof"), str)
        ):
            raise CaduceusBoundaryError("challenge_identity_mismatch")
        expected = _b64url(
            hmac.new(
                self.token.encode("utf-8"),
                _service_auth_message(self.cfg.caduceus_instance_id, nonce),
                hashlib.sha256,
            ).digest()
        )
        if not hmac.compare_digest(data["proof"], expected):
            raise CaduceusBoundaryError("challenge_proof_mismatch")
        return nonce

    def call(
        self,
        *,
        messages: Sequence[Mapping[str, Any]],
        sources: Sequence[SourceProvenance],
        workspace_identity: str,
        lane: Optional[str] = None,
        request_id: Optional[str] = None,
    ) -> CaduceusResult:
        selected_lane = lane or self.cfg.lane
        if selected_lane not in ALLOWED_LANES:
            raise CaduceusBoundaryError("lane_unsupported")
        final_messages = [dict(m) for m in messages]
        if not final_messages:
            raise CaduceusBoundaryError("messages_missing")
        # The frozen P2 contract accepts messages only. Refuse, never silently
        # discard, any non-message provider body at the caller seam.
        req_id = request_id or str(uuid.uuid4())
        fragments, origins = _source_fragments(req_id, final_messages, sources)
        ide_instance_id = f"omnis-wing-{uuid.uuid4()}"
        workspace_digest = workspace_policy_digest(workspace_identity)

        before = self.health()
        before_chain = before.get("chain") or {}
        before_count = int(before_chain.get("count") or 0)
        nonce = self._challenge()

        core: dict[str, Any] = {
            "request_id": req_id,
            "lane": selected_lane,
            "model_id": selected_lane,
            "messages": final_messages,
            "stream": False,
            "context_origin_classification": origins,
        }
        registration = {
            "ide_instance_id": ide_instance_id,
            "request_id": req_id,
            "nonce": nonce,
            "payload_core_sha256": _sha(_canonical_bytes(core)),
            "workspace_policy_digest": workspace_digest,
            "origin_classification": origins,
            "fragments": fragments,
        }
        reg_result = self._request(
            "POST",
            "/v1/omnis/context",
            headers={"content-type": "application/json", "x-caduceus-token": self.token},
            body=_wire_bytes(registration),
        )
        if reg_result.status != 200:
            raise CaduceusBoundaryError(f"context_registration_http_{reg_result.status}")
        registered = _json_object(reg_result, boundary="context_registration")
        handle = registered.get("handle")
        manifest_digest = registered.get("manifest_digest")
        if not isinstance(handle, str) or not handle or not isinstance(manifest_digest, str) or len(manifest_digest) != 64:
            raise CaduceusBoundaryError("context_registration_shape_invalid")

        body_obj = {
            **core,
            "context_handle": handle,
            "context_manifest_digest": manifest_digest,
        }
        # Match IDE field order: server-issued fields precede optional origins.
        body_obj = {
            "request_id": req_id,
            "lane": selected_lane,
            "model_id": selected_lane,
            "messages": final_messages,
            "stream": False,
            "context_handle": handle,
            "context_manifest_digest": manifest_digest,
            "context_origin_classification": origins,
        }
        wire = _wire_bytes(body_obj)
        body_digest = _sha(wire)
        binding = _b64url(
            hmac.new(
                self.token.encode("utf-8"),
                _request_binding_bytes(
                    origin=self.cfg.caduceus_base,
                    instance_id=self.cfg.caduceus_instance_id,
                    nonce=nonce,
                    request_id=req_id,
                    lane=selected_lane,
                    body_digest=body_digest,
                ),
                hashlib.sha256,
            ).digest()
        )
        headers = {
            "content-type": "application/json",
            "x-caduceus-token": self.token,
            "x-caduceus-origin": self.cfg.caduceus_base,
            "x-caduceus-challenge-nonce": nonce,
            "x-caduceus-request-id": req_id,
            "x-caduceus-lane": selected_lane,
            "x-caduceus-model-id": selected_lane,
            "x-caduceus-body-sha256": body_digest,
            "x-caduceus-request-binding": binding,
            "x-caduceus-ide-instance": ide_instance_id,
            "x-caduceus-workspace-digest": workspace_digest,
        }
        self.calls += 1
        self.last_wire_body = wire
        result = self._request("POST", "/v1/omnis/chat", headers=headers, body=wire)
        delivery = str(result.headers.get("x-caduceus-delivery-mode") or "LOCAL_ONLY")
        receipt = str(result.headers.get("x-caduceus-receipt") or "")
        terminal = str(result.headers.get("x-caduceus-terminal") or "")
        if result.status != 200:
            error = _json_object(result, boundary="chat_refusal").get("error")
            reason = "caduceus_refused"
            if isinstance(error, dict) and isinstance(error.get("type"), str):
                reason = error["type"]
            # A signed terminal/receipt on an HTTP refusal may be a response
            # gate refusal after the provider ran. Never flatten that into a
            # before-send zero-call claim.
            provider_calls = (
                1
                if delivery in ("RAW", "TRANSFORMED")
                and receipt
                and terminal
                and "COMPLETED" in terminal
                else 0
            )
            raise CaduceusBoundaryError(reason, provider_calls=provider_calls, mode=delivery)
        if delivery not in DELIVERY_MODE or delivery == "LOCAL_ONLY":
            raise CaduceusOutcomeUnknown("success_without_valid_delivery_mode", provider_may_have_run=True)
        expected_terminal = f"{delivery}_COMPLETED"
        if terminal != expected_terminal or not receipt:
            raise CaduceusOutcomeUnknown("terminal_or_receipt_missing", provider_may_have_run=True)

        data = _json_object(result, boundary="chat")
        choices = data.get("choices")
        text = None
        if isinstance(choices, list) and choices and isinstance(choices[0], dict):
            message = choices[0].get("message")
            if isinstance(message, dict):
                text = message.get("content")
        if not isinstance(text, str) or not text.strip():
            raise CaduceusOutcomeUnknown("answer_shape_invalid", provider_may_have_run=True)

        after = self.health()
        after_chain = after.get("chain") or {}
        after_count = int(after_chain.get("count") or 0)
        chain_head = str(after_chain.get("head") or "")
        if after_chain.get("ok") is not True or after_count != before_count + 2 or len(chain_head) != 64:
            raise CaduceusOutcomeUnknown("caduceus_terminal_chain_not_verified", provider_may_have_run=True)

        public = {
            "policy_id": REAL_WORK_POLICY_ID,
            "request_id": req_id,
            "delivery_mode": delivery,
            "terminal": terminal,
            "receipt": receipt,
            "body_digest": body_digest,
            "answer_digest": _sha(text.encode("utf-8")),
            "chain_head": chain_head,
            "chain_count": after_count,
            "origin_classification": origins,
            "target": {
                "provider": self.cfg.provider,
                "scheme": self.cfg.scheme,
                "hostname": self.cfg.hostname,
                "port": self.cfg.port,
                "path": self.cfg.path,
                "model": self.cfg.model,
                "residency": self.cfg.residency,
                "api_shape": self.cfg.api_shape,
            },
        }
        return CaduceusResult(
            response=_namespace(data),
            request_id=req_id,
            delivery_mode=delivery,
            terminal=terminal,
            receipt=receipt,
            chain_head=chain_head,
            chain_count=after_count,
            body_digest=body_digest,
            answer_digest=_sha(text.encode("utf-8")),
            provider_calls=1,
            public_evidence=public,
        )
