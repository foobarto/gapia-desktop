#!/bin/sh

set -eu

script_dir=$(CDPATH='' cd -- "$(dirname -- "$0")" && pwd)
project_root=$(CDPATH='' cd -- "$script_dir/.." && pwd)

for command_name in bwrap dbus-run-session gnome-shell rpm; do
    if ! command -v "$command_name" >/dev/null 2>&1; then
        printf 'Required command not found: %s\n' "$command_name" >&2
        exit 1
    fi
done

"$script_dir/prepare-nested-shell.sh"

mutter_nevra=$(rpm -q --qf '%{VERSION}-%{RELEASE}.%{ARCH}' mutter)
schemas_nevra=$(rpm -q --qf '%{VERSION}-%{RELEASE}.%{ARCH}' gsettings-desktop-schemas)
state_key=${mutter_nevra}__${schemas_nevra}
state_dir=$project_root/.tmp/nested-shell/$state_key
helper_path=$state_dir/devkit-root/usr/libexec/mutter-devkit

host_user_data=${XDG_DATA_HOME:-${HOME:?HOME is required}/.local/share}
while [ "${host_user_data%/}" != "$host_user_data" ]; do
    host_user_data=${host_user_data%/}
done
original_data_dirs=${XDG_DATA_DIRS:-/usr/local/share:/usr/share}
clean_data_dirs=
old_ifs=$IFS
IFS=:
for data_dir in $original_data_dirs; do
    while [ "${data_dir%/}" != "$data_dir" ]; do
        data_dir=${data_dir%/}
    done
    case "$data_dir" in
        ''|"$host_user_data"|"$host_user_data"/)
            continue
            ;;
    esac
    case ":$clean_data_dirs:" in
        *:"$data_dir":*)
            continue
            ;;
    esac
    if [ -z "$clean_data_dirs" ]; then
        clean_data_dirs=$data_dir
    else
        clean_data_dirs=$clean_data_dirs:$data_dir
    fi
done
IFS=$old_ifs

if [ -z "$clean_data_dirs" ]; then
    clean_data_dirs=/usr/local/share:/usr/share
fi

export GSETTINGS_SCHEMA_DIR="$state_dir/schemas"
export GSETTINGS_BACKEND=keyfile
export XDG_CONFIG_HOME="$state_dir/config"
export XDG_CACHE_HOME="$state_dir/cache/run-$$"
export XDG_STATE_HOME="$state_dir/state"
export XDG_DATA_HOME="$state_dir/data"
export XDG_DATA_DIRS="$clean_data_dirs"
export NO_AT_BRIDGE=1
mkdir -p "$XDG_CACHE_HOME"

printf 'Starting the isolated nested GNOME desktop. Exit it or press Ctrl+C here to stop.\n'
exec dbus-run-session bwrap \
    --bind / / \
    --dev-bind /dev /dev \
    --overlay-src /usr/libexec \
    --tmp-overlay /usr/libexec \
    --ro-bind "$helper_path" /usr/libexec/mutter-devkit \
    gnome-shell --devkit --wayland "$@"
