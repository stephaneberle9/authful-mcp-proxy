@echo off
(
echo {
echo   "mcpServers": {
echo     "authful-mcp-proxy": {
echo       "command": "uv",
echo       "args": [
echo         "run",
echo         "--env-file",
echo         ".env",
echo         "authful-mcp-proxy"
echo       ]
echo     }
echo   }
echo }
) > mcp.json

npx -y @modelcontextprotocol/inspector --config mcp.json --server authful-mcp-proxy