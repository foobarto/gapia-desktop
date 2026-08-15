#include <chrono>
#include <exception>
#include <iomanip>
#include <iostream>
#include <string_view>
#include <thread>

#include "runtime_pose_file.hpp"

namespace {

const char* source_name(xr_workspace::PoseSource source) {
    switch (source) {
    case xr_workspace::PoseSource::kMock:
        return "mock";
    case xr_workspace::PoseSource::kVitureSdkPose:
        return "viture-pose";
    case xr_workspace::PoseSource::kVitureSdkRaw:
        return "viture-raw";
    default:
        return "unknown";
    }
}

void print(const xr_workspace::PoseFrame& frame) {
    std::cout << "seq=" << frame.sequence << " source=" << source_name(frame.source)
              << " flags=0x" << std::hex << frame.flags << std::dec
              << " rpy_deg=" << std::fixed << std::setprecision(3)
              << frame.euler_rpy_degrees[0] << ',' << frame.euler_rpy_degrees[1] << ','
              << frame.euler_rpy_degrees[2] << " q_wxyz=" << frame.quaternion_wxyz[0]
              << ',' << frame.quaternion_wxyz[1] << ',' << frame.quaternion_wxyz[2]
              << ',' << frame.quaternion_wxyz[3];
    if ((frame.flags & xr_workspace::kRawImuValid) != 0) {
        std::cout << " raw=";
        for (std::size_t index = 0; index < frame.raw_imu.size(); ++index) {
            if (index != 0)
                std::cout << ',';
            std::cout << frame.raw_imu[index];
        }
    }
    std::cout << '\n';
}

} // namespace

int main(int argc, char** argv) {
    try {
        bool watch = false;
        if (argc == 2 && std::string_view(argv[1]) == "--watch")
            watch = true;
        else if (argc != 1) {
            std::cerr << "Usage: xr-workspace-pose-dump [--watch]\n";
            return 2;
        }

        do {
            xr_workspace::PoseFrame frame;
            if (xr_workspace::read_pose_frame(xr_workspace::default_pose_path(), frame))
                print(frame);
            else
                std::cerr << "could not obtain a consistent ABI v1 pose frame\n";
            if (watch)
                std::this_thread::sleep_for(std::chrono::milliseconds(250));
        } while (watch);
        return 0;
    } catch (const std::exception& error) {
        std::cerr << "xr-workspace-pose-dump: " << error.what() << '\n';
        return 1;
    }
}

