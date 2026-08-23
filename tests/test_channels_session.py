from __future__ import annotations

import asyncio
import json
import stat
import subprocess
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from mcn_ops.collection.channels.provider import (
    ChannelsRemoteConfig,
    ChannelsRemoteProvider,
)
from mcn_ops.collection.channels.session import (
    DEFAULT_KNOWN_HOSTS,
    DEFAULT_SSH_KEY,
    ChannelsAcquisitionConfig,
    ChannelsAcquisitionController,
    ChannelsSessionBusyError,
    ChannelsSessionConflictError,
    ChannelsSessionError,
    ChannelsSessionTimeoutError,
    WindowsSshTransport,
)
from mcn_ops.migrations import migrate_collection_task_orchestration_v1
from mcn_ops.store import Store


def _iso_after(seconds: int) -> str:
    return (datetime.now(timezone.utc) + timedelta(seconds=seconds)).isoformat()


class FakeWindowsTransport:
    def __init__(self) -> None:
        self.calls: list[dict] = []
        self.remote: dict | None = None
        self.fail_action: str | None = None

    def run(
        self,
        action: str,
        *,
        session_id: str | None = None,
        expected_generation: int | None = None,
        reason: str | None = None,
        payload: dict | None = None,
    ) -> dict:
        self.calls.append(
            {
                "action": action,
                "session_id": session_id,
                "expected_generation": expected_generation,
                "reason": reason,
                "payload": dict(payload or {}),
            }
        )
        if self.fail_action == action:
            raise ChannelsSessionTimeoutError(f"fake {action} timeout")
        if action == "Status":
            return {"ok": True, "action": "status", "status": self._status()}
        if action == "Refresh":
            assert self.remote is not None
            assert expected_generation == self.remote["generation"]
            return {"ok": True, "action": "refresh", "status": self._status()}
        if action == "Open":
            assert session_id
            assert payload
            self.remote = self._healthy(
                session_id=session_id,
                task_id=str(payload["task_id"]),
                generation=1,
            )
            return {"ok": True, "action": "open", "status": self._status()}
        if action == "Renew":
            assert self.remote is not None
            assert expected_generation == self.remote["generation"]
            self.remote["generation"] += 1
            self.remote["expires_at"] = _iso_after(3600)
            return {"ok": True, "action": "renew", "status": self._status()}
        if action == "Recover":
            assert self.remote is not None
            assert expected_generation == self.remote["generation"]
            self.remote = self._healthy(
                session_id=str(self.remote["session_id"]),
                task_id=str(self.remote["task_id"]),
                generation=int(self.remote["generation"]) + 1,
            )
            return {"ok": True, "action": "recover", "status": self._status()}
        if action == "Close":
            assert self.remote is not None
            assert expected_generation == self.remote["generation"]
            self.remote.update(
                {
                    "state": "cleaned",
                    "current_user_certificate_count": 0,
                    "local_machine_certificate_count": 0,
                    "worker_process_count": 0,
                    "listener_count": 0,
                }
            )
            return {"ok": True, "action": "close", "status": self._status()}
        raise AssertionError(action)

    def _status(self) -> dict:
        if self.remote is None:
            return {
                "session_present": False,
                "state": "absent",
                "generation": 0,
                "current_user_certificate_count": 0,
                "local_machine_certificate_count": 0,
                "worker_process_count": 0,
                "listener_count": 0,
            }
        return dict(self.remote)

    @staticmethod
    def _healthy(*, session_id: str, task_id: str, generation: int) -> dict:
        return {
            "session_present": True,
            "session_id": session_id,
            "task_id": task_id,
            "state": "active",
            "generation": generation,
            "expires_at": _iso_after(3600),
            "current_user_certificate_count": 1,
            "local_machine_certificate_count": 0,
            "worker_process_count": 1,
            "listener_count": 2,
            "firewall_block_enabled": True,
        }


