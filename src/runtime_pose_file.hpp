#pragma once

#include <filesystem>

#include "xr_workspace/pose_frame.hpp"

namespace xr_workspace {

std::filesystem::path default_pose_path();

class RuntimePoseFile {
  public:
    RuntimePoseFile();
    ~RuntimePoseFile();

    RuntimePoseFile(const RuntimePoseFile&) = delete;
    RuntimePoseFile& operator=(const RuntimePoseFile&) = delete;

    void publish(const SourceSample& sample,
                 std::chrono::steady_clock::time_point now);
    const std::filesystem::path& path() const noexcept { return path_; }

  private:
    int directory_fd_{-1};
    int file_fd_{-1};
    PoseFrame* mapped_{nullptr};
    std::filesystem::path path_;
    std::uint64_t sequence_{0};
};

bool read_pose_frame(const std::filesystem::path& path, PoseFrame& output);

} // namespace xr_workspace

