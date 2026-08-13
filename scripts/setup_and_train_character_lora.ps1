# P2 - train Flux character LoRA in ISOLATED ai-toolkit venv (never touch DirectorX .venv).
# Requires: HF token with access to black-forest-labs/FLUX.1-dev
# Prereq: bible stills in assets/characters/ar_filter_viewer/bible (12+)

$ErrorActionPreference = "Stop"
$Root = "C:\Users\user\Documents\DirectorX"
$Toolkit = "C:\ai-toolkit"
$Bible = Join-Path $Root "assets\characters\ar_filter_viewer\bible"
$Yaml = Join-Path $Root "training\flux_lora_ar_viewer_12gb.yaml"
$LoraDir = "C:\ComfyUI\models\loras"
$OutName = "dxc_arviewer.safetensors"
$PySys = "C:\Users\user\AppData\Local\Programs\Python\Python311\python.exe"
$TkPy = Join-Path $Toolkit ".venv\Scripts\python.exe"
$TkPip = Join-Path $Toolkit ".venv\Scripts\pip.exe"

Write-Host "==> P2 Flux LoRA train (12GB) - isolated toolkit venv"
$pngs = @(Get-ChildItem $Bible -Filter "bible_*.png" -ErrorAction SilentlyContinue)
if ($pngs.Count -lt 12) {
  throw "Bible incomplete: $($pngs.Count)/12 in $Bible - run gen_character_bible_stills first"
}
Write-Host "    bible images: $($pngs.Count)"

$RunPy = Join-Path $Toolkit "run.py"
if (-not (Test-Path $RunPy)) {
  if (Test-Path $Toolkit) {
    Write-Host "==> Removing incomplete toolkit clone"
    Remove-Item $Toolkit -Recurse -Force -ErrorAction SilentlyContinue
  }
  Write-Host "==> Cloning ostris/ai-toolkit -> $Toolkit"
  git clone --depth 1 https://github.com/ostris/ai-toolkit.git $Toolkit
  Push-Location $Toolkit
  git submodule update --init --recursive
  Pop-Location
} else {
  Write-Host "[=] ai-toolkit present"
}

if (-not (Test-Path $TkPy)) {
  Write-Host "==> Creating isolated venv at $Toolkit\.venv"
  & $PySys -m venv (Join-Path $Toolkit ".venv")
}

& $TkPip install -U pip
$cudaOk = $false
try {
  $probe = & $TkPy -c "import torch; print(torch.cuda.is_available())"
  if ($probe -match "True") { $cudaOk = $true }
} catch {}
if (-not $cudaOk) {
  Write-Host "==> Installing CUDA torch + torchaudio into toolkit venv"
  & $TkPip install torch==2.10.0 torchaudio==2.10.0 torchvision==0.25.0 --index-url https://download.pytorch.org/whl/cu128
} else {
  Write-Host "[=] toolkit CUDA torch OK - skip reinstall"
}
Write-Host "==> Installing ai-toolkit requirements into toolkit venv"
& $TkPip install -r (Join-Path $Toolkit "requirements.txt")
# Re-assert CUDA torch in case requirements overwrote it with CPU wheels
& $TkPip install --force-reinstall torch==2.10.0 torchaudio==2.10.0 torchvision==0.25.0 --index-url https://download.pytorch.org/whl/cu128

New-Item -ItemType Directory -Force -Path $LoraDir, (Join-Path $Root "temp\p2_lora_train") | Out-Null

# Pass HF token from DirectorX hub cache if env empty
if (-not $env:HF_TOKEN -and -not $env:HUGGING_FACE_HUB_TOKEN) {
  try {
    $tok = & "$Root\.venv\Scripts\python.exe" -c "from huggingface_hub import get_token; print(get_token() or '')"
    if ($tok) {
      $env:HF_TOKEN = $tok.Trim()
      Write-Host "[=] HF_TOKEN loaded from huggingface_hub cache"
    }
  } catch {}
}
if (-not $env:HF_TOKEN -and -not $env:HUGGING_FACE_HUB_TOKEN) {
  Write-Warning "HF_TOKEN missing - FLUX.1-dev gated download may fail"
}

Write-Host "==> Training (long). YAML: $Yaml"
Push-Location $Toolkit
& $TkPy run.py "$Yaml"
$trainExit = $LASTEXITCODE
Pop-Location
if ($trainExit -ne 0) { throw "Train failed exit=$trainExit" }

$candidates = Get-ChildItem (Join-Path $Root "temp\p2_lora_train") -Recurse -Filter "*.safetensors" -ErrorAction SilentlyContinue |
  Sort-Object LastWriteTime -Descending
if (-not $candidates -or $candidates.Count -eq 0) {
  $candidates = Get-ChildItem (Join-Path $Toolkit "output") -Recurse -Filter "*dxc_arviewer*.safetensors" -ErrorAction SilentlyContinue |
    Sort-Object LastWriteTime -Descending
}
if (-not $candidates -or $candidates.Count -eq 0) {
  throw "No LoRA .safetensors found after train"
}
$src = $candidates[0].FullName
$dest = Join-Path $LoraDir $OutName
Copy-Item $src $dest -Force
Write-Host "LORA_OK $dest ($([math]::Round((Get-Item $dest).Length/1MB,1)) MB)"
Write-Host "NEXT: render horror with LoRA ON"
