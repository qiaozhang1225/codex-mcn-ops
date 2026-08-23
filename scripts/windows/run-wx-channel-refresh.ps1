$ErrorActionPreference = "Stop"

$taskName = "CodexWxChannelRefresh"
$scriptPath = "D:\wx-channel-poc\refresh-wechat-channels.ps1"

if (Get-ScheduledTask -TaskName $taskName -ErrorAction SilentlyContinue) {
    Unregister-ScheduledTask -TaskName $taskName -Confirm:$false
}
$action = New-ScheduledTaskAction `
    -Execute "powershell.exe" `
    -Argument "-NoProfile -ExecutionPolicy Bypass -File `"$scriptPath`""
$principal = New-ScheduledTaskPrincipal `
    -UserId "WORKSTATION\qiaoz" `
    -LogonType Interactive `
    -RunLevel Highest
$settings = New-ScheduledTaskSettingsSet `
    -ExecutionTimeLimit (New-TimeSpan -Minutes 2)
Register-ScheduledTask `
    -TaskName $taskName `
    -Action $action `
    -Principal $principal `
    -Settings $settings | Out-Null
Start-ScheduledTask -TaskName $taskName

[ordered]@{
    task_name = $taskName
    started_at = (Get-Date).ToString("o")
} | ConvertTo-Json
