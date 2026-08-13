# External terminal runner for RTX 5070 GGUF profile.
# Opens in its own window; logs to temp\gguf_5070_setup.log
$ErrorActionPreference = "Continue"
$Root = "C:\Users\user\Documents\DirectorX"
Set-Location $Root
$LogDir = Join-Path $Root "temp"
New-Item -ItemType Directory -Force -Path $LogDir | Out-Null
$Log = Join-Path $LogDir "gguf_5070_setup.log"
$Py = Join-Path $Root ".venv\Scripts\python.exe"
if (-not (Test-Path $Py)) { $Py = "python" }

function Log([string]$msg) {
  $line = "[{0}] {1}" -f (Get-Date -Format "HH:mm:ss"), $msg
  Write-Host $line
  Add-Content -Path $Log -Value $line
}

function Run-Step([string]$title, [string]$exe, [string[]]$argList) {
  Log $title
  $out = Join-Path $LogDir "_stdout.tmp"
  $err = Join-Path $LogDir "_stderr.tmp"
  Remove-Item $out, $err -Force -ErrorAction SilentlyContinue
  $p = Start-Process -FilePath $exe -ArgumentList $argList -WorkingDirectory $Root -Wait -PassThru -NoNewWindow `
    -RedirectStandardOutput $out -RedirectStandardError $err
  foreach ($f in @($out, $err)) {
    if (Test-Path $f) {
      Get-Content $f | ForEach-Object {
        Write-Host $_
        Add-Content -Path $Log -Value $_
      }
    }
  }
  Log ("{0} exit={1}" -f $title, $p.ExitCode)
  return $p.ExitCode
}

"" | Set-Content -Path $Log -Encoding UTF8
Log "=== GGUF 5070 setup start ==="
Log ("Root={0}" -f $Root)
Log ("C free GB={0}" -f [math]::Round((Get-PSDrive C).Free / 1GB, 1))
Log ("Why slow: downloading ~30GB model weights over network")

$code1 = Run-Step "STEP1 download models" "powershell.exe" @(
  "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", (Join-Path $Root "scripts\download_gguf_5070.ps1")
)
$code2 = Run-Step "STEP2 build workflows" $Py @((Join-Path $Root "scripts\build_workflow_api.py"))
$code3 = Run-Step "STEP3 refresh config" $Py @((Join-Path $Root "scripts\_print_gguf_status.py"))
$code4 = Run-Step "STEP4 smoke Flux+Wan" $Py @((Join-Path $Root "scripts\_smoke_gguf_5070.py"))

Log "=== FINISHED ==="
Log ("exits download={0} build={1} status={2} smoke={3}" -f $code1, $code2, $code3, $code4)
Log ("Log file: {0}" -f $Log)
Write-Host ""
Write-Host "Done. Window stays open. Close when finished reviewing."
try { $null = $Host.UI.RawUI.ReadKey("NoEcho,IncludeKeyDown") } catch { Start-Sleep 30 }

