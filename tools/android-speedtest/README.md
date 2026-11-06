# آزمایش سرعت تبدیل گفتار روی گوشی اندروید (DataVox-SpeechTest)

یک برنامه کوچک اندروید که ۶ ویس نمونه را با whisper.cpp به متن تبدیل می‌کند. برای هر ویس زمان و متن را نشان می‌دهد. دکمه «ارسال نتیجه» هم دارد.

این برنامه برای این ساخته شد که ببینیم گوشی مشتری نسخه oldcpu می‌تواند کار تبدیل گفتار را انجام دهد یا نه. گوشی آزمایش‌شده Redmi Note 10 Pro است، با پردازنده Snapdragon 732G. فایل نصب در GitHub Release به نام `android-speedtest-v0.1` است.

## محل ساخت و ابزارها
این پوشه فقط کد منبع است. ساخت در پوشه `Desktop\New folder\datavox-android` انجام شد و ابزارهای ساخت کنار آن بودند. این ابزارها در مخزن نیستند:
- `sdk/`: build-tools 34 و android-34 از آینه Tencent، چون گوگل از ایران مسدود است.
- `ndk/`: NDK r28c.
- `third_party/`: whisper.cpp 1.9.5.
- `cache/`: مدل‌های ggml از Hugging Face.
- `pcenv`: محیط Python با cmake، ninja و pywhispercpp.

APK بدون Gradle ساخته می‌شود:

    pcenv\Scripts\python.exe build_apk.py --native

## اسکریپت‌های کنار برنامه
- `pc_compare.py`: مقایسه دقت ggml با موتور اصلی روی رایانه.
- `bench_old_cpu.py` و `build_win_old.py`: سنجش سرعت موتور ساخته‌شده برای Core 2.
- `cf_test.py`: آزمایش Cloudflare Workers AI. شناسه حساب و کلید را از `..\cloudflare.txt` می‌خواند. اگر `CF_BIND=<IP کارت شبکه>` تنظیم شود، درخواست بیرون از VPN و با IP ایران فرستاده می‌شود.

کلید امضای APK در پوشه ساخت است و در مخزن نیست.