def _store(tmp_path: Path) -> tuple[Store, str]:
    store = Store(tmp_path / "mcn.sqlite")
    store.init_db()
    migrate_collection_task_orchestration_v1(store.db_path)
    task_id = store.create_collection_task(
        command="collect Channels task",
        target_scope="keyword",
        target_count_per_role=20,
        topic="宋立心理",
        parsed={"provider": "wechat_channels_remote"},
    )
    return store, task_id


def _config(tmp_path: Path) -> ChannelsAcquisitionConfig:
    return ChannelsAcquisitionConfig(
        ssh_key_path=tmp_path / "id_ed25519",
        known_hosts_path=tmp_path / "known_hosts",
        runtime_dir=tmp_path / "runtime",
    )


def _controller(
    tmp_path: Path,
    transport: FakeWindowsTransport | None = None,
) -> tuple[ChannelsAcquisitionController, Store, str, FakeWindowsTransport]:
    store, task_id = _store(tmp_path)
    fake = transport or FakeWindowsTransport()
    controller = ChannelsAcquisitionController(
        store,
        task_id,
        config=_config(tmp_path),
        transport=fake,  # type: ignore[arg-type]
    )
    return controller, store, task_id, fake


def test_config_defaults_match_the_pinned_windows_tool_host() -> None:
    config = ChannelsAcquisitionConfig.from_env({})
    assert config.windows_host == "192.168.3.112"
    assert config.windows_user == "qiaoz"
    assert config.worker_id == "DEV-IyZU9C5DDMKxsY36"
    assert config.ssh_key_path == DEFAULT_SSH_KEY
    assert config.known_hosts_path == DEFAULT_KNOWN_HOSTS


def test_ssh_transport_is_strict_and_sends_secrets_only_over_stdin(tmp_path: Path) -> None:
    captured: dict = {}

    def runner(command, **kwargs):
        captured["command"] = list(command)
        captured.update(kwargs)
        return subprocess.CompletedProcess(
            command,
            0,
            stdout=json.dumps(
                {"ok": True, "status": {"session_present": False, "state": "absent"}}
            ),
            stderr="",
        )

    transport = WindowsSshTransport(_config(tmp_path), runner=runner)
    cloud_secret = "cloud-secret-value-which-is-private-123456"
    secret_token = "local-token-value-which-is-private-1234567"
    transport.run(
        "Open",
        session_id="chsession_123456789abc",
        payload={"cloud_secret": cloud_secret, "secret_token": secret_token},
    )
    command_text = " ".join(captured["command"])
    assert "BatchMode=yes" in captured["command"]
    assert "IdentitiesOnly=yes" in captured["command"]
    assert "StrictHostKeyChecking=yes" in captured["command"]
    assert cloud_secret not in command_text
    assert secret_token not in command_text
    assert cloud_secret in captured["input"]
    assert secret_token in captured["input"]
    assert captured["shell"] is False
    assert captured["text"] is True
    assert captured["encoding"] == "utf-8"
    assert captured["errors"] == "replace"


def test_ssh_timeout_error_does_not_expose_secret(tmp_path: Path) -> None:
    secret = "timeout-secret-value-which-must-not-leak"

    def runner(command, **kwargs):
        raise subprocess.TimeoutExpired(command, kwargs["timeout"])

    transport = WindowsSshTransport(_config(tmp_path), runner=runner)
    with pytest.raises(ChannelsSessionTimeoutError) as exc_info:
        transport.run("Open", session_id="chsession_123456789abc", payload={"x": secret})
    assert secret not in str(exc_info.value)


def test_ensure_active_is_idempotent_and_persists_only_credential_ref_and_hash(
    tmp_path: Path,
) -> None:
    controller, store, task_id, fake = _controller(tmp_path)
    secret = controller.shared_secret
    first = controller.ensure_active()
    second = controller.ensure_active()
    assert first["id"] == second["id"]
    assert [call["action"] for call in fake.calls].count("Open") == 1
    credential_path = Path(first["metadata"]["credential_ref"])
    assert credential_path.is_file()
    assert stat.S_IMODE(credential_path.stat().st_mode) == 0o600
    assert first["metadata"]["credential_sha256"]
    serialized_database = store.db_path.read_bytes()
    assert secret.encode() not in serialized_database
    credential_value = json.loads(credential_path.read_text())
    assert credential_value["secret_token"].encode() not in serialized_database
    assert store.list_channels_acquisition_sessions(task_id=task_id)[0]["status"] == "active"


