// پل JNI میان برنامه اندروید و whisper.cpp — برنامه آزمایش سرعت DataVox
#include <jni.h>
#include <android/asset_manager.h>
#include <android/asset_manager_jni.h>
#include <android/log.h>
#include <stdlib.h>
#include <string.h>
#include "whisper.h"

#define TAG "dvwhisper"
#define LOGI(...) __android_log_print(ANDROID_LOG_INFO, TAG, __VA_ARGS__)

static size_t asset_read(void *ctx, void *out, size_t n) { return AAsset_read((AAsset *) ctx, out, n); }
static bool asset_eof(void *ctx) { return AAsset_getRemainingLength64((AAsset *) ctx) <= 0; }
static void asset_close(void *ctx) { AAsset_close((AAsset *) ctx); }

JNIEXPORT jlong JNICALL
Java_com_datavox_speechtest_Whisper_initFromAsset(JNIEnv *env, jclass cls, jobject am, jstring jpath) {
    (void) cls;
    const char *path = (*env)->GetStringUTFChars(env, jpath, NULL);
    AAssetManager *mgr = AAssetManager_fromJava(env, am);
    AAsset *asset = AAssetManager_open(mgr, path, AASSET_MODE_STREAMING);
    (*env)->ReleaseStringUTFChars(env, jpath, path);
    if (!asset) return 0;
    struct whisper_model_loader loader = {
        .context = asset, .read = asset_read, .eof = asset_eof, .close = asset_close,
    };
    struct whisper_context_params cp = whisper_context_default_params();
    cp.use_gpu = false;
    cp.flash_attn = true;
    return (jlong) whisper_init_with_params(&loader, cp);
}

JNIEXPORT void JNICALL
Java_com_datavox_speechtest_Whisper_free(JNIEnv *env, jclass cls, jlong ctx) {
    (void) env; (void) cls;
    if (ctx) whisper_free((struct whisper_context *) ctx);
}

JNIEXPORT jstring JNICALL
Java_com_datavox_speechtest_Whisper_systemInfo(JNIEnv *env, jclass cls) {
    (void) cls;
    return (*env)->NewStringUTF(env, whisper_print_system_info());
}

// همان تنظیمات برنامه رومیزی: زبان فارسی، جست‌وجوی پرتوی با پهنای beam، متن راهنما، بدون شرطی شدن روی متن قبلی
// خروجی به‌صورت بایت UTF-8 برمی‌گردد تا بایت ناقص احتمالی برنامه را از کار نیندازد
JNIEXPORT jbyteArray JNICALL
Java_com_datavox_speechtest_Whisper_transcribe(JNIEnv *env, jclass cls, jlong jctx, jfloatArray jaudio,
                                               jint threads, jint beam, jstring jprompt) {
    (void) cls;
    struct whisper_context *ctx = (struct whisper_context *) jctx;
    if (!ctx) return NULL;
    jfloat *audio = (*env)->GetFloatArrayElements(env, jaudio, NULL);
    jsize n = (*env)->GetArrayLength(env, jaudio);
    const char *prompt = jprompt ? (*env)->GetStringUTFChars(env, jprompt, NULL) : NULL;

    struct whisper_full_params p = whisper_full_default_params(
        beam > 1 ? WHISPER_SAMPLING_BEAM_SEARCH : WHISPER_SAMPLING_GREEDY);
    p.n_threads = threads;
    p.language = "fa";
    p.translate = false;
    p.no_context = true;
    p.token_timestamps = true;
    p.print_progress = false;
    p.print_realtime = false;
    p.print_timestamps = false;
    p.print_special = false;
    p.beam_search.beam_size = beam;
    p.initial_prompt = (prompt && prompt[0]) ? prompt : NULL;

    whisper_reset_timings(ctx);
    int rc = whisper_full(ctx, p, audio, n);

    jbyteArray result = NULL;
    if (rc == 0) {
        int ns = whisper_full_n_segments(ctx);
        size_t cap = 256, len = 0;
        char *buf = malloc(cap);
        buf[0] = 0;
        for (int i = 0; i < ns; i++) {
            const char *t = whisper_full_get_segment_text(ctx, i);
            size_t tl = strlen(t);
            while (len + tl + 2 > cap) { cap *= 2; buf = realloc(buf, cap); }
            memcpy(buf + len, t, tl);
            len += tl;
            buf[len] = 0;
        }
        result = (*env)->NewByteArray(env, (jsize) len);
        (*env)->SetByteArrayRegion(env, result, 0, (jsize) len, (const jbyte *) buf);
        free(buf);
    }
    if (prompt) (*env)->ReleaseStringUTFChars(env, jprompt, prompt);
    (*env)->ReleaseFloatArrayElements(env, jaudio, audio, JNI_ABORT);
    return result;
}
