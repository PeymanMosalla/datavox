// DataVox.exe: اجراکننده نسخه قابل‌حمل.
// - صفحه شروع طراحی‌شده (لوگو، نسخه، نوار پیشرفت) تا موتور برنامه آماده شود.
// - برنامه در پنجره اختصاصی خودش (WebView2، بدون قاب ویندوز، با نوار عنوان طراحی‌شده در خود صفحه) باز می‌شود؛
//   اگر WebView2 روی رایانه نباشد (یا ویندوز ۷ باشد)، در پنجره «برنامه»ی Edge/Chrome و در نبودشان در مرورگر پیش‌فرض.
// - به‌روزرسانی سبک: پیش از اجرا، یا با یک کلیک از داخل برنامه (موتور خاموش، نسخه جدید جایگزین، موتور روشن،
//   پنجره باز می‌ماند). اگر نسخه جدید بالا نیاید، خودکار نسخه قبلی برمی‌گردد.
// - اجرای دوباره میان‌بر، همان پنجره باز را جلو می‌آورد.
using System;
using System.Diagnostics;
using System.Drawing;
using System.Drawing.Drawing2D;
using System.Drawing.Text;
using System.IO;
using System.Net;
using System.Runtime.InteropServices;
using System.Text.RegularExpressions;
using System.Threading;
using System.Windows.Forms;
using Microsoft.Web.WebView2.Core;
using Microsoft.Web.WebView2.WinForms;

static class Launcher
{
    public const string Url = "http://127.0.0.1:8765/";
    public const string Title = "DataVox";
    static readonly string[] RootExtras = { "Guide.html", "Recording-Guide.html" };

    public static string baseDir;
    public static Process engine;  // موتوری که همین اجراکننده روشن کرده (برای کد خروج)
    public static string dataDir;

    public static bool IsUp()
    {
        try
        {
            var req = (HttpWebRequest)WebRequest.Create(Url + "api/status");
            req.Timeout = 1500;
            req.Proxy = null;
            using (var resp = (HttpWebResponse)req.GetResponse())
                return resp.StatusCode == HttpStatusCode.OK;
        }
        catch { return false; }
    }

    static bool CanWrite(string dir)
    {
        try
        {
            Directory.CreateDirectory(dir);
            string probe = Path.Combine(dir, ".write_test");
            File.WriteAllText(probe, "ok");
            File.Delete(probe);
            return true;
        }
        catch { return false; }
    }

    public static void OpenExternal(string url)
    {
        try { Process.Start(url); } catch { }
    }

    // ویندوز ۷ و قدیمی‌تر: WebView2 آنجا دیگر پشتیبانی نمی‌شود؛ پنجره برنامه با Edge/Chrome ساخته می‌شود
    public static bool LegacyWindows()
    {
        var v = Environment.OSVersion.Version;
        return v.Major < 6 || (v.Major == 6 && v.Minor < 2);
    }

    // پیش‌نیازهای ویندوز ۷ (پوشه Windows7 بسته): KB3063858 برای بارگذاری DLLها و Universal CRT
    public static string MissingWin7Prerequisites()
    {
        if (!LegacyWindows()) return null;
        var missing = new System.Collections.Generic.List<string>();
        if (Native.GetProcAddress(Native.GetModuleHandle("kernel32.dll"), "AddDllDirectory") == IntPtr.Zero)
            missing.Add("به‌روزرسانی KB3063858 (یا KB2533623)");
        if (!File.Exists(Path.Combine(Environment.SystemDirectory, "ucrtbase.dll")))
            missing.Add("به‌روزرسانی KB2999226 (Universal C Runtime)");
        return missing.Count == 0 ? null : string.Join("\n• ", missing.ToArray());
    }

    static string FindBrowser(params string[] exes)
    {
        foreach (string exe in exes)
            foreach (var hive in new[] { Microsoft.Win32.Registry.CurrentUser, Microsoft.Win32.Registry.LocalMachine })
            {
                try
                {
                    using (var k = hive.OpenSubKey(@"SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths\" + exe))
                    {
                        string path = k == null ? null : k.GetValue("") as string;
                        if (!string.IsNullOrEmpty(path) && File.Exists(path.Trim('"'))) return path.Trim('"');
                    }
                }
                catch { }
            }
        return null;
    }

    // بدون WebView2: پنجره جدا و بدون نوار نشانی (حالت app در Edge/Chrome)؛ در نبودشان مرورگر پیش‌فرض
    public static void OpenAppWindow(string url)
    {
        if (TestMode()) { Log("test: browser window for " + url); return; }
        string browser = FindBrowser("msedge.exe", "chrome.exe");
        if (browser != null)
        {
            try
            {
                string profile = Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData), "Voice2Excel", "Browser");
                Process.Start(new ProcessStartInfo(browser, "--app=\"" + url + "\" --user-data-dir=\"" + profile +
                    "\" --no-first-run --no-default-browser-check --window-size=1280,820") { UseShellExecute = false });
                Log("opened app window: " + browser);
                return;
            }
            catch (Exception e) { Log("app window failed: " + e.Message); }
        }
        // Firefox (روی ویندوز ۷ نسخه ESR 115 همراه بسته است)؛ Internet Explorer صفحه برنامه را درست نشان نمی‌دهد
        string firefox = FindBrowser("firefox.exe");
        if (firefox != null)
        {
            try { Process.Start(new ProcessStartInfo(firefox, "-new-window \"" + url + "\"") { UseShellExecute = false }); return; }
            catch (Exception e) { Log("firefox failed: " + e.Message); }
        }
        OpenExternal(url);
    }

