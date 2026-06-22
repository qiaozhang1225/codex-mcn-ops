from __future__ import annotations

import json
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .models import AndroidDevice


class AdbError(RuntimeError):
    pass


@dataclass(frozen=True)
class CommandResult:
    args: list[str]
    returncode: int
    stdout: str
    stderr: str


class AdbClient:
    def __init__(self, adb_path: str = "adb", serial: str | None = None, timeout: int = 30):
        self.adb_path = adb_path
        self.serial = serial
        self.timeout = timeout

    def available(self) -> bool:
        return shutil.which(self.adb_path) is not None

    def base_cmd(self) -> list[str]:
        cmd = [self.adb_path]
        if self.serial:
            cmd.extend(["-s", self.serial])
        return cmd

    def run(self, *args: str, check: bool = True, timeout: int | None = None) -> CommandResult:
        cmd = [*self.base_cmd(), *args]
        proc = subprocess.run(
            cmd,
            text=True,
            capture_output=True,
            timeout=timeout or self.timeout,
        )
        result = CommandResult(cmd, proc.returncode, proc.stdout, proc.stderr)
        if check and proc.returncode != 0:
            raise AdbError(f"ADB command failed: {' '.join(cmd)}\n{proc.stderr.strip()}")
        return result

    def shell(self, *args: str, check: bool = True, timeout: int | None = None) -> CommandResult:
        return self.run("shell", *args, check=check, timeout=timeout)

    def devices(self) -> list[AndroidDevice]:
        result = self.run("devices", "-l")
        devices: list[AndroidDevice] = []
        for line in result.stdout.splitlines()[1:]:
            line = line.strip()
            if not line:
                continue
            parts = line.split()
            serial = parts[0]
            state = parts[1] if len(parts) > 1 else "unknown"
            fields: dict[str, str] = {}
            for part in parts[2:]:
                if ":" in part:
                    key, value = part.split(":", 1)
                    fields[key] = value
            devices.append(AndroidDevice(serial=serial, state=state, model=fields.get("model"), product=fields.get("product")))
        return devices

    def getprop(self, name: str) -> str:
        return self.shell("getprop", name).stdout.strip()

    def wake_and_unlock(self) -> None:
        self.shell("input", "keyevent", "KEYCODE_WAKEUP", check=False)
        self.shell("wm", "dismiss-keyguard", check=False)

    def start_app(self, package: str, activity: str | None = None) -> None:
        if activity:
            self.shell("am", "start", "-n", f"{package}/{activity}")
        else:
            self.shell("monkey", "-p", package, "-c", "android.intent.category.LAUNCHER", "1")

    def push(self, local_path: Path | str, remote_path: str) -> CommandResult:
        return self.run("push", str(local_path), remote_path, timeout=120)

    def tap(self, x: int, y: int) -> None:
        self.shell("input", "tap", str(x), str(y))

    def swipe(self, x1: int, y1: int, x2: int, y2: int, duration_ms: int = 400) -> None:
        self.shell("input", "swipe", str(x1), str(y1), str(x2), str(y2), str(duration_ms))

    def text(self, value: str) -> None:
        # adb input text is fragile for non-ASCII. Prefer clipboard-based fallback in real adapters.
        escaped = value.replace(" ", "%s").replace("&", "\\&")
        self.shell("input", "text", escaped)

    def keyevent(self, key: str) -> None:
        self.shell("input", "keyevent", key)

    def screencap(self, output_path: Path) -> Path:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        proc = subprocess.run(
            [*self.base_cmd(), "exec-out", "screencap", "-p"],
            capture_output=True,
            timeout=self.timeout,
        )
        if proc.returncode != 0:
            raise AdbError(proc.stderr.decode("utf-8", "ignore"))
        output_path.write_bytes(proc.stdout)
        return output_path

    def uiautomator_dump(self, output_path: Path) -> Path:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        remote = "/sdcard/window_dump.xml"
        self.shell("uiautomator", "dump", remote)
        result = self.run("exec-out", "cat", remote)
        output_path.write_text(result.stdout, encoding="utf-8")
        return output_path

    def doctor(self) -> dict[str, Any]:
        report: dict[str, Any] = {"adb_available": self.available(), "devices": []}
        if not report["adb_available"]:
            return report
        devices = self.devices()
        report["devices"] = [device.__dict__ for device in devices]
        if self.serial or len(devices) == 1:
            serial = self.serial or devices[0].serial
            scoped = AdbClient(self.adb_path, serial, timeout=self.timeout)
            report["selected_serial"] = serial
            report["model"] = scoped.getprop("ro.product.model")
            report["sdk"] = scoped.getprop("ro.build.version.sdk")
            report["screen_state_check"] = scoped.shell("dumpsys", "power", check=False).returncode == 0
        return report

    def doctor_json(self) -> str:
        return json.dumps(self.doctor(), ensure_ascii=False, indent=2, sort_keys=True)
