#!/usr/bin/env python3

from __future__ import annotations

import argparse
from dataclasses import dataclass
import json
import logging
import os
from pathlib import Path
import signal
import subprocess
import sys
import tempfile
import time


GLASSES_USB_VENDOR = "35ca"
GLASSES_USB_PRODUCT = "1211"
SUPPORTED_MODES = {
    "standard-1920x1080-60",
    "standard-1920x1200-60",
    "ultrawide-3840x1080-60",
    "ultrawide-3840x1200-60",
}
SUPPORTED_DOF = {"anchored", "smooth-follow", "off"}
SUPPORTED_SIZES = {"small", "medium", "large", "extra-large", "ultra-large"}
POLL_SECONDS = 0.5
DEVICE_INFO_PREFIX = "GAPIA_DEVICE_INFO "
DEVICE_INFO_STRING_KEYS = {
    "brand",
    "model",
    "firmware",
    "usb_id",
    "sdk_version",
    "device_family",
    "display_mode",
    "tracking",
    "screen_size",
}


class ConfigError(ValueError):
    pass


@dataclass(frozen=True)
class NativeDisplayConfig:
    mode: str
    dof: str
    screen_size: str
    distance: int
    make_glasses_primary: bool = False
    disable_built_in_display: bool = False

    def as_dict(self) -> dict[str, object]:
        return {
            "mode": self.mode,
            "dof": self.dof,
            "screen_size": self.screen_size,
            "distance": self.distance,
            "make_glasses_primary": self.make_glasses_primary,
            "disable_built_in_display": self.disable_built_in_display,
        }

    def helper_arguments(self) -> list[str]:
        return [
            "--mode",
            self.mode,
            "--dof",
            self.dof,
            "--size",
            self.screen_size,
            "--distance",
            str(self.distance),
        ]


def _object_without_duplicates(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ConfigError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def parse_config(text: str) -> NativeDisplayConfig:
    try:
        data = json.loads(text, object_pairs_hook=_object_without_duplicates)
    except json.JSONDecodeError as error:
        raise ConfigError(f"invalid JSON: {error}") from error
    if not isinstance(data, dict):
        raise ConfigError("the configuration root must be a JSON object")

    required = {"mode", "dof", "screen_size", "distance"}
    optional = {"make_glasses_primary", "disable_built_in_display"}
    unknown = set(data) - required - optional
    if unknown:
        raise ConfigError(f"unknown configuration key: {sorted(unknown)[0]}")
    missing = required - set(data)
    if missing:
        raise ConfigError(f"missing configuration key: {sorted(missing)[0]}")

    mode = data["mode"]
    dof = data["dof"]
    screen_size = data["screen_size"]
    distance = data["distance"]
    make_glasses_primary = data.get("make_glasses_primary", False)
    disable_built_in_display = data.get("disable_built_in_display", False)
    if mode not in SUPPORTED_MODES:
        raise ConfigError("unsupported mode")
    if dof not in SUPPORTED_DOF:
        raise ConfigError("dof must be anchored, smooth-follow, or off")
    if screen_size not in SUPPORTED_SIZES:
        raise ConfigError("unsupported screen_size")
    if type(distance) is not int or not 1 <= distance <= 10:
        raise ConfigError("distance must be an integer from 1 to 10")
    if type(make_glasses_primary) is not bool:
        raise ConfigError("make_glasses_primary must be a boolean")
    if type(disable_built_in_display) is not bool:
        raise ConfigError("disable_built_in_display must be a boolean")
    if mode.startswith("ultrawide-") and dof != "anchored":
        raise ConfigError("ultrawide mode requires anchored dof")
    return NativeDisplayConfig(
        mode,
        dof,
        screen_size,
        distance,
        make_glasses_primary,
        disable_built_in_display,
    )


def load_config(path: Path) -> tuple[NativeDisplayConfig, str]:
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as error:
        raise ConfigError(f"could not read {path}: {error}") from error
    return parse_config(text), text


def default_config_path() -> Path:
    config_home = os.environ.get("XDG_CONFIG_HOME")
    if config_home:
        return Path(config_home) / "gapia" / "config.json"
    return Path.home() / ".config" / "gapia" / "config.json"


def default_helper_path() -> Path:
    sibling = Path(__file__).resolve().with_name("gapia-native-display")
    if sibling.is_file():
        return sibling
    installed = Path.home() / ".local" / "libexec" / "gapia-native-display"
    return installed if installed.is_file() else sibling


def default_status_path() -> Path:
    runtime_dir = os.environ.get("XDG_RUNTIME_DIR")
    if runtime_dir:
        return Path(runtime_dir) / "gapia" / "native-display-status.json"
    return Path("/run/user") / str(os.getuid()) / "gapia" / "native-display-status.json"


def default_display_policy_helper_path() -> Path:
    sibling = Path(__file__).resolve().with_name(
        "gapia-gnome-display-policy"
    )
    if sibling.is_file():
        return sibling
    installed = (
        Path.home() / ".local" / "libexec" / "gapia-gnome-display-policy"
    )
    return installed if installed.is_file() else sibling


def default_display_snapshot_path() -> Path:
    return default_status_path().with_name("display-layout-snapshot.json")


def _atomic_json_write(path: Path, data: dict[str, object], mode: int) -> None:
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    temporary_name = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=path.parent,
            prefix=f".{path.name}.",
            delete=False,
        ) as temporary:
            temporary_name = temporary.name
            json.dump(data, temporary, indent=2)
            temporary.write("\n")
            temporary.flush()
            os.fsync(temporary.fileno())
        os.chmod(temporary_name, mode)
        os.replace(temporary_name, path)
    finally:
        if temporary_name is not None:
            try:
                os.unlink(temporary_name)
            except FileNotFoundError:
                pass


