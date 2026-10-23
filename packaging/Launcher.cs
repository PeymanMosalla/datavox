// Voice2Excel.exe: اجراکننده نسخه قابل‌حمل.
// - اگر برنامه در حال اجرا باشد، فقط مرورگر را باز می‌کند.
// - اگر به‌روزرسانی سبکی آماده باشد (update-staged)، آن را جایگزین می‌کند؛ اگر نسخه جدید بالا نیاید،
//   خودکار نسخه قبلی را برمی‌گرداند.
// - Python جاسازی‌شده را بدون پنجره کنسول اجرا می‌کند، منتظر آماده‌شدن می‌ماند و مرورگر را باز می‌کند.
using System;
using System.Diagnostics;
using System.Drawing;
using System.IO;
using System.Net;
using System.Threading;
using System.Windows.Forms;

static class Launcher
{
    const string Url = "http://127.0.0.1:8765/";
    const string Title = "ثبت ویس";
    static readonly string[] RootExtras = { "Guide.html", "Recording-Guide.html" };

    static string baseDir;
    static string dataDir;

    static bool IsUp()
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

    static void OpenBrowser()
    {
        try { Process.Start(Url); } catch { }
    }

    static void Log(string msg)
    {
        try
        {
            string dir = Path.Combine(dataDir ?? Path.Combine(baseDir, "data"), "logs");
            Directory.CreateDirectory(dir);
            File.AppendAllText(Path.Combine(dir, "launcher.log"), DateTime.Now.ToString("s") + " " + msg + Environment.NewLine);
        }
        catch { }
    }

