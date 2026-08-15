# Official VITURE Linux SDK capability audit

Audit date: 2026-08-14.

## Artifact inspected

The current gated Linux x86-64 download was inspected locally without copying
it into this project:

```text
archive:  VITURE_XR_Glasses_SDK_for_Linux_x86_64.zip
version:  2.4.0
dated:    2026-08-07
SHA-256:  9ceab9ecbcae0185b903cd14d17848f32b0750768a21f956b768ed18796759fc
```

The old public blog post still presents SDK 1.0.7, which supported only VITURE
Pro and is not an adequate Beast reference. The current package comes from the
[VITURE developer portal](https://www.viture.com/en-US/developer); its separate
[SDK license agreement](https://www.viture.com/en-US/viture-sdk-license-agreement)
applies.

## What it provides for Beast

The SDK exposes a C API through `libglasses.so` and public headers:

- provider discovery/lifecycle for Gen1, Gen2, and Carina device families;
- Beast product validation and market-name lookup;
- raw IMU callbacks with gyroscope, accelerometer, magnetometer, temperature,
  device timestamp, and associated VSync timestamp;
- processed 3DoF callbacks with `[roll, pitch, yaw, qw, qx, qy, qz]` in a
  North-West-Up frame; Euler values are degrees;
- reported raw and pose rates of 60, 90, 120, 240, 500, and 1000 Hz for the
  connected Beast PID;
- native/bypass mode, native 0DoF/3DoF/smooth-follow, recenter, side mode,
  display distance, and display size controls;
- 1920x1080, 1920x1200, side-by-side 3D, and native ultrawide display-mode
  identifiers at model-dependent 60/90/120 Hz rates;
- brightness levels 0-8, volume levels 0-15, electrochromic-film control,
  duty cycle, button-control options, wear status, firmware version, and state
  callbacks;
- front-camera identifiers for a separate UVC device. On this host it appears
  as `0c45:6368` and advertises 1920x1080 MJPEG at 30 fps.

SDK 2.4.0 added processed pose for Gen2 and says it requires updated glasses
firmware. The connected Beast reports firmware
`21.0.01.026_20260716`. It has no Beast 6DoF API: the SDK's 6DoF/VIO and stereo
camera APIs are for the Luma Ultra/Carina family.

## What it does not provide

The SDK does not create arbitrary Linux software displays, multiple GNOME
monitors, or application UI. It does expose the controls needed for the first
milestone: the Beast firmware can present its DisplayPort input as a native
3DoF virtual monitor and move its optical viewport across native ultrawide
modes up to 3840x1200. GNOME sees that physical ultrawide input directly.

Layouts beyond the firmware's native modes would still require application
work: software outputs, capture, pose mapping, viewport rendering, lifecycle,
and UI.

The current [public Beast product specification](https://www.viture.com/product/viture-beast-dock-pack)
identifies 1920x1200 panels per eye and advertises 1920x1200 and 3840x1200
presentations. VITURE's current [Beast overview](https://www.viture.com/academy/xr-glasses/the-beast)
describes its Mac/Windows UltraWide mode as 32:9. Those public pages do not
claim a 7680-pixel input or enumerate every resolution/rate pair.
The SDK header is a cross-product protocol superset: it defines 1920x1080,
1920x1200, 3840x1080, and 3840x1200 constants at multiple rates, but provides no
per-product display-mode support query. Constant presence is therefore not
treated as evidence that the connected Beast accepts a mode.

Device automation maps only the currently read-back Beast native mode to its
exact standard bypass equivalent. An unknown or native-ultrawide state is
rejected rather than replaced with a guessed SDK mode. Lower compatibility
modes listed by GNOME/DRM likewise do not establish native panel or firmware
capability.

It also does not publish physical-unit conversion constants for the ten-float
raw packet in its public headers. This project therefore preserves raw values
unchanged until an independently implemented fusion path is calibrated and
validated.

## Live Beast results

With the installed narrow udev rule, an ordinary desktop user can initialize
the SDK and receive command acknowledgements from USB PID `35ca:1211`. The SDK
also considers legacy/alternate PID `0x1201` valid, but the connected device is
`0x1211`.

The NVIDIA RTX 5090/Intel system had no Beast DRM connector because its Intel
integrated graphics, which supplied the display-capable USB-C/Thunderbolt path,
was disabled in firmware. Its bounded native-to-bypass test received no
processed-pose or raw callbacks. On the AMD Strix Halo system, `card1-DP-1`
exposes a `VITURE Beast` EDID, and Mutter actively drives its preferred
1920x1200@60 mode.

The connected Beast accepted native ultrawide opcode `0x3d`. Mutter then
reported the physical Beast output at `3840x1080@60`, while native anchored
3DoF moved the optical viewport across distinct left and right desktop content.
The verified active state is native mode 1, display `0x3d`, anchored DOF 1,
side mode 0, distance 9, and size 2. The display-mode command re-enumerates the
HID interface, so verification must reopen the SDK provider rather than reuse
the stale handle.

An earlier bounded test safely selected equivalent 1920x1200@60 bypass mode.
Opening the SDK processed-pose stream returned USB
execution error `-3` at every product-reported rate tested from 500 down to 60
Hz, but the raw 240 Hz fallback delivered continuous live callbacks. The
service published valid raw frames at 120 Hz and restored every captured native
setting successfully. This firmware reported zero for both SDK device and
VSync timestamps, so initial fusion must use the publisher's monotonic host
timestamp.

The SDK's bundled Beast demo registers its pose callback after provider
initialization and startup, matching this project. Callback registration order
was therefore not the cause of the earlier failure. Exact evidence is in
`device-interactions.md`.

## Privacy and dependency boundary

The SDK package includes an optional statistics-reporter API. This project does
not call it. The project itself has no HTTP client, telemetry, device-binding,
serial-hash, or licensing-check path. The proprietary SDK is opt-in, supplied
by the developer at build time, and never vendored or copied by the build.

Before a public release, distribution and linking choices still need review
against the current VITURE SDK terms. That review is deliberately separate
from proving the personal-project prototype.
