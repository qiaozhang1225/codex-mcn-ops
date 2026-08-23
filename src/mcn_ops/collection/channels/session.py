from __future__ import annotations

import hashlib
import json
import os
import secrets
import subprocess
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable, Mapping, Protocol

from ...store import Store
from ..task_contracts import ChannelsSessionStatus


DEFAULT_WINDOWS_HOST = "192.168.3.112"
DEFAULT_WINDOWS_USER = "qiaoz"
DEFAULT_WORKER_ID = "DEV-IyZU9C5DDMKxsY36"
DEFAULT_HUB_URL = "ws://192.168.3.120:18081/ws/client"
DEFAULT_SSH_KEY = Path("/Users/qiaoz-macmini/.ssh/codex_windows_collector_ed25519")
DEFAULT_KNOWN_HOSTS = Path(
    "/Users/qiaoz-macmini/.ssh/codex_windows_collector_known_hosts"
)
DEFAULT_REMOTE_SCRIPT = r"D:\wx-channel-poc\manage-wx-channel-session.ps1"
DEFAULT_WORKER_EXECUTABLE = (
    r"D:\wx-channel-poc\wx_channel_cloud_hardened_v5.6.9.exe"
)
DEFAULT_CERTIFICATE_THUMBPRINT = "D70CD039051F77C30673B8209FC15EFA650ED52C"
DEFAULT_WORKER_SHA256 = (
    "C5CFF437248220EDD113403987E6C3005136A23AEE2B410E09736DD26BD2B0EA"
)
NON_TERMINAL_SESSION_STATES = {
    ChannelsSessionStatus.PROVISIONING.value,
    ChannelsSessionStatus.ACTIVE.value,
    ChannelsSessionStatus.DEGRADED.value,
    ChannelsSessionStatus.CLEANUP_PENDING.value,
    ChannelsSessionStatus.CLEANUP_FAILED.value,
}


class ChannelsSessionError(RuntimeError):
    """The task-bound Windows acquisition session could not be used safely."""


class ChannelsSessionBusyError(ChannelsSessionError):
    """The pinned Windows worker belongs to another non-terminal session."""


class ChannelsSessionConflictError(ChannelsSessionError):
    """A stale session or lease generation attempted to mutate current state."""


class ChannelsSessionTransportError(ChannelsSessionError):
    """The authenticated SSH command failed without exposing its payload."""


class ChannelsSessionTimeoutError(ChannelsSessionTransportError, TimeoutError):
    """The Windows session command exceeded its bounded timeout."""


class SessionGuard(Protocol):
    @property
    def worker_id(self) -> str: ...

    @property
    def shared_secret(self) -> str: ...

    def ensure_active(self) -> dict[str, Any]: ...

    def refresh_page(self) -> dict[str, Any]: ...


