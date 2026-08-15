# Gapia Desktop

[![License: MIT OR Apache-2.0](https://img.shields.io/badge/license-MIT%20OR%20Apache--2.0-blue.svg)](LICENSE)

Gapia Desktop controls spatial display modes for XR glasses on GNOME/Wayland.
The first supported device is VITURE Beast on GNOME 50.

This independent project is not affiliated with or endorsed by VITURE. It is
offline-first and contains no telemetry, account, or network runtime.

## What works

- Standard `1920x1080@60` with anchored 3DoF, smooth follow, or 0DoF.
- Native `3840x1080@60` ultrawide with anchored 3DoF head-driven panning.
- Apparent screen size and distance controls.
- Optional policy to make the glasses the GNOME primary display on connection.
- Optional privacy policy to disable the built-in display only while a VITURE
  display is connected.
- Exact restoration of the prior GNOME layout when the glasses disconnect or
  the controller stops.
- A GTK 4/libadwaita settings app with Display and Device pages.
- A GNOME panel indicator showing connection, mode, and tracking state.

The glasses remain a real DisplayPort monitor. Ultrawide panning is performed
by VITURE firmware, so Gapia does not create a Mutter virtual output, capture
the desktop through PipeWire, or run a fullscreen video surface.

## Display safety

Display policies use the structured `org.gnome.Mutter.DisplayConfig` API. Before
changing a layout, Gapia saves a private runtime snapshot, asks Mutter to verify
the new layout, applies it temporarily, and waits for the reported state to
converge.

The privacy policy refuses to run unless an attached display has a VITURE EDID.
It cannot disable the built-in panel when the glasses are absent. Disconnecting
the Beast restores the built-in panel, resolution, scale, position, and primary
selection from the saved snapshot.

GNOME 50 has a logical-monitor reuse issue that can leave both unchanged
objects marked primary. Gapia orders the requested primary first to force a
clean object update, then verifies that exactly one primary was reported.

## Settings

Launch from GNOME or run:

```sh
gapia-desktop
```

The strict standard-library JSON configuration is stored at
`$XDG_CONFIG_HOME/gapia/config.json`, or `~/.config/gapia/config.json`:

```json
{
  "mode": "ultrawide-3840x1080-60",
  "dof": "anchored",
  "screen_size": "large",
  "distance": 9,
  "make_glasses_primary": false,
  "disable_built_in_display": false
}
```

Native ultrawide requires anchored 3DoF. Standard mode also supports
`smooth-follow` and `off`. Screen size is one of `small`, `medium`, `large`,
`extra-large`, or `ultra-large`; the latter is an apparent-size setting and is
not the ultrawide display mode.

## Setup

On an atomic Fedora-family GNOME host, setup is one idempotent privileged call:

```sh
sudo ./scripts/setup-host.sh --sdk-dir /path/to/extracted-viture-linux-sdk
```

The script installs missing CMake, Ninja, GTK 4, libadwaita, and PyGObject into
the invoking user's Homebrew prefix. It validates and installs the narrow
VITURE Beast udev rule, builds and tests both project configurations, migrates
the previous project config without changing its values, installs the app and
icons, and enables the per-user controller.

If the SDK path does not contain both
`include/viture_glasses_provider.h` and `x86_64/libglasses.so`, setup stops
before modifying the host and prints the missing files plus the exact rerun
command. Obtain the Linux SDK from the
[VITURE developer portal](https://www.viture.com/en-US/developer). The script
does not download or redistribute it.

A newly installed GNOME Shell extension UUID requires one logout/login on
GNOME 50 before it can be enabled. Subsequent idempotent setup runs enable it
directly.

## Device support

The official developer portal describes one cross-platform SDK for VITURE
glasses, but Gapia Desktop does **not** yet work out of the box with every
VITURE model. The current native controller deliberately accepts only the
tested Beast USB ID `35ca:1211` and uses Beast-verified display, tracking, and
size commands.

Supporting another model requires its USB identity, SDK query results, mode
capabilities, tracking support, and reconnect behavior to be verified before it
is added to the capability table. The GNOME primary/privacy layer is already
EDID-based and otherwise hardware-neutral.

## Build

Build and test the SDK-independent components:

```sh
cmake -S . -B build -G Ninja -DCMAKE_BUILD_TYPE=Debug
cmake --build build
ctest --test-dir build --output-on-failure
```

Build with the separately downloaded SDK:

```sh
cmake -S . -B build-viture -G Ninja \
  -DCMAKE_BUILD_TYPE=Debug \
  -DGAPIA_ENABLE_VITURE=ON \
  -DGAPIA_VITURE_SDK_DIR=/path/to/extracted-sdk
cmake --build build-viture
ctest --test-dir build-viture --output-on-failure
```

## Distribution

GitHub Actions builds and tests the SDK-independent code, packages the GNOME
extension, audits the source boundary, and publishes a versioned source archive
plus a generated Homebrew formula. The formula can optionally compile the
native helper during a source install when `GAPIA_VITURE_SDK_DIR` points to a
user-supplied SDK. No release, formula, or bottle contains VITURE SDK files.

Flatpak is not the primary format because the working integration needs a udev
rule, a user systemd service, a GNOME Shell extension, session D-Bus display
control, and a separately licensed native SDK. Homebrew plus the host setup
script keeps those responsibilities explicit.

## License

Licensed under either of

- Apache License, Version 2.0 ([LICENSE-APACHE](LICENSE-APACHE) or
  <https://www.apache.org/licenses/LICENSE-2.0>)
- MIT license ([LICENSE-MIT](LICENSE-MIT) or
  <https://opensource.org/licenses/MIT>)

at your option.

`SPDX-License-Identifier: MIT OR Apache-2.0`

This license covers only this project's original source and assets. SDK
redistribution constraints and the questions requiring written answers from
VITURE are in [`docs/licensing.md`](docs/licensing.md).

### Contribution

Unless explicitly stated otherwise, any contribution intentionally submitted
for inclusion in Gapia Desktop by you shall be dual-licensed as above, without
any additional terms or conditions.

## Later milestones

- Verified capability profiles for additional VITURE glasses.
- One, two, and three logical-display workflows if they provide enough value
  beyond existing GNOME tilers.
- Spatial translation of virtual displays up, down, left, right, nearer, and
  farther when a supported rendering path exists.
- A richer GNOME control-center integration after the JSON-driven behavior is
  stable.

Architecture and hardware evidence are documented in
[`docs/architecture.md`](docs/architecture.md),
[`docs/sdk-capabilities.md`](docs/sdk-capabilities.md), and
[`docs/device-interactions.md`](docs/device-interactions.md).

## Community

- Read [CONTRIBUTING.md](CONTRIBUTING.md) before proposing code or a new device
  profile.
- Use [SUPPORT.md](SUPPORT.md) to collect useful, privacy-conscious diagnostics.
- Report vulnerabilities privately according to [SECURITY.md](SECURITY.md).
- Participation is governed by [CODE_OF_CONDUCT.md](CODE_OF_CONDUCT.md).
- User-visible changes are recorded in [CHANGELOG.md](CHANGELOG.md).
