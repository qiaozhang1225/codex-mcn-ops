from mcn_ops.collection.douyin.browser_fallback import HumanActionBrowserFallback
from mcn_ops.collection.douyin.errors import ProviderRiskControlError


def test_browser_fallback_requires_human_action_without_bypass() -> None:
    result = HumanActionBrowserFallback().request_human_action(
        operation="user_post",
        error=ProviderRiskControlError("captcha", detail="cookie=secret"),
        context={"url": "https://www.douyin.com/user/test?token=secret", "cookie": "secret"},
    )

    assert result["status"] == "human_action_required"
    assert result["reason_code"] == "provider_risk_control"
    assert result["automation_attempted"] is False
    assert result["captcha_bypass_attempted"] is False
    assert "cookie" not in result["context"]
    assert "secret" not in str(result)
    assert result["context"]["url"] == "https://www.douyin.com/user/test"
