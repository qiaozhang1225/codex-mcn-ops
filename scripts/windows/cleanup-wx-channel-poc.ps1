$ErrorActionPreference = "Stop"

$workDir = "D:\wx-channel-poc"
$thumbprint = "D70CD039051F77C30673B8209FC15EFA650ED52C"
$resultPath = Join-Path $workDir "cleanup-result.json"

$result = [ordered]@{
    stopped_worker = $false
    removed_certificates = @()
    removed_tasks = @()
    removed_files = @()
}

$workerTask = Get-ScheduledTask -TaskName "CodexWxChannelPoC" -ErrorAction SilentlyContinue
if ($workerTask) {
    Stop-ScheduledTask -TaskName "CodexWxChannelPoC" -ErrorAction SilentlyContinue
}
$workerProcesses = @(
    Get-CimInstance Win32_Process -ErrorAction SilentlyContinue |
        Where-Object {
            $_.ExecutablePath -and
            $_.ExecutablePath.StartsWith($workDir, [StringComparison]::OrdinalIgnoreCase) -and
            [IO.Path]::GetFileName($_.ExecutablePath) -like "wx_channel_cloud*.exe"
        }
)
foreach ($process in $workerProcesses) {
    Stop-Process -Id $process.ProcessId -Force -ErrorAction SilentlyContinue
}
Start-Sleep -Seconds 2
$result.stopped_worker = @(
    Get-CimInstance Win32_Process -ErrorAction SilentlyContinue |
        Where-Object {
            $_.ExecutablePath -and
            $_.ExecutablePath.StartsWith($workDir, [StringComparison]::OrdinalIgnoreCase) -and
            [IO.Path]::GetFileName($_.ExecutablePath) -like "wx_channel_cloud*.exe"
        }
).Count -eq 0

# Remove only the pinned SunnyNet certificate. certutil is used instead of the
# PowerShell certificate provider because Remove-Item may require interactive UI
# even when the cleanup task is elevated.
if (@(Get-ChildItem Cert:\CurrentUser\Root | Where-Object Thumbprint -eq $thumbprint).Count) {
    & certutil.exe -user -delstore Root $thumbprint | Out-Null
    if ($LASTEXITCODE -ne 0) {
        throw "failed to remove SunnyNet certificate from CurrentUser Root"
    }
    $result.removed_certificates += "Cert:\CurrentUser\Root\$thumbprint"
}
if (@(Get-ChildItem Cert:\LocalMachine\Root | Where-Object Thumbprint -eq $thumbprint).Count) {
    & certutil.exe -delstore Root $thumbprint | Out-Null
    if ($LASTEXITCODE -ne 0) {
        throw "failed to remove SunnyNet certificate from LocalMachine Root"
    }
    $result.removed_certificates += "Cert:\LocalMachine\Root\$thumbprint"
}

$safeConfig = @'
port: 2025
download_dir: "D:/wx-channel-poc/downloads"
log_file: "D:/wx-channel-poc/logs/wx_channel.log"
max_log_size_mb: 2
save_page_snapshot: false
save_page_js: false
enable_log_interception: false
cloud_enabled: false
cloud_hub_url: ""
cloud_secret: ""
machine_id: "workstation-channels-01"
secret_token: ""
allowed_origins:
  - "https://channels.weixin.qq.com"
radar_enabled: false
metrics_enabled: false
hub_sync:
  enabled: false
  push_enabled: false
'@
Set-Content -LiteralPath (Join-Path $workDir "config.yaml") -Value $safeConfig -Encoding utf8

foreach ($logPath in @(
    (Join-Path $workDir "worker-console.log"),
    (Join-Path $workDir "worker-stderr.log"),
    (Join-Path $workDir "worker-stdout.log"),
    (Join-Path $workDir "logs\wx_channel.log")
)) {
    if (Test-Path -LiteralPath $logPath) {
        Set-Content -LiteralPath $logPath -Value "" -Encoding utf8
    }
}

foreach ($filePath in @(
    (Join-Path $workDir "cert-cleanup-status.txt"),
    (Join-Path $workDir "cert-install-result.json"),
    (Join-Path $workDir "cert-confirm-result.json"),
    (Join-Path $workDir "cert-confirm-hwnd-result.json"),
    (Join-Path $workDir "cleanup-cert.ps1"),
    (Join-Path $workDir "confirm-cert.ps1"),
    (Join-Path $workDir "confirm-cert-hwnd.ps1"),
    (Join-Path $workDir "debug.ps1"),
    (Join-Path $workDir "dialog-windows.json"),
    (Join-Path $workDir "enum-windows.ps1"),
    (Join-Path $workDir "enum-dialogs.ps1"),
    (Join-Path $workDir "inspect.ps1"),
    (Join-Path $workDir "install-cert.ps1"),
    (Join-Path $workDir "refresh-page.ps1"),
    (Join-Path $workDir "refresh-result.json"),
    (Join-Path $workDir "register-cert-task.ps1"),
    (Join-Path $workDir "register-enum-task.ps1"),
    (Join-Path $workDir "register-refresh-task.ps1"),
    (Join-Path $workDir "windows.json"),
    (Join-Path $workDir "wx_channel_cloud.exe"),
    (Join-Path $workDir "downloads\records.db"),
    (Join-Path $workDir "downloads\records.db-shm"),
    (Join-Path $workDir "downloads\records.db-wal")
)) {
    if (Test-Path -LiteralPath $filePath) {
        Remove-Item -LiteralPath $filePath -Force
        $result.removed_files += $filePath
    }
}

foreach ($taskName in @(
    "CodexLaunchWeixin",
    "CodexWxChannelCertConfirm",
    "CodexWxChannelCertConfirmHwnd",
    "CodexWxChannelCertCleanup",
    "CodexWxChannelCertInstall",
    "CodexWxChannelEnumDialogs",
    "CodexWxChannelEnumWindows",
    "CodexWxChannelRefresh"
)) {
    if (Get-ScheduledTask -TaskName $taskName -ErrorAction SilentlyContinue) {
        Unregister-ScheduledTask -TaskName $taskName -Confirm:$false
        $result.removed_tasks += $taskName
    }
}

$result.current_user_certificate_count = @(
    Get-ChildItem Cert:\CurrentUser\Root | Where-Object Thumbprint -eq $thumbprint
).Count
$result.local_machine_certificate_count = @(
    Get-ChildItem Cert:\LocalMachine\Root | Where-Object Thumbprint -eq $thumbprint
).Count
$result.listener_count = @(
    Get-NetTCPConnection -LocalPort 2025,2026 -State Listen -ErrorAction SilentlyContinue
).Count
$result.media_file_count = @(
    Get-ChildItem -LiteralPath (Join-Path $workDir "downloads") -File -ErrorAction SilentlyContinue |
        Where-Object Extension -in ".mp4", ".mov", ".m4a", ".mp3", ".wav"
).Count
$proxy = Get-ItemProperty "HKCU:\Software\Microsoft\Windows\CurrentVersion\Internet Settings"
$result.wininet_proxy_enabled = [int]$proxy.ProxyEnable
$result.wininet_proxy_server = [string]$proxy.ProxyServer
$result.firewall_block_enabled = [bool](
    Get-NetFirewallRule -Name "Codex-WxChannel-PoC-Block-Inbound" -ErrorAction Stop |
        Where-Object { $_.Enabled -eq "True" -and $_.Action -eq "Block" }
)
$result.completed_at = (Get-Date).ToString("o")

$result | ConvertTo-Json -Depth 5 | Set-Content -LiteralPath $resultPath -Encoding utf8