    public static void Log(string msg)
    {
        try
        {
            string dir = Path.Combine(dataDir ?? Path.Combine(baseDir, "data"), "logs");
            Directory.CreateDirectory(dir);
            File.AppendAllText(Path.Combine(dir, "launcher.log"), DateTime.Now.ToString("s") + " " + msg + Environment.NewLine);
        }
        catch { }
    }

    public static void ShowError(string msg)
    {
        MessageBox.Show(msg, Title, MessageBoxButtons.OK, MessageBoxIcon.Error, MessageBoxDefaultButton.Button1,
            MessageBoxOptions.RtlReading);
    }

    static void CreateDesktopShortcut(string exePath)
    {
        try
        {
            string desktop = Environment.GetFolderPath(Environment.SpecialFolder.DesktopDirectory);
            string lnk = Path.Combine(desktop, Title + ".lnk");
            RemoveLegacyShortcut(desktop);
            if (File.Exists(lnk)) return;
            // WScript.Shell نام فایل فارسی را ذخیره نمی‌کند: ابتدا با نام انگلیسی ساخته و سپس تغییر نام داده می‌شود
            string tmp = Path.Combine(desktop, "Voice2Excel-shortcut.lnk");
            Type t = Type.GetTypeFromProgID("WScript.Shell");
            dynamic shell = Activator.CreateInstance(t);
            dynamic sc = shell.CreateShortcut(tmp);
            sc.TargetPath = exePath;
            sc.WorkingDirectory = baseDir;
            sc.IconLocation = exePath + ",0";
            sc.Description = "DataVox";
            sc.Save();
            if (File.Exists(tmp)) File.Move(tmp, lnk);
        }
        catch (Exception e) { Log("shortcut: " + e.Message); }
    }

    /// <summary>میان‌بر نام قبلی برنامه («ثبت ویس») اگر به همین برنامه اشاره کند، برداشته می‌شود.</summary>
    static void RemoveLegacyShortcut(string desktop)
    {
        try
        {
            string old = Path.Combine(desktop, "ثبت ویس.lnk");
            if (!File.Exists(old)) return;
            // WScript.Shell فایل با نام فارسی را باز نمی‌کند؛ مسیر مقصد مستقیم از محتوای فایل میان‌بر خوانده می‌شود
            byte[] raw = File.ReadAllBytes(old);
            string text = (System.Text.Encoding.Default.GetString(raw) + System.Text.Encoding.Unicode.GetString(raw)).ToLowerInvariant();
            if (text.Contains("\\voice2excel.exe") || text.Contains("\\datavox.exe"))
                File.Delete(old);
        }
        catch (Exception e) { Log("legacy shortcut: " + e.Message); }
    }

    public static string Version()
    {
        try
        {
            string init = File.ReadAllText(Path.Combine(baseDir, "app", "voice2excel", "__init__.py"));
            var m = Regex.Match(init, "__version__\\s*=\\s*\"([^\"]+)\"");
            return m.Success ? m.Groups[1].Value : "";
        }
        catch { return ""; }
    }

    // ---------- به‌روزرسانی سبک ----------
    static string AppPkg { get { return Path.Combine(baseDir, "app", "voice2excel"); } }
    static string PrevPkg { get { return Path.Combine(baseDir, "app", "voice2excel.previous"); } }
    static string PrevRoot { get { return Path.Combine(baseDir, "app", "previous-root-files"); } }
    public static string StageDir { get { return Path.Combine(baseDir, "update-staged"); } }

    public static bool HasStagedUpdate()
    {
        return File.Exists(Path.Combine(StageDir, "manifest.json")) && Directory.Exists(Path.Combine(StageDir, "voice2excel"));
    }

    /// <summary>جایگزینی نسخه آماده؛ نسخه فعلی به‌عنوان «قبلی» نگه داشته می‌شود.</summary>
    public static bool ApplyStagedUpdate()
    {
        string stagedPkg = Path.Combine(StageDir, "voice2excel");
        if (!HasStagedUpdate()) return false;
        try
        {
            if (Directory.Exists(PrevPkg)) Directory.Delete(PrevPkg, true);
            if (Directory.Exists(PrevRoot)) Directory.Delete(PrevRoot, true);
            Directory.CreateDirectory(PrevRoot);
            Directory.Move(AppPkg, PrevPkg);
            Directory.Move(stagedPkg, AppPkg);
            foreach (string name in RootExtras)
            {
                string src = Path.Combine(StageDir, name), dst = Path.Combine(baseDir, name);
                if (!File.Exists(src)) continue;
                if (File.Exists(dst)) File.Copy(dst, Path.Combine(PrevRoot, name), true);
                File.Copy(src, dst, true);
            }
            Directory.Delete(StageDir, true);
            Log("update applied");
            return true;
        }
        catch (Exception e)
        {
            Log("update apply failed: " + e.Message);
            try { if (!Directory.Exists(AppPkg) && Directory.Exists(PrevPkg)) Directory.Move(PrevPkg, AppPkg); } catch { }
            return false;
        }
    }

