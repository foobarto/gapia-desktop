#!/usr/bin/env python3

from __future__ import annotations

import argparse
from dataclasses import dataclass
import json
import os
from pathlib import Path
import tempfile
import time

import gi

gi.require_version("Gio", "2.0")
from gi.repository import Gio, GLib


DISPLAY_CONFIG_NAME = "org.gnome.Mutter.DisplayConfig"
DISPLAY_CONFIG_PATH = "/org/gnome/Mutter/DisplayConfig"
DISPLAY_CONFIG_INTERFACE = "org.gnome.Mutter.DisplayConfig"
CONFIG_METHOD_VERIFY = 0
CONFIG_METHOD_TEMPORARY = 1
SNAPSHOT_VERSION = 1
APPLY_TIMEOUT_SECONDS = 5.0
APPLY_POLL_SECONDS = 0.1


class DisplayPolicyError(RuntimeError):
    pass


@dataclass(frozen=True)
class Mode:
    name: str
    supported_scales: tuple[float, ...]
    current: bool
    preferred: bool


@dataclass(frozen=True)
class Monitor:
    connector: str
    vendor: str
    product: str
    serial: str
    built_in: bool
    color_mode: int | None
    rgb_range: int | None
    modes: dict[str, Mode]

    @property
    def current_mode(self) -> Mode | None:
        return next((mode for mode in self.modes.values() if mode.current), None)

    @property
    def preferred_mode(self) -> Mode | None:
        return next((mode for mode in self.modes.values() if mode.preferred), None)


@dataclass(frozen=True)
class LogicalMonitor:
    x: int
    y: int
    scale: float
    transform: int
    primary: bool
    connectors: tuple[str, ...]


@dataclass(frozen=True)
class DisplayState:
    serial: int
    layout_mode: int
    monitors: dict[str, Monitor]
    logical_monitors: tuple[LogicalMonitor, ...]


@dataclass
class ConfigMonitor:
    connector: str
    mode: str
    color_mode: int | None
    rgb_range: int | None

    def as_dict(self) -> dict[str, object]:
        return {
            "connector": self.connector,
            "mode": self.mode,
            "color_mode": self.color_mode,
            "rgb_range": self.rgb_range,
        }

    @classmethod
    def from_dict(cls, data: object) -> ConfigMonitor:
        if not isinstance(data, dict) or set(data) != {
            "connector",
            "mode",
            "color_mode",
            "rgb_range",
        }:
            raise DisplayPolicyError("invalid monitor in display snapshot")
        if not isinstance(data["connector"], str) or not isinstance(data["mode"], str):
            raise DisplayPolicyError("invalid monitor identity in display snapshot")
        for key in ("color_mode", "rgb_range"):
            if data[key] is not None and type(data[key]) is not int:
                raise DisplayPolicyError(f"invalid {key} in display snapshot")
        return cls(
            data["connector"],
            data["mode"],
            data["color_mode"],
            data["rgb_range"],
        )


@dataclass
class ConfigLogicalMonitor:
    x: int
    y: int
    scale: float
    transform: int
    primary: bool
    monitors: list[ConfigMonitor]

    def as_dict(self) -> dict[str, object]:
        return {
            "x": self.x,
            "y": self.y,
            "scale": self.scale,
            "transform": self.transform,
            "primary": self.primary,
            "monitors": [monitor.as_dict() for monitor in self.monitors],
        }

    @classmethod
    def from_dict(cls, data: object) -> ConfigLogicalMonitor:
        required = {"x", "y", "scale", "transform", "primary", "monitors"}
        if not isinstance(data, dict) or set(data) != required:
            raise DisplayPolicyError("invalid logical monitor in display snapshot")
        if type(data["x"]) is not int or type(data["y"]) is not int:
            raise DisplayPolicyError("invalid monitor position in display snapshot")
        if type(data["scale"]) not in {int, float} or data["scale"] <= 0:
            raise DisplayPolicyError("invalid monitor scale in display snapshot")
        if type(data["transform"]) is not int or not 0 <= data["transform"] <= 7:
            raise DisplayPolicyError("invalid monitor transform in display snapshot")
        if type(data["primary"]) is not bool or not isinstance(data["monitors"], list):
            raise DisplayPolicyError("invalid logical monitor flags in display snapshot")
        monitors = [ConfigMonitor.from_dict(item) for item in data["monitors"]]
        if not monitors:
            raise DisplayPolicyError("empty logical monitor in display snapshot")
        return cls(
            data["x"],
            data["y"],
            float(data["scale"]),
            data["transform"],
            data["primary"],
            monitors,
        )