def save_config(path: Path, config: NativeDisplayConfig) -> None:
    _atomic_json_write(path, config.as_dict(), 0o644)


def parse_device_info_line(line: str) -> dict[str, object] | None:
    if not line.startswith(DEVICE_INFO_PREFIX):
        return None
    try:
        data = json.loads(line.removeprefix(DEVICE_INFO_PREFIX))
    except json.JSONDecodeError as error:
        raise ValueError(f"invalid device information: {error}") from error
    if not isinstance(data, dict):
        raise ValueError("device information must be a JSON object")
    required = DEVICE_INFO_STRING_KEYS | {
        "native_tracking",
        "distance",
        "settings",
    }
    if set(data) != required:
        raise ValueError("device information fields did not match the expected schema")
    if any(not isinstance(data[key], str) for key in DEVICE_INFO_STRING_KEYS):
        raise ValueError("device information contains a non-string field")
    if type(data["native_tracking"]) is not bool:
        raise ValueError("native_tracking must be a boolean")
    if type(data["distance"]) is not int:
        raise ValueError("device distance must be an integer")
    try:
        settings = parse_config(json.dumps(data["settings"]))
    except ConfigError as error:
        raise ValueError(f"invalid device settings: {error}") from error
    if settings.distance != data["distance"]:
        raise ValueError("device distance fields do not match")
    return data


def config_from_device_info(device: dict[str, object]) -> NativeDisplayConfig:
    try:
        return parse_config(json.dumps(device["settings"]))
    except (KeyError, ConfigError) as error:
        raise ValueError(f"invalid device settings: {error}") from error


def query_device_info(
    helper_path: Path, timeout_seconds: float = 10
) -> dict[str, object]:
    try:
        result = subprocess.run(
            [str(helper_path), "--query"],
            check=False,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            timeout=timeout_seconds,
        )
    except subprocess.TimeoutExpired as error:
        raise RuntimeError("native display query timed out") from error
    except OSError as error:
        raise RuntimeError(f"could not query the native display: {error}") from error
    device_info = None
    for line in result.stdout.splitlines():
        parsed = parse_device_info_line(line)
        if parsed is not None:
            device_info = parsed
    if result.returncode != 0:
        raise RuntimeError(
            f"native display query exited with status {result.returncode}"
        )
    if device_info is None:
        raise RuntimeError("native display query returned no device information")
    return device_info


def write_status(
    path: Path,
    state: str,
    *,
    connected: bool,
    config: NativeDisplayConfig | None = None,
    device: dict[str, object] | None = None,
    message: str | None = None,
    display_policy_active: bool = False,
) -> str:
    status: dict[str, object] = {
        "state": state,
        "connected": connected,
        "display_policy_active": display_policy_active,
    }
    if config is not None:
        status["config"] = config.as_dict()
    if device is not None:
        status["device"] = device
    if message is not None:
        status["message"] = message
    serialized = json.dumps(status, sort_keys=True)
    _atomic_json_write(path, status, 0o600)
    return serialized


