#!/bin/sh

set -eu

script_dir=$(CDPATH='' cd -- "$(dirname -- "$0")" && pwd)
project_root=$(CDPATH='' cd -- "$script_dir/.." && pwd)
extension_uuid=gapia@desktop.local
extension_source=$project_root/gnome-extension/$extension_uuid

for command_name in cpio dnf5 glib-compile-schemas gsettings rpm rpm2cpio; do
    if ! command -v "$command_name" >/dev/null 2>&1; then
        printf 'Required command not found: %s\n' "$command_name" >&2
        exit 1
    fi
done

if [ ! -d "$extension_source" ]; then
    printf 'Extension source directory not found: %s\n' "$extension_source" >&2
    exit 1
fi

mutter_nevra=$(rpm -q --qf '%{VERSION}-%{RELEASE}.%{ARCH}' mutter)
schemas_nevra=$(rpm -q --qf '%{VERSION}-%{RELEASE}.%{ARCH}' gsettings-desktop-schemas)
state_key=${mutter_nevra}__${schemas_nevra}
state_dir=$project_root/.tmp/nested-shell/$state_key
rpm_dir=$state_dir/rpms
devkit_root=$state_dir/devkit-root
schema_dir=$state_dir/schemas
data_home=$state_dir/data
config_home=$state_dir/config
cache_home=$state_dir/cache
state_home=$state_dir/state
rpm_path=$rpm_dir/mutter-devkit-$mutter_nevra.rpm
helper_path=$devkit_root/usr/libexec/mutter-devkit

mkdir -p "$rpm_dir" "$devkit_root" "$schema_dir" \
    "$data_home/gnome-shell/extensions" "$config_home" "$cache_home" "$state_home"

if [ ! -f "$rpm_path" ]; then
    printf 'Downloading the exact mutter-devkit build matching mutter %s...\n' \
        "$mutter_nevra"
    dnf5 download --destdir "$rpm_dir" "mutter-devkit-$mutter_nevra"
fi

if [ ! -x "$helper_path" ]; then
    (
        cd "$devkit_root"
        rpm2cpio "$rpm_path" | cpio -idmu --quiet
    )
fi

if [ ! -x "$helper_path" ]; then
    printf 'mutter-devkit was not extracted at the expected path: %s\n' \
        "$helper_path" >&2
    exit 1
fi

# GSETTINGS_SCHEMA_DIR is additive. Compile only the schemas missing from the
# booted image's generated cache: the current calendar and accessibility
# XML (which contain week-start-day and reduced-motion), their enum dependency,
# and the schema shipped by the matching devkit subpackage.
cp /usr/share/glib-2.0/schemas/org.gnome.desktop.calendar.gschema.xml "$schema_dir/"
cp /usr/share/glib-2.0/schemas/org.gnome.desktop.a11y.interface.gschema.xml \
    "$schema_dir/"
cp /usr/share/glib-2.0/schemas/org.gnome.desktop.enums.xml "$schema_dir/"
cp "$devkit_root/usr/share/glib-2.0/schemas/org.gnome.mutter.devkit.gschema.xml" \
    "$schema_dir/"
glib-compile-schemas --strict "$schema_dir"

if ! GSETTINGS_SCHEMA_DIR=$schema_dir \
    gsettings list-keys org.gnome.desktop.calendar | grep -qx week-start-day; then
    printf 'Private schema cache is missing week-start-day\n' >&2
    exit 1
fi

if ! GSETTINGS_SCHEMA_DIR=$schema_dir \
    gsettings list-schemas | grep -qx org.gnome.mutter.devkit; then
    printf 'Private schema cache is missing org.gnome.mutter.devkit\n' >&2
    exit 1
fi

if ! GSETTINGS_SCHEMA_DIR=$schema_dir \
    gsettings list-keys org.gnome.desktop.a11y.interface | grep -qx reduced-motion; then
    printf 'Private schema cache is missing reduced-motion\n' >&2
    exit 1
fi

extension_link=$data_home/gnome-shell/extensions/$extension_uuid
if [ -e "$extension_link" ] && [ ! -L "$extension_link" ]; then
    printf 'Refusing to replace non-symlink extension path: %s\n' \
        "$extension_link" >&2
    exit 1
fi
ln -sfn "$extension_source" "$extension_link"

GSETTINGS_SCHEMA_DIR="$schema_dir" GSETTINGS_BACKEND=keyfile \
    XDG_CONFIG_HOME="$config_home" \
    gsettings set org.gnome.shell disable-user-extensions false
GSETTINGS_SCHEMA_DIR="$schema_dir" GSETTINGS_BACKEND=keyfile \
    XDG_CONFIG_HOME="$config_home" \
    gsettings set org.gnome.shell enabled-extensions \
    "['$extension_uuid']"

printf 'Nested GNOME Shell development environment prepared in:\n  %s\n' "$state_dir"
printf 'No package was installed and no live GNOME setting was changed.\n'
