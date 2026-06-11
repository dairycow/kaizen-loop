import http.client
import json
import os
import signal
import socket
import subprocess
import time
from contextlib import contextmanager
from dataclasses import dataclass
from urllib.parse import quote, urlparse

_RETRYABLE_STATUS = frozenset({502, 503, 504})
_MAX_RETRIES = 2
_RETRY_BASE_DELAY = 0.5


def _validate_server_url(url: str | None) -> None:
    if url is None:
        return
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https"):
        raise ValueError(
            f"Invalid server URL: {url!r}. Must start with http:// or https://"
        )
    if not parsed.hostname:
        raise ValueError(f"Invalid server URL: {url!r}. No hostname found.")


@dataclass
class AgentResult:
    output: dict
    text: str = ""
    input_tokens: int = 0
    output_tokens: int = 0


class _Session:
    def __init__(self, agent: "OpenCodeAgent", session_id: str):
        self._agent = agent
        self._id = session_id

    @property
    def id(self) -> str:
        return self._id

    def send(self, prompt: str, schema: dict | None = None) -> AgentResult:
        try:
            return self._agent._send_message(self._id, prompt, schema)
        except Exception:
            self._agent._abort_session(self._id)
            raise


class OpenCodeAgent:
    def __init__(self, bin_path: str = "opencode", server_url: str | None = None):
        _validate_server_url(server_url)
        self.bin_path = bin_path
        self._external_server = server_url
        self._process: subprocess.Popen | None = None
        self._base_url: str | None = server_url
        self._port: int | None = None
        self._conn: http.client.HTTPConnection | None = None

    def _get_conn(self) -> http.client.HTTPConnection:
        if self._conn is not None:
            return self._conn
        url = self._base_url
        if not url:
            raise RuntimeError("No server URL configured")
        parsed = urlparse(url)
        self._conn = http.client.HTTPConnection(
            parsed.hostname or "127.0.0.1",
            parsed.port or 80,
            timeout=300,
        )
        return self._conn

    def _reconnect(self) -> http.client.HTTPConnection:
        self._close_conn()
        return self._get_conn()

    def _close_conn(self) -> None:
        if self._conn:
            try:
                self._conn.close()
            except Exception:
                pass
            self._conn = None

    def _http_request(
        self,
        method: str,
        path: str,
        body: dict | None = None,
        timeout: float | None = None,
        max_retries: int = _MAX_RETRIES,
    ) -> dict:
        conn = self._get_conn()
        if timeout is not None:
            conn.timeout = timeout
        headers = {"Accept": "application/json"}
        data = None
        if body is not None:
            data = json.dumps(body).encode()
            headers["Content-Type"] = "application/json"

        last_err: Exception | None = None
        for attempt in range(max_retries + 1):
            try:
                conn.request(method, path, body=data, headers=headers)
                resp = conn.getresponse()
                resp_data = resp.read()
                if 200 <= resp.status < 300:
                    return json.loads(resp_data)
                if resp.status in _RETRYABLE_STATUS and attempt < max_retries:
                    last_err = RuntimeError(f"HTTP {resp.status}")
                    time.sleep(_RETRY_BASE_DELAY * (2**attempt))
                    conn = self._reconnect()
                    continue
                raise RuntimeError(
                    f"HTTP {resp.status}: {resp_data.decode(errors='replace')}"
                )
            except (
                ConnectionError,
                OSError,
                http.client.HTTPException,
            ) as e:
                if attempt < max_retries:
                    last_err = e
                    time.sleep(_RETRY_BASE_DELAY * (2**attempt))
                    conn = self._reconnect()
                    continue
                raise RuntimeError(
                    f"Request failed after {max_retries} retries: {e}"
                ) from e
        raise last_err  # type: ignore[misc]

    def _request(
        self,
        path: str,
        method: str = "GET",
        body: dict | None = None,
        timeout: float = 300,
    ) -> dict:
        return self._http_request(method, path, body=body, timeout=timeout)

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
                self.bin_path,
                "serve",
                "--hostname",
                "127.0.0.1",
                "--port",
                str(self._port),
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
            self._http_request(
                "GET", "/global/health", timeout=5, max_retries=1
            )
        except (
            RuntimeError,
            ConnectionError,
            OSError,
            http.client.HTTPException,
        ) as e:
            port = url.split(":")[-1].rstrip("/")
            raise RuntimeError(
                f"Shared server at {url} is not reachable. "
                f"Start it with: opencode serve --hostname 127.0.0.1 --port {port}  |  Error: {e}"
            )

    def _wait_healthy(self, timeout: float = 30) -> None:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if self._process and self._process.poll() is not None:
                raise RuntimeError("opencode server exited during startup")
            try:
                conn = self._reconnect()
                conn.timeout = 2
                conn.request("GET", "/global/health")
                resp = conn.getresponse()
                resp.read()
                if resp.status == 200:
                    return
            except (ConnectionError, OSError, http.client.HTTPException):
                pass
            time.sleep(0.25)
        raise RuntimeError(
            f"opencode server did not become healthy on port {self._port}"
        )

    def _create_session(self, session_dir: str) -> str:
        resp = self._request(
            f"/session?directory={quote(session_dir, safe='')}",
            method="POST",
            body={},
            timeout=10,
        )
        return resp.get("id", "")

    @contextmanager
    def session(self, work_dir: str, repo_dir: str | None = None):
        server_cwd = repo_dir or work_dir
        self._ensure_server(server_cwd)
        session_id = self._create_session(work_dir)
        try:
            yield _Session(self, session_id)
        finally:
            self._delete_session(session_id)

    def run(
        self,
        prompt: str,
        work_dir: str,
        schema: dict | None = None,
        repo_dir: str | None = None,
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

    def _send_message(
        self, session_id: str, prompt: str, schema: dict | None = None
    ) -> AgentResult:
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
            self._request(
                f"/session/{session_id}/abort", method="POST", timeout=3
            )
        except Exception:
            pass

    def _delete_session(self, session_id: str) -> None:
        try:
            self._request(
                f"/session/{session_id}", method="DELETE", timeout=3
            )
        except Exception:
            pass

    def close(self) -> None:
        if self._external_server:
            self._close_conn()
            return
        if self._base_url:
            try:
                self._http_request(
                    "POST", "/instance/dispose", timeout=5, max_retries=0
                )
            except Exception:
                pass
        self._close_conn()
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
                        os.killpg(
                            os.getpgid(self._process.pid), signal.SIGKILL
                        )
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
