#include <array>
#include <chrono>
#include <cstdlib>
#include <exception>
#include <iomanip>
#include <iostream>
#include <memory>
#include <sstream>
#include <stdexcept>
#include <string>
#include <string_view>
#include <thread>

#include "viture_glasses_provider.h"
#include "viture_protocol_public.h"
#include "viture_version.h"

namespace {

constexpr int kBeastProductId = 0x1211;

struct Options {
    bool query{false};
    int display_mode{-1};
    int dof{VITURE_NATIVE_DOF_3};
    int size{-1};
    int distance{-1};
};

int parse_int(std::string_view option, const char* text, int minimum, int maximum) {
    char* end = nullptr;
    const long value = std::strtol(text, &end, 10);
    if (end == text || *end != '\0' || value < minimum || value > maximum)
        throw std::runtime_error("invalid value for " + std::string(option));
    return static_cast<int>(value);
}

Options parse_options(int argc, char** argv) {
    Options options;
    for (int index = 1; index < argc; ++index) {
        const std::string_view option = argv[index];
        if (option == "--query") {
            options.query = true;
        } else if (option == "--mode" && index + 1 < argc) {
            const std::string_view value = argv[++index];
            if (value == "standard-1920x1080-60")
                options.display_mode = VITURE_NATIVE_DISPLAY_MODE_1920_1080_60HZ;
            else if (value == "standard-1920x1200-60")
                options.display_mode = VITURE_NATIVE_DISPLAY_MODE_1920_1200_60HZ;
            else if (value == "ultrawide-3840x1080-60")
                options.display_mode =
                    VITURE_NATIVE_DISPLAY_MODE_ULTRAWIDE_3840_1080_60HZ;
            else if (value == "ultrawide-3840x1200-60")
                options.display_mode =
                    VITURE_NATIVE_DISPLAY_MODE_ULTRAWIDE_3840_1200_60HZ;
            else
                throw std::runtime_error(
                    "unsupported --mode value");
        } else if (option == "--dof" && index + 1 < argc) {
            const std::string_view value = argv[++index];
            if (value == "anchored")
                options.dof = VITURE_NATIVE_DOF_3;
            else if (value == "smooth-follow")
                options.dof = VITURE_NATIVE_DOF_SMOOTH_FOLLOW;
            else if (value == "off")
                options.dof = VITURE_NATIVE_DOF_0;
            else
                throw std::runtime_error("--dof must be anchored, smooth-follow, or off");
        } else if (option == "--size" && index + 1 < argc) {
            const std::string_view value = argv[++index];
            if (value == "small")
                options.size = VITURE_DISPLAY_SIZE_SMALL;
            else if (value == "medium")
                options.size = VITURE_DISPLAY_SIZE_MEDIUM;
            else if (value == "large")
                options.size = VITURE_DISPLAY_SIZE_LARGE;
            else if (value == "extra-large")
                options.size = VITURE_DISPLAY_SIZE_EXTRA;
            else if (value == "ultra-large")
                options.size = VITURE_DISPLAY_SIZE_ULTRA;
            else
                throw std::runtime_error(
                    "--size must be small, medium, large, extra-large, or ultra-large");
        } else if (option == "--distance" && index + 1 < argc) {
            options.distance = parse_int(option, argv[++index], 1, 10);
        } else if (option == "--help") {
            std::cout
                << "Usage: xr-workspace-native-display "
                   "--query\n"
                   "   or: xr-workspace-native-display "
                   "--mode standard-1920x1080-60|standard-1920x1200-60|"
                   "ultrawide-3840x1080-60|ultrawide-3840x1200-60 "
                   "--dof anchored|smooth-follow|off "
                   "--size small|medium|large|extra-large|ultra-large "
                   "--distance 1..10\n";
            std::exit(0);
        } else {
            throw std::runtime_error("unknown or incomplete option: " +
                                     std::string(option));
        }
    }
    if (options.query) {
        if (argc != 2)
            throw std::runtime_error("--query cannot be combined with settings");
        return options;
    }
    if (options.display_mode < 0 || options.size < 0 || options.distance < 0)
        throw std::runtime_error("--mode, --dof, --size, and --distance are required");
    const bool ultrawide =
        options.display_mode == VITURE_NATIVE_DISPLAY_MODE_ULTRAWIDE_3840_1080_60HZ ||
        options.display_mode == VITURE_NATIVE_DISPLAY_MODE_ULTRAWIDE_3840_1200_60HZ;
    if (ultrawide && options.dof != VITURE_NATIVE_DOF_3)
        throw std::runtime_error("ultrawide mode requires anchored 3DoF");
    return options;
}

class Provider {
  public:
    Provider() {
        xr_device_provider_set_log_level(1);
        handle_ = xr_device_provider_create(kBeastProductId);
        if (handle_ == nullptr)
            throw std::runtime_error("VITURE SDK did not find Beast PID 35ca:1211");
        if (xr_device_provider_initialize(handle_, nullptr, nullptr) !=
            VITURE_GLASSES_SUCCESS) {
            xr_device_provider_destroy(handle_);
            handle_ = nullptr;
            throw std::runtime_error("VITURE SDK initialization failed");
        }
        initialized_ = true;
        if (xr_device_provider_start(handle_) != VITURE_GLASSES_SUCCESS) {
            xr_device_provider_shutdown(handle_);
            xr_device_provider_destroy(handle_);
            handle_ = nullptr;
            initialized_ = false;
            throw std::runtime_error("VITURE SDK start failed");
        }
        started_ = true;
    }

