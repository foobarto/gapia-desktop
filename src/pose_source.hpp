#pragma once

#include <chrono>

#include "xr_workspace/pose_frame.hpp"

namespace xr_workspace {

class PoseSourceInterface {
  public:
    virtual ~PoseSourceInterface() = default;
    virtual void start() = 0;
    virtual SourceSample sample(std::chrono::steady_clock::time_point now) = 0;
    virtual void stop() noexcept = 0;
};

} // namespace xr_workspace

