"""Simplified platform adapters for runtime telemetry collection.

Extracted from trtc-eval's scripts/lib/platforms/ — only the parts needed
for capturing runtime logs from a user's already-built application.

No build/install/ensure_booted — the user's app is already compiled and
ready to run by the time telemetry collection starts (post topic Step 4).
"""
import json
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Literal


@dataclass(frozen=True)
class Device:
    kind: Literal["real", "simulator"]
    id: str
    name: str = ""


def discover_devices(platform: str) -> list[Device]:
    """Discover available devices for the given platform."""
    if platform == "web":
        return [Device(kind="simulator", id="local", name="localhost")]
    elif platform == "ios":
        return _discover_ios_devices()
    elif platform == "android":
        return _discover_android_devices()
    return []


def log_stream_command(
    platform: str,
    device: Device,
    *,
    workspace: Path | None = None,
    connect: str | None = None,
) -> list[str]:
    """Return the command array to start log streaming for the given platform.

    The returned command's stdout IS the runtime log content — it should be
    piped directly to a file by the caller (telemetry_collector.py).

    Args:
        connect: (Web only) CDP endpoint to connect to an existing browser
                 instead of launching a new one. e.g. "http://localhost:9222"
    """
    if platform == "web":
        if workspace is None:
            raise ValueError("Web platform requires --workspace")
        bridge_path = Path(__file__).resolve().parent.parent / "telemetry-bridge.mjs"
        cmd = [
            "node",
            str(bridge_path),
            "--url", "http://localhost:5173",
            "--workspace", str(workspace),
        ]
        if connect:
            cmd.extend(["--connect", connect])
        return cmd
    elif platform == "ios":
        bundle_id = _detect_ios_bundle_id(workspace)
        if device.kind == "simulator":
            return [
                "xcrun", "simctl", "launch", "--console",
                device.id, bundle_id,
            ]
        else:
            return [
                "xcrun", "devicectl", "device", "process", "launch",
                "--device", device.id, "--console", bundle_id,
            ]
    elif platform == "android":
        return [
            "adb", "-s", device.id, "logcat",
            "-s", "TRTCSDK:*", "LiveCore:*",
        ]
    else:
        raise ValueError(f"Unsupported platform: {platform}")


# ---------------------------------------------------------------------------
# iOS device discovery
# ---------------------------------------------------------------------------

def _discover_ios_devices() -> list[Device]:
    """Discover iOS simulators (booted first) and real devices."""
    devices: list[Device] = []

    # Simulators
    try:
        proc = subprocess.run(
            ["xcrun", "simctl", "list", "devices", "--json"],
            capture_output=True, text=True, check=False,
        )
        if proc.returncode == 0:
            data = json.loads(proc.stdout)
            for runtime, devs in data.get("devices", {}).items():
                if "iOS" not in runtime:
                    continue
                for dev in devs:
                    if not dev.get("isAvailable", False):
                        continue
                    devices.append(Device(
                        kind="simulator",
                        id=dev.get("udid", ""),
                        name=dev.get("name", ""),
                    ))
            # Sort booted simulators first
            devices.sort(
                key=lambda d: 0 if "Booted" in str(d) else 1
            )
    except (FileNotFoundError, json.JSONDecodeError):
        pass

    # Real devices (via devicectl)
    try:
        import tempfile
        with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as tmp:
            tmp_path = tmp.name
        proc = subprocess.run(
            ["xcrun", "devicectl", "list", "devices", "--json-output", tmp_path],
            capture_output=True, text=True, check=False,
        )
        if proc.returncode == 0:
            import os
            with open(tmp_path, "r") as f:
                data = json.load(f)
            os.unlink(tmp_path)
            for entry in data.get("result", {}).get("devices", []):
                conn = entry.get("connectionProperties", {})
                if conn.get("transportType") in ("localNetwork", "wired"):
                    udid = entry.get("hardwareProperties", {}).get("udid", "")
                    name = entry.get("deviceProperties", {}).get("name", "")
                    if udid:
                        devices.insert(0, Device(kind="real", id=udid, name=name))
    except (FileNotFoundError, json.JSONDecodeError):
        pass

    return devices


# ---------------------------------------------------------------------------
# Android device discovery
# ---------------------------------------------------------------------------

def _discover_android_devices() -> list[Device]:
    """Discover connected Android devices/emulators via adb."""
    devices: list[Device] = []
    try:
        proc = subprocess.run(
            ["adb", "devices", "-l"],
            capture_output=True, text=True, check=False,
        )
        if proc.returncode != 0:
            return devices
        for line in proc.stdout.strip().splitlines()[1:]:
            parts = line.split()
            if len(parts) < 2 or parts[1] != "device":
                continue
            serial = parts[0]
            kind: Literal["real", "simulator"] = (
                "simulator" if serial.startswith("emulator-") else "real"
            )
            devices.append(Device(kind=kind, id=serial, name=serial))
    except FileNotFoundError:
        pass
    return devices


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _detect_ios_bundle_id(workspace: Path | None) -> str:
    """Best-effort detection of the iOS app bundle ID from the project.

    Falls back to a common default if detection fails.
    """
    if workspace:
        # Try reading from project.pbxproj
        pbxproj = list(workspace.glob("*.xcodeproj/project.pbxproj"))
        if pbxproj:
            try:
                content = pbxproj[0].read_text(errors="replace")
                import re
                m = re.search(r'PRODUCT_BUNDLE_IDENTIFIER\s*=\s*"?([^";]+)', content)
                if m:
                    return m.group(1).strip()
            except OSError:
                pass
    return "com.trtc.app"
