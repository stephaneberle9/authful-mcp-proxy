import logging
import sys

from fastmcp import FastMCP
from fastmcp.server.auth import JWTVerifier
from fastmcp.server.dependencies import get_access_token

logger = logging.getLogger(__name__)


def validate_mcp_config(upstream_mcp: FastMCP):
    """Validate the upstream MCP server's configuration."""
    # Validate that the upstream MCP server's auth provider is a JWTVerifier instance.
    if upstream_mcp.auth is None or not isinstance(upstream_mcp.auth, JWTVerifier):
        raise ValueError(
            f"Auth provider used by this MCP server must be a '{JWTVerifier.__name__}' instance, got {type(upstream_mcp.auth).__name__ if upstream_mcp.auth else None}"
        )


def create_upstream_mcp() -> FastMCP:
    # FastMCP will automatically instantiate JWTVerifier based on FASTMCP_SERVER_AUTH env var
    upstream_mcp = FastMCP(name="Token-validating Upstream MCP")

    validate_mcp_config(upstream_mcp)

    @upstream_mcp.tool
    async def get_access_token_claims() -> dict:
        """Get the authenticated user's access token claims."""
        # Retrieve access token
        token = get_access_token()
        if not token:
            raise RuntimeError("Failed to retrieve access token")

        # Extract and return access token claims
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