@dataclass(frozen=True)
class ChannelsAcquisitionConfig:
    windows_host: str = DEFAULT_WINDOWS_HOST
    windows_user: str = DEFAULT_WINDOWS_USER
    worker_id: str = DEFAULT_WORKER_ID
    ssh_executable: str = "/usr/bin/ssh"
    ssh_key_path: Path = DEFAULT_SSH_KEY
    known_hosts_path: Path = DEFAULT_KNOWN_HOSTS
    remote_script: str = DEFAULT_REMOTE_SCRIPT
    runtime_dir: Path = Path("data/runtime/channels-sessions")
    hub_url: str = DEFAULT_HUB_URL
    lease_ttl_seconds: int = 3600
    renew_margin_seconds: int = 900
    connect_timeout_seconds: int = 10
    command_timeout_seconds: int = 120
    certificate_thumbprint: str = DEFAULT_CERTIFICATE_THUMBPRINT
    worker_executable: str = DEFAULT_WORKER_EXECUTABLE
    worker_sha256: str = DEFAULT_WORKER_SHA256

    @classmethod
    def from_env(
        cls,
        env: Mapping[str, str] | None = None,
    ) -> "ChannelsAcquisitionConfig":
        values = os.environ if env is None else env
        config = cls(
            windows_host=_env_text(values, "CHANNELS_WINDOWS_HOST", DEFAULT_WINDOWS_HOST),
            windows_user=_env_text(values, "CHANNELS_WINDOWS_USER", DEFAULT_WINDOWS_USER),
            worker_id=_env_text(values, "CHANNELS_WORKER_ID", DEFAULT_WORKER_ID),
            ssh_executable=_env_text(values, "CHANNELS_SSH_EXECUTABLE", "/usr/bin/ssh"),
            ssh_key_path=Path(
                _env_text(values, "CHANNELS_SSH_KEY", str(DEFAULT_SSH_KEY))
            ).expanduser(),
            known_hosts_path=Path(
                _env_text(
                    values,
                    "CHANNELS_SSH_KNOWN_HOSTS",
                    str(DEFAULT_KNOWN_HOSTS),
                )
            ).expanduser(),
            remote_script=_env_text(
                values, "CHANNELS_WINDOWS_SESSION_SCRIPT", DEFAULT_REMOTE_SCRIPT
            ),
            runtime_dir=Path(
                _env_text(
                    values,
                    "CHANNELS_SESSION_RUNTIME_DIR",
                    "data/runtime/channels-sessions",
                )
            ).expanduser(),
            hub_url=_env_text(values, "CHANNELS_WORKER_HUB_URL", DEFAULT_HUB_URL),
            lease_ttl_seconds=_env_int(values, "CHANNELS_SESSION_TTL_SECONDS", 3600),
            renew_margin_seconds=_env_int(
                values, "CHANNELS_SESSION_RENEW_MARGIN_SECONDS", 900
            ),
            connect_timeout_seconds=_env_int(
                values, "CHANNELS_SSH_CONNECT_TIMEOUT_SECONDS", 10
            ),
            command_timeout_seconds=_env_int(
                values, "CHANNELS_SSH_COMMAND_TIMEOUT_SECONDS", 120
            ),
            certificate_thumbprint=_env_text(
                values,
                "CHANNELS_CERTIFICATE_THUMBPRINT",
                DEFAULT_CERTIFICATE_THUMBPRINT,
            ).upper(),
            worker_executable=_env_text(
                values, "CHANNELS_WORKER_EXECUTABLE", DEFAULT_WORKER_EXECUTABLE
            ),
            worker_sha256=_env_text(
                values, "CHANNELS_WORKER_SHA256", DEFAULT_WORKER_SHA256
            ).upper(),
        )
        config.validate()
        return config

    @property
    def worker_key(self) -> str:
        return f"{self.windows_host}:{self.windows_user}:{self.worker_id}"

    def validate(self) -> None:
        for label, value in (
            ("windows_host", self.windows_host),
            ("windows_user", self.windows_user),
            ("worker_id", self.worker_id),
            ("ssh_executable", self.ssh_executable),
            ("remote_script", self.remote_script),
            ("hub_url", self.hub_url),
        ):
            if not str(value).strip():
                raise ValueError(f"{label} is required")
        if self.lease_ttl_seconds < 300 or self.lease_ttl_seconds > 14400:
            raise ValueError("lease_ttl_seconds must be between 300 and 14400")
        if self.renew_margin_seconds < 1 or self.renew_margin_seconds >= self.lease_ttl_seconds:
            raise ValueError("renew_margin_seconds must be positive and below the lease TTL")
        if self.connect_timeout_seconds < 1 or self.command_timeout_seconds < 1:
            raise ValueError("SSH timeouts must be positive")
        if len(self.certificate_thumbprint) != 40:
            raise ValueError("certificate_thumbprint must be a SHA-1 thumbprint")
        if len(self.worker_sha256) != 64:
            raise ValueError("worker_sha256 must be a SHA-256 digest")


Runner = Callable[..., subprocess.CompletedProcess[str]]


