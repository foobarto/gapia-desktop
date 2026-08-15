#pragma once

#include "pose_source.hpp"

namespace xr_workspace {

class MockSource final : public PoseSourceInterface {
  public:
    void start() override;
    SourceSample sample(std::chrono::steady_clock::time_point now) override;
    void stop() noexcept override {}

  private:
    std::chrono::steady_clock::time_point start_time_{};
};

} // namespace xr_workspace

