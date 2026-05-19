<!-- omit from toc -->
# OAuth flow: MCP client ↔ Authsome MCP Proxy ↔ upstream IdP

In-depth walkthrough of the OAuth dance behind `authsome-mcp-proxy`.
The proxy supports two deployment modes with very different OAuth
choreographies; this document covers both, plus what each party stores
and where.

- [Deployment modes at a glance](#deployment-modes-at-a-glance)
- [MCP client compatibility matrix](#mcp-client-compatibility-matrix)
- [Web-connector (HTTP) mode](#web-connector-http-mode)
  - [The proxy's two hats](#the-proxys-two-hats)
  - [The two flows stitched together](#the-two-flows-stitched-together)
  - [Detailed step-by-step](#detailed-step-by-step)
  - [Where the client-side record lives (per client)](#where-the-client-side-record-lives-per-client)
  - [Reconciling with classical (non-proxied) OAuth intuitions](#reconciling-with-classical-non-proxied-oauth-intuitions)
  - [What persists, what doesn't](#what-persists-what-doesnt)
  - [Implications for pod-restart resilience](#implications-for-pod-restart-resilience)
- [Desktop (stdio) mode](#desktop-stdio-mode)
  - [The proxy's single hat](#the-proxys-single-hat)
  - [The single flow](#the-single-flow)
  - [Detailed step-by-step](#detailed-step-by-step-1)
  - [Where the cache lives](#where-the-cache-lives)
  - [Reconciling with classical (non-proxied) OAuth intuitions](#reconciling-with-classical-non-proxied-oauth-intuitions-1)
  - [Persistence and failure modes](#persistence-and-failure-modes)

## Deployment modes at a glance

| Aspect | Web-connector (`--transport http`) | Desktop (`--transport stdio`) |
|---|---|---|
| Where the proxy runs | Persistent HTTP server, typically in Kubernetes or another long-running deployment | Local subprocess on the user's machine, launched by the MCP client |
| Transport to the MCP client | HTTP / streamable JSON-RPC | stdio JSON-RPC |
| Auth between MCP client and proxy | Full OAuth 2.0 + DCR + PKCE | None — local trust (the MCP client launches the proxy as its child) |
| Who registers with the upstream IdP | The proxy, once, statically | The proxy, once, statically (per user) |
| Who does the OAuth flow against the upstream IdP | The proxy, on behalf of every MCP client that connects | The proxy, on behalf of the single local user |
| Where tokens are cached | On the proxy's filesystem, briefly during the flow; **persistently on the MCP client** afterwards | On the proxy's filesystem (local user's home directory) |
| Browser pops up on which machine | The MCP client's user's machine (could be remote — e.g. Cowork in a browser) | The local user's machine |
| Concurrency | Many users share one proxy instance, each with isolated upstream sessions | Single user per proxy process |

## MCP client compatibility matrix

| MCP client | Web-connector mode | Desktop mode (proxy as stdio subprocess) |
|---|---|---|
| Claude Desktop | Indirectly via `mcp-remote` as bridge | ✅ native (configure in `claude_desktop_config.json` with `command`/`args`) |
| Claude Code | ✅ native (`claude mcp add --transport http`) | ✅ native (`claude mcp add --transport stdio`) |
| Cursor | Indirectly via `mcp-remote` | ✅ native |
| Codex | Indirectly via `mcp-remote` | ✅ native |
| MCP Inspector | ✅ native (HTTP transport) | ✅ native (stdio transport) |
| Claude.ai / Cowork | ✅ native (custom connector URL) | ❌ cannot launch local subprocesses; web-connector mode only |

> `mcp-remote` (npm) is an HTTP↔stdio bridge for clients that don't speak
> HTTP MCP natively. In web-connector mode it lets Claude Desktop / Cursor
> / Codex reach a remote proxy. In desktop mode it isn't involved at all
> — this proxy is itself the stdio server.

## Web-connector (HTTP) mode

### The proxy's two hats

In web-connector mode the proxy wears two OAuth 2.0 hats simultaneously,
and the architecture only makes sense once you separate them:

| Hat | Counterparty | Role | Credentials it holds |
|---|---|---|---|
| **OAuth 2.0 _client_** | Upstream IdP / Authorization Server (Cognito, Keycloak, Google, Azure, generic OIDC) | The proxy is a single, pre-registered confidential client of the upstream IdP. | Static `client_id` + `client_secret` for the upstream IdP, loaded from the proxy's env (`OIDC_CLIENT_ID` / `OIDC_CLIENT_SECRET`). |
| **DCR-enabled OAuth 2.0 _Authorization Server_** | The MCP client (Claude.ai/Cowork, Inspector, `mcp-remote`, …) | The proxy exposes a full OAuth AS surface (`/register`, `/authorize`, `/token`, `/.well-known/oauth-authorization-server`, `/.well-known/oauth-protected-resource/...`) with **Dynamic Client Registration** (RFC 7591). MCP clients self-register against it at runtime. | None per-MCP-client at registration time — each MCP client gets its own DCR-issued `client_id` (and `client_secret` if confidential). |

**The only way in which the proxy diverges from a "normal" OAuth AS:**
it does not mint its own access or refresh tokens. The tokens it hands
to MCP clients are the upstream IdP's tokens, passed through transparently.
This is what makes `OUTBOUND_AUTH=forward` work — the same bearer that
authenticated the MCP client against the proxy is also valid against the
upstream MCP server (assuming the upstream MCP server validates tokens
against the same IdP, which is the standard deployment).

Why bridge DCR onto a static-client IdP at all? MCP clients
(Claude.ai/Cowork, Inspector, `mcp-remote`, …) expect to self-register
via DCR. Most enterprise IdPs (Cognito, Google) only support static
client registration. The proxy stands between the two and translates:
each DCR'd MCP client gets its own identity at the proxy, while all
DCR'd clients share the proxy's single pre-registered identity at the
upstream IdP.

### The two flows stitched together

```
MCP client                    proxy                       Upstream IdP / AS
──────────                    ─────                       ─────────────────
 (1) opens browser ──── /authorize ────────────────────────────►
                            │
                            └─── redirects browser ──── /authorize ──►
                                                                      │
                                                      user logs in    │
                                                                      │
                                  ◄── redirects browser
                                  /callback?code=UPSTREAM_CODE   (a)
                                  │
                          ┌───────┘
                          │
                          │ PROXY  /token (server-to-server)
                          │ ───────────────────────── ──────────────►
                          │   grant_type=authorization_code
                          │   code=UPSTREAM_CODE
                          │   client_id=PROXY_STATIC_UPSTREAM_ID
                          │   client_secret=PROXY_STATIC_UPSTREAM_SECRET  ← THE SECRET
                          │ ◄────────── access_token+refresh_token
                          │
                          │ stores upstream tokens transiently, indexed by
                          │ a NEW proxy-issued auth code = PROXY_CODE
                          │
                          │ redirects browser ──┐
                          │                     ▼
   ◄── <mcp-client-redirect>?code=PROXY_CODE  (b)
   │
   │ MCP CLIENT  /token ─────────────────────►
   │   grant_type=authorization_code
   │   code=PROXY_CODE
   │   code_verifier=<PKCE>             ← no secret; PKCE proves the MCP
   │                                       client is the same DCR registration
   │                                       that initiated the flow
   │ ◄───── proxy looks up the upstream tokens it stored
   │        against PROXY_CODE, hands them straight back
   │
   ▼
 has upstream-issued access_token + refresh_token (location depends on client)
```

The proxy is the **client** in the upper half (its OAuth-2.0-client hat)
and the **Authorization Server** in the lower half (its DCR-enabled-AS
hat). The two halves are independent OAuth flows that the proxy
stitches together through the temporary `PROXY_CODE`.

### Detailed step-by-step

| # | Wire event | Server-side record (proxy's `${FASTMCP_HOME}/oauth-proxy/<key>/`, Fernet-encrypted) | Client-side record (location depends on the MCP client — see below) |
|---|---|---|---|
| 1 | MCP client → proxy: `POST /register` (DCR, RFC 7591) | **DCR client record** — `{dcr_client_id, dcr_client_secret, redirect_uris, scopes, …}`. The only thing the proxy needs to look up later to recognise this particular MCP client. Bridges DCR onto the proxy's single pre-registered upstream client. | **Client credentials** — the `dcr_client_id` (+ secret if confidential) the proxy just issued back. Reused on every future flow against this server. |
| 2a | MCP client → proxy: `GET /authorize` | **Transaction state** — `{txn_id, state, code_challenge, redirect_uri, requested_scopes, dcr_client_id, …}`. Short-lived; consumed in step 3. | *(in-memory PKCE verifier only — not on disk)* |
| 2b | proxy → upstream IdP: `GET /authorize` (via browser redirect) | *(no new persistent record — the transaction state from 2a is updated with the upstream-side `state` value)* | *(nothing — browser only)* |
| 3a | upstream IdP → proxy: `GET /callback?code=UPSTREAM_CODE` (via browser redirect) | **Transient** — upstream auth code held in memory until 3b completes. | *(nothing — the browser is currently on the proxy's domain)* |
| 3b | proxy → upstream IdP: `POST /token` (server-to-server) | **Upstream tokens received** — the proxy authenticates with its own upstream `client_secret` (loaded from env). Receives the real upstream `access_token` + `refresh_token`. Stores them transiently, indexed by a freshly-generated `PROXY_CODE`. | *(nothing — server-to-server call)* |
| 3c | proxy → MCP client: redirect browser to `<mcp-client-redirect>?code=PROXY_CODE` | *(no new record — `PROXY_CODE` was created in 3b)* | *(nothing yet — the local callback handler is about to fire)* |
| 3d | MCP client → proxy: `POST /token` (PKCE, no secret) | Proxy verifies `code_verifier` against the `code_challenge` from step 2a, looks up the upstream tokens stored against `PROXY_CODE`, hands them straight to the MCP client, then **deletes** the transaction record and the `PROXY_CODE → tokens` mapping. | **Upstream-issued access token + refresh token** — these are real JWTs from the upstream IdP. The MCP client puts the access token in `Authorization: Bearer …` on every subsequent JSON-RPC frame; when it expires, it calls `/token` again with `grant_type=refresh_token`. |
| 4 | MCP client → proxy: `POST /mcp` (every JSON-RPC frame) | *(no state lookup needed for the bearer itself — proxy validates the JWT against the upstream IdP's public JWKS, which it caches in memory. In `OUTBOUND_AUTH=forward` it attaches the **same** JWT to the call to the upstream MCP server, which validates it against the same JWKS.)* | *(no change — reuses the cached access token; silently runs the `/token` refresh dance when expired)* |

### Where the client-side record lives (per client)

| MCP client | Persistence layer |
|---|---|
| `mcp-remote` (npm) | `~/.mcp-auth/<server-hash>/` on local disk |
| MCP Inspector | In-memory only — re-auths on every session |
| Claude.ai / Cowork | Anthropic-managed server-side state — persists across browser sessions and devices |
| Claude Desktop / Cursor / Codex | Via `mcp-remote` (when used as a stdio bridge): `~/.mcp-auth/<server-hash>/` |

Server-side state on the proxy is uniform regardless of which MCP client
is talking to it.

### Reconciling with classical (non-proxied) OAuth intuitions

| Classical OAuth concept | Where it lives here |
|---|---|
| Confidential client with `client_secret` — calls `/token` from its callback handler | **The proxy.** The proxy is the upstream IdP's registered confidential client. The upstream `client_secret` lives in the proxy's env vars only. Used in step **3b**. |
| Public client with PKCE — calls `/token` from its local callback | **The MCP client.** It's a DCR'd public client of the proxy. No secret; PKCE binds the `/token` call to the `/authorize` call. Used in step **3d**. |
| `/callback` endpoint | Two different ones: **the proxy's `/callback`** (where the upstream IdP redirects, step 3a) and **the MCP client's redirect URI** (where the proxy redirects, step 3c — e.g. `http://localhost:XXXX/oauth/callback` for `mcp-remote`, Anthropic-hosted for Claude.ai/Cowork). |
| Authorization code | Two different ones: **`UPSTREAM_CODE`** (upstream-IdP-issued, consumed by the proxy in 3b) and **`PROXY_CODE`** (proxy-issued, consumed by the MCP client in 3d). |

### What persists, what doesn't

After step 3d completes:

- **Server side (proxy):** only the **DCR client record** from step 1
  persists. All transaction state and the transient
  `PROXY_CODE → upstream_tokens` mapping have been deleted. The proxy
  never holds long-term token storage of its own.
- **Client side (MCP client):** the **DCR `client_id`** (and
  `client_secret` if any) from step 1, plus the **upstream-issued access
  + refresh tokens** received in step 3d. Where these live depends on
  the MCP client (see table above).

### Implications for pod-restart resilience

If the proxy pod restarts without a persistent volume backing its
storage directory:

- The **DCR registry dies** → every MCP client that was registered now
  holds a `dcr_client_id` the proxy doesn't recognise.
- On the next `/token` call (or the next refresh attempt), the proxy
  returns `invalid_client` (RFC 6749 §5.2).
- Well-behaved MCP clients detect this, drop their local cache for the
  server, and re-run the full flow (browser popup, user login, fresh
  DCR registration). Less-forgiving clients may need manual
  re-registration.

Tokens themselves are *not* affected by a pod restart — they're plain
upstream-IdP-issued JWTs, validated by the upstream's public JWKS, and
the MCP client already holds them locally. They become unreachable only
because the proxy no longer recognises the DCR client they were issued
to.

So a persistent volume on this deployment is a **DCR continuity** volume,
not a *token cache* volume. The path to persist is the proxy's
`${FASTMCP_HOME}/oauth-proxy/<key>/`, which defaults to
`${HOME}/.local/share/fastmcp/oauth-proxy/<key>/` (and resolves to
`/app/.local/share/fastmcp/oauth-proxy/<key>/` inside the container with
the project's default `HOME=/app`).

The trade-off is the usual one for stateful Kubernetes workloads —
`Deployment` + ephemeral storage costs nothing but forces re-registration
on every pod restart; `StatefulSet` + `PersistentVolumeClaim` keeps DCR
registrations sticky across restarts but adds operational complexity.

## Desktop (stdio) mode

### The proxy's single hat

In desktop mode the proxy is launched as a stdio subprocess of a single
MCP client running on the same machine — Claude Desktop, Claude Code,
Cursor, Codex, or MCP Inspector. The MCP client speaks JSON-RPC to the
proxy over stdin/stdout. There is **no auth between the MCP client and
the proxy** — they share a process tree and trust each other locally.

The proxy wears only **one OAuth 2.0 hat** here: it is an **OAuth 2.0
client** of the upstream IdP, doing the classical Authorization Code +
PKCE flow on behalf of the single local user. No DCR, no AS surface, no
two-flow stitching. Just one client, one flow, one user.

This requires the user to have pre-registered an OAuth client with the
upstream IdP themselves (the proxy is *that* client) and to supply the
credentials via env vars: `OIDC_ISSUER_URL`, `OIDC_CLIENT_ID`,
`OIDC_CLIENT_SECRET` (optional for public clients), `OIDC_SCOPES`,
`OIDC_REDIRECT_URL`.

### The single flow

```
Browser                  MCP client                   proxy                Upstream IdP / AS    Upstream MCP
                         (Claude Desktop /            (local stdio
                          Code / Inspector / …)        subprocess)
                                │
                                │ launches as subprocess
                                │ ───────────────────►│
                                │                     │
                                │ JSON-RPC over stdio │
                                │ ◄──────────────────►│
                                │                     │
                                │                     │ first upstream call needs auth
                                │                     │
                                │                     │ start tiny HTTP listener on
                                │                     │ OIDC_REDIRECT_URL (e.g.
                                │                     │ http://localhost:8080/callback)
                                │                     │
                                │                     │ /authorize?…&code_challenge=…
                                │                     │ ──────────────────────────────►
   open browser ◄────────────── │ ◄───────────────────│
   to upstream                  │                     │
   /authorize URL               │                     │
        │                       │                     │
        │ user logs in          │                     │                                       
        │ ─────────────────────────────────────────────────►
        │                       │                     │                                       
        │ ◄─ redirect to localhost:8080/callback?code=UPSTREAM_CODE
        │                       │                     │
        │                       │                     │ captures UPSTREAM_CODE from
        │                       │                     │ its own localhost listener
        │                       │                     │
        │                       │                     │ /token (PKCE — no client_secret
        │                       │                     │  if public client; client_secret
        │                       │                     │  if confidential)
        │                       │                     │ ──────────────────────────────►
        │                       │                     │ ◄── access_token + refresh_token
        │                       │                     │
        │                       │                     │ persists tokens to
        │                       │                     │ ~/.cache/authsome-mcp-proxy-<ver>/
        │                       │                     │
                                │                     │ tools/prompts/resources
                                │                     │ ───────────────────────────────────────────►
                                │                     │   Authorization: Bearer <upstream JWT>
                                │ ◄─── result ────────│ ◄───────────────────────────────────────────
```

After first successful login the browser dance only repeats when the
refresh token expires; ordinary token rotation happens silently via
`grant_type=refresh_token` against the upstream IdP.

### Detailed step-by-step

| # | Event | Where it happens | Persistent record |
|---|---|---|---|
| 1 | MCP client launches the proxy as a stdio subprocess | Local machine | Proxy reads `OIDC_*` env vars into memory. Nothing on disk yet. |
| 2 | First MCP method invocation (tools/list, etc.) arrives over stdio | Proxy ↔ MCP client | None |
| 3 | Proxy needs to call the upstream MCP server; checks `~/.cache/authsome-mcp-proxy-<version>/` for a cached token | Proxy's local user home | Reads the cache if present and not expired. |
| 4a | No valid cached token: proxy starts an HTTP listener on `OIDC_REDIRECT_URL` (e.g. `http://localhost:8080/callback`) and constructs the upstream `/authorize` URL (`response_type=code`, `code_challenge`, PKCE, requested scopes) | Local | None — PKCE verifier held in memory |
| 4b | Proxy opens the user's default browser to the upstream `/authorize` URL | Local | None |
| 4c | User logs in at the upstream IdP in the browser | Browser ↔ upstream IdP | Upstream issues an auth code, redirects browser back to `http://localhost:8080/callback?code=UPSTREAM_CODE` |
| 4d | Proxy's local listener captures `UPSTREAM_CODE` | Local | None |
| 4e | Proxy calls upstream `/token` server-to-server with `code`, PKCE `code_verifier`, and the proxy's `client_id` (+ `client_secret` if confidential) | Proxy ↔ upstream IdP | Receives `access_token` + `refresh_token`; **writes them to `~/.cache/authsome-mcp-proxy-<version>/`** |
| 5 | Proxy attaches `Authorization: Bearer <access_token>` and forwards the MCP call to the upstream MCP server | Proxy ↔ upstream MCP | None |
| 6 | Subsequent MCP calls reuse the cached access token. When it expires, proxy silently runs `grant_type=refresh_token` against the upstream IdP and updates the cache. | Proxy ↔ upstream IdP | Updated tokens written to the same cache file. |
| 7 | If the refresh token also expires (or is revoked), proxy falls back to the browser flow (steps 4a–4e) on the next outbound call. | Local | Cache overwritten with fresh tokens. |

### Where the cache lives

The proxy stores upstream-IdP tokens locally for the user who owns the
process:

```
${XDG_CACHE_HOME:-$HOME/.cache}/authsome-mcp-proxy-<version>/
```

On Windows this resolves under `%LOCALAPPDATA%` or `%USERPROFILE%\.cache\`
depending on environment. The directory is namespaced by package version
so a re-install doesn't accidentally reuse incompatible cached state.

This cache has nothing to do with the web-mode `${FASTMCP_HOME}/oauth-proxy/`
directory — desktop mode never runs the DCR-bridge code path.

### Reconciling with classical (non-proxied) OAuth intuitions

| Classical OAuth concept | Where it lives here |
|---|---|
| OAuth client | **The proxy.** Single client to the upstream IdP. |
| `client_id` / `client_secret` | In the proxy's env vars (`OIDC_CLIENT_ID` / `OIDC_CLIENT_SECRET`) — the user pre-registers a client with the upstream IdP and supplies the credentials to the proxy. |
| `/callback` endpoint | **The proxy's localhost listener** at `OIDC_REDIRECT_URL` (default `http://localhost:8080/callback`). The MCP client has no callback — it doesn't speak OAuth. |
| Authorization code | A single `UPSTREAM_CODE` from the upstream IdP, consumed once in step 4e. No `PROXY_CODE` exists in desktop mode. |
| Token storage | On the user's filesystem (`~/.cache/authsome-mcp-proxy-<version>/`). |

### Persistence and failure modes

- **Token cache lost / first run** → next outbound call triggers the
  browser flow. No data loss; the user just sees a browser popup.
- **Refresh token expired or revoked** → same recovery: browser flow on
  the next outbound call.
- **`OIDC_REDIRECT_URL` port in use** → flow fails to capture the
  callback. Set a different port via `--oidc-redirect-url
  http://localhost:<other-port>/callback` (and make sure the same URL
  is whitelisted in the upstream IdP's app-client config).
- **`OIDC_REDIRECT_URL` mismatch with the upstream IdP's whitelisted
  callbacks** → upstream rejects the `/authorize` request before
  redirecting back. This is the most common misconfiguration in desktop
  mode.

No equivalent of the web-mode PVC question exists here — there is no
shared server state to lose. Each user's tokens live in their own home
directory; pod restarts and Kubernetes are not part of this picture.
