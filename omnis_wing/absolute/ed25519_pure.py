
"""Pure-Python Ed25519 (hashlib only). Test/offline spine — not a production HSM.

Algorithm: RFC 8032 / SUPERCOP ref port. Public domain lineage.
"""
from __future__ import annotations

import hashlib
from typing import Tuple

b = 256
q = 2**255 - 19
l = 2**252 + 27742317777372353535851937790883648493


def H(m: bytes) -> bytes:
    return hashlib.sha512(m).digest()


def expmod(b_: int, e: int, m: int) -> int:
    if e == 0:
        return 1
    t = expmod(b_, e // 2, m) ** 2 % m
    if e & 1:
        t = (t * b_) % m
    return t


def inv(x: int) -> int:
    return expmod(x, q - 2, q)


d = -121665 * inv(121666) % q
I = expmod(2, (q - 1) // 4, q)


def xrecover(y: int) -> int:
    xx = (y * y - 1) * inv(d * y * y + 1)
    x = expmod(xx, (q + 3) // 8, q)
    if (x * x - xx) % q != 0:
        x = (x * I) % q
    if x % 2 != 0:
        x = q - x
    return x


By = 4 * inv(5)
Bx = xrecover(By)
B = (Bx % q, By % q)


def edwards(P, Q):
    x1, y1 = P
    x2, y2 = Q
    x3 = (x1 * y2 + x2 * y1) * inv(1 + d * x1 * x2 * y1 * y2)
    y3 = (y1 * y2 + x1 * x2) * inv(1 - d * x1 * x2 * y1 * y2)
    return (x3 % q, y3 % q)


def scalarmult(P, e: int):
    if e == 0:
        return (0, 1)
    Q = scalarmult(P, e // 2)
    Q = edwards(Q, Q)
    if e & 1:
        Q = edwards(Q, P)
    return Q


def encodeint(y: int) -> bytes:
    return y.to_bytes(32, "little")


def encodepoint(P) -> bytes:
    x, y = P
    bits = [(y >> i) & 1 for i in range(b - 1)] + [x & 1]
    out = bytearray(32)
    for i, bit in enumerate(bits):
        out[i // 8] |= bit << (i % 8)
    return bytes(out)


def bit(h: bytes, i: int) -> int:
    return (h[i // 8] >> (i % 8)) & 1


def publickey_from_seed(sk: bytes) -> bytes:
    assert len(sk) == 32
    h = H(sk)
    a = 2 ** (b - 2) + sum(2**i * bit(h, i) for i in range(3, b - 2))
    A = scalarmult(B, a)
    return encodepoint(A)


def sign(m: bytes, sk: bytes) -> bytes:
    assert len(sk) == 32
    h = H(sk)
    a = 2 ** (b - 2) + sum(2**i * bit(h, i) for i in range(3, b - 2))
    r = int.from_bytes(H(h[32:b] + m), "little")
    R = scalarmult(B, r)
    A = encodepoint(scalarmult(B, a))
    S = (r + int.from_bytes(H(encodepoint(R) + A + m), "little") * a) % l
    return encodepoint(R) + encodeint(S)


def isoncurve(P) -> bool:
    x, y = P
    return (-x * x + y * y - 1 - d * x * x * y * y) % q == 0


def decodeint(s: bytes) -> int:
    return int.from_bytes(s, "little")


def decodepoint(s: bytes):
    y = sum(2**i * bit(s, i) for i in range(0, b - 1))
    x = xrecover(y)
    if x & 1 != bit(s, b - 1):
        x = q - x
    P = (x, y)
    if not isoncurve(P):
        raise ValueError("point off curve")
    return P


def verify(m: bytes, sig: bytes, pk: bytes) -> bool:
    if len(sig) != 64 or len(pk) != 32:
        return False
    try:
        R = decodepoint(sig[:32])
        A = decodepoint(pk)
        S = decodeint(sig[32:])
        h = int.from_bytes(H(encodepoint(R) + pk + m), "little")
        return scalarmult(B, S) == edwards(R, scalarmult(A, h))
    except Exception:
        return False


def generate_keypair(seed: bytes | None = None) -> Tuple[bytes, bytes]:
    import os

    sk = seed if seed is not None else os.urandom(32)
    if len(sk) != 32:
        raise ValueError("seed must be 32 bytes")
    return sk, publickey_from_seed(sk)
