import json
import os
import signal
import socket
import subprocess
import time
from dataclasses import dataclass
from urllib.error import URLError
from urllib.parse import quote
from urllib.request import Request, urlopen


@dataclass
class AgentResult:
    output: dict
    text: str = ""
    input_tokens: int = 0
    output_tokens: int = 0


class OpenCodeAgent:
    def __init__(self, bin_path: str = "opencode", server_url: str | None = None):
        self.bin_path = bin_path
        self._external_server = server_url
        self._process: subprocess.Popen | None = None
        self._base_url: str | None = server_url
        self._port: int | None = None

    def _ensure_server(self, server_cwd: str) -> None:
        if self._base_url:
            self._check_external_server()
            return

        self._port = _get_free_port()
        env = {**os.environ}
        env.pop("OPENCODE_SERVER_USERNAME", None)
        env.pop("OPENCODE_SERVER_PASSWORD", None)

        self._process = subprocess.Popen(
            [
                self.bin_path, "serve",
                "--hostname", "127.0.0.1",
                "--port", str(self._port),
                "--print-logs",
            ],
            cwd=server_cwd,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env=env,
            start_new_session=True,
        )
        self._base_url = f"http://127.0.0.1:{self._port}"
        self._wait_healthy(timeout=30)

    def _check_external_server(self) -> None:
        url = self._base_url
        if not url:
            raise RuntimeError("No server URL configured")
        try:
            req = Request(f"{url}/global/health")
            with urlopen(req, timeout=5) as resp:
                if resp.status == 200:
                    return
        except (URLError, OSError) as e:
            port = url.split(":")[-1].rstrip("/")
            raise RuntimeError(
                f"Shared server at {url} is not reachable. "
                f"Start it with: opencode serve --hostname 127.0.0.1 --port {port}  |  Error: {e}"
            )
        raise RuntimeError(
            f"Shared server at {url} returned status {resp.status}"
        )

    def _wait_healthy(self, timeout: float = 30) -> None:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if self._process and self._process.poll() is not None:
                raise RuntimeError("opencode server exited during startup")
            try:
                req = Request(f"{self._base_url}/global/health")
                with urlopen(req, timeout=2) as resp:
                    if resp.status == 200:
                        return
            except (URLError, OSError):
                pass
            time.sleep(0.25)
        raise RuntimeError(f"opencode server did not become healthy on port {self._port}")

    def _request(
        self, path: str, method: str = "GET",
        body: dict | None = None, timeout: float = 300,
    ) -> dict:
        url = f"{self._base_url}{path}"
        headers = {"Accept": "application/json"}
        data = None
        if body is not None:
            data = json.dumps(body).encode()
            headers["Content-Type"] = "application/json"
        req = Request(url, data=data, headers=headers, method=method)
        with urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read())

    def _create_session(self, session_dir: str) -> str:
        resp = self._request(
            f"/session?directory={quote(session_dir, safe='')}",
            method="POST",
            body={},
            timeout=10,
        )
        return resp.get("id", "")

    def run(
        self, prompt: str, work_dir: str,
        schema: dict | None = None, repo_dir: str | None = None,
    ) -> AgentResult:
        server_cwd = repo_dir or work_dir
        self._ensure_server(server_cwd)
        session_id = self._create_session(work_dir)
        try:
            return self._send_message(session_id, prompt, schema)
        except Exception:
            self._abort_session(session_id)
            raise
        finally:
            self._delete_session(session_id)

    def _send_message(self, session_id: str, prompt: str, schema: dict | None = None) -> AgentResult:
        body: dict = {
            "role": "user",
            "parts": [{"type": "text", "text": prompt}],
        }
        if schema:
            body["format"] = {
                "type": "json_schema",
                "schema": schema,
                "retryCount": 1,
            }
        result = self._request(
            f"/session/{session_id}/message",
            method="POST",
            body=body,
            timeout=600,
        )

        info = result.get("info", {})
        structured = info.get("structured")
        tokens = info.get("tokens", {})

        if structured:
            return AgentResult(
                output=structured,
                input_tokens=tokens.get("input", 0),
                output_tokens=tokens.get("output", 0),
            )

        text = ""
        for part in result.get("parts", []):
            if part.get("type") == "text" and part.get("text"):
                text = part["text"]

        if not text:
            raise RuntimeError("No structured output or text in agent response")

        raise RuntimeError(f"Agent returned unstructured text: {text[:200]}")

    def _abort_session(self, session_id: str) -> None:
        try:
            self._request(f"/session/{session_id}/abort", method="POST", timeout=3)
        except Exception:
            pass

    def _delete_session(self, session_id: str) -> None:
        try:
            self._request(f"/session/{session_id}", method="DELETE", timeout=3)
        except Exception:
            pass

    def close(self) -> None:
        if self._external_server:
            return
        if self._base_url:
            try:
                self._request("/instance/dispose", method="POST", timeout=5)
            except Exception:
                pass
        if self._process and self._process.poll() is None:
            try:
                self._process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                try:
                    os.killpg(os.getpgid(self._process.pid), signal.SIGTERM)
                except OSError:
                    self._process.terminate()
                try:
                    self._process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    try:
                        os.killpg(os.getpgid(self._process.pid), signal.SIGKILL)
                    except OSError:
                        self._process.kill()
                    self._process.wait(timeout=2)
        self._process = None
        self._base_url = None
        self._port = None


def _get_free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]
