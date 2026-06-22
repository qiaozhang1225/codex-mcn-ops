from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any
import base64
import json
import os
import shutil
import socket
import struct
import subprocess
import time
import urllib.parse
import urllib.request

from .douyin_cookie import DEFAULT_DOUYIN_HOME, DEFAULT_USER_AGENT, DouyinCookieResult


DEFAULT_PROFILE_DIR = Path("data/browser-profiles/douyin-cookie")


@dataclass(frozen=True)
class LoginCookieResult(DouyinCookieResult):
    browser_path: str | None = None
    profile_dir: str | None = None
    written_env_path: str | None = None

    def to_dict(self, *, include_cookie: bool = False) -> dict[str, Any]:
        payload = super().to_dict(include_cookie=include_cookie)
        payload["browser_path"] = self.browser_path
        payload["profile_dir"] = self.profile_dir
        if self.written_env_path:
            payload["written_env_path"] = self.written_env_path
        return payload


def login_and_fetch_douyin_cookie(
    *,
    browser_path: str | None = None,
    profile_dir: str | Path = DEFAULT_PROFILE_DIR,
    url: str = DEFAULT_DOUYIN_HOME,
    timeout_seconds: float = 300.0,
    poll_seconds: float = 3.0,
    min_cookie_length: int = 100,
    close_browser: bool = False,
) -> LoginCookieResult:
    resolved_browser = browser_path or find_browser_path()
    if not resolved_browser:
        return LoginCookieResult(
            status="error",
            cookie="",
            cookie_valid=False,
            cookie_count=0,
            cookie_names=[],
            error="Chrome/Chromium browser was not found.",
            profile_dir=str(profile_dir),
        )
    profile_path = Path(profile_dir)
    profile_path.mkdir(parents=True, exist_ok=True)
    port = _free_port()
    process = subprocess.Popen(
        [
            resolved_browser,
            f"--remote-debugging-port={port}",
            f"--user-data-dir={profile_path}",
            "--no-first-run",
            "--no-default-browser-check",
            url,
        ],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    try:
        _wait_for_debugger(port, timeout=min(20.0, timeout_seconds))
        deadline = time.time() + timeout_seconds
        last = _fetch_cookie_from_devtools(port, min_cookie_length=min_cookie_length)
        while time.time() < deadline:
            if last.cookie_valid:
                return _with_login_meta(last, resolved_browser, profile_path)
            time.sleep(max(0.5, poll_seconds))
            last = _fetch_cookie_from_devtools(port, min_cookie_length=min_cookie_length)
        if last.cookie:
            return _with_login_meta(last, resolved_browser, profile_path)
        return LoginCookieResult(
            status="error",
            cookie="",
            cookie_valid=False,
            cookie_count=0,
            cookie_names=[],
            error="Timed out waiting for Douyin login cookie.",
            browser_path=resolved_browser,
            profile_dir=str(profile_path),
        )
    finally:
        if close_browser:
            process.terminate()


def find_browser_path() -> str | None:
    env_path = os.environ.get("CHROME_PATH") or os.environ.get("BROWSER_PATH")
    if env_path and Path(env_path).exists():
        return env_path
    candidates = [
        "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
        str(Path.home() / "Applications/Google Chrome.app/Contents/MacOS/Google Chrome"),
        "/Applications/Chromium.app/Contents/MacOS/Chromium",
        "/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge",
    ]
    for candidate in candidates:
        if Path(candidate).exists():
            return candidate
    for executable in ["google-chrome", "chrome", "chromium", "chromium-browser", "msedge"]:
        path = shutil.which(executable)
        if path:
            return path
    return None


def write_env_cookie(cookie: str, *, env_path: str | Path = ".env.local") -> Path:
    path = Path(env_path)
    if path.parent != Path("."):
        path.parent.mkdir(parents=True, exist_ok=True)
    lines = path.read_text(encoding="utf-8").splitlines() if path.exists() else []
    rendered = f"DOUYIN_COOKIE={_shell_quote(cookie)}"
    replaced = False
    output: list[str] = []
    for line in lines:
        if line.startswith("DOUYIN_COOKIE="):
            output.append(rendered)
            replaced = True
        else:
            output.append(line)
    if not replaced:
        output.append(rendered)
    path.write_text("\n".join(output).rstrip() + "\n", encoding="utf-8")
    return path


def _with_login_meta(result: DouyinCookieResult, browser_path: str, profile_dir: Path) -> LoginCookieResult:
    return LoginCookieResult(
        status=result.status,
        cookie=result.cookie,
        cookie_valid=result.cookie_valid,
        cookie_count=result.cookie_count,
        cookie_names=result.cookie_names,
        status_code=result.status_code,
        final_url=result.final_url,
        error=result.error,
        browser_path=browser_path,
        profile_dir=str(profile_dir),
    )


def _fetch_cookie_from_devtools(port: int, *, min_cookie_length: int) -> DouyinCookieResult:
    try:
        targets = _json_get(f"http://127.0.0.1:{port}/json")
        target = _select_page_target(targets)
        if not target:
            return DouyinCookieResult(
                status="error",
                cookie="",
                cookie_valid=False,
                cookie_count=0,
                cookie_names=[],
                error="No page target found in Chrome DevTools.",
            )
        ws_url = target["webSocketDebuggerUrl"]
        response = _cdp_call(ws_url, "Network.getAllCookies")
        cookies = response.get("result", {}).get("cookies") or []
        douyin_cookies = [
            item
            for item in cookies
            if isinstance(item, dict)
            and "douyin.com" in str(item.get("domain") or "")
            and item.get("name")
            and item.get("value") is not None
        ]
        cookie = "; ".join(f"{item['name']}={item['value']}" for item in douyin_cookies)
        names = [str(item["name"]) for item in douyin_cookies]
        return DouyinCookieResult(
            status="success",
            cookie=cookie,
            cookie_valid=len(cookie) > min_cookie_length,
            cookie_count=len(douyin_cookies),
            cookie_names=names,
            final_url=target.get("url"),
        )
    except Exception as exc:
        return DouyinCookieResult(
            status="error",
            cookie="",
            cookie_valid=False,
            cookie_count=0,
            cookie_names=[],
            error=str(exc),
        )


def _select_page_target(targets: Any) -> dict[str, Any] | None:
    if not isinstance(targets, list):
        return None
    pages = [target for target in targets if target.get("type") == "page" and target.get("webSocketDebuggerUrl")]
    for target in pages:
        if "douyin.com" in str(target.get("url") or ""):
            return target
    return pages[0] if pages else None


def _wait_for_debugger(port: int, *, timeout: float) -> None:
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            _json_get(f"http://127.0.0.1:{port}/json/version")
            return
        except Exception:
            time.sleep(0.25)
    raise TimeoutError("Chrome DevTools endpoint did not become ready.")


def _json_get(url: str) -> Any:
    request = urllib.request.Request(url, headers={"User-Agent": DEFAULT_USER_AGENT})
    with urllib.request.urlopen(request, timeout=5) as response:
        return json.loads(response.read().decode("utf-8"))


def _cdp_call(ws_url: str, method: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
    parsed = urllib.parse.urlparse(ws_url)
    if parsed.scheme != "ws":
        raise ValueError(f"only ws:// DevTools endpoints are supported: {ws_url}")
    host = parsed.hostname or "127.0.0.1"
    port = parsed.port or 80
    path = parsed.path
    if parsed.query:
        path += "?" + parsed.query
    with socket.create_connection((host, port), timeout=10) as sock:
        _websocket_handshake(sock, host, port, path)
        payload = json.dumps({"id": 1, "method": method, "params": params or {}}, separators=(",", ":"))
        _send_ws_text(sock, payload)
        while True:
            message = _recv_ws_text(sock)
            decoded = json.loads(message)
            if decoded.get("id") == 1:
                if "error" in decoded:
                    raise RuntimeError(decoded["error"])
                return decoded


def _websocket_handshake(sock: socket.socket, host: str, port: int, path: str) -> None:
    key = base64.b64encode(os.urandom(16)).decode("ascii")
    request = (
        f"GET {path} HTTP/1.1\r\n"
        f"Host: {host}:{port}\r\n"
        "Upgrade: websocket\r\n"
        "Connection: Upgrade\r\n"
        f"Sec-WebSocket-Key: {key}\r\n"
        "Sec-WebSocket-Version: 13\r\n"
        "\r\n"
    )
    sock.sendall(request.encode("ascii"))
    response = b""
    while b"\r\n\r\n" not in response:
        chunk = sock.recv(4096)
        if not chunk:
            break
        response += chunk
    if b" 101 " not in response.split(b"\r\n", 1)[0]:
        raise RuntimeError("Chrome DevTools websocket handshake failed.")


def _send_ws_text(sock: socket.socket, text: str) -> None:
    data = text.encode("utf-8")
    header = bytearray([0x81])
    length = len(data)
    if length < 126:
        header.append(0x80 | length)
    elif length < 65536:
        header.append(0x80 | 126)
        header.extend(struct.pack("!H", length))
    else:
        header.append(0x80 | 127)
        header.extend(struct.pack("!Q", length))
    mask = os.urandom(4)
    masked = bytes(byte ^ mask[index % 4] for index, byte in enumerate(data))
    sock.sendall(bytes(header) + mask + masked)


def _recv_ws_text(sock: socket.socket) -> str:
    first = _recv_exact(sock, 2)
    opcode = first[0] & 0x0F
    masked = bool(first[1] & 0x80)
    length = first[1] & 0x7F
    if length == 126:
        length = struct.unpack("!H", _recv_exact(sock, 2))[0]
    elif length == 127:
        length = struct.unpack("!Q", _recv_exact(sock, 8))[0]
    mask = _recv_exact(sock, 4) if masked else b""
    data = _recv_exact(sock, length)
    if masked:
        data = bytes(byte ^ mask[index % 4] for index, byte in enumerate(data))
    if opcode == 8:
        raise RuntimeError("Chrome DevTools websocket closed.")
    if opcode != 1:
        return _recv_ws_text(sock)
    return data.decode("utf-8")


def _recv_exact(sock: socket.socket, length: int) -> bytes:
    chunks: list[bytes] = []
    remaining = length
    while remaining > 0:
        chunk = sock.recv(remaining)
        if not chunk:
            raise RuntimeError("unexpected websocket EOF")
        chunks.append(chunk)
        remaining -= len(chunk)
    return b"".join(chunks)


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def _shell_quote(value: str) -> str:
    return "'" + value.replace("'", "'\"'\"'") + "'"
