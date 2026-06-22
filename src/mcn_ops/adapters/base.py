from __future__ import annotations

from dataclasses import dataclass, field

from mcn_ops.models import AdapterStep, ContentPackage


@dataclass(frozen=True)
class PlatformSpec:
    key: str
    display_name: str
    package_name: str
    launcher_activity: str | None = None
    max_title_length: int | None = None
    max_body_length: int | None = None
    max_hashtags: int | None = None
    notes: tuple[str, ...] = ()


@dataclass
class ValidationIssue:
    field: str
    message: str


class PlatformAdapter:
    spec: PlatformSpec

    def __init__(self, spec: PlatformSpec):
        self.spec = spec

    def validate(self, content: ContentPackage) -> list[ValidationIssue]:
        issues: list[ValidationIssue] = []
        if not content.media_paths:
            issues.append(ValidationIssue("media_paths", "at least one media file is required"))
        if self.spec.max_title_length is not None and len(content.title) > self.spec.max_title_length:
            issues.append(
                ValidationIssue("title", f"title is {len(content.title)} chars; max is {self.spec.max_title_length}")
            )
        if self.spec.max_body_length is not None and len(content.body) > self.spec.max_body_length:
            issues.append(ValidationIssue("body", f"body is {len(content.body)} chars; max is {self.spec.max_body_length}"))
        if self.spec.max_hashtags is not None and len(content.hashtags) > self.spec.max_hashtags:
            issues.append(
                ValidationIssue("hashtags", f"{len(content.hashtags)} hashtags provided; max is {self.spec.max_hashtags}")
            )
        return issues

    def build_steps(self, content: ContentPackage, *, stop_before_submit: bool = True) -> list[AdapterStep]:
        steps = [
            AdapterStep(
                name="launch_app",
                description=f"Open {self.spec.display_name}",
                action="start_app",
                args={"package": self.spec.package_name, "activity": self.spec.launcher_activity},
            ),
            AdapterStep(
                name="capture_home",
                description="Capture current app state before navigation",
                action="capture",
            ),
            AdapterStep(
                name="open_publish_entry",
                description="Navigate to the platform publish entry. Coordinates/selectors are device-specific and must be calibrated.",
                action="manual_checkpoint",
                args={"checkpoint": "open_publish_entry"},
            ),
            AdapterStep(
                name="select_media",
                description="Select media from the phone gallery or app media picker.",
                action="manual_checkpoint",
                args={"checkpoint": "select_media", "media_count": len(content.media_paths)},
            ),
            AdapterStep(
                name="fill_text",
                description="Fill title, body, and hashtags.",
                action="manual_checkpoint",
                args={"checkpoint": "fill_text", "title": content.title, "body": content.body, "hashtags": content.hashtags},
            ),
            AdapterStep(
                name="set_cover_and_visibility",
                description="Set cover and visibility when the app exposes these options.",
                action="manual_checkpoint",
                args={"checkpoint": "set_cover_and_visibility", "cover_path": str(content.cover_path) if content.cover_path else None},
            ),
            AdapterStep(
                name="pre_submit_capture",
                description="Capture final confirmation screen before publishing.",
                action="capture",
            ),
        ]
        if stop_before_submit:
            steps.append(
                AdapterStep(
                    name="stop_before_submit",
                    description="Stop before tapping the final publish button.",
                    action="stop",
                    args={"reason": "human confirmation required"},
                )
            )
        else:
            steps.append(
                AdapterStep(
                    name="submit_publish",
                    description="Tap final publish button. This requires explicit live mode.",
                    action="manual_checkpoint",
                    args={"checkpoint": "submit_publish"},
                    requires_live_publish=True,
                )
            )
        return steps


def make_adapter(
    *,
    key: str,
    display_name: str,
    package_name: str,
    launcher_activity: str | None = None,
    max_title_length: int | None = None,
    max_body_length: int | None = None,
    max_hashtags: int | None = None,
    notes: tuple[str, ...] = (),
) -> PlatformAdapter:
    return PlatformAdapter(
        PlatformSpec(
            key=key,
            display_name=display_name,
            package_name=package_name,
            launcher_activity=launcher_activity,
            max_title_length=max_title_length,
            max_body_length=max_body_length,
            max_hashtags=max_hashtags,
            notes=notes,
        )
    )