class WindowsSshTransport:
    """Execute the pinned Windows session manager without placing secrets in argv."""

    def __init__(
        self,
        config: ChannelsAcquisitionConfig,
        *,
        runner: Runner = subprocess.run,
    ) -> None:
        config.validate()
        self.config = config
        self._runner = runner

    def run(
        self,
        action: str,
        *,
        session_id: str | None = None,
        expected_generation: int | None = None,
        reason: str | None = None,
        payload: Mapping[str, Any] | None = None,
    ) -> dict[str, Any]:
        normalized_action = str(action).strip().title()
        if normalized_action not in {"Open", "Renew", "Status", "Close", "Recover", "Refresh"}:
            raise ValueError(f"unsupported Channels session action: {action}")
        command = self._base_command()
        command.extend(["-Action", normalized_action])
        if session_id:
            command.extend(["-SessionId", _safe_identifier(session_id, "session_id")])
        if expected_generation is not None:
            if int(expected_generation) < 1:
                raise ValueError("expected_generation must be positive")
            command.extend(["-ExpectedGeneration", str(int(expected_generation))])
        if reason:
            command.extend(["-Reason", _safe_reason(reason)])
        stdin_text = ""
        if payload is not None:
            stdin_text = json.dumps(dict(payload), ensure_ascii=False, separators=(",", ":"))
        try:
            completed = self._runner(
                command,
                input=stdin_text,
                text=True,
                encoding="utf-8",
                errors="replace",
                capture_output=True,
                check=False,
                shell=False,
                timeout=self.config.command_timeout_seconds,
            )
        except subprocess.TimeoutExpired as exc:
            raise ChannelsSessionTimeoutError(
                f"Windows Channels {normalized_action} timed out on {self.config.windows_host}"
            ) from exc
        except OSError as exc:
            raise ChannelsSessionTransportError(
                f"Windows Channels {normalized_action} could not start SSH transport"
            ) from exc
        if completed.returncode != 0:
            raise ChannelsSessionTransportError(
                f"Windows Channels {normalized_action} failed with exit code {completed.returncode}"
            )
        try:
            result = json.loads(completed.stdout)
        except (TypeError, json.JSONDecodeError) as exc:
            raise ChannelsSessionTransportError(
                f"Windows Channels {normalized_action} returned invalid JSON"
            ) from exc
        if not isinstance(result, dict) or result.get("ok") is not True:
            raise ChannelsSessionTransportError(
                f"Windows Channels {normalized_action} did not return an ok result"
            )
        return result

    def _base_command(self) -> list[str]:
        return [
            self.config.ssh_executable,
            "-i",
            str(self.config.ssh_key_path),
            "-o",
            "BatchMode=yes",
            "-o",
            "IdentitiesOnly=yes",
            "-o",
            "StrictHostKeyChecking=yes",
            "-o",
            f"UserKnownHostsFile={self.config.known_hosts_path}",
            "-o",
            f"ConnectTimeout={self.config.connect_timeout_seconds}",
            f"{self.config.windows_user}@{self.config.windows_host}",
            "powershell.exe",
            "-NoProfile",
            "-NonInteractive",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            self.config.remote_script,
        ]


@dataclass(frozen=True)
class _Credentials:
    path: Path
    cloud_secret: str
    secret_token: str
    sha256: str


