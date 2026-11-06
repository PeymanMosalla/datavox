cmake_minimum_required(VERSION 3.16)
project(dvwhisper C CXX)

# whisper.cpp (کد منبع بیرون از مخزن؛ مسیرش را scripts/build_engine_oldcpu.py می‌دهد) به‌صورت ایستا درون یک DLL
set(BUILD_SHARED_LIBS OFF CACHE BOOL "" FORCE)
set(WHISPER_BUILD_TESTS OFF CACHE BOOL "" FORCE)
set(WHISPER_BUILD_EXAMPLES OFF CACHE BOOL "" FORCE)
set(WHISPER_BUILD_SERVER OFF CACHE BOOL "" FORCE)
set(WHISPER_ALL_WARNINGS OFF CACHE BOOL "" FORCE)
add_subdirectory(${WHISPER_SRC} whisper EXCLUDE_FROM_ALL)

add_library(dvwhisper SHARED dv_api.c)
target_link_libraries(dvwhisper PRIVATE whisper)
target_link_options(dvwhisper PRIVATE -static -Wl,--gc-sections)
