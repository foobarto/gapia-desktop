# Licensing and publication boundary

Gapia Desktop is independent software and is not affiliated with or endorsed by
VITURE. VITURE names are used only to identify compatible hardware and the
separately supplied SDK.

## Current boundary

The repository and its release artifacts must not contain:

- `libglasses.so` or any other VITURE SDK binary;
- `viture_glasses_provider.h` or another copied SDK header;
- a VITURE SDK archive, SDK documentation copy, or license-gated download; or
- a Homebrew bottle or GitHub binary built against the SDK until VITURE gives
  explicit written redistribution permission.

The host setup accepts an SDK directory supplied by the user and copies the
runtime only into that user's local installation. The GitHub workflows build
and test the independent components and audit every artifact for SDK files.

VITURE's [developer portal](https://www.viture.com/en-US/developer) describes a
unified SDK for VITURE glasses, but that is a capability statement, not a grant
to redistribute the SDK. The current public
[Terms of Service](https://www.viture.com/terms-of-service) restrict copying,
distribution, sublicensing, and commercial use of supplied software unless
VITURE authorizes it or a specific developer agreement says otherwise. The
downloaded Linux SDK examined during development did not include a separate
license or notice file that answered redistribution questions.

This document records a conservative engineering policy, not legal advice.

## Questions for VITURE

Obtain written answers before publishing SDK-backed binaries or bottles:

1. May an open-source project publicly compile and link against the Linux SDK?
2. May the SDK header be redistributed in source releases or package builds?
3. May `libglasses.so` be redistributed in GitHub releases, Homebrew bottles,
   Flatpaks, or other Linux packages?
4. If redistribution is prohibited, may end users download the SDK separately
   and use it with this application?
5. May continuous-integration workers use a private SDK copy to build and test
   artifacts that do not contain SDK files?
6. Are noncommercial and commercial distributions treated differently?
7. Which copyright notices, license text, attribution, or update obligations
   must accompany a compatible application?
8. What wording and artwork may be used to state VITURE compatibility without
   implying endorsement or violating trademark guidelines?

## Project license

Gapia Desktop's original source and assets are dual-licensed under
`MIT OR Apache-2.0`, at the recipient's option. Both are permissive licenses and
neither requires VITURE to disclose or relicense its SDK. They also do not grant
permission to copy, link, or redistribute the SDK; those rights must come from
VITURE's applicable agreement.