class ChannelsAcquisitionController:
    """Keep one Windows acquisition lease aligned with one collection task."""

    def __init__(
        self,
        store: Store,
        task_id: str,
        *,
        config: ChannelsAcquisitionConfig | None = None,
        transport: WindowsSshTransport | None = None,
    ) -> None:
        self.store = store
        self.task_id = _safe_identifier(task_id, "task_id")
        self.config = config or ChannelsAcquisitionConfig.from_env()
        self.config.validate()
        self.transport = transport or WindowsSshTransport(self.config)

    @property
    def worker_id(self) -> str:
        return self.config.worker_id

    @property
    def shared_secret(self) -> str:
        return self._credentials().cloud_secret

    def ensure_active(self) -> dict[str, Any]:
        session = self._open_session()
        if session is None:
            return self._create_and_open()
        if session["status"] in {
            ChannelsSessionStatus.CLEANUP_PENDING.value,
            ChannelsSessionStatus.CLEANUP_FAILED.value,
        }:
            raise ChannelsSessionError(
                f"Channels session {session['id']} requires cleanup before acquisition"
            )

        try:
            remote = self._remote_status(session)
        except ChannelsSessionError as exc:
            self._mark_degraded(session, exc, event_type="session_status_failed")
            raise
        remote_status = _status_body(remote)
        if not bool(remote_status.get("session_present")):
            if not _remote_artifacts_absent(remote_status):
                raise ChannelsSessionError(
                    "Windows lease is missing but pinned acquisition artifacts remain"
                )
            self._mark_absent_expired(session)
            self._delete_credentials()
            return self._create_and_open()
        remote_state = str(remote_status.get("state") or "")
        if remote_state in {
            ChannelsSessionStatus.CLEANED.value,
            ChannelsSessionStatus.EXPIRED.value,
        }:
            self._mark_expired(session, remote_status)
            self._delete_credentials()
            return self._create_and_open()
        if remote_state in {
            ChannelsSessionStatus.CLEANUP_PENDING.value,
            ChannelsSessionStatus.CLEANUP_FAILED.value,
        }:
            raise ChannelsSessionError(
                f"Windows Channels session {session['id']} requires cleanup"
            )

        remote_generation = _remote_generation(remote_status)
        local_generation = _lease_generation(session)
        if remote_generation < local_generation or remote_generation > local_generation + 1:
            raise ChannelsSessionConflictError(
                f"Channels lease generation conflict: local {local_generation}, remote {remote_generation}"
            )
        if remote_generation == local_generation + 1:
            session = self._update_active(
                session,
                remote_status,
                lease_generation=remote_generation,
                event_type="lease_generation_reconciled",
            )
            local_generation = remote_generation

        if _remote_is_healthy(remote_status):
            if session["status"] != ChannelsSessionStatus.ACTIVE.value:
                session = self._update_active(
                    session,
                    remote_status,
                    lease_generation=local_generation,
                    event_type="session_reconciled_active",
                )
            if self._needs_renewal(remote_status):
                return self.renew(expected_generation=local_generation)
            return session

        if session["status"] == ChannelsSessionStatus.PROVISIONING.value:
            self.close(
                reason="incomplete_provisioning",
                expected_generation=local_generation,
            )
            return self._create_and_open()
        return self.recover(expected_generation=local_generation)

    def renew(self, *, expected_generation: int | None = None) -> dict[str, Any]:
        session = self._require_open_session()
        generation = self._require_generation(session, expected_generation)
        try:
            result = self.transport.run(
                "Renew",
                session_id=session["id"],
                expected_generation=generation,
                payload={"ttl_seconds": self.config.lease_ttl_seconds},
            )
            remote = _status_body(result)
            _require_remote_identity(session, remote)
            if _remote_generation(remote) != generation + 1 or not _remote_is_healthy(remote):
                raise ChannelsSessionConflictError("Windows renewal returned inconsistent state")
            return self._update_active(
                session,
                remote,
                lease_generation=generation + 1,
                event_type="lease_renewed",
            )
        except ChannelsSessionError as exc:
            self._mark_degraded(session, exc, event_type="lease_renew_failed")
            raise

    def status(self) -> dict[str, Any]:
        session = self._open_session()
        result = self.transport.run("Status")
        remote = _status_body(result)
        if session is not None and bool(remote.get("session_present")):
            _require_remote_identity(session, remote)
        return {"session": session, "remote": remote}

    def refresh_page(self) -> dict[str, Any]:
        session = self._require_open_session()
        generation = _lease_generation(session)
        prior_events = self.store.list_channels_acquisition_events(session_id=session["id"])
        if any(
            event["event_type"] == "page_refreshed"
            and int(event.get("payload", {}).get("lease_generation") or 0) == generation
            for event in prior_events
        ):
            return {
                "ok": True,
                "action": "refresh",
                "reused": True,
                "status": {"session_id": session["id"], "generation": generation},
            }
        result = self.transport.run(
            "Refresh",
            session_id=session["id"],
            expected_generation=generation,
        )
        remote = _status_body(result)
        _require_remote_identity(session, remote)
        if not _remote_is_healthy(remote):
            raise ChannelsSessionError("Windows page refresh returned an unhealthy session")
        self.store.append_channels_acquisition_event(
            session_id=session["id"],
            event_type="page_refreshed",
            payload={"lease_generation": generation},
        )
        return result

    def close(
        self,
        *,
        reason: str,
        expected_generation: int | None = None,
    ) -> dict[str, Any]:
        session = self._open_session(include_terminal=True)
        if session is None:
            self._delete_credentials()
            return {"status": ChannelsSessionStatus.CLEANED.value, "reused": True}
        if session["status"] in {
            ChannelsSessionStatus.CLEANED.value,
            ChannelsSessionStatus.EXPIRED.value,
        }:
            self._delete_credentials()
            return session
        generation = self._require_generation(session, expected_generation)
        pending = session
        if session["status"] != ChannelsSessionStatus.CLEANUP_PENDING.value:
            pending = self.store.update_channels_acquisition_session(
                session["id"],
                expected_state_version=session["state_version"],
                status=ChannelsSessionStatus.CLEANUP_PENDING.value,
                metadata=self._metadata(generation),
                event_type="cleanup_requested",
                event_payload={"reason": _safe_reason(reason)},
            )
        try:
            result = self.transport.run(
                "Close",
                session_id=session["id"],
                expected_generation=generation,
                reason=reason,
            )
            remote = _status_body(result)
            _require_remote_identity(session, remote)
            if not _remote_cleanup_verified(remote):
                raise ChannelsSessionError("Windows cleanup verification failed")
            cleaned = self.store.update_channels_acquisition_session(
                session["id"],
                expected_state_version=pending["state_version"],
                status=ChannelsSessionStatus.CLEANED.value,
                cleanup_verified=True,
                metadata=self._metadata(generation),
                event_type="cleanup_verified",
                event_payload={"reason": _safe_reason(reason)},
            )
            self._delete_credentials()
            return cleaned
        except ChannelsSessionError as exc:
            current = self.store.get_channels_acquisition_session(session["id"])
            if current and current["status"] == ChannelsSessionStatus.CLEANUP_PENDING.value:
                self.store.update_channels_acquisition_session(
                    session["id"],
                    expected_state_version=current["state_version"],
                    status=ChannelsSessionStatus.CLEANUP_FAILED.value,
                    metadata=self._metadata(generation),
                    error={"type": type(exc).__name__, "message": str(exc)},
                    event_type="cleanup_failed",
                )
            raise

    def recover(self, *, expected_generation: int | None = None) -> dict[str, Any]:
        session = self._require_open_session()
        generation = self._require_generation(session, expected_generation)
        credentials = self._credentials()
        try:
            result = self.transport.run(
                "Recover",
                session_id=session["id"],
                expected_generation=generation,
                payload=self._open_payload(credentials),
            )
            remote = _status_body(result)
            _require_remote_identity(session, remote)
            if _remote_generation(remote) != generation + 1 or not _remote_is_healthy(remote):
                raise ChannelsSessionConflictError("Windows recovery returned inconsistent state")
            return self._update_active(
                session,
                remote,
                lease_generation=generation + 1,
                event_type="session_recovered",
            )
        except ChannelsSessionError as exc:
            self._mark_degraded(session, exc, event_type="session_recovery_failed")
            raise

    def _create_and_open(self) -> dict[str, Any]:
        preflight = _status_body(self.transport.run("Status"))
        if bool(preflight.get("session_present")):
            if str(preflight.get("state")) not in {
                "absent",
                ChannelsSessionStatus.CLEANED.value,
                ChannelsSessionStatus.EXPIRED.value,
            }:
                raise ChannelsSessionBusyError(
                    "Windows Channels worker has another active session"
                )
            if not _remote_cleanup_verified(preflight):
                raise ChannelsSessionError(
                    "Windows Channels worker reports a terminal lease with residual artifacts"
                )
        elif not _remote_artifacts_absent(preflight):
            raise ChannelsSessionError(
                "Windows Channels worker has residual artifacts without a lease"
            )
        credentials = self._credentials()
        expires_at = _future_iso(self.config.lease_ttl_seconds)
        try:
            session = self.store.create_channels_acquisition_session(
                task_id=self.task_id,
                worker_key=self.config.worker_key,
                windows_host=self.config.windows_host,
                certificate_thumbprint=self.config.certificate_thumbprint,
                worker_executable=self.config.worker_executable,
                lease_expires_at=expires_at,
                metadata=self._metadata(1, credentials),
            )
        except RuntimeError as exc:
            raise ChannelsSessionBusyError(str(exc)) from exc
        try:
            result = self.transport.run(
                "Open",
                session_id=session["id"],
                payload=self._open_payload(credentials),
            )
            remote = _status_body(result)
            _require_remote_identity(session, remote)
            if _remote_generation(remote) != 1 or not _remote_is_healthy(remote):
                raise ChannelsSessionConflictError("Windows open returned inconsistent state")
            return self._update_active(
                session,
                remote,
                lease_generation=1,
                event_type="session_opened",
            )
        except ChannelsSessionError as exc:
            self._mark_degraded(session, exc, event_type="session_open_failed")
            raise

    def _remote_status(self, session: dict[str, Any]) -> dict[str, Any]:
        result = self.transport.run("Status")
        remote = _status_body(result)
        if bool(remote.get("session_present")):
            _require_remote_identity(session, remote)
        return result

    def _update_active(
        self,
        session: dict[str, Any],
        remote: Mapping[str, Any],
        *,
        lease_generation: int,
        event_type: str,
    ) -> dict[str, Any]:
        return self.store.update_channels_acquisition_session(
            session["id"],
            expected_state_version=session["state_version"],
            status=ChannelsSessionStatus.ACTIVE.value,
            lease_expires_at=str(remote.get("expires_at") or session["lease_expires_at"]),
            heartbeat=True,
            metadata=self._metadata(lease_generation),
            event_type=event_type,
            event_payload={"lease_generation": lease_generation},
        )

    def _mark_degraded(
        self,
        session: dict[str, Any],
        error: Exception,
        *,
        event_type: str,
    ) -> None:
        current = self.store.get_channels_acquisition_session(session["id"])
        if current is None or current["status"] not in {
            ChannelsSessionStatus.PROVISIONING.value,
            ChannelsSessionStatus.ACTIVE.value,
            ChannelsSessionStatus.DEGRADED.value,
        }:
            return
        self.store.update_channels_acquisition_session(
            session["id"],
            expected_state_version=current["state_version"],
            status=ChannelsSessionStatus.DEGRADED.value,
            metadata=self._metadata(_lease_generation(current)),
            error={"type": type(error).__name__, "message": str(error)},
            event_type=event_type,
        )

    def _mark_expired(
        self,
        session: dict[str, Any],
        remote: Mapping[str, Any],
    ) -> dict[str, Any]:
        if not _remote_cleanup_verified(remote):
            raise ChannelsSessionError("expired Windows lease has not completed cleanup")
        return self.store.update_channels_acquisition_session(
            session["id"],
            expected_state_version=session["state_version"],
            status=ChannelsSessionStatus.EXPIRED.value,
            metadata=self._metadata(_remote_generation(remote)),
            event_type="lease_expired",
        )

    def _mark_absent_expired(self, session: dict[str, Any]) -> dict[str, Any]:
        return self.store.update_channels_acquisition_session(
            session["id"],
            expected_state_version=session["state_version"],
            status=ChannelsSessionStatus.EXPIRED.value,
            metadata=self._metadata(_lease_generation(session)),
            event_type="lease_absent_and_artifacts_clean",
        )

    def _needs_renewal(self, remote: Mapping[str, Any]) -> bool:
        try:
            expires_at = datetime.fromisoformat(str(remote["expires_at"]))
        except (KeyError, TypeError, ValueError) as exc:
            raise ChannelsSessionConflictError("Windows lease expiry is invalid") from exc
        if expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=timezone.utc)
        return expires_at.astimezone(timezone.utc) <= datetime.now(timezone.utc) + timedelta(
            seconds=self.config.renew_margin_seconds
        )

    def _open_session(self, *, include_terminal: bool = False) -> dict[str, Any] | None:
        sessions = self.store.list_channels_acquisition_sessions(task_id=self.task_id)
        if include_terminal:
            return sessions[-1] if sessions else None
        open_sessions = [item for item in sessions if item["status"] in NON_TERMINAL_SESSION_STATES]
        if len(open_sessions) > 1:
            raise ChannelsSessionConflictError("task has multiple non-terminal Channels sessions")
        return open_sessions[0] if open_sessions else None

    def _require_open_session(self) -> dict[str, Any]:
        session = self._open_session()
        if session is None:
            raise ChannelsSessionError(f"task {self.task_id} has no open Channels session")
        return session

    def _require_generation(
        self,
        session: Mapping[str, Any],
        expected_generation: int | None,
    ) -> int:
        current = _lease_generation(session)
        if expected_generation is not None and int(expected_generation) != current:
            raise ChannelsSessionConflictError(
                f"stale Channels lease generation: expected {expected_generation}, current {current}"
            )
        return current

    def _credential_path(self) -> Path:
        digest = hashlib.sha256(self.task_id.encode("utf-8")).hexdigest()[:24]
        return self.config.runtime_dir / f"{digest}.json"

    def _credentials(self) -> _Credentials:
        path = self._credential_path()
        if path.is_file():
            raw = path.read_bytes()
            try:
                value = json.loads(raw.decode("utf-8"))
            except (UnicodeDecodeError, json.JSONDecodeError) as exc:
                raise ChannelsSessionError("Channels credential file is invalid") from exc
            cloud_secret = str(value.get("cloud_secret") or "")
            secret_token = str(value.get("secret_token") or "")
            if not cloud_secret or not secret_token:
                raise ChannelsSessionError("Channels credential file is incomplete")
            path.chmod(0o600)
            return _Credentials(
                path=path,
                cloud_secret=cloud_secret,
                secret_token=secret_token,
                sha256=hashlib.sha256(raw).hexdigest(),
            )
        path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        path.parent.chmod(0o700)
        value = {
            "cloud_secret": secrets.token_urlsafe(32),
            "secret_token": secrets.token_urlsafe(32),
        }
        raw = json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8")
        temporary = path.with_name(f".{path.name}.{secrets.token_hex(8)}.tmp")
        descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        try:
            with os.fdopen(descriptor, "wb") as handle:
                handle.write(raw)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary, path)
            path.chmod(0o600)
        finally:
            if temporary.exists():
                temporary.unlink()
        return _Credentials(
            path=path,
            cloud_secret=str(value["cloud_secret"]),
            secret_token=str(value["secret_token"]),
            sha256=hashlib.sha256(raw).hexdigest(),
        )

    def _delete_credentials(self) -> None:
        path = self._credential_path()
        if path.exists():
            path.unlink()

    def _metadata(
        self,
        lease_generation: int,
        credentials: _Credentials | None = None,
    ) -> dict[str, Any]:
        credentials = credentials or self._credentials()
        return {
            "lease_generation": int(lease_generation),
            "credential_ref": str(credentials.path),
            "credential_sha256": credentials.sha256,
            "worker_id": self.config.worker_id,
            "windows_user": self.config.windows_user,
            "worker_sha256": self.config.worker_sha256,
        }

    def _open_payload(self, credentials: _Credentials) -> dict[str, Any]:
        return {
            "task_id": self.task_id,
            "ttl_seconds": self.config.lease_ttl_seconds,
            "hub_url": self.config.hub_url,
            "cloud_secret": credentials.cloud_secret,
            "secret_token": credentials.secret_token,
        }