    Provider(const Provider&) = delete;
    Provider& operator=(const Provider&) = delete;

    ~Provider() {
        if (started_)
            xr_device_provider_stop(handle_);
        if (initialized_)
            xr_device_provider_shutdown(handle_);
        if (handle_ != nullptr)
            xr_device_provider_destroy(handle_);
    }

    XRDeviceProviderHandle get() const {
        return handle_;
    }

  private:
    XRDeviceProviderHandle handle_{nullptr};
    bool initialized_{false};
    bool started_{false};
};

struct NativeState {
    int display_mode;
    int dof;
    int size;
    int distance;
};

NativeState read_state(XRDeviceProviderHandle handle) {
    if (xr_device_provider_native_get_mode(handle) != 1)
        throw std::runtime_error("Beast is not in native display mode");
    const NativeState state{
        xr_device_provider_native_get_display_mode(handle),
        xr_device_provider_native_get_dof(handle),
        xr_device_provider_native_get_display_size(handle),
        xr_device_provider_native_get_display_distance(handle),
    };
    if (state.display_mode < 0 || state.dof < 0 || state.size < 0 ||
        state.distance < 0)
        throw std::runtime_error("could not read the complete Beast native state");
    return state;
}

std::unique_ptr<Provider> reopen_provider() {
    const auto deadline = std::chrono::steady_clock::now() + std::chrono::seconds(10);
    std::string last_error;
    do {
        try {
            return std::make_unique<Provider>();
        } catch (const std::exception& error) {
            last_error = error.what();
            std::this_thread::sleep_for(std::chrono::milliseconds(250));
        }
    } while (std::chrono::steady_clock::now() < deadline);
    throw std::runtime_error("could not reopen the Beast after its mode change: " +
                             last_error);
}

template <typename Predicate>
bool wait_for_state(Predicate predicate) {
    const auto deadline = std::chrono::steady_clock::now() + std::chrono::seconds(2);
    do {
        if (predicate())
            return true;
        std::this_thread::sleep_for(std::chrono::milliseconds(100));
    } while (std::chrono::steady_clock::now() < deadline);
    return predicate();
}

void print_state(std::string_view label, const NativeState& state) {
    std::cout << label << ": display=0x" << std::hex << state.display_mode << std::dec
              << " dof=" << state.dof << " size=" << state.size
              << " distance=" << state.distance << std::endl;
}

std::string json_escape(std::string_view value) {
    std::ostringstream result;
    for (const unsigned char character : value) {
        switch (character) {
        case '"':
            result << "\\\"";
            break;
        case '\\':
            result << "\\\\";
            break;
        case '\b':
            result << "\\b";
            break;
        case '\f':
            result << "\\f";
            break;
        case '\n':
            result << "\\n";
            break;
        case '\r':
            result << "\\r";
            break;
        case '\t':
            result << "\\t";
            break;
        default:
            if (character < 0x20) {
                result << "\\u" << std::hex << std::setw(4) << std::setfill('0')
                       << static_cast<int>(character) << std::dec;
            } else {
                result << character;
            }
        }
    }
    return result.str();
}

std::string market_name() {
    std::array<char, 64> buffer{};
    int length = static_cast<int>(buffer.size());
    if (xr_device_provider_get_market_name(kBeastProductId, buffer.data(), &length) !=
        VITURE_GLASSES_SUCCESS)
        return "Unknown";
    buffer.back() = '\0';
    return buffer.data();
}

std::string firmware_version(XRDeviceProviderHandle handle) {
    std::array<char, 128> buffer{};
    int length = static_cast<int>(buffer.size());
    if (xr_device_provider_get_glasses_version(handle, buffer.data(), &length) !=
        VITURE_GLASSES_SUCCESS)
        return "Unavailable";
    buffer.back() = '\0';
    return buffer.data();
}

std::string_view device_family(int value) {
    switch (value) {
    case XR_DEVICE_TYPE_VITURE_GEN1:
        return "Gen 1";
    case XR_DEVICE_TYPE_VITURE_GEN2:
        return "Gen 2";
    case XR_DEVICE_TYPE_VITURE_CARINA:
        return "Carina";
    default:
        return "Unknown";
    }
}

std::string_view display_mode_name(int value) {
    switch (value) {
    case VITURE_NATIVE_DISPLAY_MODE_1920_1080_60HZ:
        return "1920x1080 @ 60 Hz";
    case VITURE_NATIVE_DISPLAY_MODE_1920_1200_60HZ:
        return "1920x1200 @ 60 Hz";
    case VITURE_NATIVE_DISPLAY_MODE_ULTRAWIDE_3840_1080_60HZ:
        return "3840x1080 @ 60 Hz";
    case VITURE_NATIVE_DISPLAY_MODE_ULTRAWIDE_3840_1200_60HZ:
        return "3840x1200 @ 60 Hz";
    default:
        return "Unknown";
    }
}

std::string_view display_mode_key(int value) {
    switch (value) {
    case VITURE_NATIVE_DISPLAY_MODE_1920_1080_60HZ:
        return "standard-1920x1080-60";
    case VITURE_NATIVE_DISPLAY_MODE_1920_1200_60HZ:
        return "standard-1920x1200-60";
    case VITURE_NATIVE_DISPLAY_MODE_ULTRAWIDE_3840_1080_60HZ:
        return "ultrawide-3840x1080-60";
    case VITURE_NATIVE_DISPLAY_MODE_ULTRAWIDE_3840_1200_60HZ:
        return "ultrawide-3840x1200-60";
    default:
        return "unknown";
    }
}

std::string_view dof_name(int value) {
    switch (value) {
    case VITURE_NATIVE_DOF_0:
        return "0DoF";
    case VITURE_NATIVE_DOF_3:
        return "Anchored 3DoF";
    case VITURE_NATIVE_DOF_SMOOTH_FOLLOW:
        return "Smooth follow";
    default:
        return "Unknown";
    }
}

std::string_view dof_key(int value) {
    switch (value) {
    case VITURE_NATIVE_DOF_0:
        return "off";
    case VITURE_NATIVE_DOF_3:
        return "anchored";
    case VITURE_NATIVE_DOF_SMOOTH_FOLLOW:
        return "smooth-follow";
    default:
        return "unknown";
    }
}

std::string_view size_name(int value) {
    switch (value) {
    case VITURE_DISPLAY_SIZE_SMALL:
        return "Small";
    case VITURE_DISPLAY_SIZE_MEDIUM:
        return "Medium";
    case VITURE_DISPLAY_SIZE_LARGE:
        return "Large";
    case VITURE_DISPLAY_SIZE_EXTRA:
        return "Extra large";
    case VITURE_DISPLAY_SIZE_ULTRA:
        return "Ultra large";
    default:
        return "Unknown";
    }
}

std::string_view size_key(int value) {
    switch (value) {
    case VITURE_DISPLAY_SIZE_SMALL:
        return "small";
    case VITURE_DISPLAY_SIZE_MEDIUM:
        return "medium";
    case VITURE_DISPLAY_SIZE_LARGE:
        return "large";
    case VITURE_DISPLAY_SIZE_EXTRA:
        return "extra-large";
    case VITURE_DISPLAY_SIZE_ULTRA:
        return "ultra-large";
    default:
        return "unknown";
    }
}

void print_device_info(XRDeviceProviderHandle handle, const NativeState& state) {
    const std::string model = market_name();
    const std::string firmware = firmware_version(handle);
    const char* sdk_version = GetVersionString();
    std::cout << "GAPIA_DEVICE_INFO {"
              << "\"brand\":\"VITURE\","
              << "\"model\":\"" << json_escape(model) << "\","
              << "\"firmware\":\"" << json_escape(firmware) << "\","
              << "\"usb_id\":\"35ca:1211\","
              << "\"sdk_version\":\""
              << json_escape(sdk_version == nullptr ? "Unknown" : sdk_version) << "\","
              << "\"device_family\":\""
              << device_family(xr_device_provider_get_device_type(handle)) << "\","
              << "\"native_tracking\":"
              << (xr_device_provider_is_product_support_native_dof(kBeastProductId) == 1
                      ? "true"
                      : "false")
              << ",\"display_mode\":\"" << display_mode_name(state.display_mode)
              << "\",\"tracking\":\"" << dof_name(state.dof)
              << "\",\"screen_size\":\"" << size_name(state.size)
              << "\",\"distance\":" << state.distance
              << ",\"settings\":{\"mode\":\""
              << display_mode_key(state.display_mode) << "\",\"dof\":\""
              << dof_key(state.dof) << "\",\"screen_size\":\""
              << size_key(state.size) << "\",\"distance\":" << state.distance
              << "}}" << std::endl;
}

} // namespace

