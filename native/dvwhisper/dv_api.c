// موتور گفتار رایانه‌های قدیمی (نسخه oldcpu): رابط ساده C روی whisper.cpp برای ctypes
//
// - مسیر مدل UTF-8 است و با _wfopen باز می‌شود (پوشه با نام فارسی هم کار می‌کند)
// - خروجی JSON است؛ متن‌ها به‌صورت hex بایت‌های UTF-8 تا بایت‌های ناقص یک نشانه JSON را خراب نکنند
// - *abort_flag غیرصفر شود، پردازش در اولین فرصت متوقف می‌شود
#include <stdbool.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <windows.h>
#include "whisper.h"

#define API __declspec(dllexport)

static size_t f_read(void *ctx, void *out, size_t n) { return fread(out, 1, n, (FILE *) ctx); }
static bool f_eof(void *ctx) { return feof((FILE *) ctx) != 0; }
static void f_close(void *ctx) { fclose((FILE *) ctx); }

API void *dvw_init(const char *model_path_utf8) {
    wchar_t wpath[1024];
    if (!MultiByteToWideChar(CP_UTF8, 0, model_path_utf8, -1, wpath, 1024)) return NULL;
    FILE *f = _wfopen(wpath, L"rb");
    if (!f) return NULL;
    struct whisper_model_loader loader = {.context = f, .read = f_read, .eof = f_eof, .close = f_close};
    struct whisper_context_params cp = whisper_context_default_params();
    cp.use_gpu = false;
    cp.flash_attn = true;
    return whisper_init_with_params(&loader, cp);
}

API void dvw_free(void *ctx) {
    if (ctx) whisper_free((struct whisper_context *) ctx);
}

API const char *dvw_system_info(void) { return whisper_print_system_info(); }

API void dvw_free_str(char *s) { free(s); }

typedef struct { char *buf; size_t len, cap; } sbuf;

static void put(sbuf *b, const char *s, size_t n) {
    if (b->len + n + 1 > b->cap) {
        while (b->len + n + 1 > b->cap) b->cap = b->cap ? b->cap * 2 : 4096;
        b->buf = realloc(b->buf, b->cap);
    }
    memcpy(b->buf + b->len, s, n);
    b->len += n;
    b->buf[b->len] = 0;
}

static void puts_(sbuf *b, const char *s) { put(b, s, strlen(s)); }

static void put_hex(sbuf *b, const char *s) {
    static const char hx[] = "0123456789abcdef";
    put(b, "\"", 1);
    for (const unsigned char *p = (const unsigned char *) s; *p; p++) {
        char two[2] = {hx[*p >> 4], hx[*p & 15]};
        put(b, two, 2);
    }
    put(b, "\"", 1);
}

static bool on_abort(void *user) { return user && *(volatile int *) user != 0; }

static bool on_encoder_begin(struct whisper_context *ctx, struct whisper_state *st, void *user) {
    (void) ctx; (void) st;
    return !on_abort(user);
}

API char *dvw_transcribe(void *vctx, const float *pcm, int n, int threads, int beam, const char *lang,
                         const char *prompt, volatile int *abort_flag) {
    struct whisper_context *ctx = (struct whisper_context *) vctx;
    if (!ctx) return NULL;
    struct whisper_full_params p = whisper_full_default_params(
        beam > 1 ? WHISPER_SAMPLING_BEAM_SEARCH : WHISPER_SAMPLING_GREEDY);
    p.n_threads = threads;
    p.language = (lang && lang[0]) ? lang : "fa";
    p.translate = false;
    p.no_context = true;
    p.token_timestamps = true;
    p.print_progress = false;
    p.print_realtime = false;
    p.print_timestamps = false;
    p.print_special = false;
    p.beam_search.beam_size = beam;
    p.initial_prompt = (prompt && prompt[0]) ? prompt : NULL;
    p.abort_callback = on_abort;
    p.abort_callback_user_data = (void *) abort_flag;
    p.encoder_begin_callback = on_encoder_begin;
    p.encoder_begin_callback_user_data = (void *) abort_flag;

    int rc = whisper_full(ctx, p, pcm, n);
    sbuf b = {0};
    char num[96];
    if (rc != 0 || (abort_flag && *abort_flag)) {
        snprintf(num, sizeof num, "{\"error\":%d,\"aborted\":%d}", rc, abort_flag ? *abort_flag : 0);
        puts_(&b, num);
        return b.buf;
    }
    whisper_token eot = whisper_token_eot(ctx);
    puts_(&b, "{\"segments\":[");
    int ns = whisper_full_n_segments(ctx);
    for (int i = 0; i < ns; i++) {
        if (i) puts_(&b, ",");
        snprintf(num, sizeof num, "{\"t0\":%lld,\"t1\":%lld,\"nsp\":%.4f,\"text\":",
                 (long long) whisper_full_get_segment_t0(ctx, i), (long long) whisper_full_get_segment_t1(ctx, i),
                 whisper_full_get_segment_no_speech_prob(ctx, i));
        puts_(&b, num);
        put_hex(&b, whisper_full_get_segment_text(ctx, i));
        puts_(&b, ",\"tokens\":[");
        int nt = whisper_full_n_tokens(ctx, i), first = 1;
        for (int j = 0; j < nt; j++) {
            whisper_token_data td = whisper_full_get_token_data(ctx, i, j);
            if (td.id >= eot) continue;  // نشانه‌های ویژه (زمان، زبان، پایان)
            if (!first) puts_(&b, ",");
            first = 0;
            snprintf(num, sizeof num, "{\"t0\":%lld,\"t1\":%lld,\"p\":%.4f,\"plog\":%.4f,\"h\":",
                     (long long) td.t0, (long long) td.t1, td.p, td.plog);
            puts_(&b, num);
            put_hex(&b, whisper_full_get_token_text(ctx, i, j));
            puts_(&b, "}");
        }
        puts_(&b, "]}");
    }
    puts_(&b, "]}");
    return b.buf;
}