    /// <summary>بازگرداندن نسخه قبلی پس از به‌روزرسانی ناموفق.</summary>
    public static bool RollbackUpdate()
    {
        try
        {
            if (!Directory.Exists(PrevPkg)) return false;
            if (Directory.Exists(AppPkg)) Directory.Delete(AppPkg, true);
            Directory.Move(PrevPkg, AppPkg);
            foreach (string name in RootExtras)
            {
                string src = Path.Combine(PrevRoot, name);
                if (File.Exists(src)) File.Copy(src, Path.Combine(baseDir, name), true);
            }
            Log("update rolled back");
            return true;
        }
        catch (Exception e) { Log("rollback failed: " + e.Message); return false; }
    }

    // ---------- اجرای موتور ----------
    public static Process StartApp()
    {
        var psi = new ProcessStartInfo(Path.Combine(baseDir, "python", "pythonw.exe"), "-m voice2excel --no-browser --auto-exit");
        psi.WorkingDirectory = Path.Combine(baseDir, "app");
        psi.UseShellExecute = false;
        psi.CreateNoWindow = true;
        psi.EnvironmentVariables["V2X_DATA_DIR"] = dataDir;
        psi.EnvironmentVariables["V2X_MODELS_DIR"] = Path.Combine(baseDir, "models");
        psi.EnvironmentVariables["V2X_SAMPLES_DIR"] = Path.Combine(baseDir, "samples");
        psi.EnvironmentVariables["V2X_LAUNCHER"] = "2";  // به‌روزرسانی یک‌کلیکی پشتیبانی می‌شود
        psi.EnvironmentVariables["HF_HUB_OFFLINE"] = "1";
        psi.EnvironmentVariables["HF_HUB_DISABLE_TELEMETRY"] = "1";
        psi.EnvironmentVariables["PYTHONIOENCODING"] = "utf-8";
        psi.EnvironmentVariables["PYTHONNOUSERSITE"] = "1";
        psi.EnvironmentVariables.Remove("PYTHONPATH");
        psi.EnvironmentVariables.Remove("PYTHONHOME");
        engine = Process.Start(psi);
        return engine;
    }

    /// <summary>منتظر آماده شدن موتور؛ رابط کاربری در این مدت زنده می‌ماند.</summary>
    public static bool WaitUntilUp(Process proc)
    {
        for (int i = 0; i < 240; i++)
        {
            Application.DoEvents();
            if (IsUp()) return true;
            if (proc != null && proc.HasExited) return false;
            for (int k = 0; k < 10; k++) { Thread.Sleep(25); Application.DoEvents(); }
        }
        return false;
    }

    /// <summary>اجرای موتور (با برگشت خودکار به نسخه قبلی اگر نسخه تازه بالا نیامد). null یعنی اجرا نشد.</summary>
    public static bool StartWithRollback(bool updated, Action<string> status)
    {
        Process proc = StartApp();
        if (WaitUntilUp(proc)) return true;
        if (!updated) return false;
        try { if (!proc.HasExited) proc.Kill(); } catch { }
        if (!RollbackUpdate()) return false;
        if (status != null) status("نسخه جدید اجرا نشد؛ بازگشت به نسخه قبلی…");
        if (!WaitUntilUp(StartApp())) return false;
        ShowError("نسخه جدید اجرا نشد و برنامه خودکار به نسخه قبلی برگشت. اطلاعات شما دست نخورده است.");
        return true;
    }

    // بدون پنجره اختصاصی (ویندوز ۷): اجراکننده پنهان می‌ماند تا مثل پنجره WebView2، به‌روزرسانی یک‌کلیکی را نصب و
    // موتور را دوباره روشن کند، اگر موتور ناخواسته بسته شد دوباره اجرایش کند، و با اجرای دوباره میان‌بر، پنجره برنامه را باز کند.
    // با «خروج از برنامه» یا بسته شدن خودکار پس از بستن مرورگر (کد خروج ۰) کارش تمام می‌شود.
    // آزمون خودکار روی رایانه سازنده: حالت ویندوز ۷ (بدون WebView2)، بی‌آنکه میان‌بر یا پنجره مرورگری ساخته شود
    static bool TestMode() { return Environment.GetEnvironmentVariable("V2X_TEST_BROWSER_MODE") == "1"; }