@dataclass
class LayoutSnapshot:
    layout_mode: int
    target_connector: str
    primary_connector: str
    logical_monitors: list[ConfigLogicalMonitor]

    def as_dict(self) -> dict[str, object]:
        return {
            "version": SNAPSHOT_VERSION,
            "layout_mode": self.layout_mode,
            "target_connector": self.target_connector,
            "primary_connector": self.primary_connector,
            "logical_monitors": [item.as_dict() for item in self.logical_monitors],
        }

    @classmethod
    def from_dict(cls, data: object) -> LayoutSnapshot:
        required = {
            "version",
            "layout_mode",
            "target_connector",
            "primary_connector",
            "logical_monitors",
        }
        if not isinstance(data, dict) or set(data) != required:
            raise DisplayPolicyError("invalid display snapshot schema")
        if data["version"] != SNAPSHOT_VERSION or data["layout_mode"] not in {1, 2}:
            raise DisplayPolicyError("unsupported display snapshot")
        if not isinstance(data["target_connector"], str) or not isinstance(
            data["primary_connector"], str
        ):
            raise DisplayPolicyError("invalid connector in display snapshot")
        if not isinstance(data["logical_monitors"], list):
            raise DisplayPolicyError("invalid logical monitors in display snapshot")
        logical_monitors = [
            ConfigLogicalMonitor.from_dict(item) for item in data["logical_monitors"]
        ]
        if not logical_monitors:
            raise DisplayPolicyError("display snapshot has no logical monitors")
        return cls(
            data["layout_mode"],
            data["target_connector"],
            data["primary_connector"],
            logical_monitors,
        )


class MutterDisplayConfig:
    def __init__(self):
        self.proxy = Gio.DBusProxy.new_for_bus_sync(
            Gio.BusType.SESSION,
            Gio.DBusProxyFlags.NONE,
            None,
            DISPLAY_CONFIG_NAME,
            DISPLAY_CONFIG_PATH,
            DISPLAY_CONFIG_INTERFACE,
            None,
        )

    def get_state(self) -> DisplayState:
        variant = self.proxy.call_sync(
            "GetCurrentState",
            None,
            Gio.DBusCallFlags.NO_AUTO_START,
            -1,
            None,
        )
        monitors: dict[str, Monitor] = {}
        for monitor_variant in variant[1]:
            connector, vendor, product, serial = monitor_variant[0]
            modes = {}
            for mode_variant in monitor_variant[1]:
                properties = mode_variant[6]
                mode = Mode(
                    mode_variant[0],
                    tuple(mode_variant[5]),
                    "is-current" in properties,
                    "is-preferred" in properties,
                )
                modes[mode.name] = mode
            properties = monitor_variant[2]
            monitors[connector] = Monitor(
                connector,
                vendor,
                product,
                serial,
                properties.get("is-builtin", False),
                properties.get("color-mode"),
                properties.get("rgb-range"),
                modes,
            )
        logical_monitors = tuple(
            LogicalMonitor(
                item[0],
                item[1],
                item[2],
                item[3],
                item[4],
                tuple(spec[0] for spec in item[5]),
            )
            for item in variant[2]
        )
        return DisplayState(
            variant[0],
            variant[3].get("layout-mode", 1),
            monitors,
            logical_monitors,
        )

    def apply(
        self,
        state: DisplayState,
        logical_monitors: list[ConfigLogicalMonitor],
        layout_mode: int,
        method: int,
    ) -> None:
        logical_tuples = []
        for logical in logical_monitors:
            monitor_tuples = []
            for monitor in logical.monitors:
                properties = {}
                if monitor.color_mode is not None:
                    properties["color-mode"] = GLib.Variant("u", monitor.color_mode)
                if monitor.rgb_range is not None:
                    properties["rgb-range"] = GLib.Variant("u", monitor.rgb_range)
                monitor_tuples.append((monitor.connector, monitor.mode, properties))
            logical_tuples.append(
                (
                    logical.x,
                    logical.y,
                    logical.scale,
                    logical.transform,
                    logical.primary,
                    monitor_tuples,
                )
            )
        parameters = GLib.Variant(
            "(uua(iiduba(ssa{sv}))a{sv})",
            (
                state.serial,
                method,
                logical_tuples,
                {"layout-mode": GLib.Variant("u", layout_mode)},
            ),
        )
        self.proxy.call_sync(
            "ApplyMonitorsConfig",
            parameters,
            Gio.DBusCallFlags.NO_AUTO_START,
            -1,
            None,
        )


def is_viture_monitor(monitor: Monitor) -> bool:
    return monitor.product.strip().upper().startswith("VITURE")


def find_target(state: DisplayState) -> Monitor | None:
    targets = [monitor for monitor in state.monitors.values() if is_viture_monitor(monitor)]
    if len(targets) > 1:
        raise DisplayPolicyError("multiple VITURE displays are connected")
    return targets[0] if targets else None


