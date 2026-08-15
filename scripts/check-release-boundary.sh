#!/bin/sh

set -eu

root=${1:-.}
violations=$(find "$root" \
    -type d \( \
        -name .git -o -name .tmp -o -name build -o -name 'build-*' \
    \) -prune -o \
    -type f \( \
        -name libglasses.so -o \
        -name viture_glasses_provider.h -o \
        -name 'VITURE_XR_Glasses_SDK*' -o \
        -name '*.sdk.zip' \
    \) -print)

if [ -n "$violations" ]; then
    printf 'Release boundary violation: licensed SDK files found:\n%s\n' \
        "$violations" >&2
    exit 1
fi

printf 'Release boundary check passed: no VITURE SDK files found.\n'