    static void WatchBrowserMode()
    {
        var show = new EventWaitHandle(false, EventResetMode.AutoReset, "Local\\Voice2Excel.Show");
        int down = 0, crashes = 0;
        while (true)
        {
            for (int k = 0; k < 40; k++)
            {
                if (show.WaitOne(50)) OpenAppWindow(Url);
                Application.DoEvents();
            }
            if (IsUp()) { down = 0; continue; }
            if (++down < 2) continue;
            down = 0;
            int code = -1;
            try { if (engine != null && engine.HasExited) code = engine.ExitCode; } catch { }
            string quit = Path.Combine(dataDir, ".quit");
            bool staged = HasStagedUpdate();
            if (!staged && (File.Exists(quit) || code == 0 || engine == null))
            {
                try { File.Delete(quit); } catch { }
                Log("engine closed (code " + code + "); launcher exits");
                return;
            }
            if (!staged && ++crashes > 3)
            {
                Log("engine keeps stopping; giving up");
                ShowError("موتور برنامه چند بار پشت سر هم بسته شد. برنامه را دوباره باز کنید.\nجزئیات: " +
                          Path.Combine(dataDir, "logs", "console.log"));
                return;
            }
            bool updated = staged && ApplyStagedUpdate();
            Log(updated ? "update applied; restarting engine" : "engine stopped unexpectedly (code " + code + "); restarting");
            if (!StartWithRollback(updated, null))
            {
                ShowError("موتور برنامه دوباره اجرا نشد. برنامه را ببندید و دوباره باز کنید.");
                return;
            }
        }
    }

    public static string WebViewVersion()
    {
        try { return CoreWebView2Environment.GetAvailableBrowserVersionString(); }
        catch { return null; }
    }

    [STAThread]
    static int Main()
    {
        baseDir = AppDomain.CurrentDomain.BaseDirectory.TrimEnd('\\');
        string exePath = Path.Combine(baseDir, "DataVox.exe");
        Native.EnableDpiAwareness();  // پیش از ساخت هر پنجره؛ وگرنه در نمایشگرهای ۱۲۵٪ و بیشتر، صفحه از پنجره بزرگ‌تر می‌شود
        Application.EnableVisualStyles();
        Application.SetCompatibleTextRenderingDefault(false);

        bool first;
        var mutex = new Mutex(true, "Local\\Voice2Excel.Window", out first);
        if (!first)
        {
            // پنجره باز است: همان جلو می‌آید
            try { EventWaitHandle.OpenExisting("Local\\Voice2Excel.Show").Set(); } catch { }
            return 0;
        }

        if (!File.Exists(Path.Combine(baseDir, "python", "pythonw.exe")))
        {
            ShowError("فایل‌های برنامه کامل نیستند (پوشه python پیدا نشد).\nلطفاً فایل zip را کامل از حالت فشرده خارج کنید و دوباره اجرا کنید.");
            return 1;
        }

        string prereq = MissingWin7Prerequisites();
        if (prereq != null)
        {
            ShowError("برای اجرای DataVox روی ویندوز ۷ این پیش‌نیازها هنوز نصب نشده‌اند:\n• " + prereq +
                "\n\nدر پوشه برنامه، داخل پوشه Windows7 روی فایل Install-Prerequisites.bat دوبار کلیک کنید، " +
                "پس از پایان نصب رایانه را دوباره راه‌اندازی کنید و بعد DataVox را باز کنید.");
            try { Process.Start(Path.Combine(baseDir, "Windows7")); } catch { }
            return 1;
        }

        dataDir = Path.Combine(baseDir, "data");
        if (!CanWrite(dataDir))
            dataDir = Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData), "Voice2Excel", "data");
        Directory.CreateDirectory(dataDir);

        bool webview = !LegacyWindows() && !TestMode() && WebViewVersion() != null;
        var splash = new Splash(Version());
        splash.Show();
        splash.SetStatus("در حال آماده‌سازی…");
        bool ok;
        try
        {
            if (IsUp())
                ok = true;  // موتور از اجرای قبلی هنوز روشن است
            else
            {
                bool updated = false;
                if (HasStagedUpdate())
                {
                    splash.SetStatus("در حال نصب به‌روزرسانی…");
                    updated = ApplyStagedUpdate();
                    if (updated) splash.SetVersion(Version());
                }
                splash.SetStatus("راه‌اندازی موتور برنامه…");
                ok = StartWithRollback(updated, splash.SetStatus);
            }
        }
        catch (Exception e)
        {
            splash.Close();
            ShowError("اجرای برنامه ممکن نشد:\n" + e.Message);
            return 1;
        }

        if (!ok)
        {
            splash.Close();
            string log = Path.Combine(dataDir, "logs", "console.log");
            ShowError("برنامه اجرا نشد.\nجزئیات خطا در این فایل ثبت شده است:\n" + log +
                "\n\nاگر برنامه آنتی‌ویروس دارید، پوشه برنامه را در فهرست مجاز آن قرار دهید.");
            return 1;
        }
        if (!TestMode()) CreateDesktopShortcut(exePath);

        if (!webview)
        {
            Log(LegacyWindows() ? "legacy Windows; opening a browser window" : "WebView2 runtime not found; opening a browser window");
            splash.FadeOutAndClose();
            OpenAppWindow(Url);
            WatchBrowserMode();
            GC.KeepAlive(mutex);
            return 0;
        }
        splash.SetStatus("باز کردن برنامه…");
        var win = new AppWindow(exePath, splash);
        Application.Run(win);
        GC.KeepAlive(mutex);
        return 0;
    }
}

