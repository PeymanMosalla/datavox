# آزمون بسته مشتری: zip ساخته‌شده را مثل یک مشتری تازه باز می‌کند (بدون اشتراک، آزمایشی تازه)
# و آزمون کامل کلیک رابط کاربری را رویش اجرا می‌کند. اطلاعات و برنامه خود شما دست نمی‌خورد.
#
# استفاده (از پوشه voice2excel، در PowerShell):
#   powershell -ExecutionPolicy Bypass -File scripts\customer_test.ps1 -Zip dist\DataVox-2.6.2.zip
#   powershell -ExecutionPolicy Bypass -File scripts\customer_test.ps1 -Zip dist\DataVox-2.6.2-win7.zip
# پیش‌نیاز: Node.js و Microsoft Edge نصب باشند. نتیجه سالم: «همه موارد موفق».
param([Parameter(Mandatory = $true)][string]$Zip, [int]$Port = 8799)
$ErrorActionPreference = "Stop"
$repo = Split-Path -Parent $PSScriptRoot
$zipPath = (Resolve-Path $Zip).Path
$root = "C:\DataVoxTest"   # مسیر کوتاه (سقف ۲۶۰ نویسه ویندوز)
function Status { try { Invoke-RestMethod -Uri "http://127.0.0.1:$Port/api/status" -TimeoutSec 3 } catch { $null } }
function ClearTrial { try { Remove-Item HKCU:\Software\Voice2Excel -Recurse -ErrorAction Stop } catch { } }

if (Status) { throw "درگاه $Port مشغول است؛ برنامه آزمایشی قبلی را ببندید." }
ClearTrial   # وضعیت آزمایشی از آزمون‌های قبلی پاک شود
Remove-Item $root -Recurse -Force -ErrorAction SilentlyContinue
New-Item -ItemType Directory $root | Out-Null
Write-Host "باز کردن $zipPath ..."
Add-Type -AssemblyName System.IO.Compression.FileSystem
[System.IO.Compression.ZipFile]::ExtractToDirectory($zipPath, $root)
$app = Get-ChildItem $root -Directory | Select-Object -First 1
if (Test-Path (Join-Path $app.FullName "data")) { throw "بسته نباید پوشه data داشته باشد (اطلاعات کاربر داخل zip رفته است)." }

$envDir = Join-Path $root "env"
foreach ($d in "data", "appdata", "local", "progdata") { New-Item -ItemType Directory (Join-Path $envDir $d) -Force | Out-Null }
Set-Content (Join-Path $envDir "data\settings.json") "{`"port`": $Port}" -Encoding ascii
# همه انبارهای وضعیت (APPDATA و ...) به پوشه آزمون می‌روند تا روی رایانه چیزی باقی نماند
$saved = @{}
$vars = @{ V2X_DATA_DIR = "$envDir\data"; V2X_MODELS_DIR = "$($app.FullName)\models"; V2X_SAMPLES_DIR = "$($app.FullName)\samples";
  APPDATA = "$envDir\appdata"; LOCALAPPDATA = "$envDir\local"; PROGRAMDATA = "$envDir\progdata"; TEMP = $envDir; TMP = $envDir;
  HF_HUB_OFFLINE = "1"; PYTHONIOENCODING = "utf-8"; PYTHONNOUSERSITE = "1" }
foreach ($k in $vars.Keys) { $saved[$k] = [Environment]::GetEnvironmentVariable($k); [Environment]::SetEnvironmentVariable($k, $vars[$k]) }
$proc = $null
try {
  $proc = Start-Process -FilePath "$($app.FullName)\python\python.exe" -ArgumentList "-m", "voice2excel", "--no-browser" `
    -WorkingDirectory "$($app.FullName)\app" -WindowStyle Hidden -PassThru `
    -RedirectStandardOutput "$envDir\server.log" -RedirectStandardError "$envDir\server.err.log"
  foreach ($k in $vars.Keys) { [Environment]::SetEnvironmentVariable($k, $saved[$k]) }
  $s = $null
  for ($i = 0; $i -lt 90 -and -not $s; $i++) { Start-Sleep 2; $s = Status }
  if (-not $s) { Get-Content "$envDir\server.err.log" -Tail 20; throw "موتور برنامه بالا نیامد." }
  Write-Host "برنامه نسخه $($s.version) روی درگاه $Port بالا آمد؛ آزمون کامل رابط کاربری (چند دقیقه)..."
  & node (Join-Path $repo "tests\ui_click_test.mjs") "http://127.0.0.1:$Port/" --full
  $code = $LASTEXITCODE
} finally {
  foreach ($k in $vars.Keys) { [Environment]::SetEnvironmentVariable($k, $saved[$k]) }
  try {
    $html = (Invoke-WebRequest -Uri "http://127.0.0.1:$Port/" -UseBasicParsing -TimeoutSec 5).Content
    if ($html -match 'name="v2x-token" content="([^"]+)"') { Invoke-RestMethod -Uri "http://127.0.0.1:$Port/api/shutdown" -Method Post -Headers @{ "x-v2x-token" = $Matches[1] } | Out-Null }
  } catch { }
  Start-Sleep 4
  if ($proc -and -not $proc.HasExited) { Stop-Process -Id $proc.Id -Force -ErrorAction SilentlyContinue }
  Start-Sleep 2
  Remove-Item $root -Recurse -Force -ErrorAction SilentlyContinue
  ClearTrial
}
if ($code -eq 0) { Write-Host "`nبسته سالم است." -ForegroundColor Green } else { Write-Host "`nآزمون موفق نبود؛ بالا را ببینید. (اگر فقط یک مورد زمانی بود، یک بار دیگر اجرا کنید.)" -ForegroundColor Red }
exit $code
