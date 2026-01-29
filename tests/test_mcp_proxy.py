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

            # Mock FastMCP.as_proxy
            with patch("authful_mcp_proxy.mcp_proxy.FastMCP.as_proxy") as mock_as_proxy:
                mock_proxy_server = AsyncMock()
                mock_as_proxy.return_value = mock_proxy_server

                # Run the function
                await mcp_proxy.run_async(backend_url, oidc_config, show_banner=False)

                # Verify FastMCP.as_proxy was called with the correct relayed properties (filtered)
                mock_as_proxy.assert_called_once()
                call_kwargs = mock_as_proxy.call_args.kwargs
                assert call_kwargs["backend"] == mock_client
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

                # Verify run_async was called on the proxy
                mock_proxy_server.run_async.assert_called_once()
