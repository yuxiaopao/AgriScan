"""JSON-RPC client for the official chrome-devtools MCP server (stdio)."""
import json
from pathlib import Path
import queue
import subprocess
import sys
import threading

ROOT = Path(r"E:\AgriScan")
ENTRY = ROOT / ".runtime/chrome-mcp/node_modules/chrome-devtools-mcp/build/src/bin/chrome-devtools-mcp.js"


class ChromeMcp:
    def __init__(self):
        self.errors = (ROOT / ".logs/chrome-mcp.log").open("a", encoding="utf-8")
        self.process = subprocess.Popen(
            [r"D:\nodejs\node.exe", str(ENTRY), "--browserUrl=http://127.0.0.1:9222",
             "--no-usage-statistics", f"--workspace={ROOT}", "--no-performance-crux"],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=self.errors,
            text=True, encoding="utf-8", creationflags=subprocess.CREATE_NO_WINDOW, cwd=ROOT,
        )
        self.messages = queue.Queue()
        self.index = 0
        threading.Thread(target=self.read, daemon=True).start()
        self.request("initialize", {"protocolVersion": "2024-11-05", "capabilities": {},
                                    "clientInfo": {"name": "agriscan-verification", "version": "1.0.0"}})
        self.process.stdin.write(json.dumps({"jsonrpc": "2.0", "method": "notifications/initialized"})+"\n")
        self.process.stdin.flush()

    def read(self):
        for line in self.process.stdout:
            try:
                self.messages.put(json.loads(line))
            except json.JSONDecodeError:
                pass

    def request(self, method, params):
        self.index += 1
        identifier = self.index
        self.process.stdin.write(json.dumps({"jsonrpc": "2.0", "id": identifier,
                                            "method": method, "params": params})+"\n")
        self.process.stdin.flush()
        while True:
            response = self.messages.get(timeout=60)
            if response.get("id") == identifier:
                if "error" in response:
                    raise RuntimeError(response["error"])
                return response["result"]

    def call(self, name, arguments):
        result = self.request("tools/call", {"name": name, "arguments": arguments})
        if result.get("isError"):
            raise RuntimeError(result)
        return result

    def close(self):
        self.process.terminate()
        self.process.wait(timeout=10)
        self.errors.close()


if __name__ == "__main__":
    client = ChromeMcp()
    try:
        if len(sys.argv) > 1 and sys.argv[1] == "--interactive":
            print("Chrome DevTools MCP connected", flush=True)
            for line in sys.stdin:
                if line.strip() == "quit":
                    break
                try:
                    action = json.loads(line)
                    result = client.call(action["name"], action.get("arguments", {}))
                    print(json.dumps(result, ensure_ascii=False), flush=True)
                except Exception as error:
                    print(json.dumps({"error": str(error)}, ensure_ascii=False), flush=True)
        elif len(sys.argv) == 1:
            tools = client.request("tools/list", {})["tools"]
            assert any(tool["name"] == "navigate_page" for tool in tools)
            print(json.dumps(tools, ensure_ascii=False))
        else:
            actions = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8-sig"))
            for action in actions:
                result = client.call(action["name"], action.get("arguments", {}))
                print(json.dumps({"tool": action["name"], "result": result}, ensure_ascii=False), flush=True)
    finally:
        client.close()
