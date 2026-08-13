# Requires elevation. Sets Windows pagefile to System Managed (fix Wan MoE torch_cpu AV).
$ErrorActionPreference = "Stop"
Write-Host "Before:"
Get-CimInstance Win32_ComputerSystem | Select-Object AutomaticManagedPagefile | Format-List
Get-CimInstance Win32_PageFileUsage | Format-List Name, AllocatedBaseSize, CurrentUsage

$cs = Get-CimInstance Win32_ComputerSystem
if (-not $cs.AutomaticManagedPagefile) {
    $cs | Set-CimInstance -Property @{ AutomaticManagedPagefile = $true }
    Write-Host "Enabled AutomaticManagedPagefile = True"
} else {
    Write-Host "Already System Managed"
}

Write-Host "After:"
Get-CimInstance Win32_ComputerSystem | Select-Object AutomaticManagedPagefile | Format-List
Write-Host "DONE — reboot recommended before heavy Wan MoE."
pause
