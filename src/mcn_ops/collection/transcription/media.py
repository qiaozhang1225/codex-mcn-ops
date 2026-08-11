from __future__ import annotations

import hashlib
import ipaddress
import json
import mimetypes
import shutil
import socket
import subprocess
import tempfile
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from ..douyin.errors import ProviderUnavailableError, TranscriptionInputError


DEFAULT_DOWNLOAD_LIMIT_BYTES = 2 * 1024 * 1024 * 1024
PROXY_SYNTHETIC_NETWORK = ipaddress.ip_network("198.18.0.0/15")
TRUSTED_DOUYIN_MEDIA_SUFFIXES = (
    ".douyinstatic.com",
    ".douyinvod.com",
)


@dataclass
class PreparedMedia:
    path: Path
    duration_seconds: float
    size_bytes: int
    mime_type: str
    sha256: str
    source_url: str | None = None
    temporary_directory: Path | None = None

    def read_bytes(self, *, max_bytes: int | None = None) -> bytes:
        if max_bytes is not None and self.size_bytes > max_bytes:
            raise TranscriptionInputError(f"audio exceeds the {max_bytes}-byte short-audio limit")
        return self.path.read_bytes()

    def cleanup(self) -> None:
        if self.temporary_directory is not None:
            shutil.rmtree(self.temporary_directory, ignore_errors=True)


Probe = Callable[[Path], float]
Downloader = Callable[[str, Path, int, float], None]


def prepare_media(
    source: str,
    *,
    probe: Probe | None = None,
    downloader: Downloader | None = None,
    download_limit_bytes: int = DEFAULT_DOWNLOAD_LIMIT_BYTES,
    timeout_seconds: float = 30.0,
) -> PreparedMedia:
    source = str(source or "").strip()
    if not source:
        raise TranscriptionInputError("transcription source is required")

    probe = probe or probe_duration_seconds
    parsed = urllib.parse.urlsplit(source)
    temporary_directory: Path | None = None
    source_url: str | None = None
    if parsed.scheme:
        validate_public_https_url(source)
        temporary_directory = Path(tempfile.mkdtemp(prefix="mcn-asr-"))
        suffix = Path(parsed.path).suffix.lower() or ".media"
        media_path = temporary_directory / f"input{suffix}"
        try:
            (downloader or download_url)(source, media_path, download_limit_bytes, timeout_seconds)
        except Exception:
            shutil.rmtree(temporary_directory, ignore_errors=True)
            raise
        source_url = source
    else:
        media_path = Path(source).expanduser().resolve()
        if not media_path.is_file():
            raise TranscriptionInputError(f"media file does not exist: {media_path}")

    try:
        size_bytes = media_path.stat().st_size
        if size_bytes <= 0:
            raise TranscriptionInputError("media file is empty")
        if size_bytes > download_limit_bytes:
            raise TranscriptionInputError(f"media exceeds the {download_limit_bytes}-byte limit")
        duration_seconds = float(probe(media_path))
        if duration_seconds <= 0:
            raise TranscriptionInputError("media duration must be positive")
        mime_type = mimetypes.guess_type(media_path.name)[0] or "application/octet-stream"
        return PreparedMedia(
            path=media_path,
            duration_seconds=duration_seconds,
            size_bytes=size_bytes,
            mime_type=mime_type,
            sha256=sha256_file(media_path),
            source_url=source_url,
            temporary_directory=temporary_directory,
        )
    except Exception:
        if temporary_directory is not None:
            shutil.rmtree(temporary_directory, ignore_errors=True)
        raise


def validate_public_https_url(url: str) -> None:
    parsed = urllib.parse.urlsplit(url)
    if parsed.scheme.lower() != "https" or not parsed.hostname:
        raise TranscriptionInputError("media URL must be an absolute HTTPS URL")
    hostname = parsed.hostname.lower().rstrip(".")
    if hostname == "localhost" or hostname.endswith(".localhost"):
        raise TranscriptionInputError("local media URLs are not allowed")
    try:
        address = ipaddress.ip_address(hostname)
    except ValueError:
        return
    if not address.is_global:
        raise TranscriptionInputError("private or non-global media URLs are not allowed")


def download_url(url: str, destination: Path, max_bytes: int, timeout_seconds: float) -> None:
    validate_resolved_public_https_url(url)
    request = urllib.request.Request(url, headers={"User-Agent": "codex-mcn-ops/0.1"})
    total = 0
    try:
        opener = urllib.request.build_opener(_SafeHTTPSRedirectHandler())
        with opener.open(request, timeout=timeout_seconds) as response, destination.open("wb") as output:
            while True:
                chunk = response.read(1024 * 1024)
                if not chunk:
                    break
                total += len(chunk)
                if total > max_bytes:
                    raise TranscriptionInputError(f"media download exceeds the {max_bytes}-byte limit")
                output.write(chunk)
    except TranscriptionInputError:
        destination.unlink(missing_ok=True)
        raise
    except (TimeoutError, urllib.error.URLError) as exc:
        destination.unlink(missing_ok=True)
        raise ProviderUnavailableError("failed to download transcription media", detail=str(exc)) from exc


