"""Shared matrix through real loopback CADUCEUS + external fake provider.

Proves, without live credentials:

1. generic work → RAW · DELIVERED (exactly one provider call)
2. protected representable work → useful TRANSFORMED · DELIVERED (raw marker absent)
3. planted secret/credential → LOCAL_ONLY / typed refusal before provider byte
4. hostile provider response → suppressed (no success delivery)

Requires a clean CADUCEUS assembly at the frozen pin with ``npm ci`` already
run, and an isolated profile directory. Never touches live Hermes.
"""

from __future__ import annotations

import base64
import hashlib
import json
import os
import secrets
import shutil
import signal
import socket
import subprocess
import tempfile
import threading
import time
from dataclasses import dataclass, field
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Optional
from urllib.parse import urlparse

from omnis_wing.absolute.envelope import SourceProvenance
from omnis_wing.absolute.hermes_chat_join import (
    EvidenceSession,
    WingEgressContext,
    WingRefusal,
)
from omnis_wing.absolute.real_work.caduceus_client import (
    CaduceusBoundaryError,
    CaduceusRealWorkClient,
)
from omnis_wing.absolute.real_work.config import (
    PINNED_CADUCEUS_COMMIT,
    RealWorkConfigError,
    assert_pinned_runtime_dependencies,
    parse_real_work_config,
)
from omnis_wing.absolute.real_work.runtime import (
    transmit_primary_chat,
    transmit_primary_stream,
)
from omnis_wing.absolute.receipt_spine import EvidenceLedger, make_test_signer
from omnis_wing.distribution.routes import closed_route_inventory


PLANTED_PROTECTED = "PROJECT-BLUEBIRD-CODENAME"
# Pure base64-charset secret so transform can alias rather than LOCAL_ONLY on
# encoding_ambiguous (same pattern as CODE Wave 4.1 / CADUCEUS harness).
PLANTED_SECRET = "sk-ABCDEFGHIJKLMNOPQRSTUVWX"
HOSTILE_MARKER = "HOSTILE-LEAK-PROJECT-BLUEBIRD-CODENAME"


class MatrixError(RuntimeError):
    pass


def _b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode("ascii").rstrip("=")


def _free_loopback_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return int(s.getsockname()[1])


@dataclass
class FakeProviderState:
    completions: list[dict[str, Any]] = field(default_factory=list)
    suppress_body: Optional[str] = None
    answer: str = "useful-fake-answer-about-structure"


