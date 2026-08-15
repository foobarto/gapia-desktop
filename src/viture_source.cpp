#include "viture_source.hpp"

#include <stdexcept>

#ifdef XR_WORKSPACE_HAVE_VITURE

#include <algorithm>
#include <array>
#include <chrono>
#include <iostream>
#include <mutex>
#include <string>
#include <thread>

#include "viture_device.h"
#include "viture_glasses_provider.h"
#include "viture_protocol_public.h"

namespace xr_workspace {
namespace {

constexpr int kBeastProductId = 0x1211;
constexpr auto kPoseWait = std::chrono::milliseconds(1500);

template <typename Predicate>
bool wait_for_device_state(Predicate predicate) {
    constexpr auto timeout = std::chrono::seconds(2);
    constexpr auto interval = std::chrono::milliseconds(100);
    const auto deadline = std::chrono::steady_clock::now() + timeout;
    do {
        if (predicate())
            return true;
        std::this_thread::sleep_for(interval);
    } while (std::chrono::steady_clock::now() < deadline);
    return predicate();
}

int bypass_mode_for_native_mode(int native_mode) {
    switch (native_mode) {
    case VITURE_NATIVE_DISPLAY_MODE_1920_1080_60HZ:
        return VITURE_DISPLAY_MODE_1920_1080_60HZ;
    case VITURE_NATIVE_DISPLAY_MODE_1920_1080_90HZ:
        return VITURE_DISPLAY_MODE_1920_1080_90HZ;
    case VITURE_NATIVE_DISPLAY_MODE_1920_1080_120HZ:
        return VITURE_DISPLAY_MODE_1920_1080_120HZ;
    case VITURE_NATIVE_DISPLAY_MODE_1920_1200_60HZ:
        return VITURE_DISPLAY_MODE_1920_1200_60HZ;
    case VITURE_NATIVE_DISPLAY_MODE_1920_1200_90HZ:
        return VITURE_DISPLAY_MODE_1920_1200_90HZ;
    case VITURE_NATIVE_DISPLAY_MODE_1920_1200_120HZ:
        return VITURE_DISPLAY_MODE_1920_1200_120HZ;
    case VITURE_NATIVE_DISPLAY_MODE_3D_SBS_3840_1080_60HZ:
        return VITURE_DISPLAY_MODE_3840_1080_60HZ;
    case VITURE_NATIVE_DISPLAY_MODE_3D_SBS_3840_1080_90HZ:
        return VITURE_DISPLAY_MODE_3840_1080_90HZ;
    case VITURE_NATIVE_DISPLAY_MODE_3D_SBS_3840_1200_60HZ:
        return VITURE_DISPLAY_MODE_3840_1200_60HZ;
    case VITURE_NATIVE_DISPLAY_MODE_3D_SBS_3840_1200_90HZ:
        return VITURE_DISPLAY_MODE_3840_1200_90HZ;
    default:
        return -1;
    }
}

} // namespace

struct VitureSource::Impl {
    static Impl* active;

    XRDeviceProviderHandle handle{nullptr};
    std::mutex mutex;
    SourceSample latest;
    std::chrono::steady_clock::time_point opened_at{};
    bool initialized{false};
    bool started{false};
    int open_mode{-1};
    bool received_sample{false};
    bool warned_no_raw_samples{false};
    bool allow_device_mode_change{false};
    bool restore_native_state{false};

    struct NativeState {
        int display_mode{-1};
        int dof{-1};
        int side_mode{-1};
        int distance{-1};
        int size{-1};
    } native_state;

    static void pose_callback(float* data, std::uint64_t timestamp) {
        if (active == nullptr || data == nullptr)
            return;
        std::lock_guard lock(active->mutex);
        active->latest.source_timestamp = timestamp;
        active->latest.flags = kConnected | kOrientationValid;
        active->latest.source = PoseSource::kVitureSdkPose;
        active->latest.coordinate_space = CoordinateSpace::kNorthWestUp;
        std::copy_n(data, 3, active->latest.euler_rpy_degrees.begin());
        std::copy_n(data + 3, 4, active->latest.quaternion_wxyz.begin());
        active->received_sample = true;
    }