def _env_text(values: Mapping[str, str], key: str, default: str) -> str:
    return str(values.get(key, default)).strip()


def _env_int(values: Mapping[str, str], key: str, default: int) -> int:
    try:
        return int(values.get(key, str(default)))
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{key} must be an integer") from exc


def _safe_identifier(value: str, label: str) -> str:
    normalized = str(value or "").strip()
    if not normalized or not normalized.isascii() or len(normalized) > 120 or not all(
        character.isalnum() or character in {"_", "-"} for character in normalized
    ):
        raise ValueError(f"{label} must use 1-120 safe characters")
    return normalized


def _safe_reason(value: str) -> str:
    normalized = str(value or "").strip()
    if not normalized or not normalized.isascii() or len(normalized) > 120 or not all(
        character.isalnum() or character in {"_", "-", ".", ":"}
        for character in normalized
    ):
        raise ValueError("reason must use 1-120 safe characters")
    return normalized


def _future_iso(seconds: int) -> str:
    return (datetime.now(timezone.utc) + timedelta(seconds=seconds)).isoformat()


def _status_body(result: Mapping[str, Any]) -> dict[str, Any]:
    status = result.get("status")
    if not isinstance(status, dict):
        raise ChannelsSessionTransportError("Windows Channels result has no status object")
    return dict(status)


