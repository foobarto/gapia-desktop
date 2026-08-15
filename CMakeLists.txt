cmake_minimum_required(VERSION 3.24)

project(gapia-desktop VERSION 0.1.2 LANGUAGES CXX)

option(GAPIA_ENABLE_VITURE "Build the optional official VITURE SDK backend" OFF)
set(GAPIA_VITURE_SDK_DIR "" CACHE PATH "Root of an extracted VITURE Linux SDK")

add_library(xr-workspace-pose-core STATIC
    src/mock_source.cpp
    src/runtime_pose_file.cpp
)
target_compile_features(xr-workspace-pose-core PUBLIC cxx_std_20)
target_include_directories(xr-workspace-pose-core
    PUBLIC include
    PRIVATE src
)
target_compile_options(xr-workspace-pose-core PRIVATE -Wall -Wextra -Wpedantic -Werror)

add_executable(xr-workspace-pose-service
    src/pose_service.cpp
    src/viture_source.cpp
)
target_link_libraries(xr-workspace-pose-service PRIVATE xr-workspace-pose-core)
target_include_directories(xr-workspace-pose-service PRIVATE src)
target_compile_options(xr-workspace-pose-service PRIVATE -Wall -Wextra -Wpedantic -Werror)

if(GAPIA_ENABLE_VITURE)
    if(NOT GAPIA_VITURE_SDK_DIR)
        message(FATAL_ERROR "GAPIA_VITURE_SDK_DIR is required when the VITURE backend is enabled")
    endif()
    find_path(VITURE_INCLUDE_DIR viture_glasses_provider.h
        PATHS "${GAPIA_VITURE_SDK_DIR}/include"
        NO_DEFAULT_PATH REQUIRED)
    find_library(VITURE_GLASSES_LIBRARY glasses
        PATHS "${GAPIA_VITURE_SDK_DIR}/x86_64"
        NO_DEFAULT_PATH REQUIRED)
    target_compile_definitions(xr-workspace-pose-service PRIVATE XR_WORKSPACE_HAVE_VITURE=1)
    target_include_directories(xr-workspace-pose-service SYSTEM PRIVATE "${VITURE_INCLUDE_DIR}")
    target_link_libraries(xr-workspace-pose-service PRIVATE "${VITURE_GLASSES_LIBRARY}")
    set_target_properties(xr-workspace-pose-service PROPERTIES
        BUILD_RPATH "${GAPIA_VITURE_SDK_DIR}/x86_64")

    add_executable(xr-workspace-native-display
        src/viture_native_display.cpp)
    target_include_directories(xr-workspace-native-display SYSTEM PRIVATE
        "${VITURE_INCLUDE_DIR}")
    target_link_libraries(xr-workspace-native-display PRIVATE
        "${VITURE_GLASSES_LIBRARY}")
    target_compile_features(xr-workspace-native-display PRIVATE cxx_std_20)
    target_compile_options(xr-workspace-native-display PRIVATE
        -Wall -Wextra -Wpedantic -Werror)
    set_target_properties(xr-workspace-native-display PROPERTIES
        OUTPUT_NAME "gapia-native-display"
        BUILD_RPATH "${GAPIA_VITURE_SDK_DIR}/x86_64"
        INSTALL_RPATH "$ORIGIN/../lib/gapia")
    install(TARGETS xr-workspace-native-display
        RUNTIME DESTINATION libexec
        COMPONENT native-display)
endif()

add_executable(xr-workspace-pose-dump src/pose_dump.cpp)
target_link_libraries(xr-workspace-pose-dump PRIVATE xr-workspace-pose-core)
target_include_directories(xr-workspace-pose-dump PRIVATE src)
target_compile_options(xr-workspace-pose-dump PRIVATE -Wall -Wextra -Wpedantic -Werror)

include(CTest)
if(BUILD_TESTING)
    add_executable(pose-frame-test tests/pose_frame_test.cpp)
    target_link_libraries(pose-frame-test PRIVATE xr-workspace-pose-core)
    target_include_directories(pose-frame-test PRIVATE src)
    target_compile_options(pose-frame-test PRIVATE -Wall -Wextra -Wpedantic -Werror)
    add_test(NAME pose-frame COMMAND pose-frame-test)

    find_program(GJS_EXECUTABLE gjs)
    if(GJS_EXECUTABLE)
        add_test(NAME gjs-pose-reader
            COMMAND "${GJS_EXECUTABLE}" -m "${CMAKE_SOURCE_DIR}/tests/pose_reader_test.js")
    endif()

    find_program(PYTHON3_EXECUTABLE python3)
    if(PYTHON3_EXECUTABLE)
        add_test(NAME python-native-display-config
            COMMAND "${PYTHON3_EXECUTABLE}"
                    "${CMAKE_SOURCE_DIR}/tests/native_display_config_test.py")
        add_test(NAME python-gnome-display-policy
            COMMAND "${PYTHON3_EXECUTABLE}"
                    "${CMAKE_SOURCE_DIR}/tests/gnome_display_policy_test.py")
    endif()

    find_program(SH_EXECUTABLE sh)
    if(SH_EXECUTABLE)
        add_test(NAME shell-setup-host-public-command
            COMMAND "${CMAKE_COMMAND}" -E env
                    GAPIA_SETUP_COMMAND=gapia-desktop-setup-host
                    GAPIA_SETUP_ELEVATES=1
                    "${SH_EXECUTABLE}"
                    "${CMAKE_SOURCE_DIR}/scripts/setup-host.sh" --help)
        set_tests_properties(shell-setup-host-public-command PROPERTIES
            PASS_REGULAR_EXPRESSION
                "Usage: gapia-desktop-setup-host \\[--sdk-dir PATH\\]")
    endif()
endif()

find_program(GNOME_EXTENSIONS_EXECUTABLE gnome-extensions)
if(GNOME_EXTENSIONS_EXECUTABLE)
    set(XR_WORKSPACE_EXTENSION_UUID "gapia@desktop.local")
    set(XR_WORKSPACE_EXTENSION_SOURCE
        "${CMAKE_SOURCE_DIR}/gnome-extension/${XR_WORKSPACE_EXTENSION_UUID}")
    set(XR_WORKSPACE_EXTENSION_OUTPUT
        "${CMAKE_BINARY_DIR}/extension/${XR_WORKSPACE_EXTENSION_UUID}.shell-extension.zip")
    add_custom_target(extension-package
        COMMAND "${CMAKE_COMMAND}" -E make_directory "${CMAKE_BINARY_DIR}/extension"
        COMMAND "${GNOME_EXTENSIONS_EXECUTABLE}" pack --force
                --out-dir "${CMAKE_BINARY_DIR}/extension"
                --extra-source=gapia-symbolic.svg
                "${XR_WORKSPACE_EXTENSION_SOURCE}"
        BYPRODUCTS "${XR_WORKSPACE_EXTENSION_OUTPUT}"
        COMMENT "Packaging the GNOME Shell extension"
        VERBATIM)
endif()
