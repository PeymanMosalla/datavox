# آزمون اجراکننده DataVox.exe در حالت بدون WebView2 (مثل ویندوز ۷ یا رایانه‌ای که WebView2 ندارد):
# نصب به‌روزرسانی یک‌کلیکی، راه‌اندازی دوباره موتور پس از بسته شدن ناگهانی، اجرای دوباره میان‌بر و خروج.
# فقط وقتی لازم است که packaging\Launcher.cs تغییر کرده باشد. میان‌بر روی Desktop ساخته نمی‌شود و مرورگری باز نمی‌شود.
#
# استفاده (از پوشه voice2excel؛ برنامه خودتان باید بسته باشد، چون این آزمون از درگاه 8765 استفاده می‌کند):
#   1) یک بسته به‌روزرسانی آزمایشی بسازید:
#        .venv\Scripts\python.exe scripts\build_update.py --version 9.9.9 --notes test
#      (در شاخه windows7-only نام فایل dist\DataVox-update-9.9.9-win7.zip است) و بعد از آزمون پاکش کنید.
#   2) powershell -ExecutionPolicy Bypass -File scripts\launcher_test.ps1 -Zip dist\DataVox-2.6.2.zip -UpdateZip dist\DataVox-update-9.9.9.zip
# نتیجه سالم: «RESULT: 9 passed, 0 failed».
param([Parameter(Mandatory = $true)][string]$Zip, [Parameter(Mandatory = $true)][string]$UpdateZip, [string]$License = "")
$ErrorActionPreference = "Stop"
$repo = Split-Path -Parent $PSScriptRoot
$Zip = (Resolve-Path $Zip).Path
$UpdateZip = (Resolve-Path $UpdateZip).Path
if (-not $License) { $License = Join-Path $repo "dist\DataVox\data\license.v2x" }  # به‌روزرسانی فقط با اشتراک فعال است
$root = "C:\DataVoxLauncherTest"
$results = @()
function Check($name, $ok, $detail = "") { $script:results += [pscustomobject]@{ ok = $ok; name = $name }; "{0} {1} {2}" -f ($(if ($ok) { "PASS" } else { "FAIL" }), $name, $detail) }
function Status { try { Invoke-RestMethod -Uri "http://127.0.0.1:8765/api/status" -TimeoutSec 3 } catch { $null } }
function WaitUp($sec) { for ($i = 0; $i -lt $sec; $i++) { $s = Status; if ($s) { return $s }; Start-Sleep 1 }; return $null }
function WaitDown($sec) { for ($i = 0; $i -lt $sec; $i++) { if (-not (Status)) { return $true }; Start-Sleep 1 }; return $false }
function Token { $h = (Invoke-WebRequest -Uri "http://127.0.0.1:8765/" -UseBasicParsing).Content; if ($h -match 'name="v2x-token" content="([^"]+)"') { $Matches[1] } }
function Engine { Get-CimInstance Win32_Process -Filter "name like 'python%'" | Where-Object { $_.ExecutablePath -like "$root\*" } }
function LauncherProc { Get-Process DataVox -ErrorAction SilentlyContinue | Where-Object { $_.Path -like "$root\*" } }

if (Status) { throw "درگاه 8765 مشغول است؛ اول برنامه DataVox خودتان را ببندید." }
try { Remove-Item HKCU:\Software\Voice2Excel -Recurse -ErrorAction Stop } catch { }
Remove-Item $root -Recurse -Force -ErrorAction SilentlyContinue
New-Item -ItemType Directory $root | Out-Null
Add-Type -AssemblyName System.IO.Compression.FileSystem
[System.IO.Compression.ZipFile]::ExtractToDirectory($Zip, $root)
$app = (Get-ChildItem $root -Directory | Select-Object -First 1).FullName
$exe = Join-Path $app "DataVox.exe"
$log = Join-Path $app "data\logs\launcher.log"
New-Item -ItemType Directory (Join-Path $app "data") -Force | Out-Null
Copy-Item $License (Join-Path $app "data\license.v2x")  # فقط در کپی آزمایشی؛ پوشه در پایان پاک می‌شود
$env:V2X_TEST_BROWSER_MODE = "1"
try {
  Start-Process $exe
  $s = WaitUp 120
  Check "launcher started the engine (browser mode)" ($null -ne $s) $(if ($s) { "version " + $s.version })
  Start-Sleep 3
  $l = Get-Content $log -Raw -Encoding UTF8
  Check "browser window requested instead of WebView2" ($l -match "test: browser window")
  Check "launcher stays running to watch the engine" ($null -ne (LauncherProc))

  # ۱) نصب به‌روزرسانی یک‌کلیکی
  $tok = Token
  $r = & curl.exe -s -X POST -H "x-v2x-token: $tok" -F "file=@$UpdateZip" "http://127.0.0.1:8765/api/update"
  Check "update staged" ($r -match '"version"') ([string]$r)
  Invoke-RestMethod -Uri "http://127.0.0.1:8765/api/update/apply" -Method Post -Headers @{ "x-v2x-token" = $tok } | Out-Null
  $down = WaitDown 60
  $s = WaitUp 120
  Check "one-click update: engine back after install" ($down -and $null -ne $s)
  $l = Get-Content $log -Raw -Encoding UTF8
  Check "launcher applied the update" ($l -match "update applied; restarting engine")

  # ۲) بسته شدن ناخواسته موتور
  Engine | ForEach-Object { Stop-Process -Id $_.ProcessId -Force }
  $down = WaitDown 30
  $s = WaitUp 120
  $l = Get-Content $log -Raw -Encoding UTF8
  Check "crashed engine restarted automatically" ($down -and $null -ne $s -and $l -match "engine stopped unexpectedly")

  # ۳) اجرای دوباره میان‌بر
  $before = ([regex]::Matches($l, "test: browser window")).Count
  Start-Process $exe -Wait
  Start-Sleep 3
  $l = Get-Content $log -Raw -Encoding UTF8
  Check "second launch opens the window again" (([regex]::Matches($l, "test: browser window")).Count -gt $before)

  # ۴) خروج از برنامه
  Invoke-RestMethod -Uri "http://127.0.0.1:8765/api/shutdown" -Method Post -Headers @{ "x-v2x-token" = (Token) } | Out-Null
  $down = WaitDown 60
  Start-Sleep 6
  Check "quit: engine and launcher both closed" ($down -and $null -eq (LauncherProc) -and $null -eq (Engine))
} finally {
  Remove-Item Env:\V2X_TEST_BROWSER_MODE -ErrorAction SilentlyContinue
  Engine | ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }
  LauncherProc | Stop-Process -Force -ErrorAction SilentlyContinue
  Start-Sleep 2
  try { Remove-Item HKCU:\Software\Voice2Excel -Recurse -ErrorAction Stop } catch { }
  "--- launcher.log ---"; if (Test-Path $log) { Get-Content $log -Encoding UTF8 | Select-Object -Last 12 }
  Remove-Item $root -Recurse -Force -ErrorAction SilentlyContinue
}
$failed = @($results | Where-Object { -not $_.ok }).Count
"RESULT: {0} passed, {1} failed" -f ($results.Count - $failed), $failed
exit $(if ($failed) { 1 } else { 0 })