// ================= صفحه شروع =================
sealed class Splash : Form
{
    string status = "", version;
    float phase;
    readonly float scale = Native.Scale();
    const int W = 460, H = 270;
    readonly System.Windows.Forms.Timer anim = new System.Windows.Forms.Timer();
    // رنگ‌های نشان DataVox: سبز و سرمه‌ای روی زمینه سفید
    static readonly Color Accent1 = Color.FromArgb(29, 180, 110), Accent2 = Color.FromArgb(13, 120, 110);
    readonly Image logo;

    public Splash(string version)
    {
        this.version = version;
        FormBorderStyle = FormBorderStyle.None;
        StartPosition = FormStartPosition.CenterScreen;
        Size = new Size((int)(W * scale), (int)(H * scale));
        ShowInTaskbar = true;
        TopMost = true;
        Text = Launcher.Title;
        DoubleBuffered = true;
        Opacity = 0;
        try { Icon = Icon.ExtractAssociatedIcon(Path.Combine(Launcher.baseDir, "DataVox.exe")); } catch { }
        try { logo = Image.FromFile(Path.Combine(Launcher.baseDir, "app", "voice2excel", "web", "brand", "logo.png")); } catch { }
        anim.Interval = 15;
        anim.Tick += delegate
        {
            phase = (phase + 0.012f) % 1.4f;
            if (Opacity < 1) Opacity = Math.Min(1, Opacity + 0.08);
            Invalidate();
        };
        anim.Start();
        Native.RoundCorners(this);
    }

    protected override CreateParams CreateParams
    {
        get { var cp = base.CreateParams; cp.ClassStyle |= 0x20000; return cp; }  // CS_DROPSHADOW
    }

    public void SetStatus(string s) { status = s; Invalidate(); Application.DoEvents(); }
    public void SetVersion(string v) { version = v; Invalidate(); }

    public void FadeOutAndClose()
    {
        anim.Stop();
        for (double o = Opacity; o > 0; o -= 0.1) { Opacity = Math.Max(0, o); Application.DoEvents(); Thread.Sleep(12); }
        Close();
    }

    protected override void OnPaint(PaintEventArgs e)
    {
        var g = e.Graphics;
        g.SmoothingMode = SmoothingMode.AntiAlias;
        g.TextRenderingHint = TextRenderingHint.ClearTypeGridFit;
        g.ScaleTransform(scale, scale);  // رسم با اندازه‌های منطقی، نمایش به اندازه واقعی نمایشگر
        var rc = new Rectangle(0, 0, W, H);
        g.Clear(Color.White);
        g.InterpolationMode = InterpolationMode.HighQualityBicubic;
        if (logo != null)
        {
            int lh = 140, lw = (int)(lh * logo.Width / (float)logo.Height);
            g.DrawImage(logo, new Rectangle((rc.Width - lw) / 2, 22, lw, lh));
        }
        else
        {
            Logo.Draw(g, new Rectangle(rc.Width / 2 - 36, 34, 72, 72));
            using (var f = new Font("Segoe UI", 17, FontStyle.Bold, GraphicsUnit.Point))
            using (var b = new SolidBrush(Color.FromArgb(13, 43, 82)))
            using (var sf = new StringFormat { Alignment = StringAlignment.Center })
                g.DrawString(Launcher.Title, f, b, new RectangleF(0, 118, rc.Width, 40), sf);
        }
        using (var pen = new Pen(Color.FromArgb(226, 231, 240))) g.DrawRectangle(pen, 0, 0, rc.Width - 1, rc.Height - 1);
        using (var f = new Font("Segoe UI", 9.5f))
        using (var b = new SolidBrush(Color.FromArgb(91, 100, 120)))
        using (var sf = new StringFormat { Alignment = StringAlignment.Center, FormatFlags = StringFormatFlags.DirectionRightToLeft })
        {
            if (!string.IsNullOrEmpty(version)) g.DrawString("نسخه " + version, f, b, new RectangleF(0, 172, rc.Width, 22), sf);
            g.DrawString(status, f, b, new RectangleF(0, 224, rc.Width, 22), sf);
        }
        // نوار پیشرفت نامعین با حرکت نرم
        var track = new Rectangle(80, 200, rc.Width - 160, 6);
        using (var p = Native.Pill(track)) using (var b = new SolidBrush(Color.FromArgb(230, 234, 242))) g.FillPath(b, p);
        float w = track.Width * 0.35f, x = track.X - w + (track.Width + w) * (phase / 1.4f);
        var seg = RectangleF.Intersect(new RectangleF(x, track.Y, w, track.Height), track);
        if (seg.Width > 1)
            using (var p = Native.Pill(Rectangle.Round(seg)))
            using (var b = new LinearGradientBrush(seg, Accent1, Accent2, 0f)) g.FillPath(b, p);
    }

    protected override void OnFormClosed(FormClosedEventArgs e) { anim.Stop(); if (logo != null) logo.Dispose(); base.OnFormClosed(e); }
}

