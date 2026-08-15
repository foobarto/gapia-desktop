import Gio from 'gi://Gio';
import GLib from 'gi://GLib';

export const POSE_MAGIC = 0x53505258;
export const POSE_ABI_VERSION = 1;
export const POSE_FRAME_SIZE = 128;

export const PoseFlags = Object.freeze({
    CONNECTED: 1 << 0,
    ORIENTATION_VALID: 1 << 1,
    RAW_IMU_VALID: 1 << 2,
    STALE: 1 << 3,
});

function uint64Parts(view, offset) {
    return {
        low: view.getUint32(offset, true),
        high: view.getUint32(offset + 4, true),
    };
}

function uint64PartsEqual(left, right) {
    return left.low === right.low && left.high === right.high;
}

function floatArray(view, offset, count) {
    return Array.from({length: count}, (_, index) =>
        view.getFloat32(offset + index * 4, true));
}

export function parsePoseFrame(contents) {
    if (!(contents instanceof Uint8Array) || contents.byteLength !== POSE_FRAME_SIZE)
        return null;

    const view = new DataView(contents.buffer, contents.byteOffset, contents.byteLength);
    if (view.getUint32(0, true) !== POSE_MAGIC ||
        view.getUint16(4, true) !== POSE_ABI_VERSION ||
        view.getUint16(6, true) !== POSE_FRAME_SIZE)
        return null;

    const sequence = uint64Parts(view, 8);
    const sequenceMirror = uint64Parts(view, 120);
    if ((sequence.low & 1) !== 0 || !uint64PartsEqual(sequence, sequenceMirror))
        return null;

    return {
        // Exact until the counter exceeds JavaScript's 53-bit integer range.
        sequence: sequence.high * 0x1_0000_0000 + sequence.low,
        flags: view.getUint32(40, true),
        source: view.getUint8(44),
        coordinateSpace: view.getUint8(45),
        eulerRpyDegrees: floatArray(view, 48, 3),
        quaternionWxyz: floatArray(view, 60, 4),
        rawImu: floatArray(view, 76, 10),
    };
}

export class PoseReader {
    constructor(path = null) {
        const posePath = path ?? GLib.build_filenamev([
            GLib.get_user_runtime_dir(),
            'xr-workspace',
            'pose-v1.bin',
        ]);
        this._file = Gio.File.new_for_path(posePath);
    }

    read() {
        try {
            const [success, contents] = this._file.load_contents(null);
            return success ? parsePoseFrame(contents) : null;
        } catch (error) {
            if (!error.matches?.(Gio.IOErrorEnum, Gio.IOErrorEnum.NOT_FOUND))
                console.debug(`Gapia pose read failed: ${error.message}`);
            return null;
        }
    }
}