int main(int argc, char** argv) {
    try {
        const Options options = parse_options(argc, argv);
        auto provider = std::make_unique<Provider>();
        NativeState state = read_state(provider->get());
        print_state("current native state", state);
        if (options.query) {
            print_device_info(provider->get(), state);
            return 0;
        }

        if (state.display_mode != options.display_mode) {
            const int result = xr_device_provider_native_set_display_mode(
                provider->get(), options.display_mode);
            provider.reset();
            provider = reopen_provider();
            state = read_state(provider->get());
            if (state.display_mode != options.display_mode) {
                throw std::runtime_error(
                    "Beast display mode did not match after re-enumeration; command result=" +
                    std::to_string(result));
            }
        }

        auto handle = provider->get();
        if (state.dof != options.dof &&
            xr_device_provider_native_set_dof(handle, options.dof) !=
                VITURE_GLASSES_SUCCESS)
            throw std::runtime_error("Beast rejected the tracking mode");
        if (state.size != options.size &&
            xr_device_provider_native_set_display_size(handle, options.size) !=
                VITURE_GLASSES_SUCCESS)
            throw std::runtime_error("Beast rejected the display size");
        if (state.distance != options.distance &&
            xr_device_provider_native_set_display_distance(handle, options.distance) !=
                VITURE_GLASSES_SUCCESS)
            throw std::runtime_error("Beast rejected the display distance");

        if (!wait_for_state([&] {
                const NativeState current = read_state(handle);
                return current.display_mode == options.display_mode &&
                       current.dof == options.dof && current.size == options.size &&
                       current.distance == options.distance;
            }))
            throw std::runtime_error("Beast native-state readback did not match");
        if (options.dof == VITURE_NATIVE_DOF_3 &&
            xr_device_provider_native_recenter_dof(handle) != VITURE_GLASSES_SUCCESS)
            throw std::runtime_error("Beast rejected anchored-viewport recentering");

        const NativeState applied_state = read_state(handle);
        print_state("applied native state", applied_state);
        print_device_info(handle, applied_state);
        return 0;
    } catch (const std::exception& error) {
        std::cerr << "xr-workspace-native-display: " << error.what() << '\n';
        return 1;
    }
}
