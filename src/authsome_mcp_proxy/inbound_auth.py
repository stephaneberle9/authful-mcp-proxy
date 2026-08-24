"""Inbound auth provider factory for the web (HTTP) transport.

This module dispatches ``WebConfig.inbound_auth_provider`` to the matching FastMCP
auth provider class. The proxy itself stays IdP-agnostic -- per-IdP quirks
(Cognito's ``client_id`` claim validation, Azure's scope prefixing, Google's
opaque-token handling, Keycloak's native DCR support, etc.) live inside
the FastMCP provider classes.

Two patterns are dispatched here:

- ``keycloak`` uses ``KeycloakAuthProvider`` (a ``RemoteAuthProvider``):
  modern Keycloak supports MCP-compatible DCR natively, so the proxy holds
  no IdP credentials and downstream MCP clients register directly with
  Keycloak. Lean, but requires Keycloak >= 26.6.0.
- ``oidc`` / ``aws-cognito`` / ``google`` / ``azure`` use ``OIDCProxy`` (or
  one of its IdP-specific subclasses) in DCR-bridge mode: the proxy holds a
  pre-registered static client with the IdP and bridges downstream MCP
  clients' DCR requests to that IdP's static-client model. Use ``oidc`` as
  the generic fallback for any OIDC IdP that doesn't support DCR natively
  (including older Keycloak).

``WebConfig.enable_cimd`` rides along on the ``OIDCProxy`` branches: FastMCP's
``OAuthProxy`` implements CIMD (Client ID Metadata Documents) itself, so the
proxy only has to forward the switch. It is inert for ``keycloak`` -- there
Keycloak is the authorization server, so whether a downstream client may
identify itself by URL is Keycloak's decision, not this proxy's.

To add a new IdP:

1. Add a literal to ``AuthProvider`` in :mod:`authsome_mcp_proxy.config`.
2. Add the per-provider required fields to ``WebConfig`` and its
   ``__post_init__`` validation.
3. Add a branch to :func:`build_inbound_auth`.
4. Document required params and add a working example to the README.
"""

from __future__ import annotations

from importlib.metadata import version
from typing import TYPE_CHECKING

from fastmcp.server.auth.auth import AuthProvider as FastMCPAuthProvider
from fastmcp.server.auth.oidc_proxy import OIDCProxy
from fastmcp.server.auth.providers.aws import AWSCognitoProvider
from fastmcp.server.auth.providers.azure import AzureProvider
from fastmcp.server.auth.providers.google import GoogleProvider
from fastmcp.server.auth.providers.keycloak import KeycloakAuthProvider

if TYPE_CHECKING:
    from .config import WebConfig


def _parse_scopes(scopes: str | None) -> list[str] | None:
    if not scopes:
        return None
    return scopes.split()


def _disable_cimd(provider: FastMCPAuthProvider) -> None:
    """Turn CIMD off on an already-constructed provider.

    Every other ``OIDCProxy`` subclass takes an ``enable_cimd`` keyword and
    forwards it; ``AWSCognitoProvider`` is the one that doesn't in any stable
    release up to 3.4.7, so for Cognito the manager has to be dropped after
    construction instead. ``OAuthProxy`` gates both CIMD client lookup and the
    ``client_id_metadata_document_supported`` advertisement on
    ``self._cimd_manager is not None``, and ``get_routes()`` runs later -- when
    the ASGI app is built -- so clearing it here is enough.

    Interim measure with a known end date: upstream added the passthrough in
    PrefectHQ/fastmcp#4719, which ships in 4.0 (present in 4.0.0b3, absent from
    every 3.x). When this project's floor reaches a stable 4.0, delete this
    helper and pass ``enable_cimd=`` to ``AWSCognitoProvider`` like the other
    three providers. Until then it stays correct on both lines: 4.0 keeps
    ``_cimd_manager`` where it is.
    """
    if not hasattr(provider, "_cimd_manager"):
        raise RuntimeError(
            f"Cannot disable CIMD on {type(provider).__name__}: fastmcp "
            f"{version('fastmcp')} no longer exposes _cimd_manager. Pass "
            "enable_cimd to the provider constructor instead and delete this "
            "workaround."
        )
    provider._cimd_manager = None  # ty: ignore[invalid-assignment]


