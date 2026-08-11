from __future__ import annotations


class ProviderError(Exception):
    code = "provider_error"
    fallback_allowed = False

    def __init__(self, message: str, *, detail: str | None = None) -> None:
        super().__init__(message)
        self.detail = detail


class ProviderConfigError(ProviderError):
    code = "provider_config_error"


class ProviderInputError(ProviderError):
    code = "provider_input_error"


class ProviderAuthError(ProviderError):
    code = "provider_auth_error"


class ProviderRateLimitError(ProviderError):
    code = "provider_rate_limited"
    fallback_allowed = True


class ProviderRiskControlError(ProviderError):
    code = "provider_risk_control"
    fallback_allowed = True


class ProviderResponseError(ProviderError):
    code = "provider_response_error"
    fallback_allowed = True


class ProviderUnavailableError(ProviderError):
    code = "provider_unavailable"
    fallback_allowed = True


class TranscriptionInputError(ProviderError):
    code = "transcription_input_error"
