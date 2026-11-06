package com.datavox.speechtest;

import android.app.Activity;
import android.app.ActivityManager;
import android.content.Intent;
import android.content.IntentFilter;
import android.graphics.Color;
import android.graphics.Typeface;
import android.os.BatteryManager;
import android.os.Build;
import android.os.Bundle;
import android.view.View;
import android.view.WindowManager;
import android.widget.Button;
import android.widget.LinearLayout;
import android.widget.ScrollView;
import android.widget.TextView;

import java.io.BufferedReader;
import java.io.ByteArrayOutputStream;
import java.io.FileReader;
import java.io.InputStream;
import java.nio.ByteBuffer;
import java.nio.ByteOrder;
import java.nio.charset.StandardCharsets;
import java.util.Locale;

/**
 * آزمایش سرعت تبدیل گفتار روی گوشی: ۶ ویس نمونه با مدل کوچک و مدل اصلی،
 * با همان تنظیمات برنامه رومیزی DataVox.
 */
public class MainActivity extends Activity {
    // همان متن راهنمای برنامه رومیزی (voice2excel/config.py)
    static final String PROMPT = "سلام، مهندس، شماره تماس، آدرس خیابان، کوچه، پلاک، قطعه دوم، نبش، سازه فلز، سازه بتن، "
            + "تعداد سقف، سقف‌ها اجرا شده، تازه استارت خورده، دیوارچینی، زنگ بزنین.";
    static final String[] SAMPLES = {"sample-01", "sample-02", "sample-03", "sample-04", "sample-05", "sample-06"};
    static final int BEAM = 2;

    private TextView status;
    private TextView log;
    private Button start;
    private Button share;
    private final StringBuilder report = new StringBuilder();
    private volatile boolean running;

    @Override
    protected void onCreate(Bundle b) {
        super.onCreate(b);
        getWindow().addFlags(WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON);

        LinearLayout root = new LinearLayout(this);
        root.setOrientation(LinearLayout.VERTICAL);
        root.setLayoutDirection(View.LAYOUT_DIRECTION_RTL);
        int pad = dp(16);
        root.setPadding(pad, pad, pad, pad);
        root.setBackgroundColor(Color.WHITE);

        TextView title = new TextView(this);
        title.setText("آزمایش سرعت تبدیل گفتار DataVox");
        title.setTextSize(20);
        title.setTypeface(Typeface.DEFAULT_BOLD);
        title.setTextColor(Color.rgb(20, 30, 60));
        root.addView(title);

        TextView hint = new TextView(this);
        hint.setText("این برنامه ۶ ویس نمونه را روی همین گوشی به متن تبدیل می‌کند و زمان هر کدام را اندازه می‌گیرد. "
                + "اینترنت لازم نیست.\n\n"
                + "• پیش از شروع، گوشی را به شارژر وصل کنید.\n"
                + "• تا پایان آزمایش (حدود ۱۵ تا ۳۰ دقیقه) برنامه را باز نگه دارید و به برنامه دیگری نروید.\n"
                + "• در پایان «ارسال نتیجه» را بزنید و متن را در تلگرام یا واتس‌اپ بفرستید.");
        hint.setTextSize(15);
        hint.setTextColor(Color.rgb(60, 60, 60));
        hint.setPadding(0, dp(8), 0, dp(12));
        root.addView(hint);

        start = new Button(this);
        start.setText("شروع آزمایش");
        start.setTextSize(17);
        start.setOnClickListener(v -> startTest());
        root.addView(start);

        share = new Button(this);
        share.setText("ارسال نتیجه");
        share.setTextSize(17);
        share.setEnabled(false);
        share.setOnClickListener(v -> shareReport());
        root.addView(share);

        status = new TextView(this);
        status.setTextSize(16);
        status.setTypeface(Typeface.DEFAULT_BOLD);
        status.setTextColor(Color.rgb(0, 90, 160));
        status.setPadding(0, dp(12), 0, dp(8));
        status.setText("آماده");
        root.addView(status);

        log = new TextView(this);
        log.setTextSize(13);
        log.setTextColor(Color.BLACK);
        log.setTextIsSelectable(true);
        root.addView(log);

        ScrollView sv = new ScrollView(this);
        sv.addView(root);
        setContentView(sv);

        line(deviceInfo());
    }

    private int dp(int v) {
        return Math.round(v * getResources().getDisplayMetrics().density);
    }

    private void line(String s) {
        report.append(s).append('\n');
        runOnUiThread(() -> log.setText(report.toString()));
    }

    private void setStatus(String s) {
        runOnUiThread(() -> status.setText(s));
    }

    private String deviceInfo() {
        StringBuilder sb = new StringBuilder();
        sb.append("گوشی: ").append(Build.MANUFACTURER).append(' ').append(Build.MODEL)
                .append(" | اندروید ").append(Build.VERSION.RELEASE).append('\n');
        String hw = "";
        try (BufferedReader r = new BufferedReader(new FileReader("/proc/cpuinfo"))) {
            String l;
            while ((l = r.readLine()) != null) if (l.startsWith("Hardware")) hw = l.substring(l.indexOf(':') + 1).trim();
        } catch (Exception ignored) {
        }
        sb.append("پردازنده: ").append(hw.isEmpty() ? Build.HARDWARE : hw)
                .append(" | هسته‌ها: ").append(Runtime.getRuntime().availableProcessors()).append('\n');
        ActivityManager.MemoryInfo mi = new ActivityManager.MemoryInfo();
        ((ActivityManager) getSystemService(ACTIVITY_SERVICE)).getMemoryInfo(mi);
        sb.append(String.format(Locale.US, "رم: %.1f GB (آزاد %.1f GB)\n", mi.totalMem / 1e9, mi.availMem / 1e9));
        sb.append(battery());
        return sb.toString();
    }

