from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class ContentPackage:
    id: str
    title: str
    body: str
    media_paths: list[Path] = field(default_factory=list)
    cover_path: Path | None = None
    hashtags: list[str] = field(default_factory=list)
    platform: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class PublishJob:
    id: str
    content_id: str
    platform: str
    device_serial: str | None
    status: str
    stop_before_submit: bool = True
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class AndroidDevice:
    serial: str
    state: str
    model: str | None = None
    product: str | None = None


@dataclass(frozen=True)
class AdapterStep:
    name: str
    description: str
    action: str
    args: dict[str, Any] = field(default_factory=dict)
    requires_live_publish: bool = False
