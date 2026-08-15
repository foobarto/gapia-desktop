# Host changes

This file records every change this project makes outside its working tree.
Keep entries chronological and include the reason, exact persistent state,
activation procedure, verification, and rollback instructions so the setup can
later be automated safely.

## 2026-08-15: native Beast display controller

Status: installed, enabled, active, and verified.

### Persistent state

```text
$HOME/.local/libexec/xr-workspace-native-controller
$HOME/.local/libexec/xr-workspace-native-display
$HOME/.local/lib/xr-workspace/libglasses.so
$HOME/.local/lib/xr-workspace/native_display_controller.py
$HOME/.local/bin/xr-workspace-settings
$HOME/.local/share/applications/io.github.xrworkspace.NativeDisplay.desktop
$HOME/.config/xr-workspace/config.json
$HOME/.config/systemd/user/xr-workspace-native-display.service
$HOME/.config/systemd/user/graphical-session.target.wants/
  xr-workspace-native-display.service (enablement symlink)
```

The tracked default selects native `3840x1080@60` ultrawide mode, anchored
3DoF, large apparent size, and distance 9. The controller waits for Beast USB
PID `35ca:1211` and applies each valid config revision once per connection.
The SDK runtime is copied from the separately supplied package into a stable
per-user library directory; its license remains applicable. The GTK settings
application edits the same JSON atomically and reads private controller status
from `$XDG_RUNTIME_DIR/xr-workspace/native-display-status.json`.

### Verification performed

- The SDK helper read back display `0x3d`, DOF 1, size 2, and distance 9.
- The same live query returned model `Beast`, device family `Gen 2`, firmware
  `21.0.01.026_20260716`, USB ID `35ca:1211`, and SDK version `2.4.0`; the
  Device tab displayed the controller's structured record.
- A read-only startup query returned standard 1920x1080, smooth follow, large,
  and distance 9. The GUI selected the same values both from controller status
  and after direct SDK read-back without changing or recentering the display.
- Mutter reported the Beast physical output at `3840x1080@60`.
- Turning the user's head exposed distinct left and right desktop regions,
  proving native hardware viewport movement.
- The built-in display remained 2880x1800 at scale 1.6667.
- Reapplying the same JSON was idempotent and the user service remained active
  with zero restarts.
- The GTK 4/libadwaita application launched in the active Wayland session and
  its ultrawide, standard, tracking, size, distance, and apply controls were
  visually verified.

### Rollback

```sh
systemctl --user disable --now xr-workspace-native-display.service
rm "$HOME/.local/libexec/xr-workspace-native-controller"
rm "$HOME/.local/libexec/xr-workspace-native-display"
rm "$HOME/.local/lib/xr-workspace/libglasses.so"
rm "$HOME/.local/lib/xr-workspace/native_display_controller.py"
rm "$HOME/.local/bin/xr-workspace-settings"
rm "$HOME/.local/share/applications/io.github.xrworkspace.NativeDisplay.desktop"
rm "$HOME/.config/systemd/user/xr-workspace-native-display.service"
systemctl --user daemon-reload
```

The JSON config is intentionally retained.

## 2026-08-15: retired backing-workspace viewport prototype

Status: disabled and replaced by the native display controller.

### Reason and persistent state

The controller creates one 7680x1080 Mutter backing workspace when an active
VITURE Beast output is present, consumes its PipeWire stream, and presents a
fixed-size viewport fullscreen on that physical Wayland output. The installed
user-owned files are:

```text
$HOME/.local/libexec/xr-workspace-ultrawide
$HOME/.config/xr-workspace/config.json
$HOME/.config/systemd/user/xr-workspace-ultrawide.service
$HOME/.config/systemd/user/graphical-session.target.wants/
  xr-workspace-ultrawide.service (enablement symlink)
```

The tracked setup script installs the default JSON only when no user config
exists. Reruns reconcile the executable and unit while preserving that config.
The unit does not automatically restart after a native process crash, avoiding
a repeated virtual-output add/remove cycle.

### Verification performed

- The installed controller validated `workspace=7680x1080@60`.
- The user unit remained active with one PipeWire consumer and no errors.
- Mutter exposed one active `Meta-0` at 7680x1080 to the right of the existing
  physical outputs.
- The composed Beast output showed the 1920x1080 viewport centered on its
  1920x1200 transport with 60-pixel top and bottom bars.