def glasses_usb_connected(
    devices_path: Path = Path("/sys/bus/usb/devices"),
) -> bool:
    for vendor_path in devices_path.glob("*/idVendor"):
        try:
            vendor = vendor_path.read_text(encoding="ascii").strip().lower()
            product = (
                vendor_path.with_name("idProduct")
                .read_text(encoding="ascii")
                .strip()
                .lower()
            )
        except OSError:
            continue
        if vendor == GLASSES_USB_VENDOR and product == GLASSES_USB_PRODUCT:
            return True
    return False


class NativeDisplayController:
    def __init__(
        self,
        config_path: Path,
        helper_path: Path,
        status_path: Path,
        display_policy_helper_path: Path,
        display_snapshot_path: Path,
    ):
        self.config_path = config_path
        self.helper_path = helper_path
        self.status_path = status_path
        self.display_policy_helper_path = display_policy_helper_path
        self.display_snapshot_path = display_snapshot_path
        self.running = True
        self.was_connected = False
        self.applied_revision = None
        self.failed_revision = None
        self.last_config_error = None
        self.last_status = None
        self.device_info = None
        self.display_policy_active = False

    def stop(self, _signal, _frame):
        self.running = False

    def publish_status(
        self,
        state: str,
        *,
        connected: bool,
        config: NativeDisplayConfig | None = None,
        device: dict[str, object] | None = None,
        message: str | None = None,
    ) -> None:
        status = {"state": state, "connected": connected}
        if config is not None:
            status["config"] = config.as_dict()
        if device is not None:
            status["device"] = device
        if message is not None:
            status["message"] = message
        status["display_policy_active"] = self.display_policy_active
        serialized = json.dumps(status, sort_keys=True)
        if serialized == self.last_status:
            return
        try:
            self.last_status = write_status(
                self.status_path,
                state,
                connected=connected,
                config=config,
                device=device,
                message=message,
                display_policy_active=self.display_policy_active,
            )
        except OSError as error:
            logging.error("could not update controller status: %s", error)

    def reconcile_display_policy(self, config: NativeDisplayConfig) -> bool:
        command = [
            str(self.display_policy_helper_path),
            "--snapshot",
            str(self.display_snapshot_path),
        ]
        if config.make_glasses_primary:
            command.append("--make-primary")
        if config.disable_built_in_display:
            command.append("--disable-built-in")
        try:
            result = subprocess.run(
                command,
                check=False,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
            )
        except OSError as error:
            logging.error("could not start display policy helper: %s", error)
            return False
        for line in result.stdout.splitlines():
            logging.info("display policy: %s", line)
        if result.returncode != 0:
            logging.error("display policy helper exited with status %d", result.returncode)
            return False
        self.display_policy_active = (
            config.make_glasses_primary or config.disable_built_in_display
        )
        return True

    def restore_display_policy(self) -> bool:
        if not self.display_snapshot_path.exists():
            self.display_policy_active = False
            return True
        command = [
            str(self.display_policy_helper_path),
            "--snapshot",
            str(self.display_snapshot_path),
        ]
        try:
            result = subprocess.run(
                command,
                check=False,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
            )
        except OSError as error:
            logging.error("could not restore display policy: %s", error)
            return False
        for line in result.stdout.splitlines():
            logging.info("display policy: %s", line)
        if result.returncode != 0:
            logging.error("display layout restoration exited with status %d", result.returncode)
            return False
        self.display_policy_active = False
        return True

    def apply(self, config: NativeDisplayConfig, revision: str) -> None:
        self.publish_status(
            "applying",
            connected=True,
            config=config,
            device=self.device_info,
        )
        command = [str(self.helper_path), *config.helper_arguments()]
        try:
            result = subprocess.run(
                command,
                check=False,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
            )
        except OSError as error:
            logging.error("could not start native display helper: %s", error)
            self.failed_revision = revision
            self.publish_status(
                "error",
                connected=True,
                config=config,
                device=self.device_info,
                message=str(error),
            )
            return
        for line in result.stdout.splitlines():
            try:
                device_info = parse_device_info_line(line)
            except ValueError as error:
                logging.warning("native helper: %s", error)
                continue
            if device_info is not None:
                self.device_info = device_info
            else:
                logging.info("native helper: %s", line)
        if result.returncode != 0:
            logging.error("native display helper exited with status %d", result.returncode)
            self.failed_revision = revision
            self.publish_status(
                "error",
                connected=True,
                config=config,
                device=self.device_info,
                message=f"native display helper exited with status {result.returncode}",
            )
            return
        self.applied_revision = revision
        self.failed_revision = None
        if not self.reconcile_display_policy(config):
            self.failed_revision = revision
            self.publish_status(
                "error",
                connected=True,
                config=config,
                device=self.device_info,
                message="GNOME rejected the requested display policy",
            )
            return
        logging.info(
            "native display active: mode=%s dof=%s size=%s distance=%d",
            config.mode,
            config.dof,
            config.screen_size,
            config.distance,
        )
        self.publish_status(
            "active",
            connected=True,
            config=config,
            device=self.device_info,
        )

    def run(self) -> int:
        signal.signal(signal.SIGINT, self.stop)
        signal.signal(signal.SIGTERM, self.stop)
        self.publish_status("disconnected", connected=False)
        try:
            while self.running:
                connected = glasses_usb_connected()
                if not connected:
                    if self.was_connected:
                        logging.info("VITURE Beast disconnected")
                        self.restore_display_policy()
                    self.was_connected = False
                    self.applied_revision = None
                    self.failed_revision = None
                    self.device_info = None
                    self.publish_status("disconnected", connected=False)
                    time.sleep(POLL_SECONDS)
                    continue
                if not self.was_connected:
                    logging.info("VITURE Beast connected")
                    self.was_connected = True

                try:
                    config, revision = load_config(self.config_path)
                    self.last_config_error = None
                except ConfigError as error:
                    message = str(error)
                    if message != self.last_config_error:
                        logging.error("configuration rejected: %s", message)
                        self.last_config_error = message
                    self.publish_status(
                        "config-error",
                        connected=True,
                        device=self.device_info,
                        message=message,
                    )
                    time.sleep(POLL_SECONDS)
                    continue

                if revision not in (self.applied_revision, self.failed_revision):
                    self.apply(config, revision)
                time.sleep(POLL_SECONDS)
        finally:
            self.restore_display_policy()
        return 0


