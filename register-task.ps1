# Register the daily CI/CD agent task in Windows Task Scheduler (current user, runs only while logged on).
# Usage:   .\register-task.ps1                 -> daily 18:00
#          .\register-task.ps1 -At '09:30'
#          .\register-task.ps1 -Remove         -> delete the task
# Keep ASCII-only (PowerShell 5.1).

param(
    [string]$At       = '18:00',
    [string]$TaskName = 'ResearchAI-CICD-Agent',
    [switch]$Remove
)

if ($Remove) {
    Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false
    Write-Host "Removed task $TaskName"
    exit 0
}

$script = Join-Path $PSScriptRoot 'run-agent.ps1'
$action = New-ScheduledTaskAction -Execute 'powershell.exe' `
    -Argument "-NoProfile -ExecutionPolicy Bypass -File `"$script`"" `
    -WorkingDirectory $PSScriptRoot
$trigger  = New-ScheduledTaskTrigger -Daily -At $At
$settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -ExecutionTimeLimit (New-TimeSpan -Minutes 30) -MultipleInstances IgnoreNew
Register-ScheduledTask -TaskName $TaskName -Action $action -Trigger $trigger -Settings $settings `
    -Description 'AI agent: commit and push changes to the test repo' -Force | Out-Null
Write-Host "Registered task $TaskName daily at $At. Test now with: Start-ScheduledTask -TaskName $TaskName"