static class Logo
{
    /// <summary>نشان برنامه: مربع گوشه‌گرد با رنگ اصلی و میکروفون سفید.</summary>
    public static void Draw(Graphics g, Rectangle r)
    {
        using (var p = Native.Rounded(r, r.Width / 4))
        using (var b = new LinearGradientBrush(r, Color.FromArgb(51, 85, 214), Color.FromArgb(123, 92, 255), 45f))
            g.FillPath(b, p);
        float s = r.Width / 24f;
        using (var pen = new Pen(Color.White, 1.7f * s) { StartCap = LineCap.Round, EndCap = LineCap.Round })
        {
            var cap = new RectangleF(r.X + 9.5f * s, r.Y + 5 * s, 5 * s, 9 * s);
            using (var cp = Native.Rounded(Rectangle.Round(cap), (int)(2.5f * s))) g.DrawPath(pen, cp);
            g.DrawArc(pen, r.X + 7 * s, r.Y + 6.5f * s, 10 * s, 10 * s, 0, 180);
            g.DrawLine(pen, r.X + 12 * s, r.Y + 16.5f * s, r.X + 12 * s, r.Y + 19 * s);
        }
    }
}

// ================= پنجره برنامه =================
sealed class AppWindow : Form
{
    readonly WebView2 web = new WebView2();
    readonly Splash splash;
    readonly System.Windows.Forms.Timer watch = new System.Windows.Forms.Timer();
    readonly string boundsFile = Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData), "Voice2Excel", "window.txt");
    bool shown, restarting;
    int downTicks;
    readonly float scale = Native.Scale();
    int Grip { get { return (int)Math.Round(5 * scale); } }

    public AppWindow(string exePath, Splash splash)
    {
        this.splash = splash;
        Text = Launcher.Title;
        try { Icon = Icon.ExtractAssociatedIcon(exePath); } catch { }
        FormBorderStyle = FormBorderStyle.None;
        bool dark = Native.SystemDark();
        BackColor = dark ? Color.FromArgb(23, 28, 44) : Color.FromArgb(255, 255, 255);
        MinimumSize = new Size((int)(960 * scale), (int)(620 * scale));
        StartPosition = FormStartPosition.Manual;
        RestoreBounds_();
        Padding = new Padding(WindowState == FormWindowState.Maximized ? 0 : Grip);
        web.Dock = DockStyle.Fill;
        web.DefaultBackgroundColor = dark ? Color.FromArgb(15, 19, 32) : Color.FromArgb(244, 246, 251);
        web.CreationProperties = new CoreWebView2CreationProperties
        {
            UserDataFolder = Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData), "Voice2Excel", "WebView2")
        };
        Controls.Add(web);
        Opacity = 0;  // تا بارگذاری صفحه پنهان؛ بعد با محو شدن صفحه شروع ظاهر می‌شود
        Load += async delegate
        {
            try
            {
                await web.EnsureCoreWebView2Async(null);
                Setup();
                web.Source = new Uri(Launcher.Url);
            }
            catch (Exception ex)
            {
                Launcher.Log("webview init failed: " + ex.Message);
                splash.Close();
                Launcher.OpenAppWindow(Launcher.Url);  // بدون WebView2، در پنجره مرورگر
                Close();
            }
        };
        // اجرای دوباره میان‌بر: همین پنجره جلو بیاید
        var show = new EventWaitHandle(false, EventResetMode.AutoReset, "Local\\Voice2Excel.Show");
        var t = new Thread(delegate ()
        {
            while (true) { show.WaitOne(); try { BeginInvoke((Action)BringUp); } catch { return; } }
        });
        t.IsBackground = true;
        t.Start();
        watch.Interval = 1000;
        watch.Tick += delegate { Watch(); };
    }

    void Setup()
    {
        var core = web.CoreWebView2;
        var s = core.Settings;
        s.IsStatusBarEnabled = false;
        s.AreDevToolsEnabled = false;
        s.IsPasswordAutosaveEnabled = false;
        s.IsGeneralAutofillEnabled = false;
        bool nc = false;
        try { s.IsNonClientRegionSupportEnabled = true; nc = true; } catch { }  // «app-region: drag» در نوار عنوان
        core.WebMessageReceived += (o, e) => OnMessage(e.TryGetWebMessageAsString());
        core.NewWindowRequested += (o, e) => { e.Handled = true; Launcher.OpenExternal(e.Uri); };
        core.NavigationStarting += (o, e) =>
        {
            if (e.Uri.StartsWith(Launcher.Url) || e.Uri.StartsWith("about:") || e.Uri.StartsWith("data:")) return;
            e.Cancel = true;  // پیوند بیرونی (راهنما، تلگرام، ایمیل): در برنامه پیش‌فرض ویندوز
            Launcher.OpenExternal(e.Uri);
        };
        core.DocumentTitleChanged += (o, e) => { Text = string.IsNullOrEmpty(core.DocumentTitle) ? Launcher.Title : core.DocumentTitle; };
        core.NavigationCompleted += (o, e) =>
        {
            Post(nc ? "nc:on" : "nc:off");
            Post(WindowState == FormWindowState.Maximized ? "state:max" : "state:normal");
            if (shown) return;
            shown = true;
            Opacity = 1;
            splash.FadeOutAndClose();
            Activate();
            watch.Start();
        };
    }

    void Post(string msg) { try { web.CoreWebView2.PostWebMessageAsString(msg); } catch { } }

    void OnMessage(string msg)
    {
        switch (msg)
        {
            case "min": WindowState = FormWindowState.Minimized; break;
            case "max": WindowState = WindowState == FormWindowState.Maximized ? FormWindowState.Normal : FormWindowState.Maximized; break;
            case "close": Close(); break;
            case "drag": Native.DragWindow(Handle); break;  // اگر WebView2 قدیمی «app-region» را نشناسد
            case "updating": restarting = true; break;
        }
    }

    void BringUp()
    {
        if (WindowState == FormWindowState.Minimized) WindowState = FormWindowState.Normal;
        Activate();
        BringToFront();
    }

    /// <summary>موتور برنامه خاموش شد؟ به‌روزرسانی → نصب و روشن کردن؛ «خروج از برنامه» → بستن پنجره.</summary>
    void Watch()
    {
        if (Launcher.IsUp()) { downTicks = 0; return; }
        if (++downTicks < 2) return;
        watch.Stop();
        string quit = Path.Combine(Launcher.dataDir, ".quit");
        if (File.Exists(quit) && !Launcher.HasStagedUpdate())
        {
            try { File.Delete(quit); } catch { }
            Close();
            return;
        }
        bool updated = Launcher.HasStagedUpdate() && Launcher.ApplyStagedUpdate();
        if (!updated && !restarting) Launcher.Log("engine stopped unexpectedly; restarting");
        bool ok = Launcher.StartWithRollback(updated, null);
        restarting = false;
        if (!ok)
        {
            Launcher.ShowError("موتور برنامه دوباره اجرا نشد. برنامه را ببندید و دوباره باز کنید.");
            Close();
            return;
        }
        web.Reload();  // صفحه با کلید و نسخه تازه
        watch.Start();
    }

    protected override CreateParams CreateParams
    {
        get
        {
            var cp = base.CreateParams;
            // دکمه‌های کوچک/بزرگ و قاب قابل‌تغییر: حرکات ویندوز (Snap، کوچک شدن با کلیک در نوار وظیفه، سایه)
            cp.Style |= 0x00020000 | 0x00010000 | 0x00080000 | 0x00040000;  // MINIMIZEBOX | MAXIMIZEBOX | SYSMENU | THICKFRAME
            return cp;
        }
    }

    protected override void OnHandleCreated(EventArgs e)
    {
        base.OnHandleCreated(e);
        Native.RoundCorners(this);
        Native.ExtendFrame(Handle);
    }

    protected override void WndProc(ref Message m)
    {
        const int WM_NCCALCSIZE = 0x83, WM_NCHITTEST = 0x84;
        if (m.Msg == WM_NCCALCSIZE && m.WParam != IntPtr.Zero)
        {
            // کل پنجره ناحیه برنامه است (بدون نوار عنوان ویندوز)؛ در حالت بزرگ، از لبه صفحه بیرون نمی‌زند
            if (WindowState == FormWindowState.Maximized) Native.InsetMaximized(m.LParam);
            m.Result = IntPtr.Zero;
            return;
        }
        if (m.Msg == WM_NCHITTEST && WindowState != FormWindowState.Maximized)
        {
            long lp = m.LParam.ToInt64();
            var pt = PointToClient(new Point((short)(lp & 0xFFFF), (short)((lp >> 16) & 0xFFFF)));
            bool l = pt.X < Grip, r = pt.X >= ClientSize.Width - Grip, t = pt.Y < Grip, b = pt.Y >= ClientSize.Height - Grip;
            int hit = t && l ? 13 : t && r ? 14 : b && l ? 16 : b && r ? 17 : l ? 10 : r ? 11 : t ? 12 : b ? 15 : 1;
            m.Result = (IntPtr)hit;
            return;
        }
        base.WndProc(ref m);
    }

    protected override void OnResize(EventArgs e)
    {
        base.OnResize(e);
        if (WindowState == FormWindowState.Minimized) return;
        Padding = new Padding(WindowState == FormWindowState.Maximized ? 0 : Grip);
        if (web.CoreWebView2 != null) Post(WindowState == FormWindowState.Maximized ? "state:max" : "state:normal");
    }

    // ---------- اندازه و جای پنجره ----------
    void RestoreBounds_()
    {
        var wa = Screen.PrimaryScreen.WorkingArea;
        int w = (int)(1280 * scale), h = (int)(820 * scale);
        Rectangle r = new Rectangle(wa.X + (wa.Width - w) / 2, wa.Y + (wa.Height - h) / 2, w, h);
        bool max = wa.Width < w + 80 || wa.Height < h + 40;  // نمایشگر کوچک: از اول بزرگ
        try
        {
            string[] p = File.ReadAllText(boundsFile).Split(',');
            var saved = new Rectangle(int.Parse(p[0]), int.Parse(p[1]), int.Parse(p[2]), int.Parse(p[3]));
            foreach (var sc in Screen.AllScreens)
                if (sc.WorkingArea.IntersectsWith(saved)) { r = saved; break; }
            max = p.Length > 4 && p[4] == "1";
        }
        catch { }
        r.Width = Math.Min(r.Width, wa.Width);
        r.Height = Math.Min(r.Height, wa.Height);
        Bounds = r;
        if (max) WindowState = FormWindowState.Maximized;
    }

    protected override void OnFormClosing(FormClosingEventArgs e)
    {
        try
        {
            Directory.CreateDirectory(Path.GetDirectoryName(boundsFile));
            var b = WindowState == FormWindowState.Normal ? Bounds : RestoreBounds;
            File.WriteAllText(boundsFile, string.Join(",", b.X, b.Y, b.Width, b.Height, WindowState == FormWindowState.Maximized ? "1" : "0"));
        }
        catch { }
        watch.Stop();
        base.OnFormClosing(e);
    }
}