def parse_arguments(argv):
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", type=Path, default=default_config_path())
    parser.add_argument("--helper", type=Path, default=default_helper_path())
    parser.add_argument("--status", type=Path, default=default_status_path())
    parser.add_argument(
        "--display-policy-helper",
        type=Path,
        default=default_display_policy_helper_path(),
    )
    parser.add_argument(
        "--display-snapshot",
        type=Path,
        default=default_display_snapshot_path(),
    )
    parser.add_argument("--check-config", action="store_true")
    return parser.parse_args(argv)


def main(argv=None):
    arguments = parse_arguments(argv)
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    try:
        config, _revision = load_config(arguments.config)
    except ConfigError as error:
        logging.error("%s", error)
        return 2
    if arguments.check_config:
        print(
            f"mode={config.mode} dof={config.dof} "
            f"screen_size={config.screen_size} distance={config.distance}"
        )
        return 0
    if not arguments.helper.is_file() or not os.access(arguments.helper, os.X_OK):
        logging.error(
            "VITURE SDK support is not installed: native display helper is not "
            "executable at %s. Download and extract the Linux SDK from "
            "https://www.viture.com/developer, then rerun "
            "sudo gapia-desktop-setup-host --sdk-dir /path/to/extracted-sdk",
            arguments.helper,
        )
        return 2
    if not arguments.display_policy_helper.is_file() or not os.access(
        arguments.display_policy_helper, os.X_OK
    ):
        logging.error(
            "display policy helper is not executable: %s",
            arguments.display_policy_helper,
        )
        return 2
    return NativeDisplayController(
        arguments.config,
        arguments.helper,
        arguments.status,
        arguments.display_policy_helper,
        arguments.display_snapshot,
    ).run()


if __name__ == "__main__":
    sys.exit(main())