def build_inbound_auth(
    config: WebConfig, base_url: str | None = None
) -> FastMCPAuthProvider:
    """Instantiate the FastMCP auth provider matching ``config.inbound_auth_provider``.

    The returned provider is passed to FastMCP via the ``auth=`` argument
    on the server. For DCR-bridge providers (``oidc``/``aws-cognito``/
    ``google``/``azure``) it bridges downstream MCP clients' DCR requests
    to the IdP's static-client model. For ``keycloak`` it sets up token
    verification + protected-resource-metadata advertising and relies on
    Keycloak's own DCR.

    Args:
        config: Web-mode configuration. ``WebConfig.__post_init__`` has
            already validated that all required per-provider fields are
            populated.
        base_url: Which of the configured public base URLs this provider
            should advertise as. Defaults to ``config.proxy_base_url``.
            Multi-hostname deployments call this once per entry in
            ``config.all_proxy_base_urls``, because a provider's base URL is
            baked in at construction and reaches everything the provider
            advertises -- see :mod:`authsome_mcp_proxy.host_router`.

    Returns:
        A FastMCP ``AuthProvider`` subclass instance.

    Raises:
        ValueError: If ``config.inbound_auth_provider`` is unknown.
    """
    scopes = _parse_scopes(config.scopes)
    base_url = base_url if base_url is not None else config.proxy_base_url

    if config.inbound_auth_provider == "keycloak":
        # RemoteAuthProvider: no client_id/secret; MCP client DCRs with Keycloak.
        assert config.issuer_url is not None
        return KeycloakAuthProvider(
            realm_url=config.issuer_url,
            base_url=base_url,
            required_scopes=scopes,
            audience=config.audience,
        )

    if config.inbound_auth_provider == "oidc":
        # DCR-bridge generic OIDC: derive the discovery URL from the issuer.
        # Use this for older Keycloak versions and any non-DCR OIDC IdP.
        assert config.issuer_url is not None
        assert config.client_id is not None
        config_url = f"{config.issuer_url.rstrip('/')}/.well-known/openid-configuration"
        return OIDCProxy(
            config_url=config_url,
            client_id=config.client_id,
            client_secret=config.client_secret,
            audience=config.audience,
            required_scopes=scopes,
            base_url=base_url,
            enable_cimd=config.enable_cimd,
        )

    if config.inbound_auth_provider == "aws-cognito":
        assert config.client_id is not None
        assert config.client_secret is not None
        assert config.cognito_user_pool_id is not None
        assert config.cognito_aws_region is not None
        provider = AWSCognitoProvider(
            user_pool_id=config.cognito_user_pool_id,
            aws_region=config.cognito_aws_region,
            client_id=config.client_id,
            client_secret=config.client_secret,
            required_scopes=scopes,
            base_url=base_url,
        )
        # No enable_cimd keyword on this one -- see _disable_cimd. Enabled is
        # the inherited default, so only the off switch needs applying.
        if not config.enable_cimd:
            _disable_cimd(provider)
        return provider

    if config.inbound_auth_provider == "google":
        assert config.client_id is not None
        return GoogleProvider(
            client_id=config.client_id,
            client_secret=config.client_secret,
            required_scopes=scopes,
            base_url=base_url,
            enable_cimd=config.enable_cimd,
        )

    if config.inbound_auth_provider == "azure":
        assert config.client_id is not None
        assert config.azure_tenant_id is not None
        assert scopes is not None
        return AzureProvider(
            client_id=config.client_id,
            client_secret=config.client_secret,
            tenant_id=config.azure_tenant_id,
            identifier_uri=config.azure_identifier_uri,
            required_scopes=scopes,
            base_url=base_url,
            enable_cimd=config.enable_cimd,
        )

    raise ValueError(
        f"Unknown inbound_auth_provider {config.inbound_auth_provider!r}; supported: "
        "oidc, keycloak, aws-cognito, google, azure"
    )
