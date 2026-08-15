# Device interactions

## 2026-08-15: native ultrawide anchored viewport

The SDK native display mode was changed from `0x34` to ultrawide opcode `0x3d`.
The mode change re-enumerated the Beast HID interface, invalidating the open
SDK handle. Reopening the provider returned this state:

```text
native mode:    1
display mode:   0x3d (3840x1080 at 60 Hz native ultrawide)
DOF:            1 (native anchored 3DoF)
side mode:      0
distance:       9
size:           2 (large)
```

GNOME concurrently reported the Beast output at `3840x1080@60`. Turning left
revealed a window at the left edge; turning right revealed additional wallpaper
beyond the centered subject. This proves the hardware viewport traversed
different source pixels. The built-in display remained at 2880x1800 and scale
1.6667. The working path does not use Mutter RecordVirtual, PipeWire, or
GStreamer.

This log complements `host-changes.md`. It records changes made to the glasses
themselves, including temporary state that is restored before a command exits.

## 2026-08-15: successful raw tracking with an active Beast display

Status: completed; original device settings restored and verified.

The AMD Strix Halo system exposes the glasses through all required paths:

```text
USB control:  35ca:1211 VITURE Beast XR Glasses
DRM output:   AMD card1-DP-1
EDID product: VITURE Beast
GNOME mode:   1920x1200@60, current and preferred
```

The bounded command was:

```sh
./build-viture/xr-workspace-pose-service \
  --source viture --allow-device-mode-change --duration 20
```

The service captured this native-state snapshot:

```text
native mode:    1
display mode:   0x34 (1920x1200 at 60 Hz in the native-mode opcode space)
DOF:            2 (native smooth-follow)
side mode:      0
distance:       9
size:           4
```

It selected bypass display mode `0x41`, verified the mode readback, and first
requested processed pose at 120 Hz. That request returned SDK USB-execution
error `-3`. The service's raw fallback then opened successfully at 240 Hz and
delivered continuous callbacks. The 120 Hz runtime publisher produced frames
with `source=viture-raw`, flags `0x5` (`connected | raw-valid`), changing raw
values, and a nonzero publisher monotonic timestamp. The SDK supplied zero for
both the raw callback's device timestamp and associated VSync timestamp on this
firmware.

On normal exit, the service restored native mode and all five captured values.
The SDK readback exactly matched the snapshot. Mutter still reported the Beast
connected and active at 1920x1200@60 afterward.

The official SDK 2.4.0 demo registers its pose callback after initialize/start,
as this project does. The earlier callback-order hypothesis is rejected. The
remaining tracking work is independent fusion of the now-verified raw stream,
using host monotonic time initially, unless a later SDK or firmware revision
fixes Beast processed-pose opening or its raw timestamps.

A follow-up aligned the pose request with the bundled demo by trying the
highest product-reported rate up to 500 Hz, then every lower reported rate.
The Beast returned SDK USB-execution error `-3` at 500, 240, 120, 90, and 60
Hz. Raw 240 Hz fallback still opened and delivered samples. Bypass and restore
readback now poll for the acknowledged device transition rather than checking
immediately; the final native state again matched display mode `0x34`, DOF `2`,
side mode `0`, distance `9`, and size `4` exactly.

## 2026-08-14: read-only SDK and stream probes

Status: completed; no persistent device setting changed.

The official VITURE SDK 2.4.0 lifecycle and state getters were exercised on
Beast firmware `21.0.01.026_20260716`. The pose service then opened and closed
processed-pose and raw-IMU streams while the device remained in native mode.
Both commands were acknowledged, but neither stream delivered samples in
native mode. Opening and closing an IMU stream is temporary and the provider
was stopped, shut down, and destroyed after each bounded probe.

## 2026-08-14: temporary native-to-bypass tracking probe

Status: completed; original device settings restored and verified.

The bounded command was:

```sh
./build-viture/xr-workspace-pose-service \
  --source viture --allow-device-mode-change --duration 30
```

The service read this complete native-state snapshot before making a change:

```text
native mode:    1
display mode:   0x31 (1920x1080 at 60 Hz in the native-mode opcode space)
DOF:            1 (native 3DoF)
side mode:      0
distance:       9
size:           2
```

It selected bypass mode `0` and the resolution-equivalent standard display
mode `0x31`. Both setters and readback succeeded. Processed-pose mode at 120 Hz
was acknowledged but produced no callbacks within 1.5 seconds, so the service
closed it and opened raw mode at 240 Hz. Raw mode was also acknowledged but
produced no callbacks during the remaining test window.

On normal exit the service closed the IMU stream, restored native mode and all
five captured native settings, then read every value back. The verified final
state exactly matched the snapshot above.

The lack of callbacks despite acknowledged mode/stream commands remained under
investigation at the time. Later inspection established why this system had no
Beast DRM connector: the Intel integrated graphics supplying its display-
capable USB-C/Thunderbolt path was disabled in firmware, while the connected
front USB-C port carried data only. The operating-system distribution was not
the cause. Whether the inactive video path also caused the missing callbacks
was not proven on that hardware.

After restoration, the NVIDIA RTX 5090 DRM connector check showed only
`card1-DP-1` and `card1-HDMI-A-1` connected. Their EDIDs identify Samsung
`LC34G55T` and Odyssey G5 displays. All other NVIDIA connectors were
disconnected, and no VITURE EDID or connector was present.
