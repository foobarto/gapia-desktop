#pragma once

#include <memory>

#include "pose_source.hpp"

namespace xr_workspace {

class VitureSource final : public PoseSourceInterface {
  public:
    explicit VitureSource(bool allow_device_mode_change);
    ~VitureSource() override;

    void start() override;
    SourceSample sample(std::chrono::steady_clock::time_point now) override;
    void stop() noexcept override;

  private:
    struct Impl;
    std::unique_ptr<Impl> impl_;
};

} // namespace xr_workspace
