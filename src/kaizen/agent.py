import http.client
import json
import os
import re
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


def _discover_server(project_dir: str) -> str | None:
    try:
        result = subprocess.run(
            ["pgrep", "-af", "opencode serve"],
            capture_output=True,
            text=True,
            timeout=5,
        )
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return None

    if result.returncode != 0 or not result.stdout.strip():
        return None

    candidates: list[tuple[str, bool]] = []

    project_real = os.path.realpath(project_dir)

    for line in result.stdout.strip().splitlines():
        parts = line.split(maxsplit=1)
        if len(parts) < 2:
            continue

        pid_str, cmd = parts

        port_match = re.search(r"--port\s+(\d+)", cmd)
        if not port_match:
            continue

        port = port_match.group(1)
        url = f"http://127.0.0.1:{port}"

        cwd_match = False
        try:
            proc_cwd = os.path.realpath(f"/proc/{pid_str}/cwd")
            if proc_cwd == project_real:
                cwd_match = True
        except OSError:
            pass

        candidates.append((url, cwd_match))

    candidates.sort(key=lambda c: (0 if c[1] else 1))

    for url, _ in candidates:
        try:
            parsed = urlparse(url)
            conn = http.client.HTTPConnection(
                parsed.hostname or "127.0.0.1",
                parsed.port or 80,
                timeout=2,
            )
            conn.request("GET", "/global/health")
            resp = conn.getresponse()
            resp.read()
            conn.close()
            if resp.status == 200:
                return url
        except (ConnectionError, OSError, http.client.HTTPException):
            continue

    return None


@dataclass
class AgentResult:
    output: dict
    text: str = ""
    input_tokens: int = 0
    output_tokens: int = 0


class OpenCodeAgent:
    def __init__(
        self,
        project_dir: str,
        server_url: str | None = None,
        bin_path: str = "opencode",
    ):
        _validate_server_url(server_url)
        self.bin_path = bin_path
        self._base_url: str | None = server_url
        self._project_dir = project_dir
        self._conn: http.client.HTTPConnection | None = None

    def _resolve_server(self) -> None:
        if self._base_url:
            return

        discovered = _discover_server(self._project_dir)
        if discovered:
            self._base_url = discovered
            return

        raise RuntimeError(
            "No opencode server found.\n"
            "Start one with: opencode serve --hostname 127.0.0.1 --port 4096\n"
            "Or use --server-url to specify an existing server."
        )

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

    def _request(
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

    def _create_session(self, session_dir: str) -> str:
        resp = self._request(
            "POST",
            f"/session?directory={quote(session_dir, safe='')}",
            body={},
            timeout=10,
        )
        return resp.get("id", "")

    @contextmanager
    def session(self, work_dir: str, repo_dir: str | None = None):
        self._resolve_server()
        session_id = self._create_session(work_dir)
        try:
            yield session_id
        finally:
            self._delete_session(session_id)

    def send(self, session_id: str, prompt: str, schema: dict | None = None) -> AgentResult:
        try:
            return self._send_message(session_id, prompt, schema)
        except Exception:
            self._abort_session(session_id)
            raise

    def run(
        self,
        prompt: str,
        work_dir: str,
        schema: dict | None = None,
        repo_dir: str | None = None,
    ) -> AgentResult:
        self._resolve_server()
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
            "POST",
            f"/session/{session_id}/message",
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
            self._request("POST", f"/session/{session_id}/abort", timeout=3)
        except Exception:
            pass

    def _delete_session(self, session_id: str) -> None:
        try:
            self._request("DELETE", f"/session/{session_id}", timeout=3)
        except Exception:
            pass

    def close(self) -> None:
        self._close_conn()
