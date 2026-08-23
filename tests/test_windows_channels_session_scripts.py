from __future__ import annotations

import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
WINDOWS_SCRIPTS = ROOT / "scripts" / "windows"
PRODUCTION_FILES = {
    "common": WINDOWS_SCRIPTS / "wx-channel-session-common.ps1",
    "manage": WINDOWS_SCRIPTS / "manage-wx-channel-session.ps1",
    "cleanup": WINDOWS_SCRIPTS / "cleanup-wx-channel-session.ps1",
    "watchdog": WINDOWS_SCRIPTS / "watch-wx-channel-session-lease.ps1",
    "bootstrap": WINDOWS_SCRIPTS / "bootstrap-wx-channel-session.ps1",
    "worker": WINDOWS_SCRIPTS / "start-wx-channel-worker.ps1",
}
PESTER_TEST = WINDOWS_SCRIPTS / "tests" / "wx-channel-session.Tests.ps1"

EXPECTED_CERTIFICATE_SHA256 = (
    "1A61D4F74DC31D27630B25E37AAF46C364955EDC7A6EA11EB20E4B6B05114E04"
)
EXPECTED_CERTIFICATE_THUMBPRINT = "D70CD039051F77C30673B8209FC15EFA650ED52C"
EXPECTED_WORKER_SHA256 = (
    "C5CFF437248220EDD113403987E6C3005136A23AEE2B410E09736DD26BD2B0EA"
)
EXPECTED_WORKER_NAME = "wx_channel_cloud_hardened_v5.6.9.exe"


def _read(name: str) -> str:
    return PRODUCTION_FILES[name].read_text(encoding="utf-8")


def test_production_session_scripts_are_present() -> None:
    assert all(path.is_file() for path in PRODUCTION_FILES.values())
    assert PESTER_TEST.is_file()


def test_manage_supports_the_full_session_action_contract() -> None:
    source = _read("manage")
    assert '[ValidateSet("Open", "Renew", "Status", "Close", "Recover")]' in source
    for action in ("Open", "Renew", "Status", "Close", "Recover"):
        assert f"Invoke-Wx{action}" in source
    assert "Assert-WxSessionIdentity" in source
    assert "ExpectedGeneration" in source
    assert "session_busy" in source
    assert "cleanup_required" in source
    assert "recover_required" in source


def test_secrets_are_read_only_from_ssh_stdin_not_parameters() -> None:
    source = _read("manage")
    parameter_block = source.split('$ErrorActionPreference = "Stop"', 1)[0].lower()
    assert "cloud_secret" not in parameter_block
    assert "secret_token" not in parameter_block
    assert "hub_url" not in parameter_block
    assert "[console]::in.readtoend()" in source.lower()
    assert "Read-WxStdinPayload" in source


def test_common_contract_pins_certificate_worker_and_firewall() -> None:
    source = _read("common")
    assert EXPECTED_CERTIFICATE_SHA256 in source
    assert EXPECTED_CERTIFICATE_THUMBPRINT in source
    assert EXPECTED_WORKER_SHA256 in source
    assert EXPECTED_WORKER_NAME in source
    assert "Codex-WxChannel-PoC-Block-Inbound" in source
    assert "CurrentUser\\Root" in source
    assert "LocalMachine\\Root" in source


def test_lease_and_config_writes_are_atomic_and_mutex_guarded() -> None:
    common = _read("common")
    assert "Global\\CodexWxChannelSessionLeaseV1" in common
    assert "Write-WxAtomicJson" in common
    assert "[Guid]::NewGuid" in common
    assert "Move-Item -LiteralPath $temporaryPath -Destination $Path -Force" in common
    for name in ("manage", "cleanup", "watchdog", "bootstrap", "worker"):
        source = _read(name)
        assert "Enter-WxSessionMutex" in source
        assert "Exit-WxSessionMutex" in source


def test_worker_start_uses_a_two_phase_mutex_handoff() -> None:
    source = _read("manage")
    assert "Do not hold the mutex while waiting" in source
    assert source.count("Start-WxPinnedWorkerTask") == 3  # definition, Open, Recover
    assert "Set-WxDegradedIfCurrent" in source


def test_production_cleanup_targets_only_pinned_resources() -> None:
    combined = "\n".join(_read(name) for name in PRODUCTION_FILES)
    assert "cleanup-wx-channel-poc.ps1" not in combined
    assert "wx_channel_cloud*.exe" not in combined
    assert not re.search(r"Get-Process\s+-Name\s+wx_channel", combined, re.IGNORECASE)

    common = _read("common")
    assert "Get-WxPinnedWorkerProcesses" in common
    assert "[IO.Path]::GetFullPath($script:WxWorkerPath)" in common
    assert "executable SHA256 changed" in common
    assert "certutil.exe -user -delstore Root $script:WxExpectedCertificateThumbprint" in common
    assert "certutil.exe -delstore Root $script:WxExpectedCertificateThumbprint" not in common
    assert "refusing cleanup because the pinned SunnyNet certificate exists in LocalMachine Root" in common
    assert "cloud_enabled: false" in common
    assert 'cloud_secret: ""' in common
    assert 'secret_token: ""' in common
    assert 'state = "cleanup_pending"' in common
    assert 'state = "cleanup_failed"' in common
    cleanup = _read("cleanup")
    assert "Assert-WxSessionIdentity" in cleanup
    assert "ExpectedGeneration" in cleanup


def test_watchdog_rechecks_expiry_while_holding_the_named_mutex() -> None:
    source = _read("watchdog")
    assert source.index("Enter-WxSessionMutex") < source.index("Read-WxLease")
    assert "Test-WxLeaseExpired" in source
    assert '-Reason "lease_timeout"' in source
    assert '-TerminalState "expired"' in source


def test_bootstrap_registers_only_stable_worker_and_watchdog_tasks() -> None:
    source = _read("bootstrap")
    assert '"WORKSTATION\\qiaoz"' in source
    assert "CodexWxChannelWorker" in _read("common")
    assert "CodexWxChannelLeaseGuard" in _read("common")
    assert "-LogonType Interactive" in source
    assert "-StartWhenAvailable" in source
    assert "-RepetitionInterval (New-TimeSpan -Minutes 1)" in source
    assert "certificate_installed = $false" in source


def test_worker_start_is_lease_gated_and_uses_exact_process_identity() -> None:
    source = _read("worker")
    assert "Read-WxLease" in source
    assert "Test-WxLeaseExpired" in source
    assert "Get-WxPinnedWorkerProcesses" in source
    assert "Assert-WxPinnedArtifacts" in source
    assert "Get-Process -Name" not in source
    assert "& $script:WxWorkerPath" in source
