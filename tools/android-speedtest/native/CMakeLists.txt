cmake_minimum_required(VERSION 3.16)
project(dvwhisper C CXX)

# موتور گفتار whisper.cpp به‌صورت ایستا درون یک کتابخانه مشترک برای اندروید
set(WHISPER_DIR ${CMAKE_CURRENT_SOURCE_DIR}/../third_party/whisper.cpp-1.9.5)
set(BUILD_SHARED_LIBS OFF CACHE BOOL "" FORCE)
set(WHISPER_BUILD_TESTS OFF CACHE BOOL "" FORCE)
set(WHISPER_BUILD_EXAMPLES OFF CACHE BOOL "" FORCE)
set(WHISPER_BUILD_SERVER OFF CACHE BOOL "" FORCE)
set(WHISPER_ALL_WARNINGS OFF CACHE BOOL "" FORCE)
set(GGML_NATIVE OFF CACHE BOOL "" FORCE)
set(GGML_OPENMP OFF CACHE BOOL "" FORCE)
add_subdirectory(${WHISPER_DIR} whisper EXCLUDE_FROM_ALL)

add_library(dvwhisper SHARED dv_jni.c)
target_link_libraries(dvwhisper PRIVATE whisper log android)
target_compile_options(dvwhisper PRIVATE -O3)
target_link_options(dvwhisper PRIVATE -Wl,--gc-sections -Wl,--exclude-libs,ALL)