// ================= ویندوز =================
static class Native
{
    [DllImport("user32.dll")] static extern bool ReleaseCapture();
    [DllImport("user32.dll")] static extern IntPtr SendMessage(IntPtr h, int msg, IntPtr w, IntPtr l);
    [DllImport("user32.dll")] static extern int GetSystemMetrics(int i);
    [DllImport("dwmapi.dll")] static extern int DwmSetWindowAttribute(IntPtr h, int attr, ref int value, int size);
    [DllImport("dwmapi.dll")] static extern int DwmExtendFrameIntoClientArea(IntPtr h, ref Margins m);
    [DllImport("user32.dll")] static extern bool SetProcessDpiAwarenessContext(IntPtr ctx);
    [DllImport("user32.dll")] static extern bool SetProcessDPIAware();
    [DllImport("kernel32.dll", CharSet = CharSet.Unicode)] public static extern IntPtr GetModuleHandle(string name);
    [DllImport("kernel32.dll", CharSet = CharSet.Ansi, BestFitMapping = false)] public static extern IntPtr GetProcAddress(IntPtr module, string name);

    /// <summary>اندازه‌ها به پیکسل واقعی نمایشگر (Per-Monitor v2؛ در ویندوزهای قدیمی‌تر System DPI).</summary>
    public static void EnableDpiAwareness()
    {
        try { if (SetProcessDpiAwarenessContext((IntPtr)(-4))) return; } catch { }
        try { SetProcessDPIAware(); } catch { }
    }

