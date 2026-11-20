from __future__ import annotations

import asyncio
import json
import sys
from typing import Any

from app.tools.registry import ToolRegistry


class StdioMcpServer:
    """Minimal MCP JSON-RPC bridge using newline-delimited stdio messages."""

    def __init__(self) -> None:
        self.tools = ToolRegistry()
        self.initialized = False

    async def handle(self, request: dict[str, Any]) -> dict[str, Any] | None:
        method = request.get("method")
        request_id = request.get("id")
        params = request.get("params") or {}

        if method == "initialize":
            self.initialized = True
            result = {
                "protocolVersion": "2025-06-18",
                "capabilities": {"tools": {}},
                "serverInfo": {"name": "delta-exfil-tools", "version": "0.1.0"},
            }
        elif method == "notifications/initialized":
            return None
        elif method == "ping":
            result = {}
        elif method == "tools/list":
            result = {"tools": self.tools.list_tools()}
        elif method == "tools/call":
            name = params.get("name")
            arguments = params.get("arguments") or {}
            try:
                tool_result = await self.tools.invoke(name, arguments)
                result = {
                    "content": [
                        {
                            "type": "text",
                            "text": json.dumps(tool_result, ensure_ascii=False),
                        }
                    ],
                    "isError": False,
                }
            except (KeyError, ValueError, TypeError) as exc:
                result = {
                    "content": [{"type": "text", "text": str(exc)}],
                    "isError": True,
                }
        else:
            return {
                "jsonrpc": "2.0",
                "id": request_id,
                "error": {"code": -32601, "message": f"unknown method: {method}"},
            }

        return {"jsonrpc": "2.0", "id": request_id, "result": result}


async def main() -> None:
    server = StdioMcpServer()
    loop = asyncio.get_running_loop()
    while True:
        line = await loop.run_in_executor(None, sys.stdin.readline)
        if not line:
            break
        try:
            request = json.loads(line)
        except json.JSONDecodeError:
            continue
        response = await server.handle(request)
        if response is not None:
            sys.stdout.write(json.dumps(response, ensure_ascii=False) + "\n")
            sys.stdout.flush()


if __name__ == "__main__":
    asyncio.run(main())
