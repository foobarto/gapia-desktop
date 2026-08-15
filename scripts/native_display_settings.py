#!/usr/bin/env python3

from __future__ import annotations

import json
from pathlib import Path
import sys
import threading
import time

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, Gio, GLib, Gtk, Pango


SCRIPT_DIR = Path(__file__).resolve().parent
MODULE_DIRS = (
    SCRIPT_DIR,
    Path.home() / ".local" / "lib" / "gapia",
)
for module_dir in reversed(MODULE_DIRS):
    if str(module_dir) not in sys.path:
        sys.path.insert(0, str(module_dir))

from native_display_controller import (  # noqa: E402
    ConfigError,
    NativeDisplayConfig,
    default_config_path,
    default_helper_path,
    default_status_path,
    config_from_device_info,
    load_config,
    query_device_info,
    save_config,
)


ULTRAWIDE_MODE = "ultrawide-3840x1080-60"
STANDARD_MODE = "standard-1920x1080-60"
TRACKING_VALUES = ("anchored", "smooth-follow", "off")
SIZE_VALUES = ("small", "medium", "large", "extra-large", "ultra-large")
STATUS_TIMEOUT_SECONDS = 15


class SettingsWindow(Adw.ApplicationWindow):
    def __init__(self, application: Adw.Application):
        super().__init__(application=application)
        self.config_path = default_config_path()
        self.status_path = default_status_path()
        self.helper_path = default_helper_path()
        self.pending_config: NativeDisplayConfig | None = None
        self.pending_since = 0.0
        self.standard_tracking = "smooth-follow"
        self.loading_controls = False
        self.controls_dirty = False
        self.query_in_progress = False

        self.set_title("Gapia Desktop")
        self.set_default_size(540, 430)
        self.set_size_request(360, 380)

        toolbar_view = Adw.ToolbarView()
        header = Adw.HeaderBar()
        toolbar_view.add_top_bar(header)
        self.set_content(toolbar_view)

        view_stack = Adw.ViewStack()
        self.view_stack = view_stack
        view_switcher = Adw.ViewSwitcher(
            policy=Adw.ViewSwitcherPolicy.WIDE,
            stack=view_stack,
        )
        header.set_title_widget(view_switcher)
        toolbar_view.set_content(view_stack)

        settings_page = Adw.PreferencesPage()
        settings_stack_page = view_stack.add_titled(
            settings_page, "display", "Display"
        )
        settings_stack_page.set_icon_name("video-display-symbolic")

        mode_group = Adw.PreferencesGroup(title="Display")
        settings_page.add(mode_group)

        mode_row = Adw.ActionRow(title="Workspace")
        mode_group.add(mode_row)
        mode_buttons = Gtk.Box(spacing=0)
        mode_buttons.add_css_class("linked")
        self.ultrawide_button = Gtk.ToggleButton(label="Ultrawide")
        self.standard_button = Gtk.ToggleButton(label="Standard")
        self.standard_button.set_group(self.ultrawide_button)
        self.ultrawide_button.set_size_request(100, -1)
        self.standard_button.set_size_request(100, -1)
        mode_buttons.append(self.ultrawide_button)
        mode_buttons.append(self.standard_button)
        mode_row.add_suffix(mode_buttons)

        tracking_model = Gtk.StringList.new(
            ["Anchored", "Smooth follow", "0DoF"]
        )
        self.tracking_row = Adw.ComboRow(
            title="Tracking",
            model=tracking_model,
        )
        mode_group.add(self.tracking_row)

        policy_group = Adw.PreferencesGroup(title="When glasses connect")
        settings_page.add(policy_group)

        self.primary_switch = Adw.SwitchRow(
            title="Make glasses primary",
            subtitle="Moves the GNOME primary display to the glasses",
        )
        policy_group.add(self.primary_switch)

        self.privacy_switch = Adw.SwitchRow(
            title="Disable built-in display",
            subtitle="Restores it when the glasses disconnect",
        )
        policy_group.add(self.privacy_switch)

        placement_group = Adw.PreferencesGroup(title="Placement")
        settings_page.add(placement_group)

        size_model = Gtk.StringList.new(
            ["Small", "Medium", "Large", "Extra large", "Ultra large"]
        )
        self.size_row = Adw.ComboRow(title="Screen size", model=size_model)
        placement_group.add(self.size_row)

        self.distance_row = Adw.SpinRow.new_with_range(1, 10, 1)
        self.distance_row.set_title("Distance")
        placement_group.add(self.distance_row)

        device_page = Adw.PreferencesPage()
        device_stack_page = view_stack.add_titled(device_page, "device", "Device")
        device_stack_page.set_icon_name("dialog-information-symbolic")

        identity_group = Adw.PreferencesGroup(title="Detected device")
        device_page.add(identity_group)
        self.device_rows = {}
        for key, title in (
            ("brand", "Brand"),
            ("model", "Model"),
            ("device_family", "Device family"),
            ("firmware", "Firmware"),
            ("usb_id", "USB ID"),
            ("sdk_version", "SDK version"),
            ("native_tracking", "Native tracking"),
        ):
            row = Adw.ActionRow(title=title, subtitle="Not detected")
            identity_group.add(row)
            self.device_rows[key] = row

        state_group = Adw.PreferencesGroup(title="Active hardware state")
        device_page.add(state_group)
        for key, title in (
            ("display_mode", "Display mode"),
            ("tracking", "Tracking"),
            ("screen_size", "Screen size"),
            ("distance", "Distance"),
        ):
            row = Adw.ActionRow(title=title, subtitle="Not detected")
            state_group.add(row)
            self.device_rows[key] = row

        action_bar = Gtk.ActionBar()
        status_box = Gtk.Box(spacing=8)
        status_box.set_valign(Gtk.Align.CENTER)
        self.status_icon = Gtk.Image.new_from_icon_name("dialog-information-symbolic")
        self.status_label = Gtk.Label(label="Loading configuration")
        self.status_label.set_ellipsize(Pango.EllipsizeMode.END)
        status_box.append(self.status_icon)
        status_box.append(self.status_label)
        action_bar.pack_start(status_box)

        self.apply_button = Gtk.Button()
        apply_content = Gtk.Box(spacing=7)
        apply_content.set_halign(Gtk.Align.CENTER)
        apply_content.append(Gtk.Image.new_from_icon_name("object-select-symbolic"))
        apply_content.append(Gtk.Label(label="Apply Changes"))
        self.apply_button.set_child(apply_content)
        self.apply_button.set_size_request(140, -1)
        self.apply_button.set_tooltip_text("Apply display settings")
        self.apply_button.add_css_class("suggested-action")
        action_bar.pack_end(self.apply_button)
        toolbar_view.add_bottom_bar(action_bar)

        self.ultrawide_button.connect("toggled", self.on_mode_changed)
        self.standard_button.connect("toggled", self.on_mode_changed)
        self.tracking_row.connect("notify::selected", self.on_tracking_changed)
        self.size_row.connect("notify::selected", self.on_setting_changed)
        self.distance_row.connect("notify::value", self.on_setting_changed)
        self.primary_switch.connect("notify::active", self.on_setting_changed)
        self.privacy_switch.connect("notify::active", self.on_setting_changed)
        self.apply_button.connect("clicked", self.on_apply)
        self.view_stack.connect("notify::visible-child-name", self.on_page_changed)

        self.load_current_config()
        status = self.update_status_from_file()
        self.sync_controls_from_status(status)
        if not self.helper_path.is_file():
            self.set_status(
                "VITURE SDK support is not installed; see Setup",
                "dialog-warning-symbolic",
            )
            self.status_label.set_tooltip_text(
                "Download and extract the VITURE Linux SDK, then run "
                "sudo gapia-desktop-setup-host --sdk-dir /path/to/extracted-sdk"
            )
        self.refresh_hardware_settings()
        GLib.timeout_add_seconds(1, self.refresh_status)

    def set_status(self, text: str, icon_name: str) -> None:
        self.status_label.set_label(text)
        self.status_icon.set_from_icon_name(icon_name)

    def load_current_config(self) -> None:
        try:
            config, _revision = load_config(self.config_path)
        except ConfigError as error:
            self.set_status(str(error), "dialog-error-symbolic")
            self.apply_button.set_sensitive(False)
            return

        self.set_controls(config)

    def set_controls(
        self,
        config: NativeDisplayConfig,
        *,
        update_policies: bool = True,
    ) -> None:
        self.loading_controls = True
        try:
            is_ultrawide = config.mode.startswith("ultrawide-")
            if not is_ultrawide:
                self.standard_tracking = config.dof
            self.ultrawide_button.set_active(is_ultrawide)
            self.standard_button.set_active(not is_ultrawide)
            self.tracking_row.set_selected(TRACKING_VALUES.index(config.dof))
            self.size_row.set_selected(SIZE_VALUES.index(config.screen_size))
            self.distance_row.set_value(config.distance)
            if update_policies:
                self.primary_switch.set_active(config.make_glasses_primary)
                self.privacy_switch.set_active(config.disable_built_in_display)
            self.update_mode_controls()
        finally:
            self.loading_controls = False
        self.controls_dirty = False

    def on_mode_changed(self, button: Gtk.ToggleButton) -> None:
        if not button.get_active():
            return
        if not self.loading_controls:
            self.controls_dirty = True
        self.update_mode_controls()

    def update_mode_controls(self) -> None:
        if self.ultrawide_button.get_active():
            selected = self.tracking_row.get_selected()
            if selected < len(TRACKING_VALUES) and TRACKING_VALUES[selected] != "anchored":
                self.standard_tracking = TRACKING_VALUES[selected]
            self.tracking_row.set_selected(0)
            self.tracking_row.set_sensitive(False)
            self.tracking_row.set_subtitle("Anchored is required for ultrawide")
        else:
            self.tracking_row.set_sensitive(True)
            self.tracking_row.set_subtitle("")
            self.tracking_row.set_selected(
                TRACKING_VALUES.index(self.standard_tracking)
            )

    def on_page_changed(self, _stack, _parameter) -> None:
        self.apply_button.set_visible(
            self.view_stack.get_visible_child_name() == "display"
        )

    def on_tracking_changed(self, _row, _parameter) -> None:
        if not self.standard_button.get_active():
            return
        selected = self.tracking_row.get_selected()
        if selected < len(TRACKING_VALUES):
            self.standard_tracking = TRACKING_VALUES[selected]
            if not self.loading_controls:
                self.controls_dirty = True

    def on_setting_changed(self, _row, _parameter) -> None:
        if not self.loading_controls:
            self.controls_dirty = True

    def selected_config(self) -> NativeDisplayConfig:
        if self.ultrawide_button.get_active():
            mode = ULTRAWIDE_MODE
            tracking = "anchored"
        else:
            mode = STANDARD_MODE
            tracking = TRACKING_VALUES[self.tracking_row.get_selected()]
        return NativeDisplayConfig(
            mode=mode,
            dof=tracking,
            screen_size=SIZE_VALUES[self.size_row.get_selected()],
            distance=int(self.distance_row.get_value()),
            make_glasses_primary=self.primary_switch.get_active(),
            disable_built_in_display=self.privacy_switch.get_active(),
        )

    def on_apply(self, _button: Gtk.Button) -> None:
        config = self.selected_config()
        try:
            save_config(self.config_path, config)
        except OSError as error:
            self.set_status(str(error), "dialog-error-symbolic")
            return

        self.pending_config = config
        self.controls_dirty = False
        self.pending_since = time.monotonic()
        self.apply_button.set_sensitive(False)
        self.set_status("Applying", "emblem-synchronizing-symbolic")
        GLib.timeout_add(250, self.poll_apply_status)

    def read_status(self) -> dict[str, object] | None:
        try:
            data = json.loads(self.status_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return None
        return data if isinstance(data, dict) else None

    def update_status_from_file(self) -> dict[str, object] | None:
        status = self.read_status()
        self.update_device_info(status)
        if status is None:
            self.set_status("Controller status unavailable", "dialog-warning-symbolic")
        elif status.get("state") == "active":
            self.set_status("Active", "object-select-symbolic")
        elif status.get("state") == "disconnected":
            self.set_status("Glasses disconnected", "video-display-symbolic")
        elif status.get("state") in {"error", "config-error"}:
            self.set_status(
                str(status.get("message", "Controller error")),
                "dialog-error-symbolic",
            )
        else:
            self.set_status("Applying", "emblem-synchronizing-symbolic")
        return status

    def sync_controls_from_status(
        self, status: dict[str, object] | None
    ) -> None:
        if self.controls_dirty or self.pending_config is not None or status is None:
            return
        if status.get("state") != "active":
            return
        device = status.get("device")
        if not isinstance(device, dict):
            return
        try:
            config = config_from_device_info(device)
        except ValueError:
            return
        self.set_controls(config, update_policies=False)
        self.apply_button.set_sensitive(True)

    def refresh_hardware_settings(self) -> None:
        if self.query_in_progress:
            return
        if not self.helper_path.is_file():
            return
        self.query_in_progress = True

        def query_worker() -> None:
            try:
                device = query_device_info(self.helper_path)
                error = None
            except Exception as caught_error:
                device = None
                error = str(caught_error)
            GLib.idle_add(self.finish_hardware_query, device, error)

        threading.Thread(target=query_worker, daemon=True).start()

    def finish_hardware_query(
        self,
        device: dict[str, object] | None,
        _error: str | None,
    ) -> bool:
        self.query_in_progress = False
        if device is None:
            return GLib.SOURCE_REMOVE
        self.update_device_info({"device": device})
        if not self.controls_dirty and self.pending_config is None:
            try:
                config = config_from_device_info(device)
            except ValueError:
                return GLib.SOURCE_REMOVE
            self.set_controls(config, update_policies=False)
            self.apply_button.set_sensitive(True)
        return GLib.SOURCE_REMOVE

    def update_device_info(self, status: dict[str, object] | None) -> None:
        device = status.get("device") if status is not None else None
        if not isinstance(device, dict):
            fallback = (
                "Not detected"
                if status is not None and status.get("state") == "disconnected"
                else "Unavailable"
            )
            for row in self.device_rows.values():
                row.set_subtitle(fallback)
            return

        for key, row in self.device_rows.items():
            value = device.get(key, "Unavailable")
            if key == "native_tracking" and isinstance(value, bool):
                value = "Supported" if value else "Not supported"
            row.set_subtitle(str(value))

    def refresh_status(self) -> bool:
        if self.pending_config is None:
            self.update_status_from_file()
        return GLib.SOURCE_CONTINUE

    def poll_apply_status(self) -> bool:
        status = self.read_status()
        self.update_device_info(status)
        if status is not None:
            state = status.get("state")
            if state == "disconnected":
                self.pending_config = None
                self.apply_button.set_sensitive(True)
                self.set_status(
                    "Saved; glasses disconnected", "video-display-symbolic"
                )
                return GLib.SOURCE_REMOVE
            if (
                self.pending_config is not None
                and status.get("config") == self.pending_config.as_dict()
            ):
                if state == "active":
                    self.pending_config = None
                    self.apply_button.set_sensitive(True)
                    self.set_status("Active", "object-select-symbolic")
                    return GLib.SOURCE_REMOVE
                if state == "error":
                    self.pending_config = None
                    self.apply_button.set_sensitive(True)
                    self.set_status(
                        str(status.get("message", "Controller error")),
                        "dialog-error-symbolic",
                    )
                    return GLib.SOURCE_REMOVE

        if time.monotonic() - self.pending_since >= STATUS_TIMEOUT_SECONDS:
            self.pending_config = None
            self.apply_button.set_sensitive(True)
            self.set_status("Saved; controller did not respond", "dialog-warning-symbolic")
            return GLib.SOURCE_REMOVE
        return GLib.SOURCE_CONTINUE


class SettingsApplication(Adw.Application):
    def __init__(self):
        super().__init__(
            application_id="io.github.gapiadesktop.Gapia",
            flags=Gio.ApplicationFlags.DEFAULT_FLAGS,
        )

    def do_activate(self) -> None:
        window = self.get_active_window()
        if window is None:
            window = SettingsWindow(self)
        else:
            window.refresh_hardware_settings()
        window.present()


def main(argv=None) -> int:
    application = SettingsApplication()
    return application.run(argv or sys.argv)


if __name__ == "__main__":
    raise SystemExit(main())