    static void ShowError(string msg)
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
            if (File.Exists(lnk)) return;
            // WScript.Shell نام فایل فارسی را ذخیره نمی‌کند: ابتدا با نام انگلیسی ساخته و سپس تغییر نام داده می‌شود
            string tmp = Path.Combine(desktop, "Voice2Excel-shortcut.lnk");
            Type t = Type.GetTypeFromProgID("WScript.Shell");
            dynamic shell = Activator.CreateInstance(t);
            dynamic sc = shell.CreateShortcut(tmp);
            sc.TargetPath = exePath;
            sc.WorkingDirectory = baseDir;
            sc.IconLocation = exePath + ",0";
            sc.Description = "Voice2Excel";
            sc.Save();
            if (File.Exists(tmp)) File.Move(tmp, lnk);
        }
        catch (Exception e) { Log("shortcut: " + e.Message); }
    }

    // ---------- به‌روزرسانی سبک ----------
    static string AppPkg { get { return Path.Combine(baseDir, "app", "voice2excel"); } }
    static string PrevPkg { get { return Path.Combine(baseDir, "app", "voice2excel.previous"); } }
    static string PrevRoot { get { return Path.Combine(baseDir, "app", "previous-root-files"); } }

    /// <summary>جایگزینی نسخه آماده؛ نسخه فعلی به‌عنوان «قبلی» نگه داشته می‌شود.</summary>
    static bool ApplyStagedUpdate()
    {
        string stage = Path.Combine(baseDir, "update-staged");
        string stagedPkg = Path.Combine(stage, "voice2excel");
        if (!File.Exists(Path.Combine(stage, "manifest.json")) || !Directory.Exists(stagedPkg)) return false;
        try
        {
            if (Directory.Exists(PrevPkg)) Directory.Delete(PrevPkg, true);
            if (Directory.Exists(PrevRoot)) Directory.Delete(PrevRoot, true);
            Directory.CreateDirectory(PrevRoot);
            Directory.Move(AppPkg, PrevPkg);
            Directory.Move(stagedPkg, AppPkg);
            foreach (string name in RootExtras)
            {
                string src = Path.Combine(stage, name), dst = Path.Combine(baseDir, name);
                if (!File.Exists(src)) continue;
                if (File.Exists(dst)) File.Copy(dst, Path.Combine(PrevRoot, name), true);
                File.Copy(src, dst, true);
            }
            Directory.Delete(stage, true);
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
    static bool RollbackUpdate()
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

    // ---------- اجرای برنامه ----------
    static Process StartApp()
    {
        var psi = new ProcessStartInfo(Path.Combine(baseDir, "python", "pythonw.exe"), "-m voice2excel --no-browser --auto-exit");
        psi.WorkingDirectory = Path.Combine(baseDir, "app");
        psi.UseShellExecute = false;
        psi.CreateNoWindow = true;
        psi.EnvironmentVariables["V2X_DATA_DIR"] = dataDir;
        psi.EnvironmentVariables["V2X_MODELS_DIR"] = Path.Combine(baseDir, "models");
        psi.EnvironmentVariables["V2X_SAMPLES_DIR"] = Path.Combine(baseDir, "samples");
        psi.EnvironmentVariables["HF_HUB_OFFLINE"] = "1";
        psi.EnvironmentVariables["HF_HUB_DISABLE_TELEMETRY"] = "1";
        psi.EnvironmentVariables["PYTHONIOENCODING"] = "utf-8";
        psi.EnvironmentVariables["PYTHONNOUSERSITE"] = "1";
        psi.EnvironmentVariables.Remove("PYTHONPATH");
        psi.EnvironmentVariables.Remove("PYTHONHOME");
        return Process.Start(psi);
    }

    static bool WaitUntilUp(Process proc)
    {
        for (int i = 0; i < 240; i++)
        {
            Application.DoEvents();
            if (IsUp()) return true;
            if (proc.HasExited) return false;
            Thread.Sleep(250);
        }
        return false;
    }

    static Form Splash()
    {
        var f = new Form();
        f.FormBorderStyle = FormBorderStyle.None;
        f.StartPosition = FormStartPosition.CenterScreen;
        f.Size = new Size(420, 130);
        f.BackColor = Color.FromArgb(23, 28, 44);
        f.ShowInTaskbar = true;
        f.Text = Title;
        f.TopMost = true;
        f.RightToLeft = RightToLeft.Yes;
        var l1 = new Label();
        l1.Text = Title;
        l1.ForeColor = Color.White;
        l1.Font = new Font("Tahoma", 14, FontStyle.Bold);
        l1.TextAlign = ContentAlignment.MiddleCenter;
        l1.SetBounds(0, 22, 420, 36);
        var l2 = new Label();
        l2.Text = "در حال آماده‌سازی برنامه... چند ثانیه صبر کنید";
        l2.ForeColor = Color.FromArgb(184, 191, 211);
        l2.Font = new Font("Tahoma", 9.5f);
        l2.TextAlign = ContentAlignment.MiddleCenter;
        l2.SetBounds(0, 66, 420, 30);
        f.Controls.Add(l1);
        f.Controls.Add(l2);
        return f;
    }

    [STAThread]
    static int Main()
    {
        baseDir = AppDomain.CurrentDomain.BaseDirectory.TrimEnd('\\');
        string exePath = Path.Combine(baseDir, "Voice2Excel.exe");

        if (IsUp()) { OpenBrowser(); return 0; }

        if (!File.Exists(Path.Combine(baseDir, "python", "pythonw.exe")))
        {
            ShowError("فایل‌های برنامه کامل نیستند (پوشه python پیدا نشد).\nلطفاً فایل zip را کامل از حالت فشرده خارج کنید و دوباره اجرا کنید.");
            return 1;
        }

        dataDir = Path.Combine(baseDir, "data");
        if (!CanWrite(dataDir))
            dataDir = Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData), "Voice2Excel", "data");
        Directory.CreateDirectory(dataDir);

        bool updated = ApplyStagedUpdate();

        var splash = Splash();
        splash.Show();
        Application.DoEvents();
        Process proc;
        bool ok;
        try
        {
            proc = StartApp();
            ok = WaitUntilUp(proc);
            if (!ok && updated)
            {
                try { if (!proc.HasExited) proc.Kill(); } catch { }
                if (RollbackUpdate())
                {
                    proc = StartApp();
                    ok = WaitUntilUp(proc);
                    if (ok)
                    {
                        splash.Close();
                        ShowError("نسخه جدید اجرا نشد و برنامه خودکار به نسخه قبلی برگشت. اطلاعات شما دست نخورده است.");
                    }
                }
            }
        }
        catch (Exception e)
        {
            splash.Close();
            ShowError("اجرای برنامه ممکن نشد:\n" + e.Message);
            return 1;
        }
        if (splash.Visible) splash.Close();

        if (!ok)
        {
            string log = Path.Combine(dataDir, "logs", "console.log");
            ShowError("برنامه اجرا نشد.\nجزئیات خطا در این فایل ثبت شده است:\n" + log +
                "\n\nاگر برنامه آنتی‌ویروس دارید، پوشه برنامه را در فهرست مجاز آن قرار دهید.");
            return 1;
        }
        CreateDesktopShortcut(exePath);
        OpenBrowser();
        return 0;
    }
}
