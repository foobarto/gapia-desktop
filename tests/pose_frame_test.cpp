#include <cassert>
#include <cmath>
#include <cstdlib>
#include <filesystem>
#include <iostream>

#include <sys/stat.h>
#include <unistd.h>

#include "mock_source.hpp"
#include "runtime_pose_file.hpp"

int main() {
    char path_template[] = "/tmp/xr-workspace-test-XXXXXX";
    char* runtime_directory = ::mkdtemp(path_template);
    assert(runtime_directory != nullptr);
    assert(::setenv("XDG_RUNTIME_DIR", runtime_directory, 1) == 0);

    {
        xr_workspace::MockSource source;
        source.start();
        const auto now = std::chrono::steady_clock::now();
        const auto sample = source.sample(now);
        assert((sample.flags & xr_workspace::kOrientationValid) != 0);

        xr_workspace::RuntimePoseFile publisher;
        publisher.publish(sample, now);

        xr_workspace::PoseFrame frame;
        assert(xr_workspace::read_pose_frame(publisher.path(), frame));
        assert(frame.magic == xr_workspace::kPoseMagic);
        assert(frame.abi_version == xr_workspace::kPoseAbiVersion);
        assert(frame.struct_size == sizeof(xr_workspace::PoseFrame));
        assert((frame.sequence & 1U) == 0);
        assert(frame.sequence_mirror == frame.sequence);
        assert(frame.source == xr_workspace::PoseSource::kMock);
        assert((frame.flags & xr_workspace::kOrientationValid) != 0);

        float norm = 0.0F;
        for (float value : frame.quaternion_wxyz)
            norm += value * value;
        assert(std::abs(norm - 1.0F) < 0.0001F);

        struct stat status {};
        assert(::stat(publisher.path().c_str(), &status) == 0);
        assert((status.st_mode & 0777) == 0600);
        assert(::stat(publisher.path().parent_path().c_str(), &status) == 0);
        assert((status.st_mode & 0777) == 0700);
    }

    std::filesystem::remove_all(runtime_directory);
    std::cout << "pose ABI, seqlock read, quaternion, and permissions verified\n";
    return 0;
}
