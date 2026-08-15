# Architecture and implementation boundaries

## Goal

Present a GNOME desktop through VITURE Beast glasses as a spatial virtual
monitor. The first deliverable is one native ultrawide monitor with anchored
3DoF plus a settings application for switching between native ultrawide and
standard profiles. Spatial placement and camera-assisted position tracking
come later. Multiple monitor subdivision is deferred unless it provides value
beyond existing GNOME window tilers.

## Display model

For the first milestone, the Beast firmware supplies the spatial compositor:

- the **virtual monitor** is the spatial screen visible in the glasses;
- the **GNOME monitor** is the physical Beast DisplayPort output in native
  `3840x1080@60` ultrawide mode;
- the **viewport** is the approximately 1920-pixel-wide region visible through
  the glasses at one head orientation; and
- anchored 3DoF moves that viewport across the 3840-pixel GNOME desktop.

This was verified with distinct desktop content at both horizontal edges.
Turning left revealed a window at the left boundary, while turning right
revealed wallpaper beyond the centered subject. GNOME simultaneously reported
the Beast at `3840x1080@60` and retained the built-in monitor's existing
2880x1800 mode and 1.6667 scale.

Apparent screen size and display mode are independent SDK settings.
`ultra-large` means apparent-size value 4; it is not native ultrawide mode.
The verified default uses apparent size 2 (large) and distance 9.

Native ultrawide supports the stationary anchored profile. Standard 1920-wide
modes also support smooth-follow and 0DoF profiles for vehicles and other
sustained-motion environments where an anchored inertial frame may be
undesirable.

## Component boundary

```text
GTK settings application or JSON editor
    |
    v  atomic JSON config
native_display_controller.py
    |
    v
xr-workspace-native-display + official SDK
    |                         |
    | USB native settings     | DisplayPort mode change
    v                         v
Beast anchored compositor   GNOME 3840x1080 monitor
```

The SDK helper is a short-lived child of the controller, isolated from GNOME
Shell. A native display-mode change re-enumerates the Beast HID interface, so
the helper closes its stale SDK provider, waits for the device, reopens it, and
uses the new handle for authoritative state verification.

The settings application and controller share the same strict JSON schema.
The controller applies a valid revision once per connection and publishes
apply state and SDK-read device information under
`$XDG_RUNTIME_DIR/xr-workspace`. The GUI's Device tab reads that private file;
on activation it also invokes the short-lived helper's read-only query after
the controller is idle. The query reads native state without setting or
recentering it. Unsaved GUI edits are never overwritten by a background
refresh. Native ultrawide configurations require anchored 3DoF. Standard
configurations may select anchored, smooth-follow, or off.

## Pose research path

The separate pose service is not involved in the working native-ultrawide
path. It remains available for future layouts that require a host renderer.
High-rate pose data is not sent over D-Bus. A 128-byte seqlock frame in the
per-user runtime directory provides a small local transport.

Path: `$XDG_RUNTIME_DIR/xr-workspace/pose-v1.bin`

Permissions: parent directory `0700`, regular file `0600`, both owned by the
current user. Symlinks are rejected. The producer validates ownership and
object type.

The little-endian frame contains:

- magic `XRPS`, ABI version, and structure size;
- matching even/odd seqlock counters at offsets 8 and 120;
- producer monotonic time, SDK device timestamp, and SDK VSync timestamp;
- validity flags, source kind, and coordinate-space identifier;
- `[roll, pitch, yaw]` in degrees;
- quaternion `[w, x, y, z]`; and
- the SDK raw packet's ten floats, unchanged.

SDK pose coordinates are North-West-Up. Raw packets remain unscaled because
the public SDK documents their ordering but not physical-unit conversion
constants. Host-side fusion requires separate calibration and validation.

## Official SDK boundary

The SDK backend is opt-in and compiled only with
`XR_WORKSPACE_ENABLE_VITURE=ON`. The project does not vendor its headers or
binaries. The native display service calls provider lifecycle, native display
mode, DOF, recenter, distance, and size APIs. The optional pose research path
also calls IMU registration/open/close APIs. Neither path calls the SDK
statistics reporter or contains a network client.

The connected firmware rejects the SDK processed-pose stream at every reported
rate from 500 down to 60 Hz. Raw 240 Hz samples work, but report zero device and
VSync timestamps. Native anchored 3DoF therefore remains both simpler and more
reliable for the current single-monitor milestone.

## Retired prototype

A Mutter `RecordVirtual` plus PipeWire/GStreamer prototype proved that a large
software output could be captured. It was removed from the supported path
because its fullscreen Wayland surface disturbed physical monitor composition,
and GStreamer crashed when the target output disconnected. RecordVirtual may
still be evaluated later for layouts that Beast firmware cannot provide, but
it is not required for the verified native ultrawide monitor.

## Planned sequence

1. Keep the verified native 3840x1080 anchored viewport reliable across
   connection, configuration changes, and login.
2. Validate standard 1920-wide smooth-follow and 0DoF profiles for motion use.
3. Add opt-in policies that make the Beast primary or temporarily disable the
   previous main output, restoring prior GNOME state on disconnect.
4. Add user-controlled spatial placement and a GNOME top-bar control.
5. Evaluate monitor subdivision only if native firmware exposes it or window
   tiling cannot provide the required workflow.
6. Evaluate monocular visual-inertial odometry for relative 6DoF after camera,
   IMU, extrinsic, noise, and time-offset calibration are proven viable.

The NVIDIA RTX 5090/Intel system lacked a Beast display connector while its
display-capable integrated graphics path was disabled in firmware. The AMD
Strix Halo system exposes the verified `3840x1080@60` native ultrawide mode, so
the current video path is no longer blocked by host firmware configuration.
