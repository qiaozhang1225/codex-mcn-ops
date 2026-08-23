$ErrorActionPreference = "Stop"

$workDir = "D:\wx-channel-poc"
$exePath = Join-Path $workDir "wx_channel_cloud_hardened_v5.6.9.exe"
$configPath = Join-Path $workDir "config.yaml"
$consoleLog = Join-Path $workDir "worker-console.log"
$expectedSha256 = "C5CFF437248220EDD113403987E6C3005136A23AEE2B410E09736DD26BD2B0EA"

if (!(Test-Path $exePath) -or !(Test-Path $configPath)) {
    throw "worker executable or config is missing"
}
if ((Get-FileHash -Algorithm SHA256 -LiteralPath $exePath).Hash -ne $expectedSha256) {
    throw "worker executable SHA256 mismatch"
}

$blockRule = Get-NetFirewallRule -Name "Codex-WxChannel-PoC-Block-Inbound" -ErrorAction Stop
if (!$blockRule.Enabled -or [string]$blockRule.Action -ne "Block") {
    throw "required inbound block rule is not enabled"
}

Get-Process -Name wx_channel_cloud,wx_channel_cloud_hardened_v5.6.9 -ErrorAction SilentlyContinue |
    Stop-Process -Force
New-Item -ItemType Directory -Path (Join-Path $workDir "logs") -Force | Out-Null
Set-Content -LiteralPath $consoleLog -Value "" -Encoding utf8
Set-Content -LiteralPath (Join-Path $workDir "logs\wx_channel.log") -Value "" -Encoding utf8

Set-Location $workDir
"[$(Get-Date -Format o)] hardened worker starting" | Add-Content -LiteralPath $consoleLog -Encoding utf8
& $exePath *>> $consoleLog
"[$(Get-Date -Format o)] worker exited with code $LASTEXITCODE" | Add-Content -LiteralPath $consoleLog -Encoding utf8