def test_busy_remote_fails_before_creating_a_database_session(tmp_path: Path) -> None:
    fake = FakeWindowsTransport()
    fake.remote = fake._healthy(
        session_id="chsession_other1234",
        task_id="ctask_other123456",
        generation=3,
    )
    controller, store, task_id, _ = _controller(tmp_path, fake)
    with pytest.raises(ChannelsSessionBusyError):
        controller.ensure_active()
    assert store.list_channels_acquisition_sessions(task_id=task_id) == []


def test_residual_remote_artifacts_fail_closed_before_database_session(
    tmp_path: Path,
) -> None:
    fake = FakeWindowsTransport()
    fake.remote = {
        "session_present": False,
        "state": "absent",
        "generation": 0,
        "current_user_certificate_count": 1,
        "local_machine_certificate_count": 0,
        "worker_process_count": 0,
        "listener_count": 0,
    }
    controller, store, task_id, _ = _controller(tmp_path, fake)
    with pytest.raises(ChannelsSessionError, match="residual artifacts"):
        controller.ensure_active()
    assert store.list_channels_acquisition_sessions(task_id=task_id) == []


def test_renew_uses_generation_cas_and_rejects_a_stale_generation(tmp_path: Path) -> None:
    controller, _store_value, _task_id, fake = _controller(tmp_path)
    controller.ensure_active()
    renewed = controller.renew(expected_generation=1)
    assert renewed["metadata"]["lease_generation"] == 2
    calls_before = len(fake.calls)
    with pytest.raises(ChannelsSessionConflictError):
        controller.renew(expected_generation=1)
    assert len(fake.calls) == calls_before


def test_ensure_active_renews_a_lease_inside_the_safety_margin(tmp_path: Path) -> None:
    controller, _store_value, _task_id, fake = _controller(tmp_path)
    controller.ensure_active()
    assert fake.remote is not None
    fake.remote["expires_at"] = _iso_after(60)
    renewed = controller.ensure_active()
    assert renewed["metadata"]["lease_generation"] == 2
    assert [call["action"] for call in fake.calls].count("Renew") == 1


def test_stale_close_cannot_cleanup_new_generation_and_verified_close_deletes_secret(
    tmp_path: Path,
) -> None:
    controller, _store_value, _task_id, fake = _controller(tmp_path)
    opened = controller.ensure_active()
    credential_path = Path(opened["metadata"]["credential_ref"])
    controller.renew(expected_generation=1)
    calls_before = len(fake.calls)
    with pytest.raises(ChannelsSessionConflictError):
        controller.close(reason="task_completed", expected_generation=1)
    assert len(fake.calls) == calls_before
    assert credential_path.exists()
    cleaned = controller.close(reason="task_completed", expected_generation=2)
    assert cleaned["status"] == "cleaned"
    assert not credential_path.exists()


def test_failed_cleanup_is_persisted_and_keeps_credentials_for_retry(tmp_path: Path) -> None:
    controller, store, task_id, fake = _controller(tmp_path)
    opened = controller.ensure_active()
    credential_path = Path(opened["metadata"]["credential_ref"])
    fake.fail_action = "Close"
    with pytest.raises(ChannelsSessionTimeoutError):
        controller.close(reason="task_cancelled", expected_generation=1)
    current = store.list_channels_acquisition_sessions(task_id=task_id)[0]
    assert current["status"] == "cleanup_failed"
    assert credential_path.exists()


