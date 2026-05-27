import logging
import os
import sys

from fastmcp import FastMCP
from fastmcp.server.auth import JWTVerifier
from fastmcp.server.dependencies import get_access_token

logger = logging.getLogger(__name__)


def _build_jwt_verifier() -> JWTVerifier:
    """Construct a JWTVerifier from JWT_* environment variables."""
    issuer = os.environ.get("JWT_ISSUER")
    jwks_uri = os.environ.get("JWT_JWKS_URI")
    if not issuer or not jwks_uri:
        raise ValueError(
            "JWT_ISSUER and JWT_JWKS_URI environment variables are required. "
            "See .env.example for the full list."
        )

    audience = os.environ.get("JWT_AUDIENCE") or None
    scopes_csv = os.environ.get("JWT_REQUIRED_SCOPES", "").strip()
    required_scopes = [s.strip() for s in scopes_csv.split(",") if s.strip()] or None

    return JWTVerifier(
        issuer=issuer,
        jwks_uri=jwks_uri,
        audience=audience,
        required_scopes=required_scopes,
    )


def create_upstream_mcp() -> FastMCP:
    upstream_mcp = FastMCP(
        name="Token-validating Upstream MCP", auth=_build_jwt_verifier()
    )

    @upstream_mcp.tool
    async def get_access_token_claims() -> dict:
        """Get the authenticated user's access token claims."""
        token = get_access_token()
        if not token:
            raise RuntimeError("Failed to retrieve access token")
        return {
            "sub": token.claims.get("sub"),
            "username": token.claims.get("username"),
            "cognito:groups": token.claims.get("cognito:groups", []),
        }

    return upstream_mcp


def main():
    try:
        upstream_mcp = create_upstream_mcp()
        upstream_mcp.run(transport="http", port=8090, log_level="DEBUG")
    except KeyboardInterrupt:
        # Graceful shutdown, suppress noisy logs resulting from asyncio.run task cancellation propagation
        pass
    except ValueError as e:
        # Configuration error, log w/o stack trace
        logger.error(f"Configuration error: {e}")
        sys.exit(1)
    except RuntimeError as e:
        # Runtime error, log w/o stack trace
        logger.error(f"Runtime error: {e}")
        sys.exit(1)
    except Exception as e:
        # Unexpected internal error, include full stack trace
        logger.error(f"Internal error: {e}", exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    main()
