"""Configuration models for the MCP proxy."""

from dataclasses import dataclass


@dataclass
class OIDCConfig:
    """
    OIDC authentication configuration.

    This dataclass encapsulates OIDC/OAuth 2.0 parameters used for authenticating
    with external authorization servers. All fields are optional to support
    configuration via environment variables as fallback.

    Attributes:
        issuer_url: OIDC issuer URL (e.g., https://keycloak.example.com/realms/myrealm)
        client_id: OAuth client identifier
        client_secret: OAuth client secret (optional for public OIDC clients that don't require any such)
        scopes: Space-separated OAuth scopes (e.g., "openid profile email")
        redirect_url: Localhost callback URL for OAuth redirect (e.g., http://localhost:8080/auth/callback)
    """

    issuer_url: str
    client_id: str
    client_secret: str | None = None
    scopes: str | None = None
    redirect_url: str | None = None