    private String battery() {
        Intent bi = registerReceiver(null, new IntentFilter(Intent.ACTION_BATTERY_CHANGED));
        if (bi == null) return "";
        int temp = bi.getIntExtra(BatteryManager.EXTRA_TEMPERATURE, 0);
        int plugged = bi.getIntExtra(BatteryManager.EXTRA_PLUGGED, 0);
        int level = bi.getIntExtra(BatteryManager.EXTRA_LEVEL, -1);
        return String.format(Locale.US, "باتری: %d%% | دما %.1f°C | %s", level, temp / 10.0,
                plugged != 0 ? "به شارژ وصل" : "به شارژ وصل نیست");
    }

    private void startTest() {
        if (running) return;
        running = true;
        start.setEnabled(false);
        share.setEnabled(false);
        new Thread(this::runAll, "speechtest").start();
    }

    private void runAll() {
        try {
            line("");
            line("موتور: " + Whisper.systemInfo());
            int big = Math.min(4, Runtime.getRuntime().availableProcessors());
            // ۱) مدل اصلی (q8_0، هم‌دقت با برنامه رومیزی) روی ۶ ویس
            runModel("مدل اصلی q8", "models/turbo-q8.bin", new int[]{big}, SAMPLES);
            // ۲) همان مدل با تعداد هسته‌های دیگر روی یک ویس، برای پیدا کردن بهترین تنظیم
            runModel("مدل اصلی q8، تعداد هسته‌های دیگر", "models/turbo-q8.bin", new int[]{2, 6, 8},
                    new String[]{"sample-01"});
            // ۳) نسخه فشرده‌تر همان مدل (q5) روی ۲ ویس، برای مقایسه سرعت
            runModel("مدل اصلی q5", "models/turbo-q5.bin", new int[]{big}, new String[]{"sample-01", "sample-02"});
            line("");
            line("پایان. " + battery());
            setStatus("آزمایش تمام شد. «ارسال نتیجه» را بزنید.");
        } catch (Throwable t) {
            line("خطا: " + t);
            setStatus("خطا رخ داد. «ارسال نتیجه» را بزنید.");
        } finally {
            running = false;
            runOnUiThread(() -> {
                start.setEnabled(true);
                share.setEnabled(true);
            });
        }
    }

    private void runModel(String name, String asset, int[] threadsList, String[] samples) throws Exception {
        line("");
        line("=== " + name + " ===");
        setStatus("بارگذاری " + name + " ...");
        long t0 = System.nanoTime();
        long ctx = Whisper.initFromAsset(getAssets(), asset);
        if (ctx == 0) {
            line("بارگذاری مدل ناموفق بود.");
            return;
        }
        line(String.format(Locale.US, "بارگذاری مدل: %.1f ثانیه", (System.nanoTime() - t0) / 1e9));
        try {
            for (int threads : threadsList) {
                double sumAudio = 0, sumTime = 0;
                for (int i = 0; i < samples.length; i++) {
                    float[] audio = readWav("samples/" + samples[i] + ".wav");
                    double dur = audio.length / 16000.0;
                    setStatus(String.format(Locale.US, "%s — ویس %d از %d (%d هسته)", name, i + 1, samples.length, threads));
                    long s = System.nanoTime();
                    byte[] out = Whisper.transcribe(ctx, audio, threads, BEAM, PROMPT);
                    double el = (System.nanoTime() - s) / 1e9;
                    sumAudio += dur;
                    sumTime += el;
                    String text = out == null ? "(خطا در تبدیل)" : new String(out, StandardCharsets.UTF_8).trim();
                    line(String.format(Locale.US, "%s | %d هسته | ویس %.1f ث ← %.1f ث (×%.2f)", samples[i], threads, dur, el, el / dur));
                    line("   " + text);
                }
                line(String.format(Locale.US, "جمع %d هسته: ویس %.0f ث ← %.0f ث | هر دقیقه ویس ≈ %.0f ثانیه",
                        threads, sumAudio, sumTime, 60 * sumTime / sumAudio));
            }
        } finally {
            Whisper.free(ctx);
        }
        line(battery());
    }

    private float[] readWav(String asset) throws Exception {
        ByteArrayOutputStream bo = new ByteArrayOutputStream();
        try (InputStream in = getAssets().open(asset)) {
            byte[] buf = new byte[65536];
            int n;
            while ((n = in.read(buf)) > 0) bo.write(buf, 0, n);
        }
        ByteBuffer bb = ByteBuffer.wrap(bo.toByteArray()).order(ByteOrder.LITTLE_ENDIAN);
        // پیدا کردن تکه data در فایل WAV (۱۶ کیلوهرتز، تک‌کاناله، ۱۶ بیتی)
        int pos = 12;
        while (pos + 8 <= bb.limit()) {
            int id = bb.getInt(pos);
            int size = bb.getInt(pos + 4);
            if (id == 0x61746164) { // "data"
                int count = Math.min(size, bb.limit() - pos - 8) / 2;
                float[] f = new float[count];
                for (int i = 0; i < count; i++) f[i] = bb.getShort(pos + 8 + 2 * i) / 32768f;
                return f;
            }
            pos += 8 + size + (size & 1);
        }
        throw new IllegalStateException("WAV بدون data: " + asset);
    }

    private void shareReport() {
        Intent i = new Intent(Intent.ACTION_SEND);
        i.setType("text/plain");
        i.putExtra(Intent.EXTRA_TEXT, report.toString());
        startActivity(Intent.createChooser(i, "ارسال نتیجه"));
    }
}
