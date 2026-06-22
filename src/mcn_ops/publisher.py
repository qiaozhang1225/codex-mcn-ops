from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from .adb import AdbClient, AdbError
from .adapters import get_adapter
from .models import ContentPackage
from .store import Store, loads


@dataclass(frozen=True)
class PublishRunResult:
    job_id: str
    status: str
    run_dir: Path
    message: str


class PublishRunner:
    def __init__(self, store: Store, adb_path: str = "adb", runs_dir: Path | str = "runs"):
        self.store = store
        self.adb_path = adb_path
        self.runs_dir = Path(runs_dir)

    def content_from_row(self, row) -> ContentPackage:
        return ContentPackage(
            id=row["id"],
            title=row["title"],
            body=row["body"],
            media_paths=[Path(p) for p in loads(row["media_paths_json"], [])],
            cover_path=Path(row["cover_path"]) if row["cover_path"] else None,
            hashtags=loads(row["hashtags_json"], []),
            metadata=loads(row["metadata_json"], {}),
        )

    def prepare_assets(self, job_id: str, *, remote_dir: str = "/sdcard/Download/codex-mcn-ops") -> list[str]:
        job, content_row = self.store.get_job_with_content(job_id)
        content = self.content_from_row(content_row)
        device_serial = job["device_serial"]
        if not device_serial:
            raise ValueError("publish job has no device_serial")
        adb = AdbClient(self.adb_path, device_serial)
        adb.shell("mkdir", "-p", remote_dir, check=False)
        pushed: list[str] = []
        for media_path in content.media_paths:
            remote_path = f"{remote_dir}/{media_path.name}"
            adb.push(media_path, remote_path)
            pushed.append(remote_path)
        if content.cover_path:
            remote_path = f"{remote_dir}/{content.cover_path.name}"
            adb.push(content.cover_path, remote_path)
            pushed.append(remote_path)
        self.store.add_run_log(
            job_id=job_id,
            platform=job["platform"],
            device_serial=device_serial,
            step_name="push_assets",
            status="ok",
            message=f"pushed {len(pushed)} files",
            metadata={"remote_paths": pushed},
        )
        return pushed

    def run_job(
        self,
        job_id: str,
        *,
        dry_run: bool = True,
        stop_before_submit: bool | None = None,
        live_publish: bool = False,
    ) -> PublishRunResult:
        job, content_row = self.store.get_job_with_content(job_id)
        platform = job["platform"]
        adapter = get_adapter(platform)
        content = self.content_from_row(content_row)
        stop = bool(job["stop_before_submit"]) if stop_before_submit is None else stop_before_submit
        device_serial = job["device_serial"]
        run_dir = self.runs_dir / job_id
        run_dir.mkdir(parents=True, exist_ok=True)

        issues = adapter.validate(content)
        if issues:
            message = "; ".join(f"{issue.field}: {issue.message}" for issue in issues)
            self.store.add_run_log(
                job_id=job_id,
                platform=platform,
                device_serial=device_serial,
                step_name="validate",
                status="failed",
                message=message,
            )
            self.store.update_publish_job_status(job_id, "validation_failed")
            return PublishRunResult(job_id, "validation_failed", run_dir, message)

        if not device_serial and not dry_run:
            raise ValueError("device_serial is required for non-dry-run publishing")

        adb = AdbClient(self.adb_path, device_serial) if device_serial else None
        status = "dry_run_completed" if dry_run else "stopped_before_submit"
        self.store.update_publish_job_status(job_id, "running")

        for index, step in enumerate(adapter.build_steps(content, stop_before_submit=stop), start=1):
            if step.requires_live_publish and not live_publish:
                self.store.add_run_log(
                    job_id=job_id,
                    platform=platform,
                    device_serial=device_serial,
                    step_name=step.name,
                    status="skipped",
                    message="live publish disabled",
                )
                status = "stopped_before_live_publish"
                break

            artifact_path: str | None = None
            try:
                if dry_run:
                    step_status = "planned"
                    message = step.description
                elif step.action == "start_app":
                    assert adb is not None
                    adb.wake_and_unlock()
                    adb.start_app(step.args["package"], step.args.get("activity"))
                    step_status = "ok"
                    message = step.description
                elif step.action == "capture":
                    assert adb is not None
                    screenshot = adb.screencap(run_dir / f"{index:02d}_{step.name}.png")
                    artifact_path = str(screenshot)
                    try:
                        dump = adb.uiautomator_dump(run_dir / f"{index:02d}_{step.name}.xml")
                        message = f"{step.description}; UI dump saved to {dump}"
                    except AdbError as exc:
                        message = f"{step.description}; UI dump failed: {exc}"
                    step_status = "ok"
                elif step.action == "manual_checkpoint":
                    step_status = "needs_calibration"
                    message = f"{step.description} A calibrated device script or Computer Use handoff is required."
                elif step.action == "stop":
                    step_status = "stopped"
                    message = step.args.get("reason", step.description)
                    status = "stopped_before_submit"
                    self.store.add_run_log(
                        job_id=job_id,
                        platform=platform,
                        device_serial=device_serial,
                        step_name=step.name,
                        status=step_status,
                        message=message,
                        artifact_path=artifact_path,
                        metadata=step.args,
                    )
                    break
                else:
                    step_status = "unknown_action"
                    message = f"unsupported adapter action: {step.action}"

                self.store.add_run_log(
                    job_id=job_id,
                    platform=platform,
                    device_serial=device_serial,
                    step_name=step.name,
                    status=step_status,
                    message=message,
                    artifact_path=artifact_path,
                    metadata=step.args,
                )
            except Exception as exc:
                self.store.add_run_log(
                    job_id=job_id,
                    platform=platform,
                    device_serial=device_serial,
                    step_name=step.name,
                    status="failed",
                    message=str(exc),
                    metadata=step.args,
                )
                self.store.update_publish_job_status(job_id, "failed")
                return PublishRunResult(job_id, "failed", run_dir, str(exc))

        self.store.update_publish_job_status(job_id, status)
        return PublishRunResult(job_id, status, run_dir, f"job {job_id} {status}")
