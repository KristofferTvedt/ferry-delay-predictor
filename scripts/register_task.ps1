# Registers a Windows Scheduled Task that runs the collector every 15 minutes.
# Uses pythonw.exe so no console window pops up on each run.
#
# Default (no admin):   powershell -ExecutionPolicy Bypass -File scripts\register_task.ps1
#   Runs only while you are logged on. A reboot to a logged-out state pauses it.
#
# Reboot-proof (admin):  run from an ELEVATED PowerShell, add -Background:
#   powershell -ExecutionPolicy Bypass -File scripts\register_task.ps1 -Background
#   Runs whether you are logged on or not, and fires again at every startup, so
#   reboots and the login screen no longer stop collection.
#
# Remove with:  Unregister-ScheduledTask -TaskName "FerryDelayCollector" -Confirm:$false

param([switch]$Background)

$ErrorActionPreference = "Stop"
$root   = Split-Path -Parent $PSScriptRoot
$python = Join-Path $root ".venv\Scripts\pythonw.exe"
$name   = "FerryDelayCollector"

if (-not (Test-Path $python)) { throw "venv pythonw not found at $python" }

if ($Background) {
    $isAdmin = ([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()
               ).IsInRole([Security.Principal.WindowsBuiltinRole]::Administrator)
    if (-not $isAdmin) {
        throw "-Background registers a 'run whether logged on or not' task and must be run from an elevated PowerShell (Run as administrator)."
    }
}

$action = New-ScheduledTaskAction -Execute $python -Argument "-m ferrydelay.collector" -WorkingDirectory $root

$triggers = @(
    New-ScheduledTaskTrigger -Once -At (Get-Date) `
        -RepetitionInterval (New-TimeSpan -Minutes 15) `
        -RepetitionDuration (New-TimeSpan -Days 3650)
)
# In background mode also fire right after boot, so a reboot resumes collection
# immediately instead of waiting for the next 15-minute slot.
if ($Background) { $triggers += New-ScheduledTaskTrigger -AtStartup }

$settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -DontStopOnIdleEnd `
             -MultipleInstances IgnoreNew

if ($Background) {
    # S4U: runs whether the user is logged on or not, no stored password, survives
    # reboots and sign-out. Registering it requires elevation.
    $principal = New-ScheduledTaskPrincipal -UserId "$env:USERDOMAIN\$env:USERNAME" `
                 -LogonType S4U -RunLevel Limited
} else {
    # Interactive: runs while the user session is logged on (survives an RDP
    # disconnect or lock; a full sign-out or reboot pauses it). Needs no admin.
    $principal = New-ScheduledTaskPrincipal -UserId "$env:USERDOMAIN\$env:USERNAME" `
                 -LogonType Interactive -RunLevel Limited
}

Register-ScheduledTask -TaskName $name -Action $action -Trigger $triggers `
    -Settings $settings -Principal $principal `
    -Description "Poll met.no + Entur for ferry delay data" -Force | Out-Null

if (-not (Get-ScheduledTask -TaskName $name -ErrorAction SilentlyContinue)) {
    throw "Registration failed - task '$name' not found after Register-ScheduledTask."
}

$mode = if ($Background) { "background (whether logged on or not)" } else { "logged-on only" }
Write-Host "Registered '$name' - every 15 min, $mode. Data -> data\ferry.db"
