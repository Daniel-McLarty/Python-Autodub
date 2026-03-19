FFmpeg Build Information for AI Auto-Dubbing Studio
===================================================

This binary was compiled to provide a minimal, high-performance toolset 
specifically for audio processing and stream copying within the 
AI Auto-Dubbing Studio project.

Version: n8.0
License: LGPL v2.1
Compiler: gcc 15.2.0 (Rev8, Built by MSYS2 project)

Configuration Flags:
--------------------
configuration: --prefix=./build --arch=x86_64 --target-os=mingw32 --cc=gcc --pkg-config-flags=--static --extra-ldflags=-static --enable-static --disable-shared --disable-all --enable-ffmpeg --enable-avcodec --enable-avformat --enable-avfilter --enable-swresample --enable-protocol=file --enable-filter='loudnorm,aresample,amix,volume,pan,atempo' --enable-demuxer='mov,matroska,wav,aac,mp3,flac,srt' --enable-muxer='matroska,mov,mp4,wav,flac' --enable-decoder='aac,mp3,pcm_s16le,h264,hevc,vp9,flac,srt' --enable-encoder='pcm_s16le,aac,flac,srt' --disable-debug --disable-doc --disable-gpl --disable-nonfree --disable-network

Build Notes:
------------
This build was generated using the standard FFmpeg source code without 
modification. It was configured with --disable-gpl and --disable-nonfree 
to ensure strict LGPL v2.1 compliance for redistribution.

For the full original source code, visit: https://ffmpeg.org/download.html