def validate_resolved_public_https_url(url: str) -> None:
    validate_public_https_url(url)
    hostname = str(urllib.parse.urlsplit(url).hostname or "")
    try:
        addresses = {item[4][0] for item in socket.getaddrinfo(hostname, 443, type=socket.SOCK_STREAM)}
    except socket.gaierror as exc:
        raise ProviderUnavailableError("media hostname could not be resolved") from exc
    if not addresses:
        raise ProviderUnavailableError("media hostname resolved to no addresses")
    non_global = [ipaddress.ip_address(address) for address in addresses if not ipaddress.ip_address(address).is_global]
    proxy_synthetic_only = bool(non_global) and all(
        address in PROXY_SYNTHETIC_NETWORK for address in non_global
    )
    trusted_proxy_media = proxy_synthetic_only and any(
        hostname == suffix[1:] or hostname.endswith(suffix)
        for suffix in TRUSTED_DOUYIN_MEDIA_SUFFIXES
    )
    if non_global and not trusted_proxy_media:
        raise TranscriptionInputError("media hostname resolves to a private or non-global address")


class _SafeHTTPSRedirectHandler(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        validate_resolved_public_https_url(newurl)
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def probe_duration_seconds(path: Path, *, timeout_seconds: float = 20.0) -> float:
    command = [
        "ffprobe",
        "-v",
        "error",
        "-show_entries",
        "format=duration",
        "-of",
        "json",
        str(path),
    ]
    try:
        completed = subprocess.run(command, capture_output=True, text=True, timeout=timeout_seconds, check=False)
    except FileNotFoundError as exc:
        raise TranscriptionInputError("ffprobe is required to inspect media") from exc
    except subprocess.TimeoutExpired as exc:
        raise ProviderUnavailableError("ffprobe timed out") from exc
    if completed.returncode != 0:
        raise TranscriptionInputError(f"ffprobe failed: {completed.stderr.strip()[:200]}")
    try:
        return float(json.loads(completed.stdout)["format"]["duration"])
    except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
        raise TranscriptionInputError("ffprobe returned no valid duration") from exc


def normalize_audio(
    source: Path,
    destination: Path,
    *,
    timeout_seconds: float = 120.0,
) -> Path:
    destination.parent.mkdir(parents=True, exist_ok=True)
    command = [
        "ffmpeg",
        "-nostdin",
        "-y",
        "-i",
        str(source),
        "-vn",
        "-ac",
        "1",
        "-ar",
        "16000",
        "-codec:a",
        "libmp3lame",
        "-b:a",
        "32k",
        str(destination),
    ]
    try:
        completed = subprocess.run(command, capture_output=True, text=True, timeout=timeout_seconds, check=False)
    except FileNotFoundError as exc:
        raise TranscriptionInputError("ffmpeg is required to normalize media") from exc
    except subprocess.TimeoutExpired as exc:
        raise ProviderUnavailableError("ffmpeg timed out") from exc
    if completed.returncode != 0 or not destination.is_file():
        destination.unlink(missing_ok=True)
        raise TranscriptionInputError(f"ffmpeg failed: {completed.stderr.strip()[-300:]}")
    return destination


def normalize_prepared_media(media: PreparedMedia) -> PreparedMedia:
    """Convert video/unknown containers to a compact ASR-safe MP3."""
    if media.mime_type.startswith("audio/"):
        return media
    temporary_directory = media.temporary_directory
    owns_directory = temporary_directory is None
    if temporary_directory is None:
        temporary_directory = Path(tempfile.mkdtemp(prefix="mcn-asr-normalized-"))
    destination = temporary_directory / "normalized.mp3"
    try:
        normalize_audio(media.path, destination)
        return PreparedMedia(
            path=destination,
            duration_seconds=media.duration_seconds,
            size_bytes=destination.stat().st_size,
            mime_type="audio/mpeg",
            sha256=sha256_file(destination),
            # The original URL still points at the video/unknown container,
            # not at this normalized MP3. Long-ASR must upload the MP3.
            source_url=None,
            temporary_directory=temporary_directory,
        )
    except Exception:
        if owns_directory:
            shutil.rmtree(temporary_directory, ignore_errors=True)
        raise


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()
