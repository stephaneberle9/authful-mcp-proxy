"""Configuration models for the MCP proxy.

Two transports, two config shapes:

- ``DesktopConfig`` -- stdio mode. The proxy runs as a local process launched
  by the MCP client, performs the OAuth Authorization Code + PKCE flow
  against an external OIDC provider on behalf of the local user, caches
  tokens on disk, and forwards them as Bearer tokens to the upstream MCP
  server. No inbound auth (local trust between MCP client and proxy).

- ``WebConfig`` -- http mode. The proxy runs as a standalone HTTP server.
  Downstream MCP clients (Claude.ai, MCP Inspector, etc.) authenticate
  against the proxy; the proxy bridges that to a configured upstream IdP.
  Outbound auth to the upstream MCP server is independently configurable
  via ``outbound_auth``.

The pattern this proxy serves in web mode depends on what credential the
operator plugs in for outbound auth -- see the *MCP Server Auth Architecture
Patterns* write-up. Primary target is Pattern C (``outbound_auth='forward'``).
Pattern B.1 (tenant-scoped outbound credential) and Pattern B.2 (per-user
outbound credential) are partially supported via ``oauth-client-credentials``
and ``static`` outbound modes; mechanism is orthogonal to pattern (B.1 vs
B.2 is determined by the scope of the configured credential, not by which
mechanism is used).
"""

from dataclasses import dataclass
from typing import Literal, TypeAlias

AuthProvider: TypeAlias = Literal["oidc", "keycloak", "aws-cognito", "google", "azure"]
"""Inbound auth provider type for web mode.

Two distinct patterns are dispatched:

- ``keycloak`` -> FastMCP's ``KeycloakAuthProvider`` (a ``RemoteAuthProvider``).
  Modern Keycloak (>= 26.6.0) supports MCP-compatible Dynamic Client
  Registration natively, so the proxy holds no IdP credentials of its own;
  downstream MCP clients DCR directly against Keycloak. The proxy's job
  reduces to JWT verification + advertising Keycloak as the authorization
  server via OAuth 2.0 protected-resource metadata.
- ``oidc`` / ``aws-cognito`` / ``google`` / ``azure`` -> DCR-bridge style
  (``OIDCProxy`` or one of its IdP-specific subclasses). The proxy holds a
  pre-registered static ``client_id`` / ``client_secret`` with the IdP and
  bridges downstream MCP clients' DCR requests to the IdP's static-client
  model. Use ``oidc`` as a fallback for older Keycloak or any generic OIDC
  IdP.
"""

OutboundAuthMode: TypeAlias = Literal["forward", "oauth-client-credentials", "static"]
"""Outbound auth mechanism the proxy uses when calling the upstream MCP.

- ``forward`` -- reuse the downstream session's bearer token (Pattern C).
- ``oauth-client-credentials`` -- proxy obtains its own token via OAuth
  client-credentials grant against an outbound token endpoint independent
  of the inbound IdP.
- ``static`` -- proxy injects a configured literal header value. Covers API
  keys, API tokens, and personal access tokens (PATs) uniformly -- same wire
  shape under different upstream vocabularies.
"""


@dataclass
class DesktopConfig:
    """Configuration for stdio (desktop) transport.

    Attributes:
        issuer_url: OIDC issuer URL (e.g.
            ``https://keycloak.example.com/realms/myrealm``).
        client_id: OAuth client identifier.
        client_secret: OAuth client secret. Optional for public OIDC clients
            that don't require one.
        scopes: Space-separated OAuth scopes (e.g. ``"openid profile email"``).
        redirect_url: Localhost callback URL for the OAuth redirect.
    """

    issuer_url: str
    client_id: str
    client_secret: str | None = None
    scopes: str | None = None
    redirect_url: str | None = None


