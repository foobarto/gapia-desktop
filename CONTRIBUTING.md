# Contributing to Gapia Desktop

Thank you for helping improve Gapia Desktop. Contributions can include code,
tests, hardware observations, documentation, packaging, and design work.

By participating, you agree to follow the [Code of Conduct](CODE_OF_CONDUCT.md).

## Before opening a change

- Search existing issues before filing a new one.
- Use an issue to discuss new device profiles, display-policy behavior, or
  architectural changes before investing in a large implementation.
- Use private vulnerability reporting for security issues. See
  [SECURITY.md](SECURITY.md).
- Keep changes focused. Unrelated cleanup should be a separate contribution.

## Development setup

The SDK-independent components build with CMake, Ninja, a C++ compiler,
Python 3, and GJS:

```sh
cmake -S . -B build -G Ninja -DCMAKE_BUILD_TYPE=Debug
cmake --build build
ctest --test-dir build --output-on-failure
```

Native VITURE control requires a separately downloaded Linux SDK:

```sh
cmake -S . -B build-viture -G Ninja \
  -DCMAKE_BUILD_TYPE=Debug \
  -DGAPIA_ENABLE_VITURE=ON \
  -DGAPIA_VITURE_SDK_DIR=/path/to/extracted-sdk
cmake --build build-viture
ctest --test-dir build-viture --output-on-failure
```

Never commit SDK headers, libraries, archives, documentation copies, or
SDK-linked binaries. Run `./scripts/check-release-boundary.sh` before sending a
change. The full boundary is documented in [docs/licensing.md](docs/licensing.md).

## Hardware changes

Device support must be based on observed capabilities, not product-family
assumptions. Include the following evidence where applicable:

- vendor, model, USB ID, firmware, and SDK version;
- reported display modes and EDID identity;
- tracking, size, distance, and reconnect behavior;
- GNOME and OS versions used for testing; and
- the exact safety and restoration behavior of any display-policy change.

Changes that can disable or rearrange physical displays must fail closed when
the target glasses are absent, use Mutter's verification path, and restore the
previous layout on disconnect or service stop.

## Pull requests

Before submitting a pull request:

- run the relevant CTest configurations;
- run `shellcheck scripts/*.sh` and `actionlint` when changing those files;
- add or update tests for changed behavior;
- update user-facing and architecture documentation;
- confirm no private host names, personal paths, credentials, or licensed SDK
  files are present; and
- describe any hardware testing that could not be performed.

## License

Unless explicitly stated otherwise, intentionally submitted contributions are
licensed under either MIT or Apache-2.0, at the recipient's option, as described
in [LICENSE](LICENSE).