    public static float Scale()
    {
        try { using (var g = Graphics.FromHwnd(IntPtr.Zero)) return Math.Max(1f, g.DpiX / 96f); }
        catch { return 1f; }
    }

    [StructLayout(LayoutKind.Sequential)] struct Margins { public int L, R, T, B; }
    [StructLayout(LayoutKind.Sequential)] struct Rect { public int L, T, R, B; }

    public static void DragWindow(IntPtr h)
    {
        ReleaseCapture();
        SendMessage(h, 0xA1, (IntPtr)2, IntPtr.Zero);  // WM_NCLBUTTONDOWN, HTCAPTION
    }

    /// <summary>گوشه‌های گرد ویندوز ۱۱ (در ویندوز ۱۰ بی‌اثر).</summary>
    public static void RoundCorners(Form f)
    {
        try { int round = 2; DwmSetWindowAttribute(f.Handle, 33, ref round, 4); } catch { }
    }

    /// <summary>سایه و پویانمایی‌های پنجره ویندوز برای پنجره بی‌قاب.</summary>
    public static void ExtendFrame(IntPtr h)
    {
        try { var m = new Margins { L = 0, R = 0, T = 0, B = 1 }; DwmExtendFrameIntoClientArea(h, ref m); } catch { }
    }

    public static void InsetMaximized(IntPtr lparam)
    {
        var r = (Rect)Marshal.PtrToStructure(lparam, typeof(Rect));
        int fx = GetSystemMetrics(32) + GetSystemMetrics(92), fy = GetSystemMetrics(33) + GetSystemMetrics(92);
        r.L += fx; r.T += fy; r.R -= fx; r.B -= fy;
        Marshal.StructureToPtr(r, lparam, false);
    }

    public static bool SystemDark()
    {
        try
        {
            using (var k = Microsoft.Win32.Registry.CurrentUser.OpenSubKey(@"Software\Microsoft\Windows\CurrentVersion\Themes\Personalize"))
                return k != null && (int)k.GetValue("AppsUseLightTheme", 1) == 0;
        }
        catch { return false; }
    }

    public static GraphicsPath Rounded(Rectangle r, int radius)
    {
        int d = Math.Max(1, radius * 2);
        var p = new GraphicsPath();
        p.AddArc(r.X, r.Y, d, d, 180, 90);
        p.AddArc(r.Right - d, r.Y, d, d, 270, 90);
        p.AddArc(r.Right - d, r.Bottom - d, d, d, 0, 90);
        p.AddArc(r.X, r.Bottom - d, d, d, 90, 90);
        p.CloseFigure();
        return p;
    }

    public static GraphicsPath Pill(Rectangle r) { return Rounded(r, Math.Max(1, r.Height / 2)); }
}