@dataclass
class WebConfig:
    """Configuration for http (web connector) transport.

    Inbound (downstream MCP client -> proxy):
        auth_provider: Which inbound auth provider to use.
        base_url: Publicly reachable URL of the proxy (e.g.
            ``https://mcp.example.com``). Used by every provider to advertise
            its authorization/token/JWKS endpoints to downstream MCP clients
            via the OAuth 2.0 protected-resource metadata document.
        client_id: OAuth client ID. Required for ``oidc``, ``aws-cognito``,
            ``google``, ``azure``. Unused for ``keycloak`` (DCR-direct).
        client_secret: OAuth client secret. Required for ``aws-cognito``;
            optional for ``oidc`` / ``google`` / ``azure``; unused for
            ``keycloak``.
        scopes: Space-separated OAuth scopes for the inbound flow. Required
            for ``azure`` (FastMCP's ``AzureProvider`` requires
            ``required_scopes``).
        issuer_url: For ``oidc`` and ``keycloak``: the issuer URL of the
            IdP / Keycloak realm (e.g.
            ``https://keycloak.example.com/realms/myrealm``). For ``oidc``,
            the OIDC discovery URL is derived as
            ``{issuer_url}/.well-known/openid-configuration``. Required for
            both ``oidc`` and ``keycloak``.
        audience: Optional JWT ``aud`` claim to require. Used by ``oidc``
            and ``keycloak``. Recommended for production deployments.
        cognito_user_pool_id: AWS Cognito user pool ID -- required for ``aws-cognito``.
        cognito_aws_region: AWS region for the Cognito user pool -- required
            for ``aws-cognito``.
        azure_tenant_id: Azure AD tenant ID -- required for ``azure``.
        azure_identifier_uri: Azure Application ID URI used for scope
            prefixing. Optional for ``azure``.

    Outbound (proxy -> upstream MCP server):
        outbound_auth: Outbound auth mechanism.
        outbound_client_id: OAuth client ID -- required for
            ``oauth-client-credentials``.
        outbound_client_secret: OAuth client secret -- required for
            ``oauth-client-credentials``.
        outbound_token_url: Token endpoint for the client-credentials grant
            -- required for ``oauth-client-credentials``. Independent of the
            inbound IdP: in Pattern B the upstream's auth mechanism is by
            definition disconnected from the IdP that fronts the proxy.
        outbound_header_name: Header name for ``static`` mode. Defaults to
            ``Authorization``.
        outbound_header_value: Literal header value for ``static`` mode
            -- required for ``static``. E.g. ``"Bearer eyJ..."`` for a bearer
            token, or a bare API key paired with
            ``outbound_header_name="X-API-Key"``.

    Server identity (advertised to downstream MCP clients):
        In stdio mode the proxy connects once at startup and relays the
        upstream's ``serverInfo`` so the proxy appears transparent. In web
        mode that startup relay isn't always possible (``outbound_auth=
        'forward'`` has no inbound session yet) so these fields let the
        operator hard-code what downstream clients should see. Each maps
        directly to the matching ``create_proxy()`` kwarg.

        server_name: Display name (e.g. ``"ANALYZE"``). Without this, the
            proxy falls back to FastMCP's auto-generated ``FastMCPProxy-xxxx``.
        server_version: Display version string.
        server_instructions: Instructions the LLM sees alongside the
            tool catalog -- influences tool selection.
        server_website_url: Project URL shown in client UIs.
    """

    auth_provider: AuthProvider
    base_url: str
    client_id: str | None = None
    client_secret: str | None = None
    scopes: str | None = None

    # oidc / keycloak
    issuer_url: str | None = None
    audience: str | None = None

    # aws-cognito
    cognito_user_pool_id: str | None = None
    cognito_aws_region: str | None = None

    # azure
    azure_tenant_id: str | None = None
    azure_identifier_uri: str | None = None

    # outbound
    outbound_auth: OutboundAuthMode = "forward"
    outbound_client_id: str | None = None
    outbound_client_secret: str | None = None
    outbound_token_url: str | None = None
    outbound_header_name: str = "Authorization"
    outbound_header_value: str | None = None

    # server identity advertised to downstream MCP clients
    server_name: str | None = None
    server_version: str | None = None
    server_instructions: str | None = None
    server_website_url: str | None = None

    def __post_init__(self) -> None:
        self._validate_inbound()
        self._validate_outbound()

    def _validate_inbound(self) -> None:
        if self.auth_provider == "keycloak":
            if not self.issuer_url:
                raise ValueError("auth_provider='keycloak' requires issuer_url")
            # KeycloakAuthProvider is a RemoteAuthProvider: no client_id /
            # client_secret needed (the MCP client DCRs directly with Keycloak).
        elif self.auth_provider == "oidc":
            if not self.issuer_url:
                raise ValueError("auth_provider='oidc' requires issuer_url")
            if not self.client_id:
                raise ValueError("auth_provider='oidc' requires client_id")
        elif self.auth_provider == "aws-cognito":
            missing = [
                name
                for name, value in (
                    ("client_id", self.client_id),
                    ("client_secret", self.client_secret),
                    ("cognito_user_pool_id", self.cognito_user_pool_id),
                    ("cognito_aws_region", self.cognito_aws_region),
                )
                if not value
            ]
            if missing:
                raise ValueError(
                    f"auth_provider='aws-cognito' requires {', '.join(missing)}"
                )
        elif self.auth_provider == "google":
            if not self.client_id:
                raise ValueError("auth_provider='google' requires client_id")
        elif self.auth_provider == "azure":
            if not self.client_id:
                raise ValueError("auth_provider='azure' requires client_id")
            if not self.azure_tenant_id:
                raise ValueError("auth_provider='azure' requires azure_tenant_id")
            if not self.scopes:
                # AzureProvider's required_scopes is a mandatory list[str].
                raise ValueError("auth_provider='azure' requires scopes")

    def _validate_outbound(self) -> None:
        if self.outbound_auth == "oauth-client-credentials":
            missing = [
                name
                for name, value in (
                    ("outbound_client_id", self.outbound_client_id),
                    ("outbound_client_secret", self.outbound_client_secret),
                    ("outbound_token_url", self.outbound_token_url),
                )
                if not value
            ]
            if missing:
                raise ValueError(
                    f"outbound_auth='oauth-client-credentials' requires {', '.join(missing)}"
                )
        elif self.outbound_auth == "static":
            if not self.outbound_header_value:
                raise ValueError(
                    "outbound_auth='static' requires outbound_header_value"
                )


ProxyConfig: TypeAlias = DesktopConfig | WebConfig
"""Discriminated union of the two transport-specific config shapes.

Call sites should narrow with ``isinstance(config, DesktopConfig)`` /
``isinstance(config, WebConfig)`` before reading transport-specific fields.
"""
