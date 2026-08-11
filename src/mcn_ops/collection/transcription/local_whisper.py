from __future__ import annotations

import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from ..douyin.contracts import ProviderResult, build_provider_result
from ..douyin.errors import ProviderConfigError, ProviderUnavailableError, TranscriptionInputError


Runner = Callable[..., subprocess.CompletedProcess[str]]


@dataclass
class LocalWhisperAdapter:
    executable: str = "mlx_whisper"
    model: str = "mlx-community/whisper-large-v3-turbo"
    language: str = "zh"
    timeout_seconds: float = 1800.0
    runner: Runner = subprocess.run
    provider_name: str = "local-mlx-whisper"

    def transcribe(
        self,
        source: str,
        *,
        source_package: dict[str, Any] | None = None,
        use_cache: bool = True,
    ) -> ProviderResult:
        del use_cache
        path = Path(source).expanduser().resolve()
        if not path.is_file():
            raise TranscriptionInputError(f"media file does not exist: {path}")
        if shutil.which(self.executable) is None and self.runner is subprocess.run:
            raise ProviderConfigError(f"{self.executable} is not installed")

        output_directory = Path(tempfile.mkdtemp(prefix="mcn-whisper-"))
        output_name = "transcript"
        command = [
            self.executable,
            str(path),
            "--model",
            self.model,
            "--language",
            self.language,
            "-f",
            "txt",
            "--output-dir",
            str(output_directory),
            "--output-name",
            output_name,
        ]
        try:
            completed = self.runner(
                command,
                capture_output=True,
                text=True,
                timeout=self.timeout_seconds,
                check=False,
            )
            if completed.returncode != 0:
                raise ProviderUnavailableError(
                    "local Whisper failed",
                    detail=str(completed.stderr or "")[:300],
                )
            output_path = output_directory / f"{output_name}.txt"
            text = output_path.read_text(encoding="utf-8").strip() if output_path.is_file() else completed.stdout.strip()
            if not text:
                raise ProviderUnavailableError("local Whisper returned empty text")
            package = dict(source_package or {})
            package["transcript_text"] = text
            return build_provider_result(
                provider=self.provider_name,
                method_key="douyin_extract_video_text",
                normalized={
                    "text": text,
                    "language": self.language,
                    "segments": [],
                    "source_package": package,
                },
                raw={"engine": self.executable},
                usage={"cloud_cost_cny": 0, "model": self.model},
            )
        except subprocess.TimeoutExpired as exc:
            raise ProviderUnavailableError("local Whisper timed out") from exc
        finally:
            shutil.rmtree(output_directory, ignore_errors=True)
