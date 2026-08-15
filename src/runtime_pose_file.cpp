#include "runtime_pose_file.hpp"

#include <atomic>
#include <cerrno>
#include <cstring>
#include <stdexcept>
#include <string>
#include <system_error>
#include <new>

#include <fcntl.h>
#include <sys/mman.h>
#include <sys/stat.h>
#include <sys/types.h>
#include <unistd.h>

namespace xr_workspace {
namespace {

std::runtime_error system_error(const std::string& operation) {
    return std::runtime_error(operation + ": " + std::strerror(errno));
}

void validate_owned_directory(int fd, const char* description, bool require_private) {
    struct stat status {};
    if (::fstat(fd, &status) != 0)
        throw system_error(std::string("inspect ") + description);
    if (!S_ISDIR(status.st_mode) || status.st_uid != ::getuid())
        throw std::runtime_error(std::string(description) +
                                 " must be a directory owned by the current user");
    if (require_private && (status.st_mode & 0077) != 0)
        throw std::runtime_error(std::string(description) +
                                 " must not grant group or other permissions");
}

void validate_owned_regular_file(int fd) {
    struct stat status {};
    if (::fstat(fd, &status) != 0)
        throw system_error("inspect pose file");
    if (!S_ISREG(status.st_mode) || status.st_uid != ::getuid() || status.st_nlink != 1)
        throw std::runtime_error(
            "pose file must be a singly linked regular file owned by the current user");
}

std::uint64_t monotonic_ns(std::chrono::steady_clock::time_point now) {
    return static_cast<std::uint64_t>(
        std::chrono::duration_cast<std::chrono::nanoseconds>(now.time_since_epoch()).count());
}

} // namespace

std::filesystem::path default_pose_path() {
    const char* runtime = std::getenv("XDG_RUNTIME_DIR");
    if (runtime == nullptr || *runtime == '\0')
        throw std::runtime_error("XDG_RUNTIME_DIR is not set");
    return std::filesystem::path(runtime) / kRuntimeSubdirectory / kPoseFilename;
}

RuntimePoseFile::RuntimePoseFile() {
    static_assert(std::atomic_ref<std::uint64_t>::is_always_lock_free,
                  "the pose ABI requires lock-free 64-bit atomics");

    const char* runtime = std::getenv("XDG_RUNTIME_DIR");
    if (runtime == nullptr || *runtime == '\0')
        throw std::runtime_error("XDG_RUNTIME_DIR is not set");

    const int parent_fd = ::open(runtime, O_RDONLY | O_DIRECTORY | O_CLOEXEC | O_NOFOLLOW);
    if (parent_fd < 0)
        throw system_error("open XDG_RUNTIME_DIR");

    try {
        validate_owned_directory(parent_fd, "XDG_RUNTIME_DIR", true);
        if (::mkdirat(parent_fd, kRuntimeSubdirectory, 0700) != 0 && errno != EEXIST)
            throw system_error("create xr-workspace runtime directory");

        directory_fd_ = ::openat(parent_fd, kRuntimeSubdirectory,
                                 O_RDONLY | O_DIRECTORY | O_CLOEXEC | O_NOFOLLOW);
        if (directory_fd_ < 0)
            throw system_error("open xr-workspace runtime directory");
        validate_owned_directory(directory_fd_, "xr-workspace runtime directory", false);
        if (::fchmod(directory_fd_, 0700) != 0)
            throw system_error("set xr-workspace runtime directory permissions");

        file_fd_ = ::openat(directory_fd_, kPoseFilename,
                            O_RDWR | O_CREAT | O_CLOEXEC | O_NOFOLLOW, 0600);
        if (file_fd_ < 0)
            throw system_error("open pose file");
        validate_owned_regular_file(file_fd_);
        if (::fchmod(file_fd_, 0600) != 0)
            throw system_error("set pose file permissions");
        if (::ftruncate(file_fd_, static_cast<off_t>(sizeof(PoseFrame))) != 0)
            throw system_error("resize pose file");

        void* mapping = ::mmap(nullptr, sizeof(PoseFrame), PROT_READ | PROT_WRITE,
                               MAP_SHARED, file_fd_, 0);
        if (mapping == MAP_FAILED)
            throw system_error("map pose file");
        mapped_ = ::new (mapping) PoseFrame{};
        path_ = default_pose_path();
    } catch (...) {
        ::close(parent_fd);
        if (mapped_ != nullptr)
            ::munmap(mapped_, sizeof(PoseFrame));
        if (file_fd_ >= 0)
            ::close(file_fd_);
        if (directory_fd_ >= 0)
            ::close(directory_fd_);
        mapped_ = nullptr;
        file_fd_ = -1;
        directory_fd_ = -1;
        throw;
    }

    ::close(parent_fd);
}

RuntimePoseFile::~RuntimePoseFile() {
    if (mapped_ != nullptr) {
        SourceSample disconnected;
        publish(disconnected, std::chrono::steady_clock::now());
        ::munmap(mapped_, sizeof(PoseFrame));
    }
    if (file_fd_ >= 0)
        ::close(file_fd_);
    if (directory_fd_ >= 0)
        ::close(directory_fd_);
}

void RuntimePoseFile::publish(const SourceSample& sample,
                              std::chrono::steady_clock::time_point now) {
    PoseFrame next;
    next.sequence = sequence_ + 2;
    next.sequence_mirror = sequence_ + 2;
    next.monotonic_timestamp_ns = monotonic_ns(now);
    next.source_timestamp = sample.source_timestamp;
    next.source_vsync_timestamp = sample.source_vsync_timestamp;
    next.flags = sample.flags;
    next.source = sample.source;
    next.coordinate_space = sample.coordinate_space;
    next.euler_rpy_degrees = sample.euler_rpy_degrees;
    next.quaternion_wxyz = sample.quaternion_wxyz;
    next.raw_imu = sample.raw_imu;

    auto sequence = std::atomic_ref(mapped_->sequence);
    auto sequence_mirror = std::atomic_ref(mapped_->sequence_mirror);
    sequence.store(sequence_ + 1, std::memory_order_release);
    sequence_mirror.store(sequence_ + 1, std::memory_order_release);
    auto* mapped_bytes = reinterpret_cast<std::byte*>(mapped_);
    const auto* next_bytes = reinterpret_cast<const std::byte*>(&next);
    std::memcpy(mapped_bytes, next_bytes, offsetof(PoseFrame, sequence));
    constexpr std::size_t after_sequence =
        offsetof(PoseFrame, sequence) + sizeof(PoseFrame::sequence);
    std::memcpy(mapped_bytes + after_sequence, next_bytes + after_sequence,
                offsetof(PoseFrame, sequence_mirror) - after_sequence);
    std::atomic_thread_fence(std::memory_order_release);
    sequence_ += 2;
    sequence_mirror.store(sequence_, std::memory_order_release);
    sequence.store(sequence_, std::memory_order_release);
}

bool read_pose_frame(const std::filesystem::path& path, PoseFrame& output) {
    const int fd = ::open(path.c_str(), O_RDONLY | O_CLOEXEC | O_NOFOLLOW);
    if (fd < 0)
        throw system_error("open pose file for reading");

    struct stat status {};
    if (::fstat(fd, &status) != 0) {
        const int saved_errno = errno;
        ::close(fd);
        errno = saved_errno;
        throw system_error("inspect pose file for reading");
    }
    if (!S_ISREG(status.st_mode) || status.st_uid != ::getuid() ||
        status.st_size != static_cast<off_t>(sizeof(PoseFrame))) {
        ::close(fd);
        throw std::runtime_error("pose file has unexpected type, owner, or size");
    }

    void* mapping = ::mmap(nullptr, sizeof(PoseFrame), PROT_READ, MAP_SHARED, fd, 0);
    const int saved_errno = errno;
    ::close(fd);
    if (mapping == MAP_FAILED) {
        errno = saved_errno;
        throw system_error("map pose file for reading");
    }

    const auto* frame = static_cast<const PoseFrame*>(mapping);
    bool consistent = false;
    for (int attempt = 0; attempt < 20; ++attempt) {
        auto sequence = std::atomic_ref(frame->sequence);
        const std::uint64_t before = sequence.load(std::memory_order_acquire);
        if ((before & 1U) != 0)
            continue;
        std::memcpy(&output, frame, sizeof(output));
        std::atomic_thread_fence(std::memory_order_acquire);
        const auto sequence_mirror = std::atomic_ref(frame->sequence_mirror);
        const std::uint64_t mirror = sequence_mirror.load(std::memory_order_acquire);
        const std::uint64_t after = sequence.load(std::memory_order_acquire);
        if (before == after && after == mirror && output.sequence_mirror == after &&
            (after & 1U) == 0) {
            consistent = true;
            break;
        }
    }
    ::munmap(mapping, sizeof(PoseFrame));

    if (!consistent)
        return false;
    return output.magic == kPoseMagic && output.abi_version == kPoseAbiVersion &&
           output.struct_size == sizeof(PoseFrame);
}

} // namespace xr_workspace
