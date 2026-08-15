#!/bin/sh

set -eu

if [ "$#" -lt 1 ] || [ "$#" -gt 2 ]; then
    printf 'Usage: %s VERSION [OUTPUT_DIR]\n' "$0" >&2
    exit 2
fi

version=$1
output_dir=${2:-dist}
script_dir=$(CDPATH='' cd -- "$(dirname -- "$0")" && pwd)
project_root=$(CDPATH='' cd -- "$script_dir/.." && pwd)
staging=$(mktemp -d)
trap 'rm -rf "$staging"' EXIT HUP INT TERM
archive_root=$staging/gapia-desktop-$version

mkdir -p "$archive_root" "$output_dir"
for path in \
    .github .gitignore CHANGELOG.md CMakeLists.txt CODE_OF_CONDUCT.md \
    CONTRIBUTING.md README.md SECURITY.md SUPPORT.md \
    LICENSE LICENSE-APACHE LICENSE-MIT Formula assets config docs \
    gnome-extension include packaging scripts src tests; do
    cp -R "$project_root/$path" "$archive_root/"
done

"$project_root/scripts/check-release-boundary.sh" "$archive_root"
tar \
    --exclude='__pycache__' \
    --exclude='*.pyc' \
    -C "$staging" -czf \
    "$output_dir/gapia-desktop-$version.tar.gz" \
    "gapia-desktop-$version"
printf '%s\n' "$output_dir/gapia-desktop-$version.tar.gz"