    static void raw_callback(float* data, std::uint64_t timestamp,
                             std::uint64_t vsync_timestamp) {
        if (active == nullptr || data == nullptr)
            return;
        std::lock_guard lock(active->mutex);
        active->latest.source_timestamp = timestamp;
        active->latest.source_vsync_timestamp = vsync_timestamp;
        active->latest.flags = kConnected | kRawImuValid;
        active->latest.source = PoseSource::kVitureSdkRaw;
        active->latest.coordinate_space = CoordinateSpace::kUnspecified;
        std::copy_n(data, 10, active->latest.raw_imu.begin());
        active->received_sample = true;
    }

    void open_raw() {
        if (open_mode >= 0)
            xr_device_provider_close_imu(handle, static_cast<std::uint8_t>(open_mode));
        {
            std::lock_guard lock(mutex);
            latest = SourceSample{};
            latest.flags = kConnected;
            latest.source = PoseSource::kVitureSdkRaw;
            received_sample = false;
            warned_no_raw_samples = false;
        }
        const int callback_result =
            xr_device_provider_register_imu_raw_callback(handle, raw_callback);
        if (callback_result != VITURE_GLASSES_SUCCESS)
            throw std::runtime_error("VITURE SDK rejected raw IMU callback: " +
                                     std::to_string(callback_result));
        const int open_result = xr_device_provider_open_imu(
            handle, VITURE_IMU_MODE_RAW, VITURE_IMU_FREQUENCY_MEDIUM_HIGH);
        if (open_result != VITURE_GLASSES_SUCCESS)
            throw std::runtime_error("VITURE SDK could not open raw IMU stream: " +
                                     std::to_string(open_result));
        open_mode = VITURE_IMU_MODE_RAW;
        opened_at = std::chrono::steady_clock::now();
    }

    void prepare_host_tracking() {
        const int native_mode = xr_device_provider_native_get_mode(handle);
        if (native_mode < 0)
            throw std::runtime_error("VITURE SDK could not read Beast native mode: " +
                                     std::to_string(native_mode));
        if (native_mode == 0)
            return;
        if (native_mode != 1)
            throw std::runtime_error("VITURE SDK returned an unknown Beast native mode");
        if (!allow_device_mode_change)
            throw std::runtime_error(
                "Beast is in native display mode, which does not deliver host IMU samples; "
                "rerun with --allow-device-mode-change to switch to bypass mode and "
                "restore the complete native state on normal exit");

        native_state.display_mode = xr_device_provider_native_get_display_mode(handle);
        native_state.dof = xr_device_provider_native_get_dof(handle);
        native_state.side_mode = xr_device_provider_native_get_side_mode(handle);
        native_state.distance = xr_device_provider_native_get_display_distance(handle);
        native_state.size = xr_device_provider_native_get_display_size(handle);
        if (native_state.display_mode < 0 || native_state.dof < 0 ||
            native_state.side_mode < 0 || native_state.distance < 0 ||
            native_state.size < 0)
            throw std::runtime_error("could not snapshot complete Beast native state; "
                                     "refusing to switch modes");

        const int bypass_display_mode = bypass_mode_for_native_mode(native_state.display_mode);
        if (bypass_display_mode < 0)
            throw std::runtime_error("current Beast native display mode has no safe bypass "
                                     "equivalent; refusing to switch modes");

        std::cerr << "Beast native-state snapshot: display_mode=0x" << std::hex
                  << native_state.display_mode << std::dec << " dof=" << native_state.dof
                  << " side=" << native_state.side_mode
                  << " distance=" << native_state.distance << " size=" << native_state.size
                  << "; temporary bypass display_mode=0x" << std::hex
                  << bypass_display_mode << std::dec << '\n';

        const int mode_result = xr_device_provider_native_set_mode(handle, 0);
        if (mode_result != VITURE_GLASSES_SUCCESS)
            throw std::runtime_error("could not switch Beast to bypass mode: " +
                                     std::to_string(mode_result));
        restore_native_state = true;
        const int display_result =
            xr_device_provider_set_display_mode(handle, bypass_display_mode);
        if (display_result != VITURE_GLASSES_SUCCESS)
            throw std::runtime_error("could not complete Beast bypass-mode switch: " +
                                     std::to_string(display_result));
        const bool bypass_verified = wait_for_device_state([&] {
            return xr_device_provider_native_get_mode(handle) == 0 &&
                   xr_device_provider_get_display_mode(handle) == bypass_display_mode;
        });
        if (!bypass_verified)
            throw std::runtime_error("Beast bypass-mode readback did not match the requested "
                                     "state; restoring native state");
        std::cerr << "Beast temporary bypass state verified: display_mode=0x" << std::hex
                  << bypass_display_mode << std::dec << '\n';
    }

