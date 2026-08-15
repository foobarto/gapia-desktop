#!/usr/bin/env python3

import json
import os
from pathlib import Path
import stat
import sys
from tempfile import TemporaryDirectory
import unittest


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "scripts"))

from native_display_controller import (
    ConfigError,
    config_from_device_info,
    glasses_usb_connected,
    load_config,
    parse_config,
    parse_device_info_line,
    save_config,
    write_status,
)


class NativeDisplayConfigTest(unittest.TestCase):
    def test_project_config_selects_verified_ultrawide_profile(self):
        config, _revision = load_config(PROJECT_ROOT / "config" / "gapia.json")
        self.assertEqual(config.mode, "ultrawide-3840x1080-60")
        self.assertEqual(config.dof, "anchored")
        self.assertEqual(config.screen_size, "large")
        self.assertEqual(config.distance, 9)
        self.assertFalse(config.make_glasses_primary)
        self.assertFalse(config.disable_built_in_display)
        self.assertEqual(
            config.helper_arguments(),
            [
                "--mode",
                "ultrawide-3840x1080-60",
                "--dof",
                "anchored",
                "--size",
                "large",
                "--distance",
                "9",
            ],
        )

    def test_standard_mode_allows_every_tracking_profile(self):
        for tracking in ("anchored", "smooth-follow", "off"):
            config = parse_config(
                json.dumps(
                    {
                        "mode": "standard-1920x1080-60",
                        "dof": tracking,
                        "screen_size": "medium",
                        "distance": 7,
                    }
                )
            )
            self.assertEqual(config.dof, tracking)

    def test_connection_policies_are_optional_strict_booleans(self):
        config = parse_config(
            '{"mode":"standard-1920x1080-60","dof":"smooth-follow",'
            '"screen_size":"large","distance":9,'
            '"make_glasses_primary":true,"disable_built_in_display":true}'
        )
        self.assertTrue(config.make_glasses_primary)
        self.assertTrue(config.disable_built_in_display)

        legacy = parse_config(
            '{"mode":"standard-1920x1080-60","dof":"smooth-follow",'
            '"screen_size":"large","distance":9}'
        )
        self.assertFalse(legacy.make_glasses_primary)
        self.assertFalse(legacy.disable_built_in_display)

        with self.assertRaisesRegex(ConfigError, "must be a boolean"):
            parse_config(
                '{"mode":"standard-1920x1080-60","dof":"smooth-follow",'
                '"screen_size":"large","distance":9,'
                '"disable_built_in_display":1}'
            )

    def test_ultrawide_rejects_non_anchored_dof(self):
        with self.assertRaisesRegex(ConfigError, "requires anchored"):
            parse_config(
                '{"mode":"ultrawide-3840x1080-60","dof":"off",'
                '"screen_size":"large","distance":9}'
            )

    def test_unknown_and_duplicate_keys_are_rejected(self):
        with self.assertRaisesRegex(ConfigError, "unknown configuration key"):
            parse_config(
                '{"mode":"standard-1920x1200-60","dof":"off",'
                '"screen_size":"large","distance":9,"width":1920}'
            )
        with self.assertRaisesRegex(ConfigError, "duplicate JSON key"):
            parse_config(
                '{"mode":"standard-1920x1200-60",'
                '"mode":"standard-1920x1080-60","dof":"off",'
                '"screen_size":"large","distance":9}'
            )

    def test_invalid_distance_is_rejected(self):
        with self.assertRaisesRegex(ConfigError, "distance must be an integer"):
            parse_config(
                '{"mode":"standard-1920x1200-60","dof":"off",'
                '"screen_size":"large","distance":true}'
            )

    def test_usb_presence_matches_vendor_and_product(self):
        with TemporaryDirectory() as directory:
            device = Path(directory) / "5-1.3"
            device.mkdir()
            (device / "idVendor").write_text("35ca\n", encoding="ascii")
            (device / "idProduct").write_text("1211\n", encoding="ascii")
            self.assertTrue(glasses_usb_connected(Path(directory)))
            (device / "idProduct").write_text("ffff\n", encoding="ascii")
            self.assertFalse(glasses_usb_connected(Path(directory)))

    def test_config_save_is_atomic_and_round_trips(self):
        with TemporaryDirectory() as directory:
            path = Path(directory) / "nested" / "config.json"
            expected = parse_config(
                '{"mode":"standard-1920x1080-60","dof":"smooth-follow",'
                '"screen_size":"large","distance":9}'
            )
            save_config(path, expected)
            actual, _revision = load_config(path)
            self.assertEqual(actual, expected)
            self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o644)
            self.assertEqual(list(path.parent.glob(".config.json.*")), [])

    def test_runtime_status_is_private_and_structured(self):
        with TemporaryDirectory() as directory:
            path = Path(directory) / "runtime" / "status.json"
            config = parse_config(
                '{"mode":"ultrawide-3840x1080-60","dof":"anchored",'
                '"screen_size":"large","distance":9}'
            )
            serialized = write_status(
                path,
                "active",
                connected=True,
                config=config,
                display_policy_active=True,
            )
            self.assertEqual(json.loads(serialized), json.loads(path.read_text()))
            self.assertTrue(json.loads(serialized)["display_policy_active"])
            self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o600)
            self.assertEqual(os.listdir(path.parent), ["status.json"])

    def test_device_information_uses_a_strict_json_record(self):
        expected = {
            "brand": "VITURE",
            "model": "Beast",
            "firmware": "1.2.3",
            "usb_id": "35ca:1211",
            "sdk_version": "2.4.0",
            "device_family": "Gen 2",
            "native_tracking": True,
            "display_mode": "3840x1080 @ 60 Hz",
            "tracking": "Anchored 3DoF",
            "screen_size": "Large",
            "distance": 9,
            "settings": {
                "mode": "ultrawide-3840x1080-60",
                "dof": "anchored",
                "screen_size": "large",
                "distance": 9,
            },
        }
        line = "GAPIA_DEVICE_INFO " + json.dumps(expected)
        self.assertEqual(parse_device_info_line(line), expected)
        self.assertEqual(
            config_from_device_info(expected),
            parse_config(json.dumps(expected["settings"])),
        )
        self.assertIsNone(parse_device_info_line("ordinary helper output"))
        with self.assertRaisesRegex(ValueError, "expected schema"):
            parse_device_info_line(
                "GAPIA_DEVICE_INFO " + json.dumps({"model": "Beast"})
            )


if __name__ == "__main__":
    unittest.main()