- Disconnecting the glasses exposed a GStreamer `waylandsink` crash in its
  Wayland output callback about three seconds after the Beast USB hub vanished.
  The unit's `Restart=no` policy prevented an add/remove loop. The direct Beast
  desktop remained available after reconnect, which also restored the built-in
  display's full image. The controller now polls the Beast USB vendor/product
  identity every 250 ms and releases GStreamer before stopping its Mutter
  session, ahead of the later DisplayPort output removal. That guard passed a
  deliberate disconnect/reconnect test, but the design was retired because
  the native Beast ultrawide path provides the required viewport directly.

### Rollback

```sh
systemctl --user disable --now xr-workspace-ultrawide.service
rm "$HOME/.local/libexec/xr-workspace-ultrawide"
rm "$HOME/.config/systemd/user/xr-workspace-ultrawide.service"
systemctl --user daemon-reload
```

The user JSON is intentionally left in place. Remove
`$HOME/.config/xr-workspace/config.json` separately only when its settings are
no longer wanted.

## 2026-08-15: atomic-host development tools and Beast USB access

Status: applied and verified on the current development host.

### Reason

On the AMD Strix Halo system, GNOME detects the Beast display. CMake and Ninja
were absent, and Bluefin 44's atomic package model made the existing user-owned
Homebrew installation the appropriate place for development tools. Separately,
the per-host Beast udev rule had not yet been installed, so the USB control
node was not writable by the desktop user. The immutable base image was left
unchanged.

### Persistent changes

The existing user-owned Homebrew installation now provides:

```text
cmake 4.4.2
ninja 1.13.2
```

Homebrew also upgraded its own `ca-certificates` formula to the current
2026-08-13 release as a CMake dependency. These files remain entirely under
`/home/linuxbrew/.linuxbrew`.

The validated project rule was installed as:

```text
/etc/udev/rules.d/70-viture-beast.rules  root:root 0644
```

The rule remains limited to VITURE USB vendor/product `35ca:1211`. The
current host can reproduce the dependency installation, rule activation,
build, and tests with one command:

```sh
sudo ./scripts/setup-host.sh
```

The script performs Homebrew operations and project builds as `SUDO_USER`; it
uses root only for the udev installation and activation. It is idempotent and
may be rerun to reconcile the same dependency, rule, and build state.

### Verification performed

- The project and installed udev rules pass `udevadm verify` and match byte
  for byte.
- The host exposes the Beast display as AMD DRM connector `card1-DP-1`, with
  a `VITURE Beast` EDID and a 1920x1200 mode.
- Both the SDK-free and SDK-enabled builds configure and compile locally.
- Both builds pass the C++ pose-frame and GJS pose-reader tests.
- `scripts/setup-host.sh` completed successfully twice in succession; the
  second run made no package or build changes and reverified USB access.
- No `rpm-ostree` deployment, system package, kernel argument, or firmware
  setting was changed.

USB bus/device numbers and the DRM card number are transient observations and
must not be embedded in automation.

### Rollback

Remove the Beast rule, reload udev, and reconnect the glasses:

```sh
sudo rm /etc/udev/rules.d/70-viture-beast.rules
sudo udevadm control --reload-rules
```

The user-space build tools can be removed independently:

```sh
brew uninstall cmake ninja
```

Do not remove Homebrew's shared `ca-certificates` formula solely for this
rollback; other installed formulae may depend on it.

## 2026-08-14: VITURE Beast USB access

Status: applied and verified on the development host.

### Reason

VITURE Glasses SDK 2.4.0 opens the Beast USB device with read/write access.
Before this change, the active user could read but not write the raw USB node,
so SDK initialization appeared to succeed while device commands timed out.

The rule is deliberately limited to the Beast control device with USB vendor
and product ID `35ca:1211`. It does not grant access to all VITURE devices and
does not make the node world-writable.

### Persistent change

Project source:

`packaging/udev/70-viture-beast.rules`

Installed destination:

`/etc/udev/rules.d/70-viture-beast.rules`

Installed ownership and mode:

`root:root 0644`

Rule contents:

```udev
SUBSYSTEM=="usb", ENV{DEVTYPE}=="usb_device", ATTR{idVendor}=="35ca", ATTR{idProduct}=="1211", MODE:="0660", TAG+="uaccess"
SUBSYSTEM=="hidraw", KERNEL=="hidraw[0-9]*", ATTRS{idVendor}=="35ca", ATTRS{idProduct}=="1211", MODE:="0660", TAG+="uaccess"
```