def _lease_generation(session: Mapping[str, Any]) -> int:
    metadata = session.get("metadata")
    value = metadata.get("lease_generation") if isinstance(metadata, dict) else None
    try:
        generation = int(value or 1)
    except (TypeError, ValueError) as exc:
        raise ChannelsSessionConflictError("stored Channels lease generation is invalid") from exc
    if generation < 1:
        raise ChannelsSessionConflictError("stored Channels lease generation is invalid")
    return generation


def _remote_generation(remote: Mapping[str, Any]) -> int:
    try:
        generation = int(remote.get("generation") or 0)
    except (TypeError, ValueError) as exc:
        raise ChannelsSessionConflictError("Windows lease generation is invalid") from exc
    if generation < 1:
        raise ChannelsSessionConflictError("Windows lease generation is invalid")
    return generation


def _require_remote_identity(
    session: Mapping[str, Any],
    remote: Mapping[str, Any],
) -> None:
    if str(remote.get("session_id") or "") != str(session["id"]):
        raise ChannelsSessionConflictError("Windows session id does not match the database")
    if str(remote.get("task_id") or "") != str(session["task_id"]):
        raise ChannelsSessionConflictError("Windows task id does not match the database")


def _remote_is_healthy(remote: Mapping[str, Any]) -> bool:
    return (
        str(remote.get("state") or "") == ChannelsSessionStatus.ACTIVE.value
        and int(remote.get("current_user_certificate_count") or 0) == 1
        and int(remote.get("local_machine_certificate_count") or 0) == 0
        and int(remote.get("worker_process_count") or 0) == 1
        and bool(remote.get("firewall_block_enabled"))
    )


def _remote_cleanup_verified(remote: Mapping[str, Any]) -> bool:
    return (
        str(remote.get("state") or "")
        in {ChannelsSessionStatus.CLEANED.value, ChannelsSessionStatus.EXPIRED.value}
        and int(remote.get("current_user_certificate_count") or 0) == 0
        and int(remote.get("local_machine_certificate_count") or 0) == 0
        and int(remote.get("worker_process_count") or 0) == 0
        and int(remote.get("listener_count") or 0) == 0
    )


def _remote_artifacts_absent(remote: Mapping[str, Any]) -> bool:
    return (
        int(remote.get("current_user_certificate_count") or 0) == 0
        and int(remote.get("local_machine_certificate_count") or 0) == 0
        and int(remote.get("worker_process_count") or 0) == 0
        and int(remote.get("listener_count") or 0) == 0
    )
