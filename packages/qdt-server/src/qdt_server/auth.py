"""The command token (ADR 0074, 0082): commands from another computer need a bearer token from this
server's token file; from this computer (loopback) nothing changes.

The token file is plain text: one token per line, optionally followed by whitespace and a label (the
desk or person it was given to); blank lines and `#` comments are ignored. A token is revoked by
deleting its line, and the file is read on every command, so a revocation needs no restart. A missing
file means every command from elsewhere is refused. `python -m qdt_server --add-token <label>` appends a
fresh token and prints it once.
"""

import hmac
import ipaddress
import secrets
from pathlib import Path

from fastapi import HTTPException, Request

SAFE_METHODS = frozenset({"GET", "HEAD", "OPTIONS"})
"""Reads, and the browser's CORS preflight: never challenged (ADR 0074: reads need only the network)."""


def is_loopback(host: str) -> bool:
    """True for 127.0.0.0/8, ::1 and an IPv4-mapped loopback; False for anything that is not an IP
    address, so an unparsable peer is treated as another computer (fail closed)."""
    try:
        ip = ipaddress.ip_address(host)
    except ValueError:
        return False
    mapped = getattr(ip, "ipv4_mapped", None)
    return ip.is_loopback or (mapped is not None and mapped.is_loopback)


def read_tokens(path: Path) -> dict[str, str]:
    """The tokens in `path` with their labels (empty when the file is missing)."""
    tokens: dict[str, str] = {}
    if not path.exists():
        return tokens
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        token, _, label = line.partition(" ")
        tokens[token] = label.strip()
    return tokens


def new_token(path: Path, label: str) -> str:
    """Append a fresh token labelled `label` to `path` (created if needed, readable by the owner only
    where the OS honours modes) and return it; the caller prints it once, it is never shown again."""
    token = secrets.token_urlsafe(32)
    path.parent.mkdir(parents=True, exist_ok=True)
    existing = path.read_text(encoding="utf-8") if path.exists() else ""
    sep = "" if not existing or existing.endswith("\n") else "\n"
    with path.open("a", encoding="utf-8") as f:
        f.write(f"{sep}{token} {' '.join(label.split())}\n")
    try:
        path.chmod(0o600)
    except OSError:  # a filesystem without modes
        pass
    return token


def accepted(path: Path, presented: str) -> bool:
    """True when `presented` is one of the tokens in `path`, compared in constant time."""
    return any(hmac.compare_digest(presented, t) for t in read_tokens(path))


def command_token(path: Path):
    """A FastAPI dependency for the stand router: a command (any method that is not a read) from a
    peer that is not loopback must carry `Authorization: Bearer <token>` with a token from `path`."""

    def check(request: Request) -> None:
        if request.method in SAFE_METHODS:
            return
        if request.client is not None and is_loopback(request.client.host):
            return
        scheme, _, token = request.headers.get("authorization", "").partition(" ")
        if scheme.lower() != "bearer" or not token.strip():
            raise HTTPException(
                401,
                "commands from another computer need a token: send 'Authorization: Bearer <token>' "
                "with a token from this server's token file (ADR 0074)",
                headers={"WWW-Authenticate": "Bearer"},
            )
        if not accepted(path, token.strip()):
            raise HTTPException(
                401,
                "token not accepted: it is not in this server's token file, or its line was removed",
                headers={"WWW-Authenticate": 'Bearer error="invalid_token"'},
            )

    return check