`TAG+="uaccess"` lets systemd-logind grant the active local desktop user a
read/write ACL. `MODE:="0660"` prevents a later udev rule from widening the
device-node mode.

The separate Beast UVC camera already receives access through the operating
system's standard video-device rules, so this project did not add a camera
permission rule.

### Commands actually run

The rule was validated before installation:

```sh
udevadm verify packaging/udev/70-viture-beast.rules
```

It was installed and activated through PolicyKit:

```sh
pkexec /usr/bin/install -o root -g root -m 0644 \
  "$PWD/packaging/udev/70-viture-beast.rules" \
  /etc/udev/rules.d/70-viture-beast.rules
pkexec /usr/bin/udevadm control --reload-rules
pkexec /usr/bin/udevadm trigger --action=change \
  /sys/bus/usb/devices/3-10.3
```

`3-10.3` was the Beast's transient sysfs path during this run. Automation must
not hard-code it. Discover the device by `idVendor=35ca` and
`idProduct=1211`, or let the rule apply naturally on the next connection.

An automation-friendly retrigger is:

```sh
sudo udevadm trigger --action=change --subsystem-match=usb \
  --attr-match=idVendor=35ca --attr-match=idProduct=1211
```

Unplugging and reconnecting the glasses after reloading the rules is also
sufficient.

### Verification performed

The installed rule was checked against the project copy and parsed again:

```sh
cmp packaging/udev/70-viture-beast.rules \
  /etc/udev/rules.d/70-viture-beast.rules
udevadm verify /etc/udev/rules.d/70-viture-beast.rules
```

Observed effective permissions:

```text
/dev/bus/usb/003/075  crw-rw---- root:root
/dev/hidraw14         crw-rw---- root:root
ACL on both:          user:$USER:rw-
```

The bus/device number and `hidraw` number are transient and must not be used as
stable identifiers.

Normal-user `test -r` and `test -w` checks succeeded for both control nodes.
The non-root SDK probe then completed its create/initialize/start/read/stop/
shutdown lifecycle and received successful acknowledgements from the Beast.

### Rollback

Remove the installed rule, reload udev, and reconnect the glasses:

```sh
sudo rm /etc/udev/rules.d/70-viture-beast.rules
sudo udevadm control --reload-rules
```

The tracked project copy remains available for reinstalling the rule. Removing
the project copy is a separate source-control decision and is not part of host
rollback.

### Explicitly not changed

- No packages were installed or removed.
- No kernel modules, kernel command-line options, EDID files, bootloader files,
  or display configuration files were changed.
- No users or groups were created or modified.
- No system or user services were installed, enabled, or started.
- No XRLinuxDriver or Breezy Desktop components were installed or executed.
- No glasses settings were changed by the SDK verification probe.

## 2026-08-14: per-user pose runtime file

Status: active runtime convention; non-persistent.

### Reason and state

Running the pose service creates these session-local objects:

```text
$XDG_RUNTIME_DIR/xr-workspace/             desktop user/group 0700
$XDG_RUNTIME_DIR/xr-workspace/pose-v1.bin  desktop user/group 0600, 128 bytes
```

The numeric `/run/user/1000` was `$XDG_RUNTIME_DIR` for this session and must
not be hard-coded. The service rejects symlinks, validates ownership and object
types, and leaves a disconnected frame when it exits normally. The entire
runtime directory is removed automatically when the user's runtime session is
destroyed. No service was installed or enabled.

Development tests also used the equivalent ignored path
`.tmp/runtime-test/xr-workspace/pose-v1.bin` inside the project.

### Verification performed

The mock path was verified as a `0700` directory and a `0600`, 128-byte regular
file. A separate reader obtained a consistent even seqlock sequence and a
normalized mock quaternion. The live SDK path used the same ABI and published
its source/validity state.

### Rollback

Stop the pose service, then remove the per-user runtime directory if immediate
cleanup is wanted:

```sh
rm -r "$XDG_RUNTIME_DIR/xr-workspace"
```

This removes only ephemeral IPC state; it does not affect source files or
glasses settings.

## 2026-08-14: GNOME Shell development extension files

Status: installed per-user; not loaded or enabled in the current Shell.

### Reason and persistent state

The package produced by the `extension-package` CMake target was installed for
live renderer testing. It was replaced in place after the first nested-shell
test exposed and fixed a GNOME 50 `addChrome()` API mismatch:

```sh
gnome-extensions install --force \
  build/extension/xr-workspace@viture-linux.local.shell-extension.zip
```