def config_from_current(state: DisplayState) -> list[ConfigLogicalMonitor]:
    result = []
    for logical in state.logical_monitors:
        monitors = []
        for connector in logical.connectors:
            monitor = state.monitors[connector]
            mode = monitor.current_mode
            if mode is None:
                raise DisplayPolicyError(f"active monitor {connector} has no current mode")
            monitors.append(
                ConfigMonitor(
                    connector,
                    mode.name,
                    monitor.color_mode,
                    monitor.rgb_range,
                )
            )
        result.append(
            ConfigLogicalMonitor(
                logical.x,
                logical.y,
                logical.scale,
                logical.transform,
                logical.primary,
                monitors,
            )
        )
    return result


def snapshot_from_state(state: DisplayState, target: Monitor) -> LayoutSnapshot:
    logical_monitors = config_from_current(state)
    primary = next((item for item in logical_monitors if item.primary), None)
    if primary is None:
        raise DisplayPolicyError("current display configuration has no primary monitor")
    return LayoutSnapshot(
        state.layout_mode,
        target.connector,
        primary.monitors[0].connector,
        logical_monitors,
    )


def current_logical_by_connector(
    state: DisplayState,
) -> dict[str, LogicalMonitor]:
    return {
        connector: logical
        for logical in state.logical_monitors
        for connector in logical.connectors
    }


def restore_layout(
    state: DisplayState,
    snapshot: LayoutSnapshot,
    target: Monitor | None,
) -> list[ConfigLogicalMonitor]:
    current_logical = current_logical_by_connector(state)
    current_configs = config_from_current(state)
    restored_connectors: set[str] = set()
    restored = []
    for saved_logical in snapshot.logical_monitors:
        monitors = []
        contains_target = False
        for saved_monitor in saved_logical.monitors:
            connector = saved_monitor.connector
            is_target = connector == snapshot.target_connector
            if is_target:
                if target is None:
                    continue
                connector = target.connector
                contains_target = True
            monitor = state.monitors.get(connector)
            if monitor is None:
                continue
            if is_target and monitor.current_mode is not None:
                mode = monitor.current_mode
                color_mode = monitor.color_mode
                rgb_range = monitor.rgb_range
            else:
                mode = monitor.modes.get(saved_monitor.mode)
                if mode is None:
                    mode = monitor.current_mode or monitor.preferred_mode
                color_mode = saved_monitor.color_mode
                rgb_range = saved_monitor.rgb_range
            if mode is None:
                continue
            monitors.append(ConfigMonitor(connector, mode.name, color_mode, rgb_range))
            restored_connectors.add(connector)
        if not monitors:
            continue
        scale = saved_logical.scale
        if contains_target and target is not None and target.connector in current_logical:
            scale = current_logical[target.connector].scale
        restored.append(
            ConfigLogicalMonitor(
                saved_logical.x,
                saved_logical.y,
                scale,
                saved_logical.transform,
                saved_logical.primary,
                monitors,
            )
        )
    for current in current_configs:
        if any(monitor.connector not in restored_connectors for monitor in current.monitors):
            restored.append(current)
    if not restored:
        raise DisplayPolicyError("no monitors are available for layout restoration")
    return restored


def select_primary(
    logical_monitors: list[ConfigLogicalMonitor], connector: str
) -> None:
    selected = None
    for logical in logical_monitors:
        logical.primary = any(monitor.connector == connector for monitor in logical.monitors)
        if logical.primary:
            selected = logical
    if selected is None:
        logical_monitors[0].primary = True
        selected = logical_monitors[0]

    # GNOME 50 does not clear is_primary when reusing an unchanged logical
    # monitor. Moving the requested primary first forces a clean object update.
    logical_monitors.remove(selected)
    logical_monitors.insert(0, selected)


def normalize_positions(logical_monitors: list[ConfigLogicalMonitor]) -> None:
    minimum_x = min(item.x for item in logical_monitors)
    minimum_y = min(item.y for item in logical_monitors)
    for logical in logical_monitors:
        logical.x -= minimum_x
        logical.y -= minimum_y


def build_policy_layout(
    state: DisplayState,
    snapshot: LayoutSnapshot,
    target: Monitor,
    make_primary: bool,
    disable_built_in: bool,
) -> list[ConfigLogicalMonitor]:
    logical_monitors = restore_layout(state, snapshot, target)
    if disable_built_in:
        built_in = {
            monitor.connector for monitor in state.monitors.values() if monitor.built_in
        }
        filtered = []
        for logical in logical_monitors:
            logical.monitors = [
                monitor for monitor in logical.monitors if monitor.connector not in built_in
            ]
            if logical.monitors:
                filtered.append(logical)
        logical_monitors = filtered
        if not logical_monitors:
            raise DisplayPolicyError("privacy policy would disable every monitor")
    primary_connector = (
        target.connector
        if make_primary or disable_built_in
        else snapshot.primary_connector
    )
    select_primary(logical_monitors, primary_connector)
    normalize_positions(logical_monitors)
    return logical_monitors


