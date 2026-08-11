from __future__ import annotations

from mcn_ops.collection.douyin.contracts import build_provider_result
from mcn_ops.collection.douyin.doctor import DoctorCheck, run_doctor


class FakeProvider:
    provider_name = "direct"

    def call(self, method_key, params=None, body=None, use_cache=True):
        return build_provider_result(provider=self.provider_name, method_key=method_key)


def test_doctor_reports_missing_transcriber_without_network() -> None:
    result = run_doctor(FakeProvider())

    assert result["ok"] is False
    assert result["status"] == "attention_required"
    assert result["checks"][0]["provider"] == "direct"
    assert result["checks"][1]["code"] == "not_configured"


def test_doctor_allows_explicitly_disabled_transcription() -> None:
    result = run_doctor(FakeProvider(), transcription_required=False)

    assert result["ok"] is True
    assert result["status"] == "ready"
    assert result["checks"][1]["code"] == "disabled"


def test_doctor_redacts_secrets_from_injected_checks() -> None:
    check = DoctorCheck(
        "credentials",
        lambda: {
            "ok": True,
            "code": "configured",
            "api_key": "aliyun-secret",
            "nested": {"cookie": "session-secret", "region": "beijing"},
        },
    )

    result = run_doctor(FakeProvider(), checks=[check])

    rendered = str(result)
    assert "aliyun-secret" not in rendered
    assert "session-secret" not in rendered
    assert result["checks"][-1]["api_key"] == "<redacted>"
    assert result["checks"][-1]["nested"]["cookie"] == "<redacted>"


def test_doctor_exposes_exception_type_but_not_exception_message() -> None:
    def fail():
        raise RuntimeError("cookie=private-value")

    result = run_doctor(FakeProvider(), checks=[DoctorCheck("network", fail)])

    rendered = str(result)
    assert "private-value" not in rendered
    assert result["checks"][-1]["error_type"] == "RuntimeError"


def test_doctor_redacts_credentials_embedded_in_safe_named_messages() -> None:
    check = DoctorCheck(
        "probe",
        lambda: {"ok": False, "message": "authorization=private bearer abc.def.ghi"},
    )

    result = run_doctor(FakeProvider(), checks=[check])

    assert "private" not in str(result)
    assert "abc.def.ghi" not in str(result)
