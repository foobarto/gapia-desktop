#include <cmath>
#include <cstdlib>
#include <filesystem>
#include <iostream>

#include <sys/stat.h>
#include <unistd.h>

#include "mock_source.hpp"
#include "runtime_pose_file.hpp"

namespace {

void require(bool condition, const char* expression, int line) {
    if (condition)
        return;

    std::cerr << "check failed at line " << line << ": " << expression << '\n';
    std::exit(EXIT_FAILURE);
}

}  // namespace

#define CHECK(expression) require(static_cast<bool>(expression), #expression, __LINE__)

int main() {
    char path_template[] = "/tmp/xr-workspace-test-XXXXXX";
    char* runtime_directory = ::mkdtemp(path_template);
    CHECK(runtime_directory != nullptr);
    CHECK(::setenv("XDG_RUNTIME_DIR", runtime_directory, 1) == 0);

    {
        xr_workspace::MockSource source;
        source.start();
        const auto now = std::chrono::steady_clock::now();
        const auto sample = source.sample(now);
        CHECK((sample.flags & xr_workspace::kOrientationValid) != 0);

        xr_workspace::RuntimePoseFile publisher;
        publisher.publish(sample, now);

        xr_workspace::PoseFrame frame;
        CHECK(xr_workspace::read_pose_frame(publisher.path(), frame));
        CHECK(frame.magic == xr_workspace::kPoseMagic);
        CHECK(frame.abi_version == xr_workspace::kPoseAbiVersion);
        CHECK(frame.struct_size == sizeof(xr_workspace::PoseFrame));
        CHECK((frame.sequence & 1U) == 0);
        CHECK(frame.sequence_mirror == frame.sequence);
        CHECK(frame.source == xr_workspace::PoseSource::kMock);
        CHECK((frame.flags & xr_workspace::kOrientationValid) != 0);

        float norm = 0.0F;
        for (float value : frame.quaternion_wxyz)
            norm += value * value;
        CHECK(std::abs(norm - 1.0F) < 0.0001F);

        struct stat status {};
        CHECK(::stat(publisher.path().c_str(), &status) == 0);
        CHECK((status.st_mode & 0777) == 0600);
        CHECK(::stat(publisher.path().parent_path().c_str(), &status) == 0);
        CHECK((status.st_mode & 0777) == 0700);
    }

    std::filesystem::remove_all(runtime_directory);
    std::cout << "pose ABI, seqlock read, quaternion, and permissions verified\n";
    return 0;
}