def _atomic_save(path: Path, data: dict[str, object]) -> None:
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
        os.chmod(temporary_name, 0o600)
        os.replace(temporary_name, path)
    finally:
        if temporary_name is not None:
            try:
                os.unlink(temporary_name)
            except FileNotFoundError:
                pass


def save_snapshot(path: Path, snapshot: LayoutSnapshot) -> None:
    _atomic_save(path, snapshot.as_dict())


def load_snapshot(path: Path) -> LayoutSnapshot | None:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return None
    except (OSError, json.JSONDecodeError) as error:
        raise DisplayPolicyError(f"could not read display snapshot: {error}") from error
    return LayoutSnapshot.from_dict(data)


def remove_snapshot(path: Path) -> None:
    try:
        path.unlink()
    except FileNotFoundError:
        pass


def apply_verified(
    display_config: MutterDisplayConfig,
    logical_monitors: list[ConfigLogicalMonitor],
    layout_mode: int,
    verify_only: bool,
) -> None:
    state = display_config.get_state()
    display_config.apply(
        state, logical_monitors, layout_mode, CONFIG_METHOD_VERIFY
    )
    if verify_only:
        return
    state = display_config.get_state()
    display_config.apply(
        state, logical_monitors, layout_mode, CONFIG_METHOD_TEMPORARY
    )
    deadline = time.monotonic() + APPLY_TIMEOUT_SECONDS
    while time.monotonic() < deadline:
        if layout_matches(display_config.get_state(), logical_monitors):
            return
        time.sleep(APPLY_POLL_SECONDS)
    raise DisplayPolicyError("GNOME did not activate the requested display layout")


def layout_matches(
    state: DisplayState,
    expected: list[ConfigLogicalMonitor],
) -> bool:
    actual_by_connectors = {
        frozenset(item.connectors): item for item in state.logical_monitors
    }
    expected_by_connectors = {
        frozenset(monitor.connector for monitor in item.monitors): item
        for item in expected
    }
    if set(actual_by_connectors) != set(expected_by_connectors):
        return False
    for connectors, expected_logical in expected_by_connectors.items():
        actual = actual_by_connectors[connectors]
        if (
            actual.x != expected_logical.x
            or actual.y != expected_logical.y
            or abs(actual.scale - expected_logical.scale) > 0.001
            or actual.transform != expected_logical.transform
            or actual.primary != expected_logical.primary
        ):
            return False
        for expected_monitor in expected_logical.monitors:
            monitor = state.monitors.get(expected_monitor.connector)
            if monitor is None or monitor.current_mode is None:
                return False
            if monitor.current_mode.name != expected_monitor.mode:
                return False
    return True


def reconcile(
    snapshot_path: Path,
    make_primary: bool,
    disable_built_in: bool,
    verify_only: bool = False,
) -> str:
    display_config = MutterDisplayConfig()
    state = display_config.get_state()
    target = find_target(state)
    snapshot = load_snapshot(snapshot_path)

    if not make_primary and not disable_built_in:
        if snapshot is None:
            return "display policy inactive"
        logical_monitors = restore_layout(state, snapshot, target)
        select_primary(logical_monitors, snapshot.primary_connector)
        normalize_positions(logical_monitors)
        apply_verified(
            display_config, logical_monitors, snapshot.layout_mode, verify_only
        )
        if not verify_only:
            remove_snapshot(snapshot_path)
        return "previous display layout restored"

    if target is None:
        raise DisplayPolicyError("no VITURE display is connected")
    if snapshot is None:
        snapshot = snapshot_from_state(state, target)
        if not verify_only:
            save_snapshot(snapshot_path, snapshot)
    logical_monitors = build_policy_layout(
        state,
        snapshot,
        target,
        make_primary,
        disable_built_in,
    )
    apply_verified(display_config, logical_monitors, snapshot.layout_mode, verify_only)
    policies = []
    if make_primary:
        policies.append("VITURE primary")
    if disable_built_in:
        policies.append("built-in disabled")
    return "display policy active: " + ", ".join(policies)


def parse_arguments(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--snapshot", type=Path, required=True)
    parser.add_argument("--make-primary", action="store_true")
    parser.add_argument("--disable-built-in", action="store_true")
    parser.add_argument("--verify-only", action="store_true")
    return parser.parse_args(argv)


def main(argv=None) -> int:
    arguments = parse_arguments(argv)
    try:
        message = reconcile(
            arguments.snapshot,
            arguments.make_primary,
            arguments.disable_built_in,
            arguments.verify_only,
        )
    except (DisplayPolicyError, GLib.Error) as error:
        print(f"gapia-gnome-display-policy: {error}")
        return 1
    print(message)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
