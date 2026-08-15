#include <atomic>
#include <chrono>
#include <csignal>
#include <cstdlib>
#include <exception>
#include <iostream>
#include <memory>
#include <stdexcept>
#include <string_view>
#include <thread>

#include "mock_source.hpp"
#include "runtime_pose_file.hpp"
#include "viture_source.hpp"

namespace {

std::atomic_bool running{true};

void stop_signal(int) {
    running.store(false, std::memory_order_relaxed);
}

struct Options {
    std::string_view source{"mock"};
    int rate_hz{120};
    int duration_seconds{0};
    bool allow_device_mode_change{false};
};

int parse_positive_int(std::string_view option, const char* text, bool allow_zero) {
    char* end = nullptr;
    const long value = std::strtol(text, &end, 10);
    if (end == text || *end != '\0' || value < (allow_zero ? 0 : 1) || value > 1000)
        throw std::runtime_error("invalid value for " + std::string(option));
    return static_cast<int>(value);
}

Options parse_options(int argc, char** argv) {
    Options result;
    for (int index = 1; index < argc; ++index) {
        const std::string_view option = argv[index];
        if (option == "--source" && index + 1 < argc) {
            result.source = argv[++index];
        } else if (option == "--rate" && index + 1 < argc) {
            result.rate_hz = parse_positive_int(option, argv[++index], false);
        } else if (option == "--duration" && index + 1 < argc) {
            result.duration_seconds = parse_positive_int(option, argv[++index], true);
        } else if (option == "--allow-device-mode-change") {
            result.allow_device_mode_change = true;
        } else if (option == "--help") {
            std::cout << "Usage: xr-workspace-pose-service "
                         "[--source mock|viture] [--rate 1..1000] "
                         "[--duration seconds] [--allow-device-mode-change]\n";
            std::exit(0);
        } else {
            throw std::runtime_error("unknown or incomplete option: " + std::string(option));
        }
    }
    if (result.source != "mock" && result.source != "viture")
        throw std::runtime_error("--source must be mock or viture");
    return result;
}

} // namespace

int main(int argc, char** argv) {
    try {
        const Options options = parse_options(argc, argv);
        std::unique_ptr<xr_workspace::PoseSourceInterface> source;
        if (options.source == "mock")
            source = std::make_unique<xr_workspace::MockSource>();
        else
            source = std::make_unique<xr_workspace::VitureSource>(
                options.allow_device_mode_change);

        xr_workspace::RuntimePoseFile output;
        source->start();
        std::signal(SIGINT, stop_signal);
        std::signal(SIGTERM, stop_signal);

        std::cout << "publishing " << options.source << " pose data at "
                  << options.rate_hz << " Hz to " << output.path() << '\n';
        const auto start = std::chrono::steady_clock::now();
        const auto period = std::chrono::nanoseconds(1'000'000'000 / options.rate_hz);
        auto deadline = start;
        while (running.load(std::memory_order_relaxed)) {
            const auto now = std::chrono::steady_clock::now();
            output.publish(source->sample(now), now);
            if (options.duration_seconds > 0 &&
                now - start >= std::chrono::seconds(options.duration_seconds))
                break;
            deadline += period;
            std::this_thread::sleep_until(deadline);
            if (std::chrono::steady_clock::now() - deadline > period * 4)
                deadline = std::chrono::steady_clock::now();
        }
        source->stop();
        return 0;
    } catch (const std::exception& error) {
        std::cerr << "xr-workspace-pose-service: " << error.what() << '\n';
        return 1;
    }
}
