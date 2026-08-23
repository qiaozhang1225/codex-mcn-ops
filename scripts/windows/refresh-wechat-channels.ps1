$ErrorActionPreference = "Stop"

$resultPath = "D:\wx-channel-poc\refresh-result.json"
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
    process_id = $process.Id
    refreshed_at = (Get-Date).ToString("o")
} | ConvertTo-Json | Set-Content -LiteralPath $resultPath -Encoding utf8
