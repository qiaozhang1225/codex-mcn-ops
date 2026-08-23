from __future__ import annotations

import hashlib
import ipaddress
import shutil
import socket
import tempfile
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from ..douyin.errors import ProviderUnavailableError, TranscriptionInputError
from .media_probe import _Isaac64
from .provider import ChannelsMediaLease


DEFAULT_DOWNLOAD_LIMIT_BYTES = 2 * 1024 * 1024 * 1024
ENCRYPTED_PREFIX_BYTES = 128 * 1024
PROXY_SYNTHETIC_NETWORK = ipaddress.ip_network("198.18.0.0/15")
TRUSTED_CHANNELS_MEDIA_SUFFIXES = (".video.qq.com",)


@dataclass
class ChannelsPreparedMedia:
    work_id: str
    path: Path
    size_bytes: int
    advertised_size_bytes: int
    size_matches_detail: bool
    sha256: str
    source_host: str
    decrypted_prefix_bytes: int
    temporary_directory: Path

    def cleanup(self) -> None:
        shutil.rmtree(self.temporary_directory, ignore_errors=True)


Downloader = Callable[[str, Path, int, float], None]


def acquire_channels_media(
    lease: ChannelsMediaLease,
    *,
    downloader: Downloader | None = None,
    download_limit_bytes: int = DEFAULT_DOWNLOAD_LIMIT_BYTES,
    timeout_seconds: float = 120.0,
) -> ChannelsPreparedMedia:
    if not lease.work_id.strip() or not lease.locator.strip():
        raise TranscriptionInputError("Channels media lease requires work_id and locator")
    _validate_channels_locator(lease.locator)
    temporary_directory = Path(tempfile.mkdtemp(prefix="mcn-channels-media-"))
    encrypted_path = temporary_directory / "encrypted.part"
    media_path = temporary_directory / f"{lease.work_id}.mp4"
    try:
        (downloader or _download_locator)(
            lease.locator,
            encrypted_path,
            download_limit_bytes,
            timeout_seconds,
        )
        size_bytes = encrypted_path.stat().st_size
        if size_bytes <= 0:
            raise TranscriptionInputError("Channels media download is empty")
        decrypted_bytes = _decrypt_prefix(encrypted_path, lease.decryption_key)
        _validate_media_header(encrypted_path)
        encrypted_path.replace(media_path)
        return ChannelsPreparedMedia(
            work_id=lease.work_id,
            path=media_path,
            size_bytes=size_bytes,
            advertised_size_bytes=lease.file_size,
            size_matches_detail=lease.file_size <= 0 or size_bytes == lease.file_size,
            sha256=_sha256_file(media_path),
            source_host=urllib.parse.urlsplit(lease.locator).hostname or "",
            decrypted_prefix_bytes=decrypted_bytes,
            temporary_directory=temporary_directory,
        )
    except Exception:
        shutil.rmtree(temporary_directory, ignore_errors=True)
        raise


def _download_locator(url: str, destination: Path, max_bytes: int, timeout_seconds: float) -> None:
    request = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"}, method="GET")
    total = 0
    try:
        with urllib.request.urlopen(request, timeout=timeout_seconds) as response, destination.open(
            "wb"
        ) as output:
            declared_size = _header_int(response.headers.get("Content-Length"))
            if declared_size > max_bytes:
                raise TranscriptionInputError("Channels media exceeds the configured size limit")
            while True:
                chunk = response.read(1024 * 1024)
                if not chunk:
                    break
                total += len(chunk)
                if total > max_bytes:
                    raise TranscriptionInputError("Channels media exceeds the configured size limit")
                output.write(chunk)
    except TranscriptionInputError:
        destination.unlink(missing_ok=True)
        raise
    except (TimeoutError, urllib.error.URLError) as exc:
        destination.unlink(missing_ok=True)
        raise ProviderUnavailableError(
            "failed to download Channels media",
            detail=type(exc).__name__,
        ) from exc


def _decrypt_prefix(path: Path, decryption_key: str) -> int:
    prefix_size = min(path.stat().st_size, ENCRYPTED_PREFIX_BYTES)
    with path.open("r+b") as handle:
        prefix = handle.read(prefix_size)
        if _looks_like_media_header(prefix):
            return 0
        if not decryption_key:
            raise TranscriptionInputError("encrypted Channels media has no decryption key")
        try:
            seed = int(decryption_key, 10)
        except ValueError as exc:
            raise TranscriptionInputError("Channels media decryption key is invalid") from exc
        key_stream = _Isaac64(seed).generate(len(prefix))
        decrypted = bytes(left ^ right for left, right in zip(prefix, key_stream, strict=True))
        handle.seek(0)
        handle.write(decrypted)
    return prefix_size


def _validate_media_header(path: Path) -> None:
    with path.open("rb") as handle:
        header = handle.read(64)
    if not _looks_like_media_header(header):
        raise TranscriptionInputError("decrypted Channels file has no recognized media header")


def _looks_like_media_header(value: bytes) -> bool:
    return any(marker in value[:64] for marker in (b"ftyp", b"styp", b"moov", b"mdat"))


def _validate_channels_locator(url: str) -> None:
    parsed = urllib.parse.urlsplit(url)
    if parsed.scheme.lower() != "https" or not parsed.hostname:
        raise TranscriptionInputError("Channels media locator must be absolute HTTPS")
    hostname = parsed.hostname.lower().rstrip(".")
    if not any(hostname == suffix[1:] or hostname.endswith(suffix) for suffix in TRUSTED_CHANNELS_MEDIA_SUFFIXES):
        raise TranscriptionInputError("Channels media locator host is not allowlisted")
    try:
        addresses = {
            item[4][0] for item in socket.getaddrinfo(hostname, 443, type=socket.SOCK_STREAM)
        }
    except socket.gaierror as exc:
        raise ProviderUnavailableError("Channels media hostname could not be resolved") from exc
    for address_text in addresses:
        address = ipaddress.ip_address(address_text)
        if address.is_global or address in PROXY_SYNTHETIC_NETWORK:
            continue
        raise TranscriptionInputError("Channels media hostname resolves to a private address")


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _header_int(value: str | None) -> int:
    try:
        return int(value or 0)
    except ValueError:
        return 0
