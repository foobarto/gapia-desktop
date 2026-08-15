#include "mock_source.hpp"

#include <cmath>

namespace xr_workspace {
namespace {

constexpr float kPi = 3.14159265358979323846F;

std::array<float, 4> quaternion_from_rpy(float roll_degrees, float pitch_degrees,
                                         float yaw_degrees) {
    const float scale = kPi / 360.0F;
    const float cr = std::cos(roll_degrees * scale);
    const float sr = std::sin(roll_degrees * scale);
    const float cp = std::cos(pitch_degrees * scale);
    const float sp = std::sin(pitch_degrees * scale);
    const float cy = std::cos(yaw_degrees * scale);
    const float sy = std::sin(yaw_degrees * scale);
    return {
        cr * cp * cy + sr * sp * sy,
        sr * cp * cy - cr * sp * sy,
        cr * sp * cy + sr * cp * sy,
        cr * cp * sy - sr * sp * cy,
    };
}

} // namespace

void MockSource::start() {
    start_time_ = std::chrono::steady_clock::now();
}

SourceSample MockSource::sample(std::chrono::steady_clock::time_point now) {
    const float seconds = std::chrono::duration<float>(now - start_time_).count();
    SourceSample result;
    result.flags = kConnected | kOrientationValid;
    result.source = PoseSource::kMock;
    result.coordinate_space = CoordinateSpace::kNorthWestUp;
    result.euler_rpy_degrees = {
        5.0F * std::cos(2.0F * kPi * seconds / 6.0F),
        8.0F * std::sin(2.0F * kPi * seconds / 5.0F),
        22.0F * std::sin(2.0F * kPi * seconds / 8.0F),
    };
    result.quaternion_wxyz = quaternion_from_rpy(
        result.euler_rpy_degrees[0], result.euler_rpy_degrees[1],
        result.euler_rpy_degrees[2]);
    return result;
}

} // namespace xr_workspace

