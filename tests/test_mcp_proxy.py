from unittest.mock import AsyncMock, patch

import pytest

from authful_mcp_proxy import mcp_proxy
from authful_mcp_proxy.config import OIDCConfig


@pytest.mark.asyncio
async def test_run_async_relays_server_info():
    """Test that run_async correctly relays server name and version from backend."""
    backend_url = "http://backend:8080"
    oidc_config = OIDCConfig(
        issuer_url="https://auth.example.com", client_id="test-client"
    )

    # Create mock server_info and init_result that behave like Pydantic models
    # with model_dump and extra fields
    class MockModel:
        def __init__(self, data):
            self._data = data
            for k, v in data.items():
                setattr(self, k, v)

        def model_dump(self, exclude=None):
            if exclude is None:
                return self._data.copy()
            return {k: v for k, v in self._data.items() if k not in exclude}

    # Mock ExternalOIDCAuth
    with patch("authful_mcp_proxy.mcp_proxy.ExternalOIDCAuth"):
        # Mock Client
        with patch("authful_mcp_proxy.mcp_proxy.Client") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.__aenter__.return_value = mock_client

            server_info_data = {
                "name": "BackendServer",
                "version": "1.2.3",
                "websiteUrl": "https://example.com",
                "icons": [{"uri": "https://example.com/icon.png", "type": "image/png"}],
                "title": "Some Title",
                "custom_info_prop": "info-value",
            }
            mock_server_info = MockModel(server_info_data)

            init_result_data = {
                "serverInfo": mock_server_info,
                "instructions": "Test instructions",
                "custom_init_prop": "init-value",
                "protocolVersion": "2024-11-05",
                "capabilities": {},
            }
            mock_init_result = MockModel(init_result_data)

            mock_client.initialize_result = mock_init_result
            mock_client_cls.return_value = mock_client

            # Mock create_proxy
            with patch("authful_mcp_proxy.mcp_proxy.create_proxy") as mock_as_proxy:
                mock_proxy_server = AsyncMock()
                mock_as_proxy.return_value = mock_proxy_server

                # Run the function
                await mcp_proxy.run_async(backend_url, oidc_config, show_banner=False)

                # Verify create_proxy was called with the correct relayed properties (filtered)
                mock_as_proxy.assert_called_once()
                call_args = mock_as_proxy.call_args
                assert call_args.args[0] == mock_client
                call_kwargs = call_args.kwargs
                assert call_kwargs["name"] == "BackendServer"
                assert call_kwargs["version"] == "1.2.3"
                assert call_kwargs["instructions"] == "Test instructions"
                assert call_kwargs["website_url"] == "https://example.com"
                assert call_kwargs["icons"] == [
                    {"uri": "https://example.com/icon.png", "type": "image/png"}
                ]

                # Verify unknown props were NOT passed to avoid TypeError
                assert "title" not in call_kwargs
                assert "custom_info_prop" not in call_kwargs
                assert "custom_init_prop" not in call_kwargs

                # Verify run_async was called on the proxy with default stdio transport
                mock_proxy_server.run_async.assert_called_once_with(
                    transport="stdio",
                    show_banner=False,
                )


@pytest.mark.asyncio
async def test_run_async_uses_fresh_proxy_client():
    """Test that create_proxy receives a fresh disconnected client, not the connected
    info client — ensuring each incoming MCP session gets an isolated backend connection."""
    backend_url = "http://backend:8080"
    oidc_config = OIDCConfig(
        issuer_url="https://auth.example.com", client_id="test-client"
    )

    with patch("authful_mcp_proxy.mcp_proxy.ExternalOIDCAuth"):
        with patch("authful_mcp_proxy.mcp_proxy.Client") as mock_client_cls:
            info_client = AsyncMock()
            info_client.__aenter__.return_value = info_client
            info_client.initialize_result = None

            proxy_client = AsyncMock()

            # Return different objects: first call is for the info connection,
            # second call is for the disconnected proxy client.
            mock_client_cls.side_effect = [info_client, proxy_client]

            with patch("authful_mcp_proxy.mcp_proxy.create_proxy") as mock_create_proxy:
                mock_proxy_server = AsyncMock()
                mock_create_proxy.return_value = mock_proxy_server

                await mcp_proxy.run_async(backend_url, oidc_config, show_banner=False)

                # Client was constructed twice
                assert mock_client_cls.call_count == 2

                # create_proxy received the second (disconnected) client, not the first
                received_client = mock_create_proxy.call_args.args[0]
                assert received_client is proxy_client
                assert received_client is not info_client


@pytest.mark.asyncio
async def test_run_async_http_transport():
    """Test that http transport and host/port kwargs are forwarded to the proxy server."""
    backend_url = "http://backend:8080"
    oidc_config = OIDCConfig(
        issuer_url="https://auth.example.com", client_id="test-client"
    )

    with patch("authful_mcp_proxy.mcp_proxy.ExternalOIDCAuth"):
        with patch("authful_mcp_proxy.mcp_proxy.Client") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.__aenter__.return_value = mock_client
            mock_client.initialize_result = None
            mock_client_cls.return_value = mock_client

            with patch("authful_mcp_proxy.mcp_proxy.create_proxy") as mock_create_proxy:
                mock_proxy_server = AsyncMock()
                mock_create_proxy.return_value = mock_proxy_server

                await mcp_proxy.run_async(
                    backend_url,
                    oidc_config,
                    transport="http",
                    show_banner=False,
                    host="0.0.0.0",
                    port=8000,
                )

                mock_proxy_server.run_async.assert_called_once_with(
                    transport="http",
                    show_banner=False,
                    host="0.0.0.0",
                    port=8000,
                )
