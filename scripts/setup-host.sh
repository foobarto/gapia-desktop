#!/bin/sh

set -eu

script_dir=$(CDPATH='' cd -- "$(dirname -- "$0")" && pwd)
project_root=$(CDPATH='' cd -- "$script_dir/.." && pwd)
cd "$project_root"
rule_source=$project_root/packaging/udev/70-viture-beast.rules
rule_destination=/etc/udev/rules.d/70-viture-beast.rules
controller_source=$project_root/scripts/native_display_controller.py
display_policy_source=$project_root/scripts/gnome_display_policy.py
settings_source=$project_root/scripts/native_display_settings.py
config_source=$project_root/config/gapia.json
service_source=$project_root/packaging/systemd/gapia-display.service
desktop_source=$project_root/packaging/applications/io.github.gapiadesktop.Gapia.desktop
extension_uuid=gapia@desktop.local
extension_zip=$project_root/build/extension/$extension_uuid.shell-extension.zip
sdk_dir=${GAPIA_VITURE_SDK_DIR:-$project_root/.tmp/sdk-analysis/current-sdk}

usage() {
    cat <<EOF
Usage: sudo $0 [--sdk-dir PATH]

Set up this atomic GNOME host for Gapia Desktop development. The script:
  - installs CMake and Ninja through Homebrew when the host lacks them;
  - installs and activates the narrow VITURE Beast udev access rule;
  - configures, builds, and tests the independent core;
  - builds and tests the VITURE backend from a separately extracted SDK;
  - installs and starts the per-user native-display controller; and
  - installs the settings application, icons, and GNOME panel indicator.

The licensed SDK is required for native VITURE control and is never downloaded
or redistributed by this script. Obtain the Linux SDK from:
  https://www.viture.com/developer
EOF
}

while [ "$#" -gt 0 ]; do
    case "$1" in
        --sdk-dir)
            if [ "$#" -lt 2 ]; then
                printf '%s\n' '--sdk-dir requires a path' >&2
                exit 2
            fi
            sdk_dir=$2
            shift 2
            ;;
        -h|--help)
            usage
            exit 0
            ;;
        *)
            printf 'Unknown argument: %s\n' "$1" >&2
            usage >&2
            exit 2
            ;;
    esac
done

if [ "$(id -u)" -ne 0 ]; then
    printf 'Run this script once through sudo: sudo %s\n' "$0" >&2
    exit 1
fi

setup_user=${SUDO_USER:-}
if [ -z "$setup_user" ] && [ -n "${PKEXEC_UID:-}" ]; then
    setup_user=$(id -nu "$PKEXEC_UID" 2>/dev/null || true)
fi
if [ -z "$setup_user" ] || [ "$setup_user" = root ]; then
    printf '%s\n' \
        'Could not identify the non-root invoking user from sudo or pkexec.' >&2
    printf '%s\n' \
        'Run this script through sudo or pkexec from the desktop user account.' >&2
    exit 1
fi

for command_name in getent install runuser udevadm; do
    if ! command -v "$command_name" >/dev/null 2>&1; then
        printf 'Required host command not found: %s\n' "$command_name" >&2
        exit 1
    fi
done

user_home=$(getent passwd "$setup_user" | cut -d: -f6)
if [ -z "$user_home" ] || [ ! -d "$user_home" ]; then
    printf 'Could not determine the home directory for %s\n' "$setup_user" >&2
    exit 1
fi
setup_group=$(id -gn "$setup_user")
setup_uid=$(id -u "$setup_user")
user_runtime_dir=/run/user/$setup_uid

brew=
for candidate in \
    /home/linuxbrew/.linuxbrew/bin/brew \
    "$user_home/.linuxbrew/bin/brew" \
    /opt/homebrew/bin/brew; do
    if [ -x "$candidate" ]; then
        brew=$candidate
        break
    fi
done

user_path=/usr/local/bin:/usr/local/sbin:/usr/bin:/usr/sbin:/bin:/sbin
if [ -n "$brew" ]; then
    brew_bin=$(dirname -- "$brew")
    user_path=$brew_bin:$user_path
