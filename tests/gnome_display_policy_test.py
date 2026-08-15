#!/usr/bin/env python3

from pathlib import Path
import sys
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "scripts"))

from gnome_display_policy import (  # noqa: E402
    ConfigLogicalMonitor,
    ConfigMonitor,
    DisplayPolicyError,
    DisplayState,
    LogicalMonitor,
    Mode,
    Monitor,
    build_policy_layout,
    find_target,
    layout_matches,
    reconcile,
    snapshot_from_state,
)


def monitor(
    connector: str,
    product: str,
    *,
    built_in: bool,
    mode_name: str,
) -> Monitor:
    mode = Mode(mode_name, (1.0,), True, True)
    return Monitor(
        connector,
        "VIT" if product.startswith("VITURE") else "BOE",
        product,
        "serial",
        built_in,
        None,
        None,
        {mode_name: mode},
    )


def connected_state() -> DisplayState:
    built_in = monitor(
        "eDP-1", "Internal panel", built_in=True, mode_name="2880x1800@60.000"
    )
    glasses = monitor(
        "DP-1", "VITURE Beast", built_in=False, mode_name="3840x1080@60.000"
    )
    return DisplayState(
        7,
        1,
        {built_in.connector: built_in, glasses.connector: glasses},
        (
            LogicalMonitor(0, 0, 1.5, 0, True, ("eDP-1",)),
            LogicalMonitor(1920, 0, 1.0, 0, False, ("DP-1",)),
        ),
    )


class DisplayPolicyTest(unittest.TestCase):
    def test_privacy_layout_keeps_only_connected_viture_display(self):
        state = connected_state()
        target = find_target(state)
        self.assertIsNotNone(target)
        snapshot = snapshot_from_state(state, target)

        layout = build_policy_layout(
            state,
            snapshot,
            target,
            make_primary=False,
            disable_built_in=True,
        )

        self.assertEqual(len(layout), 1)
        self.assertEqual(layout[0].monitors[0].connector, "DP-1")
        self.assertTrue(layout[0].primary)

    def test_primary_policy_keeps_built_in_active(self):
        state = connected_state()
        target = find_target(state)
        snapshot = snapshot_from_state(state, target)

        layout = build_policy_layout(
            state,
            snapshot,
            target,
            make_primary=True,
            disable_built_in=False,
        )

        self.assertEqual(
            {item.monitors[0].connector for item in layout}, {"eDP-1", "DP-1"}
        )
        primary = next(item for item in layout if item.primary)
        self.assertEqual(primary.monitors[0].connector, "DP-1")
        self.assertIs(layout[0], primary)
        self.assertTrue(layout_matches(state, snapshot.logical_monitors))
        self.assertFalse(layout_matches(state, layout))

    def test_privacy_policy_refuses_to_run_without_viture_display(self):
        state = connected_state()
        state = DisplayState(
            state.serial,
            state.layout_mode,
            {"eDP-1": state.monitors["eDP-1"]},
            (state.logical_monitors[0],),
        )

        class FakeDisplayConfig:
            def __init__(self):
                self.apply_calls = []

            def get_state(self):
                return state

            def apply(self, *args):
                self.apply_calls.append(args)

        with TemporaryDirectory() as directory:
            snapshot_path = Path(directory) / "snapshot.json"
            with patch(
                "gnome_display_policy.MutterDisplayConfig", FakeDisplayConfig
            ):
                with self.assertRaisesRegex(
                    DisplayPolicyError, "no VITURE display is connected"
                ):
                    reconcile(
                        snapshot_path,
                        make_primary=False,
                        disable_built_in=True,
                    )
            self.assertFalse(snapshot_path.exists())


if __name__ == "__main__":
    unittest.main()
