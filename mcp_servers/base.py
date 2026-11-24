"""A tiny, dependency-free MCP server (stdio transport, newline-delimited JSON-RPC 2.0).

Implements the parts of the Model Context Protocol that clients need to discover and use tools and resources:
initialize / notifications/initialized / ping / tools/list / tools/call / resources/list / resources/read.
Because it speaks the standard protocol, any MCP client (Claude Desktop, the official SDK, our own client) can use it.
Never print to stdout except protocol messages; logs go to stderr.
"""
import json
import sys
import traceback

SUPPORTED_VERSIONS = ["2025-06-18", "2025-03-26", "2024-11-05"]


class MCPServer:
    def __init__(self, name: str, version: str = "1.0.0", instructions: str = ""):
        self.name, self.version, self.instructions = name, version, instructions
        self.tools: dict[str, dict] = {}
        self.resources: dict[str, dict] = {}

    # ---- registration -----------------------------------------------------
    def tool(self, name: str, description: str, properties: dict | None = None, required: list[str] | None = None):
        def deco(fn):
            self.tools[name] = {
                "name": name, "description": description, "fn": fn,
                "inputSchema": {"type": "object", "properties": properties or {}, "required": required or []},
            }
            return fn
        return deco

    def resource(self, uri: str, name: str, description: str, mime: str = "text/plain"):
        def deco(fn):
            self.resources[uri] = {"uri": uri, "name": name, "description": description, "mimeType": mime, "fn": fn}
            return fn
        return deco

    # ---- protocol ---------------------------------------------------------
    def handle(self, msg: dict) -> dict | None:
        method, mid, params = msg.get("method"), msg.get("id"), msg.get("params") or {}
        if method is None:  # a response from the client; nothing to do
            return None
        try:
            result = self._dispatch(method, params)
        except KeyError as exc:
            return self._error(mid, -32601, f"Method not found: {exc.args[0]}") if mid is not None else None
        except ValueError as exc:
            return self._error(mid, -32602, str(exc)) if mid is not None else None
        except Exception as exc:  # pragma: no cover
            traceback.print_exc(file=sys.stderr)
            return self._error(mid, -32603, f"Internal error: {exc}") if mid is not None else None
        if mid is None:  # notification
            return None
        return {"jsonrpc": "2.0", "id": mid, "result": result}

    def _dispatch(self, method: str, params: dict):
        if method == "initialize":
            wanted = params.get("protocolVersion")
            out = {
                "protocolVersion": wanted if wanted in SUPPORTED_VERSIONS else SUPPORTED_VERSIONS[0],
                "capabilities": {"tools": {"listChanged": False}, "resources": {"listChanged": False, "subscribe": False}},
                "serverInfo": {"name": self.name, "version": self.version},
            }
            if self.instructions:
                out["instructions"] = self.instructions
            return out
        if method in ("notifications/initialized", "notifications/cancelled"):
            return None
        if method == "ping":
            return {}
        if method == "tools/list":
            return {"tools": [{k: v for k, v in t.items() if k != "fn"} for t in self.tools.values()]}
        if method == "tools/call":
            name = params.get("name")
            if name not in self.tools:
                raise ValueError(f"Unknown tool: {name}")
            try:
                data = self.tools[name]["fn"](**(params.get("arguments") or {}))
                text = data if isinstance(data, str) else json.dumps(data, indent=2, default=str)
                return {"content": [{"type": "text", "text": text}], "isError": False}
            except TypeError as exc:
                return {"content": [{"type": "text", "text": f"Invalid arguments: {exc}"}], "isError": True}
            except Exception as exc:
                return {"content": [{"type": "text", "text": f"Error: {exc}"}], "isError": True}
        if method == "resources/list":
            return {"resources": [{k: v for k, v in r.items() if k != "fn"} for r in self.resources.values()]}
        if method == "resources/read":
            uri = params.get("uri")
            if uri not in self.resources:
                raise ValueError(f"Unknown resource: {uri}")
            r = self.resources[uri]
            return {"contents": [{"uri": uri, "mimeType": r["mimeType"], "text": r["fn"]()}]}
        raise KeyError(method)

    @staticmethod
    def _error(mid, code: int, message: str) -> dict:
        return {"jsonrpc": "2.0", "id": mid, "error": {"code": code, "message": message}}

    def serve(self) -> None:
        for line in sys.stdin:
            line = line.strip()
            if not line:
                continue
            try:
                msg = json.loads(line)
            except json.JSONDecodeError:
                sys.stdout.write(json.dumps(self._error(None, -32700, "Parse error")) + "\n")
                sys.stdout.flush()
                continue
            for m in (msg if isinstance(msg, list) else [msg]):
                reply = self.handle(m)
                if reply is not None:
                    sys.stdout.write(json.dumps(reply) + "\n")
                    sys.stdout.flush()
