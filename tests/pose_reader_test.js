import {
    POSE_ABI_VERSION,
    POSE_FRAME_SIZE,
    POSE_MAGIC,
    PoseFlags,
    PoseReader,
    parsePoseFrame,
} from '../gnome-extension/gapia@desktop.local/poseReader.js';

function assert(condition, message) {
    if (!condition)
        throw new Error(message);
}

const bytes = new Uint8Array(POSE_FRAME_SIZE);
const view = new DataView(bytes.buffer);
view.setUint32(0, POSE_MAGIC, true);
view.setUint16(4, POSE_ABI_VERSION, true);
view.setUint16(6, POSE_FRAME_SIZE, true);
view.setUint32(8, 42, true);
view.setUint32(12, 0, true);
view.setUint32(40, PoseFlags.CONNECTED | PoseFlags.ORIENTATION_VALID, true);
view.setUint8(44, 1);
view.setUint8(45, 1);
view.setFloat32(48, 1.25, true);
view.setFloat32(52, -2.5, true);
view.setFloat32(56, 17.75, true);
view.setFloat32(60, 1, true);
view.setUint32(120, 42, true);
view.setUint32(124, 0, true);

const pose = parsePoseFrame(bytes);
assert(pose !== null, 'valid pose frame was rejected');
assert(pose.sequence === 42, 'sequence was parsed incorrectly');
assert(pose.source === 1 && pose.coordinateSpace === 1,
    'source metadata was parsed incorrectly');
assert(Math.abs(pose.eulerRpyDegrees[2] - 17.75) < 0.0001,
    'Euler data was parsed incorrectly');

view.setUint32(120, 40, true);
assert(parsePoseFrame(bytes) === null, 'mismatched seqlock mirror was accepted');
view.setUint32(120, 43, true);
view.setUint32(8, 43, true);
assert(parsePoseFrame(bytes) === null, 'odd seqlock sequence was accepted');

if (ARGV.length > 0) {
    const livePose = new PoseReader(ARGV[0]).read();
    assert(livePose !== null, 'C++ publisher frame was rejected by GJS reader');
    assert(livePose.source === 1, 'expected the C++ mock source');
    assert((livePose.flags & PoseFlags.ORIENTATION_VALID) !== 0,
        'C++ mock frame was not orientation-valid');
}

print('GJS pose ABI parser verified');
