$ErrorActionPreference = "Stop"
. (Join-Path $PSScriptRoot "wx-channel-session-common.ps1")

$lease = Read-WxLease
if ($null -eq $lease -or [string]$lease.state -ne "active") {
    throw "WeChat Channels refresh requires an active acquisition lease"
}
$counts = Get-WxCertificateCounts
if ([int]$counts.current_user -ne 1 -or [int]$counts.local_machine -ne 0) {
    throw "WeChat Channels refresh requires the isolated CurrentUser certificate"
}
$process = Get-Process WeChatAppEx -ErrorAction SilentlyContinue |
    Where-Object { $_.MainWindowHandle -ne 0 -and $_.MainWindowTitle } |
    Select-Object -First 1
if (!$process) {
    throw "visible WeChat Channels process was not found"
}
$shell = New-Object -ComObject WScript.Shell
$activated = $shell.AppActivate($process.Id)
if (!$activated) {
    throw "failed to activate WeChat Channels window"
}
Start-Sleep -Milliseconds 500
$shell.SendKeys("^r")

[ordered]@{
    ok = $true
    session_id = [string]$lease.session_id
    generation = [long]$lease.generation
    process_id = $process.Id
    refreshed_at = (Get-Date).ToString("o")
} | ForEach-Object { Write-WxAtomicJson -Path $script:WxRefreshResultPath -Value $_ }
