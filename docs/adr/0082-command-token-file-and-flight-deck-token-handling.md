# 0082 — The command token: a token file beside the registry root, checked per request on the stand router, loopback exempt; Flight Deck takes the token from its address and keeps it in the browser

**Status:** Accepted
**Date:** 2026-10-24
**Step:** 6c (goal 1, deliverable 5; implements ADR 0074's "must now": the token check with L0 tests for refusal and loopback exemption, Flight Deck sends the token)

## Context
ADR 0074 decided that a stand server bound to a non-loopback address refuses `POST`/`DELETE` without a
bearer token from a server-side token file, one token per desk or person, revocable by deleting its
line, with reads open to the network and nothing changed on loopback. Building it forced choices the
ADR left open: where the file lives and what it looks like, whether "bound off loopback" is a property
of the server or of each request, which routes count as commands, how a browser on another desk is
given the token and where it keeps it, and what happens when there is no file at all. The demo
deployment (session 29) runs Flight Deck and the stand server on the same laptop, so none of this was
exercised there; it matters as soon as a second desk drives a stand (deliverable 13, the lab PC).

## Decision
1. **The token file is `<root>/tokens`** by default (`--tokens` overrides), plain text: one token per
   line, optional whitespace and a label after it, blank lines and `#` comments ignored. It is read on
   every command, so deleting a line revokes without a restart. **A missing file refuses every command
   from elsewhere** (fail closed); the server logs how to make one. `python -m qdt_server --add-token
   "<label>"` appends a `secrets.token_urlsafe(32)` token, sets the file owner-only where the OS has
   modes, prints the token once and exits.
2. **The check is per request, by peer address**, not by the address the server bound: a dependency on
   the `stand` router (the router ADR 0081 made for everything that needs a stand) challenges any method
   other than `GET`/`HEAD`/`OPTIONS` whose peer is not loopback (127.0.0.0/8, `::1`, an IPv4-mapped
   loopback; a peer that is not an IP address counts as another computer). So a server bound to
   `0.0.0.0` still takes untokened commands from its own machine, as ADR 0074 asks, and the rule needs
   no knowledge of how the server was started.
3. **Commands are the stand router's writes.** Reads, `POST /stream/replay` (a read that happens to be
   a POST, ADR 0081) and the browser's CORS preflight are never challenged. A read server has no stand
   router and therefore no token; it has nothing to command.
4. **A refusal is a 401** with `WWW-Authenticate: Bearer` and a `detail` that says what to send. The
   CORS middleware stays outside the router with open origins, so the 401 reaches the browser with CORS
   headers and Flight Deck shows the server's sentence rather than a CORS error.
5. **Flight Deck takes the token from its address**, `?token=<token>` or `#token=<token>` (the fragment
   never leaves the browser), keeps it in `localStorage` under the API base it was given for, removes it
   from the address with `history.replaceState`, and sends it as `Authorization: Bearer` on every call;
   without one it sends nothing and a command from another desk shows the 401. Nothing in the UI asks
   for a token or reports whether one is held: the long address a desk is given carries it once.
6. **Tests speak from loopback** by giving `TestClient` the peer `("127.0.0.1", 50000)`; its default
   peer, `testclient`, is not an address and is treated as another computer. The token tests use an
   RFC 5737 documentation address as the other computer.

## Consequences
- Easier: one bad desk cannot drive a stand without a token, with no accounts, no sessions and no change
  to the single-machine workflow; revoking is deleting a line; the file is created by one command.
- Harder: a token in a URL is a secret in a URL. It is removed from the address on first load, but the
  address it arrived in may sit in a chat or an email; treat a token like a password and revoke it
  when in doubt. One shared browser profile holds one token per API base. A proxy in front of the
  server would make every peer look like the proxy: none is planned (ADR 0074 keeps the server on the
  measurement PC's network); if one arrives, the check must read the forwarded address and this ADR is
  amended.
- Must now: a runbook section for giving a desk its token when a stand server is first bound off
  loopback (the lab PC, deliverable 13); `R-4` on the bench (a command from another computer without a
  token is refused and changes nothing on the scope); the hub (ADR 0076) replaces these tokens for
  clients that go through it.

## Alternatives considered
- Decide by the bound address (`--host`), as ADR 0074's wording suggests — rejected: the server would
  need to know its own reachability, and a server on `0.0.0.0` would then challenge its own machine's
  Flight Deck; peer address is what the request carries.
- A middleware over every `POST`/`DELETE` — rejected: it would challenge replay on the read server, the
  one POST every viewer makes, and it is the stand router that ADR 0081 already made the boundary.
- Tokens in `Settings` or an environment variable — rejected: a file with a label per line is the
  revocation mechanism ADR 0074 asked for, and it is readable by the person who administers the stand.
- No check when the file is missing (open by default) — rejected: a stand server exposed to the lab
  subnet by a forgotten step would accept commands from every desk.
- A token prompt in Flight Deck — rejected for now: a desk is given one long address, as it already is
  for `?api=` and `?ws=`; a prompt adds UI that the hub (ADR 0076) will replace with a login.
- `sessionStorage` or memory only — rejected: the token would be asked for again at every reload; the
  address it came from would have to be kept, which is worse.
