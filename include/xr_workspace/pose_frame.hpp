#pragma once

#include <array>
#include <cstddef>
#include <cstdint>
#include <type_traits>

namespace xr_workspace {

inline constexpr std::uint32_t kPoseMagic = 0x53505258U; // "XRPS" on little-endian hosts
inline constexpr std::uint16_t kPoseAbiVersion = 1;
inline constexpr std::size_t kPoseFrameSize = 128;
inline constexpr char kRuntimeSubdirectory[] = "xr-workspace";
inline constexpr char kPoseFilename[] = "pose-v1.bin";

enum PoseFlags : std::uint32_t {
    kConnected = 1U << 0,
    kOrientationValid = 1U << 1,
    kRawImuValid = 1U << 2,
    kStale = 1U << 3,
};

enum class PoseSource : std::uint8_t {
    kUnknown = 0,
    kMock = 1,
    kVitureSdkPose = 2,
    kVitureSdkRaw = 3,
};

enum class CoordinateSpace : std::uint8_t {
    kUnspecified = 0,
    kNorthWestUp = 1,
};

// Cross-process ABI. Do not reorder or reinterpret fields without increasing
// kPoseAbiVersion and using a new runtime filename.
struct alignas(64) PoseFrame {
    std::uint32_t magic{kPoseMagic};
    std::uint16_t abi_version{kPoseAbiVersion};
    std::uint16_t struct_size{kPoseFrameSize};
    std::uint64_t sequence{0};
    std::uint64_t monotonic_timestamp_ns{0};
    std::uint64_t source_timestamp{0};
    std::uint64_t source_vsync_timestamp{0};
    std::uint32_t flags{0};
    PoseSource source{PoseSource::kUnknown};
    CoordinateSpace coordinate_space{CoordinateSpace::kUnspecified};
    std::uint16_t reserved0{0};
    std::array<float, 3> euler_rpy_degrees{};
    std::array<float, 4> quaternion_wxyz{1.0F, 0.0F, 0.0F, 0.0F};
    std::array<float, 10> raw_imu{};
    std::uint32_t reserved1{0};
    std::uint64_t sequence_mirror{0};
};

static_assert(std::is_trivially_copyable_v<PoseFrame>);
static_assert(sizeof(PoseFrame) == kPoseFrameSize);
static_assert(alignof(PoseFrame) == 64);
static_assert(offsetof(PoseFrame, sequence) == 8);
static_assert(offsetof(PoseFrame, monotonic_timestamp_ns) == 16);
static_assert(offsetof(PoseFrame, flags) == 40);
static_assert(offsetof(PoseFrame, euler_rpy_degrees) == 48);
static_assert(offsetof(PoseFrame, quaternion_wxyz) == 60);
static_assert(offsetof(PoseFrame, raw_imu) == 76);
static_assert(offsetof(PoseFrame, sequence_mirror) == 120);

struct SourceSample {
    std::uint64_t source_timestamp{0};
    std::uint64_t source_vsync_timestamp{0};
    std::uint32_t flags{0};
    PoseSource source{PoseSource::kUnknown};
    CoordinateSpace coordinate_space{CoordinateSpace::kUnspecified};
    std::array<float, 3> euler_rpy_degrees{};
    std::array<float, 4> quaternion_wxyz{1.0F, 0.0F, 0.0F, 0.0F};
    std::array<float, 10> raw_imu{};
};

} // namespace xr_workspace
