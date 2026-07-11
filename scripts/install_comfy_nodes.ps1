# Install recommended ComfyUI custom nodes for DirectorX
$ErrorActionPreference = "Stop"
$Comfy = "C:\ComfyUI"
$Nodes = Join-Path $Comfy "custom_nodes"

if (-not (Test-Path $Comfy)) {
  Write-Error "ComfyUI not found at $Comfy"
}

$repos = @(
  "https://github.com/city96/ComfyUI-GGUF.git",
  "https://github.com/kijai/ComfyUI-WanVideoWrapper.git",
  "https://github.com/cubiq/ComfyUI_IPAdapter_plus.git",
  "https://github.com/Kosinkadink/ComfyUI-VideoHelperSuite.git",
  "https://github.com/Fannovel16/ComfyUI-Frame-Interpolation.git"
)

Set-Location $Nodes
foreach ($url in $repos) {
  $name = [IO.Path]::GetFileNameWithoutExtension($url)
  $dest = Join-Path $Nodes $name
  if (Test-Path $dest) {
    Write-Host "[=] exists: $name"
    continue
  }
  Write-Host "[+] cloning $name"
  git clone --depth 1 $url $dest
}

Write-Host ""
Write-Host "Restart ComfyUI after this. Then install each node's requirements.txt if present."
Get-ChildItem $Nodes -Directory | ForEach-Object {
  $req = Join-Path $_.FullName "requirements.txt"
  if (Test-Path $req) {
    Write-Host "pip install -r `"$req`"   # $($_.Name)"
  }
}
