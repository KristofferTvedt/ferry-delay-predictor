# Registers a weekly Scheduled Task that snapshots the database (WAL-safe).
# Run once:  powershell -ExecutionPolicy Bypass -File scripts\register_backup_task.ps1
# Remove:    Unregister-ScheduledTask -TaskName "FerryDelayBackup" -Confirm:$false

$ErrorActionPreference = "Stop"
$root   = Split-Path -Parent $PSScriptRoot
$python = Join-Path $root ".venv\Scripts\python.exe"
$name   = "FerryDelayBackup"

if (-not (Test-Path $python)) { throw "venv python not found at $python" }

$action  = New-ScheduledTaskAction -Execute $python -Argument "-m ferrydelay.backup" -WorkingDirectory $root
$trigger = New-ScheduledTaskTrigger -Weekly -DaysOfWeek Sunday -At 3am
$settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -MultipleInstances IgnoreNew
$principal = New-ScheduledTaskPrincipal -UserId "$env:USERDOMAIN\$env:USERNAME" `
             -LogonType Interactive -RunLevel Limited

Register-ScheduledTask -TaskName $name -Action $action -Trigger $trigger `
    -Settings $settings -Principal $principal `
    -Description "Weekly WAL-safe snapshot of ferry.db" -Force | Out-Null

if (-not (Get-ScheduledTask -TaskName $name -ErrorAction SilentlyContinue)) {
    throw "Registration failed - task '$name' not found."
}
Write-Host "Registered '$name' - weekly snapshot Sundays 03:00 -> backups\"