fi

as_user() {
    runuser -u "$setup_user" -- env \
        HOME="$user_home" USER="$setup_user" LOGNAME="$setup_user" \
        XDG_RUNTIME_DIR="$user_runtime_dir" \
        DBUS_SESSION_BUS_ADDRESS="unix:path=$user_runtime_dir/bus" \
        PATH="$user_path" "$@"
}

sdk_header=$sdk_dir/include/viture_glasses_provider.h
sdk_runtime=$sdk_dir/x86_64/libglasses.so
if [ ! -r "$sdk_header" ] || [ ! -r "$sdk_runtime" ]; then
    printf 'VITURE Linux SDK support is not installed from %s.\n' \
        "$sdk_dir" >&2
    if [ ! -r "$sdk_header" ]; then
        printf 'Missing SDK header: %s\n' "$sdk_header" >&2
    fi
    if [ ! -r "$sdk_runtime" ]; then
        printf 'Missing SDK runtime: %s\n' "$sdk_runtime" >&2
    fi
    printf '\nTo finish setup:\n' >&2
    printf '  1. Download the Linux SDK from https://www.viture.com/developer\n' >&2
    printf '  2. Extract it without copying its licensed files into this project.\n' >&2
    printf '  3. Rerun: sudo %s --sdk-dir /path/to/extracted-sdk\n' "$0" >&2
    exit 2
fi
printf 'Found the VITURE SDK header and runtime at %s.\n' "$sdk_dir"

if ! as_user sh -c \
    'command -v cmake >/dev/null 2>&1 && command -v ninja >/dev/null 2>&1'; then
    if [ -z "$brew" ]; then
        printf 'CMake or Ninja is missing and Homebrew was not found for %s.\n' \
            "$setup_user" >&2
        exit 1
    fi
    printf 'Installing user-space build tools through %s...\n' "$brew"
    as_user "$brew" install cmake ninja
else
    printf 'CMake and Ninja are already available; skipping installation.\n'
fi

for command_name in python3 systemctl; do
    if ! as_user sh -c \
        "command -v '$command_name' >/dev/null 2>&1"; then
        printf 'Required desktop runtime command not found: %s\n' \
            "$command_name" >&2
        exit 1
    fi
done
as_user python3 -c 'import json'

printf 'Validating and installing the VITURE Beast access rule...\n'
udevadm verify "$rule_source"
install -o root -g root -m 0644 "$rule_source" "$rule_destination"
udevadm control --reload-rules
udevadm trigger --action=change --subsystem-match=usb \
    --attr-match=idVendor=35ca --attr-match=idProduct=1211
udevadm settle
cmp "$rule_source" "$rule_destination"
udevadm verify "$rule_destination"

