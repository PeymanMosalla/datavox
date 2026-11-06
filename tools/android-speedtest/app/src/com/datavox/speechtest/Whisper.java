package com.datavox.speechtest;

import android.content.res.AssetManager;

/** پل به موتور گفتار whisper.cpp (کتابخانه libdvwhisper.so). */
final class Whisper {
    static {
        System.loadLibrary("dvwhisper");
    }

    private Whisper() {}

    static native long initFromAsset(AssetManager am, String path);

    static native void free(long ctx);

    static native String systemInfo();

    /** متن به‌صورت بایت UTF-8؛ null یعنی خطا. */
    static native byte[] transcribe(long ctx, float[] audio, int threads, int beam, String prompt);
}