def test_open_timeout_keeps_credentials_and_marks_session_degraded_for_recovery(
    tmp_path: Path,
) -> None:
    fake = FakeWindowsTransport()
    fake.fail_action = "Open"
    controller, store, task_id, _ = _controller(tmp_path, fake)
    credential_path = controller._credential_path()
    with pytest.raises(ChannelsSessionTimeoutError):
        controller.ensure_active()
    current = store.list_channels_acquisition_sessions(task_id=task_id)[0]
    assert current["status"] == "degraded"
    assert credential_path.exists()
    fake.fail_action = None
    recovered = controller.ensure_active()
    assert recovered["status"] == "active"
    sessions = store.list_channels_acquisition_sessions(task_id=task_id)
    assert [item["status"] for item in sessions] == ["expired", "active"]


def test_recover_advances_generation_when_remote_health_is_degraded(tmp_path: Path) -> None:
    controller, _store_value, _task_id, fake = _controller(tmp_path)
    controller.ensure_active()
    assert fake.remote is not None
    fake.remote["worker_process_count"] = 0
    recovered = controller.ensure_active()
    assert recovered["metadata"]["lease_generation"] == 2
    assert [call["action"] for call in fake.calls].count("Recover") == 1


def test_refresh_page_is_bound_to_current_session_generation(tmp_path: Path) -> None:
    controller, store, _task_id, fake = _controller(tmp_path)
    opened = controller.ensure_active()
    result = controller.refresh_page()
    reused = controller.refresh_page()
    assert result["action"] == "refresh"
    assert reused["reused"] is True
    refresh_calls = [call for call in fake.calls if call["action"] == "Refresh"]
    assert len(refresh_calls) == 1
    refresh_call = refresh_calls[-1]
    assert refresh_call["session_id"] == opened["id"]
    assert refresh_call["expected_generation"] == 1
    events = store.list_channels_acquisition_events(session_id=opened["id"])
    assert events[-1]["event_type"] == "page_refreshed"


def test_provider_calls_guard_before_every_ephemeral_hub_start(monkeypatch) -> None:
    class Guard:
        worker_id = "workstation-channels-01"
        shared_secret = "guard-secret"

        def __init__(self) -> None:
            self.calls = 0
            self.refresh_calls = 0

        def ensure_active(self) -> dict:
            self.calls += 1
            return {"status": "active"}

        def refresh_page(self) -> dict:
            self.refresh_calls += 1
            return {"ok": True}

    hubs: list = []

    class FakeHub:
        def __init__(self, *, shared_secret, allowed_worker_ids):
            self.shared_secret = shared_secret
            self.allowed_worker_ids = allowed_worker_ids
            hubs.append(self)

        async def start(self, host, port, *, ssl_context=None):
            self.started = (host, port, ssl_context)

    guard = Guard()
    monkeypatch.setattr("mcn_ops.collection.channels.provider.ChannelsHub", FakeHub)
    provider = ChannelsRemoteProvider(
        ChannelsRemoteConfig(
            worker_id=guard.worker_id,
            shared_secret="environment-placeholder",
        ),
        session_guard=guard,
    )
    asyncio.run(provider._start_hub())
    asyncio.run(provider._start_hub())
    assert guard.calls == 2
    assert guard.refresh_calls == 2
    assert [hub.shared_secret for hub in hubs] == ["guard-secret", "guard-secret"]


def test_remote_config_accepts_guard_overrides_without_secret_environment(monkeypatch) -> None:
    monkeypatch.delenv("CHANNELS_WORKER_ID", raising=False)
    monkeypatch.delenv("CHANNELS_HUB_SECRET", raising=False)
    monkeypatch.delenv("CHANNELS_HUB_HOST", raising=False)
    monkeypatch.delenv("CHANNELS_ALLOW_INSECURE_LAN", raising=False)
    config = ChannelsRemoteConfig.from_env(
        worker_id_override="workstation-channels-01",
        shared_secret_override="guard-secret",
    )
    assert config.worker_id == "workstation-channels-01"
    assert config.shared_secret == "guard-secret"

    managed = ChannelsRemoteConfig.from_env(
        worker_id_override="workstation-channels-01",
        shared_secret_override="guard-secret",
        managed_session=True,
    )
    assert managed.host == "0.0.0.0"
    assert managed.allow_insecure_lan is True