beast_sysfs=
for device in /sys/bus/usb/devices/*; do
    if [ ! -r "$device/idVendor" ] || [ ! -r "$device/idProduct" ]; then
        continue
    fi
    if [ "$(cat "$device/idVendor")" = 35ca ] && \
        [ "$(cat "$device/idProduct")" = 1211 ]; then
        beast_sysfs=$device
        break
    fi
done

if [ -n "$beast_sysfs" ]; then
    bus_number=$(cat "$beast_sysfs/busnum")
    device_number=$(cat "$beast_sysfs/devnum")
    beast_node=$(printf '/dev/bus/usb/%03d/%03d' \
        "$bus_number" "$device_number")
    if [ ! -e "$beast_node" ]; then
        printf 'Beast USB node did not reappear after the udev trigger.\n' >&2
        exit 1
    fi
    if ! as_user test -r "$beast_node" || ! as_user test -w "$beast_node"; then
        printf '%s cannot read and write %s after applying the rule.\n' \
            "$setup_user" "$beast_node" >&2
        printf 'Reconnect the glasses once, then rerun this script.\n' >&2
        exit 1
    fi
    printf 'Verified %s has read/write access to %s.\n' \
        "$setup_user" "$beast_node"
else
    printf 'The Beast is not connected; the udev rule will apply on connection.\n'
fi

printf 'Configuring, building, and testing the independent core...\n'
as_user cmake -S "$project_root" -B "$project_root/build" -G Ninja \
    -DCMAKE_BUILD_TYPE=Debug
as_user cmake --build "$project_root/build"
as_user ctest --test-dir "$project_root/build" --output-on-failure
if ! as_user sh -c 'command -v gnome-extensions >/dev/null 2>&1'; then
    printf 'GNOME Shell extension tooling is required but was not found.\n' >&2
    exit 1
fi
as_user cmake --build "$project_root/build" --target extension-package

printf 'Building and testing the VITURE backend with SDK at %s...\n' "$sdk_dir"
as_user cmake -S "$project_root" -B "$project_root/build-viture" -G Ninja \
    -DCMAKE_BUILD_TYPE=Debug \
    -DGAPIA_ENABLE_VITURE=ON \
    -DGAPIA_VITURE_SDK_DIR="$sdk_dir"
as_user cmake --build "$project_root/build-viture"
as_user ctest --test-dir "$project_root/build-viture" --output-on-failure

if ! as_user python3 -c \
    'import gi; gi.require_version("Gtk", "4.0"); gi.require_version("Adw", "1"); from gi.repository import Adw, Gtk'; then
    if [ -z "$brew" ]; then
        printf 'GTK 4 and libadwaita Python bindings are missing and Homebrew was not found.\n' >&2
        exit 1
    fi
    printf 'Installing the settings application runtime through %s...\n' "$brew"
    as_user "$brew" install pygobject3 gtk4 libadwaita
    as_user python3 -c \
        'import gi; gi.require_version("Gtk", "4.0"); gi.require_version("Adw", "1"); from gi.repository import Adw, Gtk'
else
    printf 'GTK 4 and libadwaita Python bindings are already available.\n'
fi

printf 'Installing Gapia Desktop for the invoking desktop user...\n'
install -d -o "$setup_user" -g "$setup_group" -m 0755 \
    "$user_home/.local/bin" \
    "$user_home/.local/libexec" \
    "$user_home/.local/lib/gapia" \
    "$user_home/.local/share/applications" \
    "$user_home/.config/gapia" \
    "$user_home/.config/systemd/user"
install -o "$setup_user" -g "$setup_group" -m 0755 \
    "$controller_source" "$user_home/.local/libexec/gapia-native-controller"
install -o "$setup_user" -g "$setup_group" -m 0755 \
    "$display_policy_source" \
    "$user_home/.local/libexec/gapia-gnome-display-policy"
install -o "$setup_user" -g "$setup_group" -m 0644 \
    "$controller_source" \
    "$user_home/.local/lib/gapia/native_display_controller.py"
install -o "$setup_user" -g "$setup_group" -m 0755 \
    "$settings_source" "$user_home/.local/bin/gapia-desktop"
install -o "$setup_user" -g "$setup_group" -m 0644 \
    "$desktop_source" \
    "$user_home/.local/share/applications/io.github.gapiadesktop.Gapia.desktop"
install -o "$setup_user" -g "$setup_group" -m 0644 \
    "$sdk_dir/x86_64/libglasses.so" \
    "$user_home/.local/lib/gapia/libglasses.so"
as_user cmake --install "$project_root/build-viture" \
    --prefix "$user_home/.local" --component native-display
install -o "$setup_user" -g "$setup_group" -m 0644 \
    "$service_source" \
    "$user_home/.config/systemd/user/gapia-display.service"

for icon_size in 32 48 64 128 256 512; do
    icon_dir=$user_home/.local/share/icons/hicolor/${icon_size}x${icon_size}/apps
    install -d -o "$setup_user" -g "$setup_group" -m 0755 "$icon_dir"
    install -o "$setup_user" -g "$setup_group" -m 0644 \
        "$project_root/assets/icons/${icon_size}x${icon_size}/apps/io.github.gapiadesktop.Gapia.png" \
        "$icon_dir/io.github.gapiadesktop.Gapia.png"
done

user_config=$user_home/.config/gapia/config.json
legacy_config=$user_home/.config/xr-workspace/config.json
if [ -L "$user_config" ] || { [ -e "$user_config" ] && [ ! -f "$user_config" ]; }; then
    printf 'Refusing to replace non-regular user config: %s\n' "$user_config" >&2
    exit 1
fi
if [ ! -e "$user_config" ]; then
    if [ -f "$legacy_config" ] && \
        as_user "$user_home/.local/libexec/gapia-native-controller" \
            --config "$legacy_config" --check-config >/dev/null 2>&1; then
        printf 'Migrating the existing display configuration to Gapia Desktop.\n'
        install -o "$setup_user" -g "$setup_group" -m 0644 \
            "$legacy_config" "$user_config"
    else
        install -o "$setup_user" -g "$setup_group" -m 0644 \
            "$config_source" "$user_config"
    fi
else
    if as_user "$user_home/.local/libexec/gapia-native-controller" \
        --config "$user_config" --check-config >/dev/null 2>&1; then
        printf 'Preserving existing user config at %s.\n' "$user_config"
    elif as_user python3 -c \
        'import json, sys; data=json.load(open(sys.argv[1], encoding="utf-8")); expected={"width":7680,"height":1080,"refresh_rate":60}; allowed=expected | {"screen_scale":0.75}; raise SystemExit(0 if data == expected or data == allowed else 1)' \
        "$user_config"; then
        printf 'Migrating the generated backing-workspace config to native display control.\n'
        install -o "$setup_user" -g "$setup_group" -m 0644 \
            "$config_source" "$user_config"
    else
        printf 'Existing config is not valid for native display control: %s\n' \
            "$user_config" >&2
        printf 'Refusing to overwrite a customized configuration.\n' >&2
        exit 1
    fi
fi
as_user "$user_home/.local/libexec/gapia-native-controller" \
    --config "$user_config" --check-config
as_user systemctl --user disable --now xr-workspace-native-display.service 2>/dev/null || true
as_user systemctl --user disable --now xr-workspace-ultrawide.service 2>/dev/null || true
rm -f "$user_home/.config/systemd/user/xr-workspace-ultrawide.service"
rm -f "$user_home/.local/libexec/xr-workspace-ultrawide"
rm -f "$user_home/.config/systemd/user/xr-workspace-native-display.service"
rm -f "$user_home/.local/libexec/xr-workspace-native-controller"
rm -f "$user_home/.local/libexec/xr-workspace-native-display"
rm -f "$user_home/.local/libexec/xr-workspace-gnome-display-policy"
rm -f "$user_home/.local/bin/xr-workspace-settings"
rm -f "$user_home/.local/share/applications/io.github.xrworkspace.NativeDisplay.desktop"
as_user systemctl --user daemon-reload
as_user systemctl --user enable gapia-display.service
as_user systemctl --user restart gapia-display.service
as_user systemctl --user --quiet is-active gapia-display.service
as_user gnome-extensions disable xr-workspace@viture-linux.local 2>/dev/null || true
as_user gnome-extensions uninstall xr-workspace@viture-linux.local 2>/dev/null || true
as_user gnome-extensions install --force "$extension_zip"
if ! as_user gnome-extensions enable "$extension_uuid"; then
    printf 'The panel indicator is installed but GNOME must be logged out once before it can be enabled.\n'
fi
if as_user sh -c 'command -v update-desktop-database >/dev/null 2>&1'; then
    as_user update-desktop-database "$user_home/.local/share/applications"
fi
if as_user sh -c 'command -v gtk-update-icon-cache >/dev/null 2>&1'; then
    as_user gtk-update-icon-cache -f -t "$user_home/.local/share/icons/hicolor"
fi

printf 'Gapia Desktop host setup completed successfully.\n'
