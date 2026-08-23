param(
    [string]$InteractiveUser = "WORKSTATION\qiaoz"
)

$ErrorActionPreference = "Stop"
. (Join-Path $PSScriptRoot "wx-channel-session-common.ps1")

if ($InteractiveUser -cne "WORKSTATION\qiaoz") {
    throw "bootstrap is pinned to WORKSTATION\qiaoz"
}

$requiredScripts = @(
    "wx-channel-session-common.ps1",
    "manage-wx-channel-session.ps1",
    "cleanup-wx-channel-session.ps1",
    "watch-wx-channel-session-lease.ps1",
    "start-wx-channel-worker.ps1"
)
foreach ($scriptName in $requiredScripts) {
    $scriptPath = Join-Path $script:WxWorkDir $scriptName
    if (!(Test-Path -LiteralPath $scriptPath)) {
        throw "required production script is missing: $scriptPath"
    }
}

$mutex = $null
try {
    $mutex = Enter-WxSessionMutex
    $existingLease = Read-WxLease
    if ($null -ne $existingLease -and [string]$existingLease.state -notin @("cleaned", "expired")) {
        throw "refusing to bootstrap while a non-terminal Channels session exists"
    }
    Assert-WxPinnedArtifacts
    New-Item -ItemType Directory -Path $script:WxSessionDir -Force | Out-Null
    New-Item -ItemType Directory -Path (Join-Path $script:WxWorkDir "logs") -Force | Out-Null
    New-Item -ItemType Directory -Path (Join-Path $script:WxWorkDir "downloads") -Force | Out-Null
    Write-WxSafeConfig

    & icacls.exe $script:WxSessionDir /inheritance:r `
        /grant:r "${InteractiveUser}:(OI)(CI)F" `
        /grant:r "*S-1-5-32-544:(OI)(CI)F" `
        /grant:r "*S-1-5-18:(OI)(CI)F" | Out-Null
    if ($LASTEXITCODE -ne 0) {
        throw "failed to restrict Channels session directory ACL"
    }
    & icacls.exe $script:WxConfigPath /inheritance:r `
        /grant:r "${InteractiveUser}:F" `
        /grant:r "*S-1-5-32-544:F" `
        /grant:r "*S-1-5-18:F" | Out-Null
    if ($LASTEXITCODE -ne 0) {
        throw "failed to restrict Channels config ACL"
    }

    $principal = New-ScheduledTaskPrincipal `
        -UserId $InteractiveUser `
        -LogonType Interactive `
        -RunLevel Highest

    $workerAction = New-ScheduledTaskAction `
        -Execute "powershell.exe" `
        -Argument "-NoProfile -NonInteractive -ExecutionPolicy Bypass -File `"D:\wx-channel-poc\start-wx-channel-worker.ps1`""
    $workerSettings = New-ScheduledTaskSettingsSet `
        -AllowStartIfOnBatteries `
        -DontStopIfGoingOnBatteries `
        -ExecutionTimeLimit ([TimeSpan]::Zero)
    if (Get-ScheduledTask -TaskName $script:WxWorkerTaskName -ErrorAction SilentlyContinue) {
        Unregister-ScheduledTask -TaskName $script:WxWorkerTaskName -Confirm:$false
    }
    Register-ScheduledTask `
        -TaskName $script:WxWorkerTaskName `
        -Action $workerAction `
        -Principal $principal `
        -Settings $workerSettings | Out-Null

    $watchdogAction = New-ScheduledTaskAction `
        -Execute "powershell.exe" `
        -Argument "-NoProfile -NonInteractive -ExecutionPolicy Bypass -File `"D:\wx-channel-poc\watch-wx-channel-session-lease.ps1`""
    $watchdogTriggers = @(
        (New-ScheduledTaskTrigger -AtLogOn -User $InteractiveUser),
        (New-ScheduledTaskTrigger `
            -Once `
            -At ((Get-Date).AddMinutes(1)) `
            -RepetitionInterval (New-TimeSpan -Minutes 1) `
            -RepetitionDuration (New-TimeSpan -Days 3650))
    )
    $watchdogSettings = New-ScheduledTaskSettingsSet `
        -AllowStartIfOnBatteries `
        -DontStopIfGoingOnBatteries `
        -StartWhenAvailable `
        -ExecutionTimeLimit (New-TimeSpan -Minutes 5)
    if (Get-ScheduledTask -TaskName $script:WxWatchdogTaskName -ErrorAction SilentlyContinue) {
        Unregister-ScheduledTask -TaskName $script:WxWatchdogTaskName -Confirm:$false
    }
    Register-ScheduledTask `
        -TaskName $script:WxWatchdogTaskName `
        -Action $watchdogAction `
        -Trigger $watchdogTriggers `
        -Principal $principal `
        -Settings $watchdogSettings | Out-Null

    [ordered]@{
        ok = $true
        action = "bootstrap"
        worker_task = $script:WxWorkerTaskName
        watchdog_task = $script:WxWatchdogTaskName
        watchdog_interval_seconds = 60
        interactive_user = $InteractiveUser
        certificate_installed = $false
        completed_at = [DateTimeOffset]::UtcNow.ToString("o")
    } | ConvertTo-Json -Depth 5
} finally {
    Exit-WxSessionMutex -Mutex $mutex
}
