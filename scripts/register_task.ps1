# Registers a Windows Scheduled Task that runs the collector every 15 minutes.
# Run once from the project root:  powershell -ExecutionPolicy Bypass -File scripts\register_task.ps1
# Remove with:  Unregister-ScheduledTask -TaskName "FerryDelayCollector" -Confirm:$false

$ErrorActionPreference = "Stop"
$root   = Split-Path -Parent $PSScriptRoot
$python = Join-Path $root ".venv\Scripts\python.exe"
$name   = "FerryDelayCollector"

if (-not (Test-Path $python)) { throw "venv python not found at $python" }

$action  = New-ScheduledTaskAction -Execute $python -Argument "-m ferrydelay.collector" -WorkingDirectory $root
$trigger = New-ScheduledTaskTrigger -Once -At (Get-Date) `
             -RepetitionInterval (New-TimeSpan -Minutes 15) `
             -RepetitionDuration (New-TimeSpan -Days 3650)
$settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -DontStopOnIdleEnd `
             -MultipleInstances IgnoreNew
# Interactive: runs while the user session is logged on (survives an RDP
# disconnect / lock — only a full sign-out stops it). Needs no admin rights.
$principal = New-ScheduledTaskPrincipal -UserId "$env:USERDOMAIN\$env:USERNAME" `
             -LogonType Interactive -RunLevel Limited

Register-ScheduledTask -TaskName $name -Action $action -Trigger $trigger `
    -Settings $settings -Principal $principal `
    -Description "Poll met.no + Entur for ferry delay data" -Force | Out-Null

if (-not (Get-ScheduledTask -TaskName $name -ErrorAction SilentlyContinue)) {
    throw "Registration failed - task '$name' not found after Register-ScheduledTask."
}

Write-Host "Registered '$name' - collecting every 15 min. Data -> data\ferry.db"