This created:

```text
$HOME/.local/share/gnome-shell/extensions/
  xr-workspace@viture-linux.local/
    extension.js
    metadata.json
    poseReader.js
    stylesheet.css
```

No system-wide files were written. GNOME Shell 50.3 did not discover a newly
installed local extension in the already-running Wayland session. Both
`gnome-extensions info` and `gnome-extensions enable` reported that the UUID
does not exist in the live Shell, which requires a logout/login to rescan local
extension directories.

The persistent `org.gnome.shell enabled-extensions` value was read after the
failed enable request and did not contain `xr-workspace@viture-linux.local`.
`org.gnome.shell disable-user-extensions` remained `false`. No GNOME setting
was changed by this installation.

### Verification performed

- The source package was created with `gnome-extensions pack` and included all
  four required files.
- `unzip -t` reported no archive errors.
- The installed files and metadata UUID were read back from the per-user
  extension directory. All four files match the corrected project sources.
- The GJS pose-reader module passed its standalone ABI parser test.
- An isolated nested GNOME Shell loaded the corrected package with
  `enabled=true`, an empty `error` field, and an empty `GetExtensionErrors`
  result. The XR Workspace surface was therefore constructed successfully.
- The already-running real Shell still does not know the UUID. Loading it in
  the real desktop remains unverified until the next login.

### Rollback

After GNOME has discovered the extension, the supported removal command is:

```sh
gnome-extensions uninstall xr-workspace@viture-linux.local
```

Before discovery, remove only the exact per-user directory shown above. If it
is later enabled, disable it before uninstalling:

```sh
gnome-extensions disable xr-workspace@viture-linux.local
```

## 2026-08-14: isolated nested GNOME Shell development environment

Status: project-local scratch and user cache only; no package installed.

### Reason and state

GNOME Wayland cannot restart or rescan extension directories in place. The
first supported development command failed because this Bazzite image does not
include `/usr/libexec/mutter-devkit`, and because its generated system schema
cache did not contain `org.gnome.desktop.calendar`'s `week-start-day` key even
though the installed XML defines it.

The project now provides:

```text
scripts/prepare-nested-shell.sh
scripts/run-nested-shell.sh
```

The preparation script downloads the exact package matching the installed
Mutter build, but does not install it. For the current image that artifact is:

```text
.tmp/nested-shell/50.3-3.fc44.x86_64__50.1-1.fc44.x86_64/
  rpms/mutter-devkit-50.3-3.fc44.x86_64.rpm
```

Its SHA-256 is:

```text
5fd0cc246d5051ee2e7138de2296845710dd324c60917931a960f0385adc827f
```

The RPM is extracted under that ignored `.tmp` tree. A minimal private schema
cache supplies the current calendar and accessibility schemas, their enum
dependency, and the devkit schema. A private GSettings keyfile enables only
`xr-workspace@viture-linux.local`, and a private XDG data directory links
directly to the tracked extension source.

At launch, Bubblewrap overlays the extracted helper at
`/usr/libexec/mutter-devkit` only inside the nested process mount namespace.
The host `/usr/libexec` directory is not changed. The separate D-Bus session,
GNOME Shell, helper, and portal processes exit with the nested desktop.

The `dnf5` query/download refreshed ordinary repository metadata under
`$HOME/.cache/libdnf5` at approximately 20:53 local time. That shared cache is
the only observed write outside the project and the already-documented
per-user extension installation. No `rpm-ostree` deployment or live package
state was changed.

### Verification performed

- The exact helper started GNOME Shell 50.3 and Mutter created its virtual
  `Meta-0` monitor.
- The private cache exposes `week-start-day`, `reduced-motion`, and
  `org.gnome.mutter.devkit`.
- The nested extension service reported XR Workspace `enabled=true`, no error,
  and an empty extension-error array.
- The nested settings backend did not change the real desktop's enabled
  extension list; XR Workspace is still absent there.
- No `gnome-shell --devkit` or `mutter-devkit` process remained after the
  bounded verification.

Expected warnings about logind/systemd activation, portals, AT-SPI, and the
already-owned `wayland-0` socket occur in a nested session and did not prevent
Shell startup or extension loading.

### Rollback

Stop the nested desktop, then remove only its ignored project scratch tree:

```sh
rm -r .tmp/nested-shell
```

The DNF repository metadata cache is shared with normal package-manager use and
does not need removal. The scripts will recreate the project-local environment
for the currently installed Mutter and schema package versions when next run.
