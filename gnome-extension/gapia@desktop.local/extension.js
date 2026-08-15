import Gio from 'gi://Gio';
import GLib from 'gi://GLib';
import St from 'gi://St';

import {Extension} from 'resource:///org/gnome/shell/extensions/extension.js';
import * as Main from 'resource:///org/gnome/shell/ui/main.js';
import * as PanelMenu from 'resource:///org/gnome/shell/ui/panelMenu.js';
import * as PopupMenu from 'resource:///org/gnome/shell/ui/popupMenu.js';


const STATUS_INTERVAL_SECONDS = 1;
const DESKTOP_ID = 'io.github.gapiadesktop.Gapia.desktop';


export default class GapiaExtension extends Extension {
    enable() {
        this._statusFile = Gio.File.new_for_path(GLib.build_filenamev([
            GLib.get_user_runtime_dir(),
            'gapia',
            'native-display-status.json',
        ]));

        this._indicator = new PanelMenu.Button(0.0, 'XR display settings');
        this._icon = new St.Icon({
            gicon: Gio.icon_new_for_string(GLib.build_filenamev([
                this.path,
                'gapia-symbolic.svg',
            ])),
            style_class: 'system-status-icon gapia-panel-icon',
        });
        this._indicator.add_child(this._icon);

        this._deviceItem = new PopupMenu.PopupMenuItem(
            'Glasses disconnected',
            {reactive: false},
        );
        this._modeItem = new PopupMenu.PopupMenuItem(
            'No active display profile',
            {reactive: false},
        );
        this._indicator.menu.addMenuItem(this._deviceItem);
        this._indicator.menu.addMenuItem(this._modeItem);
        this._indicator.menu.addMenuItem(new PopupMenu.PopupSeparatorMenuItem());

        const settingsItem = new PopupMenu.PopupImageMenuItem(
            'Open Display Settings',
            'video-display-symbolic',
        );
        settingsItem.connect('activate', () => this._openSettings());
        this._indicator.menu.addMenuItem(settingsItem);

        Main.panel.addToStatusArea(
            'gapia',
            this._indicator,
            0,
            'right',
        );
        this._refresh();
        this._timerId = GLib.timeout_add_seconds(
            GLib.PRIORITY_DEFAULT,
            STATUS_INTERVAL_SECONDS,
            () => this._refresh(),
        );
    }

    disable() {
        if (this._timerId) {
            GLib.source_remove(this._timerId);
            this._timerId = 0;
        }
        this._indicator?.destroy();
        this._indicator = null;
        this._icon = null;
        this._deviceItem = null;
        this._modeItem = null;
        this._statusFile = null;
    }

    _readStatus() {
        try {
            const [success, contents] = this._statusFile.load_contents(null);
            if (!success)
                return null;
            const value = JSON.parse(new TextDecoder().decode(contents));
            return value && typeof value === 'object' ? value : null;
        } catch (error) {
            if (!error.matches?.(Gio.IOErrorEnum, Gio.IOErrorEnum.NOT_FOUND))
                console.debug(`Gapia status read failed: ${error.message}`);
            return null;
        }
    }

    _refresh() {
        if (!this._indicator)
            return GLib.SOURCE_REMOVE;

        const status = this._readStatus();
        const connected = status?.connected === true;
        this._icon.opacity = connected ? 255 : 110;
        const device = status?.device;
        this._deviceItem.label.text = connected
            ? `${device?.brand ?? 'XR'} ${device?.model ?? 'glasses'}`
            : 'Glasses disconnected';

        if (status?.state === 'active' && status.config) {
            const workspace = status.config.mode?.startsWith('ultrawide-')
                ? 'Ultrawide'
                : 'Standard';
            const tracking = status.config.dof === 'smooth-follow'
                ? 'Smooth follow'
                : status.config.dof === 'anchored'
                    ? 'Anchored'
                    : '0DoF';
            this._modeItem.label.text = `${workspace} · ${tracking}`;
        } else if (status?.state === 'error' || status?.state === 'config-error') {
            this._modeItem.label.text = 'Display controller needs attention';
        } else {
            this._modeItem.label.text = 'No active display profile';
        }
        return GLib.SOURCE_CONTINUE;
    }

    _openSettings() {
        const desktopInfo = Gio.DesktopAppInfo.new(DESKTOP_ID);
        if (desktopInfo) {
            desktopInfo.launch([], null);
            return;
        }
        GLib.spawn_async(
            null,
            ['gapia-desktop'],
            null,
            GLib.SpawnFlags.SEARCH_PATH,
            null,
        );
    }
}