    void restore_device_state() noexcept {
        if (!restore_native_state || handle == nullptr)
            return;

        bool commands_okay =
            xr_device_provider_native_set_mode(handle, 1) == VITURE_GLASSES_SUCCESS;
        commands_okay &= wait_for_device_state(
            [&] { return xr_device_provider_native_get_mode(handle) == 1; });
        commands_okay &=
            xr_device_provider_native_set_display_mode(handle, native_state.display_mode) ==
            VITURE_GLASSES_SUCCESS;
        commands_okay &= xr_device_provider_native_set_dof(handle, native_state.dof) ==
                         VITURE_GLASSES_SUCCESS;
        commands_okay &=
            xr_device_provider_native_set_side_mode(handle, native_state.side_mode) ==
            VITURE_GLASSES_SUCCESS;
        commands_okay &= xr_device_provider_native_set_display_distance(
                             handle, native_state.distance) == VITURE_GLASSES_SUCCESS;
        commands_okay &= xr_device_provider_native_set_display_size(handle, native_state.size) ==
                         VITURE_GLASSES_SUCCESS;
        const bool state_restored = wait_for_device_state([&] {
            return xr_device_provider_native_get_mode(handle) == 1 &&
                   xr_device_provider_native_get_display_mode(handle) ==
                       native_state.display_mode &&
                   xr_device_provider_native_get_dof(handle) == native_state.dof &&
                   xr_device_provider_native_get_side_mode(handle) == native_state.side_mode &&
                   xr_device_provider_native_get_display_distance(handle) ==
                       native_state.distance &&
                   xr_device_provider_native_get_display_size(handle) == native_state.size;
        });
        const int verified_mode = xr_device_provider_native_get_mode(handle);
        const int verified_display = xr_device_provider_native_get_display_mode(handle);
        const int verified_dof = xr_device_provider_native_get_dof(handle);
        const int verified_side = xr_device_provider_native_get_side_mode(handle);
        const int verified_distance = xr_device_provider_native_get_display_distance(handle);
        const int verified_size = xr_device_provider_native_get_display_size(handle);
        if (!state_restored)
            std::cerr << "xr-workspace-pose-service: WARNING: one or more Beast native "
                         "settings could not be restored; readback: mode="
                      << verified_mode << " display=0x" << std::hex << verified_display
                      << std::dec << " dof=" << verified_dof << " side=" << verified_side
                      << " distance=" << verified_distance << " size=" << verified_size
                      << '\n';
        else
            std::cerr << "Beast native state restored and verified: display_mode=0x"
                      << std::hex << verified_display << std::dec << " dof=" << verified_dof
                      << " side=" << verified_side << " distance=" << verified_distance
                      << " size=" << verified_size
                      << (commands_okay ? "" : " (final state verified after a command error)")
                      << '\n';
        restore_native_state = false;
    }
};

VitureSource::Impl* VitureSource::Impl::active = nullptr;

VitureSource::VitureSource(bool allow_device_mode_change)
    : impl_(std::make_unique<Impl>()) {
    impl_->allow_device_mode_change = allow_device_mode_change;
}

VitureSource::~VitureSource() {
    stop();
}

void VitureSource::start() {
    if (Impl::active != nullptr)
        throw std::runtime_error("only one VITURE source may be active");
    Impl::active = impl_.get();

    try {
        // Keep the opaque SDK quiet except for failures. This is a process-local
        // logging choice, not a glasses setting, and no log hook is registered.
        xr_device_provider_set_log_level(1);
        impl_->handle = xr_device_provider_create(kBeastProductId);
        if (impl_->handle == nullptr)
            throw std::runtime_error("VITURE SDK did not find Beast PID 35ca:1211");
        const int initialize_result =
            xr_device_provider_initialize(impl_->handle, nullptr, nullptr);
        if (initialize_result != VITURE_GLASSES_SUCCESS)
            throw std::runtime_error("VITURE SDK initialize failed: " +
                                     std::to_string(initialize_result));
        impl_->initialized = true;
        const int start_result = xr_device_provider_start(impl_->handle);
        if (start_result != VITURE_GLASSES_SUCCESS)
            throw std::runtime_error("VITURE SDK start failed: " +
                                     std::to_string(start_result));
        impl_->started = true;
        impl_->prepare_host_tracking();

        const int callback_result =
            xr_device_provider_register_imu_pose_callback(impl_->handle,
                                                          Impl::pose_callback);
        if (callback_result != VITURE_GLASSES_SUCCESS)
            throw std::runtime_error("VITURE SDK rejected pose callback: " +
                                     std::to_string(callback_result));
        int pose_frequency = -1;
        int open_result = -1;
        for (int frequency = VITURE_IMU_FREQUENCY_HIGH;
             frequency >= VITURE_IMU_FREQUENCY_LOW; --frequency) {
            if (!xr_device_provider_is_product_support_imu_frequency(
                    kBeastProductId, VITURE_IMU_MODE_POSE, frequency))
                continue;
            open_result = xr_device_provider_open_imu(
                impl_->handle, VITURE_IMU_MODE_POSE, frequency);
            if (open_result == VITURE_GLASSES_SUCCESS) {
                pose_frequency = frequency;
                break;
            }
            std::cerr << "xr-workspace-pose-service: processed pose stream open failed ("
                      << open_result << ") at SDK frequency " << frequency << '\n';
        }
        if (open_result != VITURE_GLASSES_SUCCESS) {
            std::cerr << "xr-workspace-pose-service: all product-supported processed pose "
                         "rates failed; falling back to raw IMU\n";
            impl_->open_raw();
            return;
        }
        std::cerr << "xr-workspace-pose-service: processed pose stream opened at SDK "
                     "frequency "
                  << pose_frequency << '\n';
        impl_->open_mode = VITURE_IMU_MODE_POSE;
        impl_->opened_at = std::chrono::steady_clock::now();
        std::lock_guard lock(impl_->mutex);
        impl_->latest.flags = kConnected;
        impl_->latest.source = PoseSource::kVitureSdkPose;
    } catch (...) {
        stop();
        throw;
    }
}

SourceSample VitureSource::sample(std::chrono::steady_clock::time_point now) {
    bool fallback_to_raw = false;
    {
        std::lock_guard lock(impl_->mutex);
        fallback_to_raw = impl_->open_mode == VITURE_IMU_MODE_POSE &&
                          !impl_->received_sample && now - impl_->opened_at >= kPoseWait;
    }
    if (fallback_to_raw) {
        std::cerr << "xr-workspace-pose-service: no processed pose samples arrived within "
                  << kPoseWait.count() << " ms; falling back to raw IMU\n";
        impl_->open_raw();
    }
    bool warn_no_samples = false;
    SourceSample result;
    {
        std::lock_guard lock(impl_->mutex);
        if (impl_->open_mode == VITURE_IMU_MODE_RAW && !impl_->received_sample &&
            now - impl_->opened_at >= kPoseWait) {
            impl_->latest.flags |= kStale;
            warn_no_samples = !impl_->warned_no_raw_samples;
            impl_->warned_no_raw_samples = true;
        }
        result = impl_->latest;
    }
    if (warn_no_samples)
        std::cerr << "xr-workspace-pose-service: Beast acknowledged raw IMU streaming "
                     "but no samples arrived\n";
    return result;
}

void VitureSource::stop() noexcept {
    if (!impl_)
        return;
    if (impl_->handle != nullptr && impl_->open_mode >= 0) {
        xr_device_provider_close_imu(impl_->handle,
                                     static_cast<std::uint8_t>(impl_->open_mode));
        impl_->open_mode = -1;
    }
    impl_->restore_device_state();
    if (impl_->handle != nullptr && impl_->started) {
        xr_device_provider_stop(impl_->handle);
        impl_->started = false;
    }
    if (impl_->handle != nullptr && impl_->initialized) {
        xr_device_provider_shutdown(impl_->handle);
        impl_->initialized = false;
    }
    if (impl_->handle != nullptr) {
        xr_device_provider_destroy(impl_->handle);
        impl_->handle = nullptr;
    }
    if (Impl::active == impl_.get())
        Impl::active = nullptr;
}

} // namespace xr_workspace

#else

namespace xr_workspace {

struct VitureSource::Impl {};

VitureSource::VitureSource(bool) : impl_(std::make_unique<Impl>()) {}
VitureSource::~VitureSource() = default;

void VitureSource::start() {
    throw std::runtime_error(
        "this build has no VITURE SDK backend; configure with "
        "-DXR_WORKSPACE_ENABLE_VITURE=ON and -DXR_WORKSPACE_VITURE_SDK_DIR=...");
}

SourceSample VitureSource::sample(std::chrono::steady_clock::time_point) {
    return {};
}

void VitureSource::stop() noexcept {}

} // namespace xr_workspace

#endif
