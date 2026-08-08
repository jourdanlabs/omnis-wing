"""M3 transport binding — redirect attacks refuse before body/credential forward.

Authorization binds the actual destination tuple derived from client config.
A client that will automatically follow HTTP redirects can land bytes on a
different host than the one authorized. WING refuses **explicitly enabled**
redirect following before any provider call.

Note: bare httpx default ``max_redirects`` alone is NOT treated as evidence —
many SDKs ship that default without WING owning the socket. Explicit
``follow_redirects=True`` / ``allow_redirects=True`` / WING probe flags refuse.
Post-authorization hostname mutation is always refuse.
"""

from __future__ import annotations

from typing import Any, Optional, Tuple


def client_redirect_risk(client: Any) -> Optional[str]:
    """Return a refusal reason if *client* explicitly enables redirects."""
    if client is None:
        return None

    seen: set[int] = set()

    def walk(obj: Any, depth: int = 0) -> Optional[str]:
        if obj is None or depth > 4:
            return None
        oid = id(obj)
        if oid in seen:
            return None
        seen.add(oid)

        for attr in ("follow_redirects", "allow_redirects", "_wing_follow_redirects"):
            if hasattr(obj, attr):
                try:
                    val = getattr(obj, attr)
                except Exception:
                    val = None
                if val is True:
                    return f"redirect_enabled:{attr}=True"

        for nested_attr in (
            "_client",
            "http_client",
            "_http_client",
            "session",
            "_session",
        ):
            inner = getattr(obj, nested_attr, None)
            if inner is not None and inner is not obj:
                hit = walk(inner, depth + 1)
                if hit:
                    return hit
        return None

    return walk(client)


def assert_no_redirect_transport(client: Any) -> Tuple[bool, Optional[str]]:
    """(ok, reason). ok False → caller must REFUSE_DESTINATION, provider_calls=0."""
    reason = client_redirect_risk(client)
    if reason:
        return False, reason
    return True, None


def refuse_redirect_mutation(
    authorized_hostname: str,
    post_auth_hostname: str,
) -> Optional[str]:
    """Post-authorization hostname change is a redirect-class attack."""
    a = (authorized_hostname or "").strip().lower()
    b = (post_auth_hostname or "").strip().lower()
    if not a or not b:
        return "redirect_hostname_incomplete"
    if a != b:
        return f"redirect_hostname_mutation:{a}->{b}"
    return None