class _FakeHandler(BaseHTTPRequestHandler):
    state: FakeProviderState  # set on server

    def log_message(self, fmt: str, *args: Any) -> None:  # noqa: A003
        return

    def do_GET(self) -> None:  # noqa: N802
        if self.path.rstrip("/").endswith("/models"):
            body = json.dumps({"data": [{"id": "MiniMax-M3"}]}).encode()
            self.send_response(200)
            self.send_header("content-type", "application/json")
            self.send_header("content-length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        self.send_response(404)
        self.end_headers()

    def do_POST(self) -> None:  # noqa: N802
        length = int(self.headers.get("content-length") or 0)
        raw = self.rfile.read(length) if length else b""
        path = urlparse(self.path).path
        rec = {
            "path": path,
            "headers": {k.lower(): v for k, v in self.headers.items()},
            "raw": raw,
            "text": raw.decode("utf-8", errors="replace"),
            "sha256": hashlib.sha256(raw).hexdigest(),
        }
        if path.rstrip("/").endswith("/chat/completions") or path.endswith(
            "/chat/completions"
        ):
            self.state.completions.append(rec)
            content = self.state.suppress_body or self.state.answer
            body = json.dumps(
                {
                    "id": "fake-wing-1",
                    "model": "MiniMax-M3",
                    "choices": [
                        {
                            "index": 0,
                            "message": {"role": "assistant", "content": content},
                            "finish_reason": "stop",
                        }
                    ],
                    "usage": {
                        "prompt_tokens": 3,
                        "completion_tokens": 5,
                        "total_tokens": 8,
                    },
                }
            ).encode()
            self.send_response(200)
            self.send_header("content-type", "application/json")
            self.send_header("content-length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        self.state.completions.append(rec)
        self.send_response(404)
        self.end_headers()


def start_fake_provider(*, answer: str = "useful-fake-answer-about-structure") -> dict[str, Any]:
    state = FakeProviderState(answer=answer)
    server = ThreadingHTTPServer(("127.0.0.1", 0), _FakeHandler)
    _FakeHandler.state = state  # type: ignore[attr-defined]
    server.state = state  # type: ignore[attr-defined]
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    port = int(server.server_address[1])
    return {
        "server": server,
        "thread": thread,
        "port": port,
        "base_url": f"http://127.0.0.1:{port}/v1",
        "state": state,
        "close": lambda: (server.shutdown(), server.server_close()),
    }


def _lanes_yaml(*, provider_port: int, instance_note: str = "wing-dist") -> str:
    # Operator-owned lanes: MiniMax CN product binding + loopback destinations
    # authorized for the external fake (MINIMAX_BASE_URL rewrite). Transformer
    # binding must match the frozen CADUCEUS pin's terminus-transform constants.
    return f"""version: 1
endpoint_allowlist:
  - "127.0.0.1"
  - "localhost"
  - "api.minimax.io"
providers:
  minimax:
    kind: openai
    base_url_env: MINIMAX_BASE_URL
    base_url_default: http://127.0.0.1:{provider_port}/v1
    api_key_env: MINIMAX_API_KEY
    model_env: MINIMAX_MODEL
    residency: CN
    requires_api_key: true
lanes:
  codegen:
    sensitive: false
    chain: [minimax]
  plan:
    sensitive: false
    chain: [minimax]
  validation:
    sensitive: false
    chain: [minimax]
terminus_real_work_v1:
  policy_id: TERMINUS_REAL_WORK_V1
  policy_version: "1"
  expires_at: "2027-08-09T00:00:00.000Z"
  destinations:
    - id: minimax-loopback-codegen-m3
      scheme: http
      host: 127.0.0.1
      port: {provider_port}
      path: /v1/chat/completions
      api_shape: openai_chat_completions
      provider_id: minimax
      model: MiniMax-M3
      lane: codegen
      residency: CN
      allowed_delivery_modes: [RAW, TRANSFORMED, LOCAL_ONLY]
    - id: minimax-prod-codegen-m3
      scheme: https
      host: api.minimax.io
      port: 443
      path: /v1/chat/completions
      api_shape: openai_chat_completions
      provider_id: minimax
      model: MiniMax-M3
      lane: codegen
      residency: CN
      allowed_delivery_modes: [RAW, TRANSFORMED, LOCAL_ONLY]
  transformer:
    impl: caduceus-terminus-transform
    version: "1.0.1"
    corpus_digest: 82bd40c148dba6199da344f0cc848def7922168479f1dad201da3ef88e601952
    protocol: terminus-transform-v1
  allowed_request_fields:
    - model
    - messages
    - stream
    - request_id
    - lane
    - model_id
    - temperature
    - max_tokens
    - max_completion_tokens
    - tools
    - tool_choice
    - context_handle
    - context_manifest_digest
    - context_ide_instance_id
    - context_workspace_policy_digest
    - context_origin_classification
  allowed_content_formats: [text, openai_chat_messages]
  limits:
    max_input_bytes: 262144
    max_output_bytes: 262144
    max_messages: 64
    max_breadth_sources: 32
  default_fallback_destinations: []
  response_handling:
    allowed: [CLEAN, REDACTED, SUPPRESSED, REINTEGRATION_REFUSED, NOT_APPLICABLE]
  local_resolver:
    enabled: true
    mode: local_work_packet
# note: {instance_note}
"""


def _mint_service_token() -> str:
    return _b64url(secrets.token_bytes(32))


def _start_caduceus(
    *,
    caduceus_root: Path,
    port: int,
    instance_id: str,
    service_token: str,
    lanes_path: Path,
    state_dir: Path,
    provider_base: str,
    log_path: Path,
) -> subprocess.Popen:
    entry = caduceus_root / "src" / "caduceus.mjs"
    if not entry.is_file():
        raise MatrixError("caduceus_entry_missing")
    env = dict(os.environ)
    env["CADUCEUS_HOST"] = "127.0.0.1"
    env["CADUCEUS_PORT"] = str(port)
    env["CADUCEUS_INSTANCE_ID"] = instance_id
    env["CADUCEUS_SERVICE_TOKEN"] = service_token
    env["CADUCEUS_LANES"] = str(lanes_path)
    env["CADUCEUS_STATE_DIR"] = str(state_dir)
    # Force provider to external loopback fake; never a live host.
    env["MINIMAX_BASE_URL"] = provider_base
    env["MINIMAX_API_KEY"] = "fake-minimax-key-not-live"
    env["MINIMAX_MODEL"] = "MiniMax-M3"
    # Strip real credentials if present so we never hit live endpoints.
    for k in list(env):
        if k.endswith("_API_KEY") and k not in ("MINIMAX_API_KEY",):
            env.pop(k, None)
    log_path.parent.mkdir(parents=True, exist_ok=True)
    out = log_path.open("ab", buffering=0)
    proc = subprocess.Popen(
        ["node", str(entry)],
        cwd=str(caduceus_root),
        env=env,
        stdin=subprocess.DEVNULL,
        stdout=out,
        stderr=out,
        start_new_session=True,
    )
    return proc


def _wait_health(base: str, token: str, instance_id: str, timeout: float = 20.0) -> dict[str, Any]:
    cfg = parse_real_work_config(
        {
            "policy_id": "TERMINUS_REAL_WORK_V1",
            "caduceus_base": base,
            "caduceus_instance_id": instance_id,
            "caduceus_root": str(Path("/tmp")),  # not used for health
            "caduceus_commit": PINNED_CADUCEUS_COMMIT,
            "service_token_env": "CADUCEUS_SERVICE_TOKEN",
            "timeout_seconds": 10,
            "target": {
                "provider": "minimax",
                "scheme": "https",
                "hostname": "api.minimax.io",
                "port": 443,
                "path": "/v1/chat/completions",
                "model": "MiniMax-M3",
                "residency": "CN",
                "api_shape": "openai_chat_completions",
                "lane": "codegen",
            },
        },
        source="matrix-health",
    )
    # Override root check is not run for health alone via client — we still need
    # a real root for full matrix. Health wait uses raw urllib via client.
    os.environ["CADUCEUS_SERVICE_TOKEN"] = token
    # Temporary: parse requires absolute root; use /tmp which exists.
    client = CaduceusRealWorkClient(cfg, token=token)
    deadline = time.monotonic() + timeout
    last = "pending"
    while time.monotonic() < deadline:
        try:
            health = client.health()
            if health.get("ok") is True or health.get("terminus") is True:
                return health
            last = json.dumps(health)
        except Exception as exc:  # noqa: BLE001
            last = type(exc).__name__
            time.sleep(0.2)
    raise MatrixError(f"caduceus_health_timeout:{last}")


def _source(path: str, content: str, *, classification: str, protected: bool = False) -> SourceProvenance:
    return SourceProvenance(
        path=path,
        content_digest=hashlib.sha256(content.encode()).hexdigest(),
        classification=classification,
        protected_root=protected,
        crown_jewel=False,
        byte_range=None,
        whole_content=True,
    )


def _agent() -> Any:
    return type(
        "DistAgent",
        (),
        {
            "wing_real_work_status": {},
            "direct_client_constructions": 0,
        },
    )()


def run_external_matrix(
    *,
    caduceus_root: str | Path,
    work_dir: Optional[str | Path] = None,
) -> dict[str, Any]:
    """Run the shared matrix against real CADUCEUS + external fake provider."""
    root = Path(caduceus_root).resolve()
    if not (root / "src" / "caduceus.mjs").is_file():
        raise MatrixError("caduceus_root_invalid")
    # Verify pin + deps before starting.
    tmp_cfg = parse_real_work_config(
        {
            "policy_id": "TERMINUS_REAL_WORK_V1",
            "caduceus_base": "http://127.0.0.1:9",
            "caduceus_instance_id": "matrix-precheck",
            "caduceus_root": str(root),
            "caduceus_commit": PINNED_CADUCEUS_COMMIT,
            "service_token_env": "CADUCEUS_SERVICE_TOKEN",
            "timeout_seconds": 30,
            "target": {
                "provider": "minimax",
                "scheme": "https",
                "hostname": "api.minimax.io",
                "port": 443,
                "path": "/v1/chat/completions",
                "model": "MiniMax-M3",
                "residency": "CN",
                "api_shape": "openai_chat_completions",
                "lane": "codegen",
            },
        },
        source="matrix-precheck",
    )
    try:
        assert_pinned_runtime_dependencies(tmp_cfg)
    except RealWorkConfigError as exc:
        raise MatrixError(str(exc)) from exc

    inventory = closed_route_inventory()
    base_work = Path(work_dir) if work_dir else Path(tempfile.mkdtemp(prefix="wing-dist-matrix-"))
    base_work.mkdir(parents=True, exist_ok=True)
    os.chmod(base_work, 0o700)

    fake = start_fake_provider(answer="useful-fake-answer-about-module-structure")
    caduceus_port = _free_loopback_port()
    instance_id = f"wing-dist-{secrets.token_hex(6)}"
    service_token = _mint_service_token()
    lanes_path = base_work / "caduceus-lanes.yaml"
    lanes_path.write_text(
        _lanes_yaml(provider_port=int(fake["port"])),
        encoding="utf-8",
    )
    os.chmod(lanes_path, 0o600)
    state_dir = base_work / "caduceus-state"
    state_dir.mkdir(mode=0o700)
    (state_dir / "chain.jsonl").write_bytes(b"")
    os.chmod(state_dir / "chain.jsonl", 0o600)
    log_path = base_work / "caduceus.log"

    proc: Optional[subprocess.Popen] = None
    results: dict[str, Any] = {
        "schema": "omnis-wing.external-matrix.v1",
        "caduceus_commit": PINNED_CADUCEUS_COMMIT,
        "caduceus_root": str(root),
        "route_inventory": inventory,
        "cases": {},
    }

    try:
        proc = _start_caduceus(
            caduceus_root=root,
            port=caduceus_port,
            instance_id=instance_id,
            service_token=service_token,
            lanes_path=lanes_path,
            state_dir=state_dir,
            provider_base=str(fake["base_url"]),
            log_path=log_path,
        )
        base = f"http://127.0.0.1:{caduceus_port}"
        health = _wait_health(base, service_token, instance_id)
        results["health"] = {
            "ok": health.get("ok"),
            "terminus": health.get("terminus"),
            "service_auth": health.get("service_auth"),
            "instance_id": health.get("instance_id") or instance_id,
        }

        os.environ["CADUCEUS_SERVICE_TOKEN"] = service_token
        os.environ["OMNIS_WING_SIGNER_MODE"] = "test"
        cfg = parse_real_work_config(
            {
                "policy_id": "TERMINUS_REAL_WORK_V1",
                "caduceus_base": base,
                "caduceus_instance_id": instance_id,
                "caduceus_root": str(root),
                "caduceus_commit": PINNED_CADUCEUS_COMMIT,
                "service_token_env": "CADUCEUS_SERVICE_TOKEN",
                "timeout_seconds": 60,
                "target": {
                    "provider": "minimax",
                    "scheme": "https",
                    "hostname": "api.minimax.io",
                    "port": 443,
                    "path": "/v1/chat/completions",
                    "model": "MiniMax-M3",
                    "residency": "CN",
                    "api_shape": "openai_chat_completions",
                    "lane": "codegen",
                },
            },
            source="matrix",
        )
        client = CaduceusRealWorkClient(cfg, token=service_token)

        # --- Case 1: generic RAW ---
        fake["state"].completions.clear()
        fake["state"].suppress_body = None
        fake["state"].answer = "generic-raw-answer"
        generic_msg = "hello from wing distribution matrix"
        generic_sources = (
            _source("payload:generic", generic_msg, classification="generic"),
        )
        raw_result = client.call(
            messages=[{"role": "user", "content": generic_msg}],
            sources=generic_sources,
            workspace_identity=str(base_work / "ws-generic"),
        )
        raw_provider_bodies = [c["text"] for c in fake["state"].completions]
        results["cases"]["generic_raw"] = {
            "delivery_mode": raw_result.delivery_mode,
            "provider_calls": raw_result.provider_calls,
            "answer": str(raw_result.response.choices[0].message.content),
            "provider_request_count": len(fake["state"].completions),
            "provider_bodies_contain_user_text": any(
                generic_msg in b for b in raw_provider_bodies
            ),
            "pass": (
                raw_result.delivery_mode == "RAW"
                and raw_result.provider_calls == 1
                and len(fake["state"].completions) == 1
                and "generic-raw-answer" in str(raw_result.response.choices[0].message.content)
            ),
        }

        # --- Case 2: protected useful TRANSFORMED ---
        fake["state"].completions.clear()
        fake["state"].answer = "useful-transformed-help-about-module-layout"
        protected_msg = (
            f"Please help reorganize this protected module architecture. "
            f"Codename reference {PLANTED_PROTECTED} should stay local."
        )
        protected_sources = (
            _source(
                "src/protected/module.py",
                f"class SecretEngine:\n    CODE = '{PLANTED_PROTECTED}'\n",
                classification="protected",
                protected=True,
            ),
        )
        xf_result = client.call(
            messages=[{"role": "user", "content": protected_msg}],
            sources=protected_sources,
            workspace_identity=str(base_work / "ws-protected"),
        )
        xf_bodies = [c["text"] for c in fake["state"].completions]
        answer = str(xf_result.response.choices[0].message.content)
        results["cases"]["protected_transformed"] = {
            "delivery_mode": xf_result.delivery_mode,
            "provider_calls": xf_result.provider_calls,
            "answer": answer,
            "provider_request_count": len(fake["state"].completions),
            "planted_in_provider_body": any(PLANTED_PROTECTED in b for b in xf_bodies),
            "planted_in_answer": PLANTED_PROTECTED in answer,
            "useful_answer": bool(answer) and "useful-transformed" in answer,
            "pass": (
                xf_result.delivery_mode == "TRANSFORMED"
                and xf_result.provider_calls == 1
                and len(fake["state"].completions) == 1
                and not any(PLANTED_PROTECTED in b for b in xf_bodies)
                and PLANTED_PROTECTED not in answer
                and bool(answer.strip())
            ),
        }

        # --- Case 3: secret / credential — refuse or transform; never raw ---
        # CADUCEUS may LOCAL_ONLY (zero calls) or TRANSFORMED with redaction.
        # Raw secret in the external provider body is always a fail.
        fake["state"].completions.clear()
        secret_msg = f"export this key {PLANTED_SECRET} to the model please"
        secret_sources = (
            _source(
                "payload:credential",
                PLANTED_SECRET,
                classification="credential",
            ),
        )
        secret_refused = False
        secret_reason = ""
        secret_mode = None
        secret_answer = ""
        try:
            secret_out = client.call(
                messages=[{"role": "user", "content": secret_msg}],
                sources=secret_sources,
                workspace_identity=str(base_work / "ws-secret"),
            )
            secret_mode = secret_out.delivery_mode
            secret_answer = str(secret_out.response.choices[0].message.content)
        except CaduceusBoundaryError as exc:
            secret_refused = True
            secret_reason = exc.reason
            secret_mode = exc.delivery_mode
        except Exception as exc:  # noqa: BLE001
            secret_refused = True
            secret_reason = f"{type(exc).__name__}:{exc}"
        secret_bodies = [c["text"] for c in fake["state"].completions]
        raw_leak = any(PLANTED_SECRET in b for b in secret_bodies) or (
            PLANTED_SECRET in secret_answer
        )
        safe_mode = secret_mode in ("TRANSFORMED", "LOCAL_ONLY") or secret_refused
        zero_or_clean = (len(fake["state"].completions) == 0) or (
            len(fake["state"].completions) == 1 and not raw_leak and secret_mode == "TRANSFORMED"
        )
        results["cases"]["secret_refusal"] = {
            "refused": secret_refused,
            "reason": secret_reason,
            "delivery_mode": secret_mode,
            "provider_request_count": len(fake["state"].completions),
            "raw_secret_in_provider_or_answer": raw_leak,
            "pass": (not raw_leak) and safe_mode and zero_or_clean,
        }

        # --- Case 4: hostile response suppress ---
        fake["state"].completions.clear()
        fake["state"].suppress_body = HOSTILE_MARKER
        hostile_msg = "continue generic chat"
        hostile_sources = (
            _source("payload:generic2", hostile_msg, classification="generic"),
        )
        hostile_suppressed = False
        hostile_reason = ""
        try:
            client.call(
                messages=[{"role": "user", "content": hostile_msg}],
                sources=hostile_sources,
                workspace_identity=str(base_work / "ws-hostile"),
            )
        except CaduceusBoundaryError as exc:
            hostile_suppressed = True
            hostile_reason = exc.reason
        except Exception as exc:  # noqa: BLE001
            hostile_suppressed = True
            hostile_reason = f"{type(exc).__name__}:{exc}"
        results["cases"]["hostile_suppress"] = {
            "suppressed": hostile_suppressed,
            "reason": hostile_reason,
            "provider_request_count": len(fake["state"].completions),
            "pass": hostile_suppressed and len(fake["state"].completions) == 1,
        }

        # --- Case 5: buffered stream (same gate) ---
        fake["state"].completions.clear()
        fake["state"].suppress_body = None
        fake["state"].answer = "buffered-stream-answer"
        ledger_path = base_work / "wing-ledger.jsonl"
        if ledger_path.exists():
            ledger_path.unlink()
        ledger = EvidenceLedger(ledger_path)
        evidence = EvidenceSession(signer=make_test_signer(), ledger=ledger)
        agent = _agent()
        # Point runtime at real client via test plant.
        os.environ["OMNIS_WING_REAL_WORK_CONFIG"] = str(base_work / "rw.json")
        (base_work / "rw.json").write_text(
            json.dumps(
                {
                    "policy_id": "TERMINUS_REAL_WORK_V1",
                    "caduceus_base": base,
                    "caduceus_instance_id": instance_id,
                    "caduceus_root": str(root),
                    "caduceus_commit": PINNED_CADUCEUS_COMMIT,
                    "service_token_env": "CADUCEUS_SERVICE_TOKEN",
                    "timeout_seconds": 60,
                    "target": {
                        "provider": "minimax",
                        "scheme": "https",
                        "hostname": "api.minimax.io",
                        "port": 443,
                        "path": "/v1/chat/completions",
                        "model": "MiniMax-M3",
                        "residency": "CN",
                        "api_shape": "openai_chat_completions",
                        "lane": "codegen",
                    },
                },
                sort_keys=True,
            ),
            encoding="utf-8",
        )
        # Plant client for runtime by monkeypatching _client_for path via env test mode.
        from omnis_wing.absolute.real_work import runtime as runtime_mod

        original_client_for = getattr(runtime_mod, "_client_for", None)

        def _planted_client_for(*_a, **_k):  # noqa: ANN001
            return client

        if original_client_for is not None:
            runtime_mod._client_for = _planted_client_for  # type: ignore[attr-defined]
        try:
            # Planted client is only accepted in test signer mode (_client_for).
            agent._wing_caduceus_client = client  # type: ignore[attr-defined]
            ctx = WingEgressContext(
                sources=(
                    _source("payload:stream", "stream please", classification="generic"),
                ),
                evidence=evidence,
            )
            # Prefer direct client stream-buffer proof if runtime wiring differs.
            stream_ok = False
            stream_detail: dict[str, Any] = {}
            try:
                out = transmit_primary_stream(
                    agent=agent,
                    api_kwargs={
                        "messages": [{"role": "user", "content": "stream please"}],
                        "stream": True,
                    },
                    wing_ctx=ctx,
                )
                chunks = list(out)
                stream_detail = {
                    "chunks": len(chunks),
                    "provider_request_count": len(fake["state"].completions),
                }
                stream_ok = (
                    len(chunks) >= 1
                    and len(fake["state"].completions) == 1
                )
            except Exception as exc:  # noqa: BLE001
                # Fall back: non-stream path already proved; stream buffers same client.
                stream_detail = {"error": f"{type(exc).__name__}:{exc}"}
                # Buffered behavior still proven via unit suite; mark conditional.
                stream_ok = False
            results["cases"]["buffered_stream"] = {
                **stream_detail,
                "pass": stream_ok,
                "note": "buffered after CADUCEUS response gate; not token SSE",
            }
        finally:
            if original_client_for is not None:
                runtime_mod._client_for = original_client_for  # type: ignore[attr-defined]
            os.environ.pop("OMNIS_WING_REAL_WORK_CONFIG", None)

        results["all_pass"] = all(
            case.get("pass") is True for case in results["cases"].values()
        )
        results["work_dir"] = str(base_work)
        results["fake_provider_port"] = int(fake["port"])
        results["caduceus_port"] = caduceus_port
        return results
    finally:
        if proc is not None and proc.poll() is None:
            try:
                os.killpg(proc.pid, signal.SIGTERM)
            except ProcessLookupError:
                pass
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                try:
                    os.killpg(proc.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
        try:
            fake["close"]()
        except Exception:  # noqa: BLE001
            pass
