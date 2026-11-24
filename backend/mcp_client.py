"""Minimal MCP client (stdio transport): spawn a server, handshake, list/call tools.

Used by the booking agent to reach the partner lab, and by the admin page to show what each server offers.
"""
import json
import os
import queue
import subprocess
import sys
import threading

from .config import BASE_DIR

PROTOCOL = "2025-06-18"


class MCPError(Exception):
    pass


class MCPClient:
    def __init__(self, module: str, timeout: float = 20.0, env: dict | None = None):
        self.module, self.timeout, self._id = module, timeout, 0
        self._env = {**os.environ, **(env or {}), "PYTHONUNBUFFERED": "1"}
        self._q: queue.Queue = queue.Queue()
        self.proc: subprocess.Popen | None = None
        self.server_info: dict = {}

    def __enter__(self) -> "MCPClient":
        self.proc = subprocess.Popen([sys.executable, "-m", self.module], cwd=BASE_DIR, env=self._env, text=True, bufsize=1,
                                     stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
        threading.Thread(target=self._reader, daemon=True).start()
        res = self.request("initialize", {"protocolVersion": PROTOCOL, "capabilities": {},
                                          "clientInfo": {"name": "netracare-agent", "version": "1.0"}})
        self.server_info = res.get("serverInfo", {})
        self._send({"jsonrpc": "2.0", "method": "notifications/initialized"})
        return self

    def __exit__(self, *exc) -> None:
        if self.proc:
            try:
                self.proc.stdin.close()
                self.proc.wait(timeout=3)
            except Exception:
                self.proc.kill()

    def _reader(self) -> None:
        for line in self.proc.stdout:
            try:
                self._q.put(json.loads(line))
            except json.JSONDecodeError:
                pass

    def _send(self, msg: dict) -> None:
        self.proc.stdin.write(json.dumps(msg) + "\n")
        self.proc.stdin.flush()

    def request(self, method: str, params: dict | None = None) -> dict:
        self._id += 1
        self._send({"jsonrpc": "2.0", "id": self._id, "method": method, "params": params or {}})
        while True:
            try:
                msg = self._q.get(timeout=self.timeout)
            except queue.Empty:
                raise MCPError(f"MCP server '{self.module}' did not answer {method} within {self.timeout}s")
            if msg.get("id") == self._id:
                if "error" in msg:
                    raise MCPError(msg["error"].get("message", "MCP error"))
                return msg.get("result", {})

    def list_tools(self) -> list[dict]:
        return self.request("tools/list")["tools"]

    def call_tool(self, name: str, arguments: dict | None = None) -> dict:
        res = self.request("tools/call", {"name": name, "arguments": arguments or {}})
        text = "\n".join(c.get("text", "") for c in res.get("content", []) if c.get("type") == "text")
        try:
            data = json.loads(text)
        except (json.JSONDecodeError, TypeError):
            data = None
        if res.get("isError"):
            raise MCPError(text)
        return {"text": text, "data": data}

    def list_resources(self) -> list[dict]:
        return self.request("resources/list")["resources"]

    def read_resource(self, uri: str) -> str:
        return self.request("resources/read", {"uri": uri})["contents"][0]["text"]


LAB = "mcp_servers.partner_lab_server"
CLINIC = "mcp_servers.clinic_server"


def call_lab(tool: str, arguments: dict | None = None):
    """One-shot call to the partner-lab MCP server; returns parsed JSON (or text)."""
    with MCPClient(LAB) as c:
        res = c.call_tool(tool, arguments)
    return res["data"] if res["data"] is not None else res["text"]


def describe_servers() -> list[dict]:
    out = []
    for label, module in (("NetraCare clinic", CLINIC), ("ClearView partner lab", LAB)):
        try:
            with MCPClient(module) as c:
                out.append({"server": label, "module": module, "info": c.server_info,
                            "tools": [{"name": t["name"], "description": t["description"]} for t in c.list_tools()],
                            "resources": [r["uri"] for r in c.list_resources()], "ok": True})
        except Exception as exc:
            out.append({"server": label, "module": module, "ok": False, "error": str(exc), "tools": [], "resources": []})
    return out
