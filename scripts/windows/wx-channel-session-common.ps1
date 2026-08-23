$script:WxWorkDir = "D:\wx-channel-poc"
$script:WxSessionDir = Join-Path $script:WxWorkDir "session"
$script:WxLeasePath = Join-Path $script:WxSessionDir "lease.json"
$script:WxConfigPath = Join-Path $script:WxWorkDir "config.yaml"
$script:WxCertificatePath = Join-Path $script:WxWorkDir "SunnyRoot-poc.cer"
$script:WxWorkerPath = Join-Path $script:WxWorkDir "wx_channel_cloud_hardened_v5.6.9.exe"
$script:WxWorkerTaskName = "CodexWxChannelWorker"
$script:WxInteractiveCleanupTaskName = "CodexWxChannelInteractiveCleanup"
$script:WxRefreshTaskName = "CodexWxChannelRefresh"
$script:WxRefreshResultPath = Join-Path $script:WxSessionDir "refresh-result.json"
$script:WxWatchdogTaskName = "CodexWxChannelLeaseGuard"
$script:WxMutexName = "Global\CodexWxChannelSessionLeaseV1"
$script:WxExpectedCertificateSha256 = "1A61D4F74DC31D27630B25E37AAF46C364955EDC7A6EA11EB20E4B6B05114E04"
$script:WxExpectedCertificateThumbprint = "D70CD039051F77C30673B8209FC15EFA650ED52C"
$script:WxExpectedWorkerSha256 = "C5CFF437248220EDD113403987E6C3005136A23AEE2B410E09736DD26BD2B0EA"

function Enter-WxSessionMutex {
    param([int]$TimeoutSeconds = 30)

    $mutex = New-Object System.Threading.Mutex($false, $script:WxMutexName)
    try {
        $acquired = $mutex.WaitOne([TimeSpan]::FromSeconds($TimeoutSeconds))
    } catch [System.Threading.AbandonedMutexException] {
        $acquired = $true
    }
    if (!$acquired) {
        $mutex.Dispose()
        throw "timed out waiting for the Channels session mutex"
    }
    return $mutex
}

function Exit-WxSessionMutex {
    param([System.Threading.Mutex]$Mutex)

    if ($null -ne $Mutex) {
        try {
            $Mutex.ReleaseMutex()
        } finally {
            $Mutex.Dispose()
        }
    }
}

function Write-WxAtomicText {
    param(
        [Parameter(Mandatory = $true)][string]$Path,
        [Parameter(Mandatory = $true)][AllowEmptyString()][string]$Value
    )

    $parent = Split-Path -Parent $Path
    New-Item -ItemType Directory -Path $parent -Force | Out-Null
    $temporaryPath = Join-Path $parent (".{0}.{1}.tmp" -f [IO.Path]::GetFileName($Path), [Guid]::NewGuid().ToString("N"))
    try {
        Set-Content -LiteralPath $temporaryPath -Value $Value -Encoding utf8
        Move-Item -LiteralPath $temporaryPath -Destination $Path -Force
    } finally {
        if (Test-Path -LiteralPath $temporaryPath) {
            Remove-Item -LiteralPath $temporaryPath -Force
        }
    }
}

function Write-WxAtomicJson {
    param(
        [Parameter(Mandatory = $true)][string]$Path,
        [Parameter(Mandatory = $true)]$Value
    )

    Write-WxAtomicText -Path $Path -Value ($Value | ConvertTo-Json -Depth 8)
}

function Read-WxLease {
    if (!(Test-Path -LiteralPath $script:WxLeasePath)) {
        return $null
    }
    try {
        return Get-Content -LiteralPath $script:WxLeasePath -Raw -Encoding utf8 | ConvertFrom-Json
    } catch {
        throw "Channels lease file is invalid JSON"
    }
}

function Test-WxLeaseExpired {
    param([Parameter(Mandatory = $true)]$Lease)

    try {
        $expiresAt = [DateTimeOffset]::Parse([string]$Lease.expires_at).ToUniversalTime()
    } catch {
        return $true
    }
    return $expiresAt -le [DateTimeOffset]::UtcNow
}

function Assert-WxSessionIdentity {
    param(
        [Parameter(Mandatory = $true)]$Lease,
        [Parameter(Mandatory = $true)][string]$SessionId,
        [Parameter(Mandatory = $true)][long]$ExpectedGeneration
    )

    if ([string]$Lease.session_id -cne $SessionId) {
        throw "session id mismatch"
    }
    if ([long]$Lease.generation -ne $ExpectedGeneration) {
        throw "lease generation mismatch"
    }
}

function Assert-WxPinnedArtifacts {
    if (!(Test-Path -LiteralPath $script:WxCertificatePath)) {
        throw "pinned SunnyNet certificate file is missing"
    }
    if ((Get-FileHash -Algorithm SHA256 -LiteralPath $script:WxCertificatePath).Hash -cne $script:WxExpectedCertificateSha256) {
        throw "SunnyNet certificate SHA256 mismatch"
    }
    $certificate = New-Object System.Security.Cryptography.X509Certificates.X509Certificate2($script:WxCertificatePath)
    if ($certificate.Thumbprint -cne $script:WxExpectedCertificateThumbprint) {
        throw "SunnyNet certificate thumbprint mismatch"
    }
    if (!(Test-Path -LiteralPath $script:WxWorkerPath)) {
        throw "pinned Channels worker executable is missing"
    }
    if ((Get-FileHash -Algorithm SHA256 -LiteralPath $script:WxWorkerPath).Hash -cne $script:WxExpectedWorkerSha256) {
        throw "Channels worker SHA256 mismatch"
    }
    $blockRule = Get-NetFirewallRule -Name "Codex-WxChannel-PoC-Block-Inbound" -ErrorAction Stop
    if (!$blockRule.Enabled -or [string]$blockRule.Action -ne "Block") {
        throw "required Channels inbound block rule is not enabled"
    }
}

function Get-WxPinnedWorkerProcesses {
    return @(
        Get-CimInstance Win32_Process -ErrorAction SilentlyContinue |
            Where-Object {
                $_.ExecutablePath -and
                [string]::Equals(
                    [IO.Path]::GetFullPath([string]$_.ExecutablePath),
                    [IO.Path]::GetFullPath($script:WxWorkerPath),
                    [StringComparison]::OrdinalIgnoreCase
                )
            }
    )
}

function Get-WxCertificateCounts {
    return [ordered]@{
        current_user = @(
            Get-ChildItem Cert:\CurrentUser\Root |
                Where-Object Thumbprint -eq $script:WxExpectedCertificateThumbprint
        ).Count
        local_machine = @(
            Get-ChildItem Cert:\LocalMachine\Root |
                Where-Object Thumbprint -eq $script:WxExpectedCertificateThumbprint
        ).Count
    }
}

function Install-WxPinnedCertificate {
    Assert-WxPinnedArtifacts
    $counts = Get-WxCertificateCounts
    if ([int]$counts.local_machine -ne 0) {
        throw "pinned SunnyNet certificate unexpectedly exists in LocalMachine Root"
    }
    if ([int]$counts.current_user -eq 0) {
        $certificate = New-Object System.Security.Cryptography.X509Certificates.X509Certificate2($script:WxCertificatePath)
        $store = New-Object System.Security.Cryptography.X509Certificates.X509Store(
            "Root",
            [System.Security.Cryptography.X509Certificates.StoreLocation]::CurrentUser
        )
        try {
            $store.Open([System.Security.Cryptography.X509Certificates.OpenFlags]::ReadWrite)
            $store.Add($certificate)
        } finally {
            $store.Close()
        }
    }
    $verifiedCounts = Get-WxCertificateCounts
    if ([int]$verifiedCounts.current_user -ne 1 -or [int]$verifiedCounts.local_machine -ne 0) {
        throw "SunnyNet certificate was not isolated to CurrentUser Root"
    }
}

function Remove-WxPinnedCertificate {
    $counts = Get-WxCertificateCounts
    if ([int]$counts.local_machine -gt 0) {
        throw "refusing cleanup because the pinned SunnyNet certificate exists in LocalMachine Root"
    }
    if ([int]$counts.current_user -gt 0) {
        & certutil.exe -user -delstore Root $script:WxExpectedCertificateThumbprint | Out-Null
        if ($LASTEXITCODE -ne 0) {
            throw "failed to remove pinned SunnyNet certificate from CurrentUser Root"
        }
    }
}

function Start-WxInteractiveCleanupTask {
    & schtasks.exe /Run /TN $script:WxInteractiveCleanupTaskName | Out-Null
    if ($LASTEXITCODE -ne 0) {
        throw "failed to dispatch the interactive Channels cleanup task"
    }
    # Interactive scheduled tasks can remain queued for longer than 30 seconds
    # while the signed-in desktop is busy. Keep this below the Mac-side 120s SSH
    # command timeout, but long enough to avoid reporting a false cleanup failure
    # after the exact worker and listeners have already stopped.
    $deadline = [DateTimeOffset]::UtcNow.AddSeconds(90)
    do {
        Start-Sleep -Milliseconds 500
        $counts = Get-WxCertificateCounts
        $task = Get-ScheduledTask -TaskName $script:WxInteractiveCleanupTaskName -ErrorAction SilentlyContinue
        if ([int]$counts.current_user -eq 0 -and $task -and [string]$task.State -ne "Running") {
            return
        }
    } while ([DateTimeOffset]::UtcNow -lt $deadline)
    throw "interactive Channels certificate cleanup did not complete"
}

function Assert-WxSecretValue {
    param(
        [Parameter(Mandatory = $true)][string]$Label,
        [Parameter(Mandatory = $true)][string]$Value
    )

    if ($Value -notmatch '^[A-Za-z0-9._~-]{32,256}$') {
        throw "$Label must be 32-256 URL-safe characters"
    }
}

function Get-WxLeaseWindow {
    param([Parameter(Mandatory = $true)]$Payload)

    try {
        $ttlSeconds = [int]$Payload.ttl_seconds
    } catch {
        throw "ttl_seconds must be an integer"
    }
    if ($ttlSeconds -lt 300 -or $ttlSeconds -gt 14400) {
        throw "ttl_seconds must be between 300 and 14400"
    }
    return [DateTimeOffset]::UtcNow.AddSeconds($ttlSeconds)
}

function Assert-WxHubUrl {
    param([Parameter(Mandatory = $true)][string]$HubUrl)

    $uri = $null
    if (![Uri]::TryCreate($HubUrl, [UriKind]::Absolute, [ref]$uri)) {
        throw "hub_url must be an absolute URI"
    }
    if ($uri.Scheme -notin @("ws", "wss") -or $uri.AbsolutePath -ne "/ws/client") {
        throw "hub_url must use ws/wss and end with /ws/client"
    }
}

function Write-WxWorkerConfig {
    param([Parameter(Mandatory = $true)]$Payload)

    $hubUrl = [string]$Payload.hub_url
    $cloudSecret = [string]$Payload.cloud_secret
    $secretToken = [string]$Payload.secret_token
    Assert-WxHubUrl -HubUrl $hubUrl
    Assert-WxSecretValue -Label "cloud_secret" -Value $cloudSecret
    Assert-WxSecretValue -Label "secret_token" -Value $secretToken
    $config = @"
port: 2025
download_dir: "D:/wx-channel-poc/downloads"
log_file: "D:/wx-channel-poc/logs/wx_channel.log"
max_log_size_mb: 2
save_page_snapshot: false
save_page_js: false
enable_log_interception: false
cloud_enabled: true
cloud_hub_url: "$hubUrl"
cloud_secret: "$cloudSecret"
machine_id: "DEV-IyZU9C5DDMKxsY36"
secret_token: "$secretToken"
allowed_origins:
  - "https://channels.weixin.qq.com"
radar_enabled: false
metrics_enabled: false
hub_sync:
  enabled: false
  push_enabled: false
"@
    Write-WxAtomicText -Path $script:WxConfigPath -Value $config
}

function Write-WxSafeConfig {
    $config = @'
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
machine_id: "DEV-IyZU9C5DDMKxsY36"
secret_token: ""
allowed_origins:
  - "https://channels.weixin.qq.com"
radar_enabled: false
metrics_enabled: false
hub_sync:
  enabled: false
  push_enabled: false
'@
    Write-WxAtomicText -Path $script:WxConfigPath -Value $config
}

function Get-WxSanitizedStatus {
    param($Lease = $null)

    if ($null -eq $Lease) {
        $Lease = Read-WxLease
    }
    $counts = Get-WxCertificateCounts
    $workerProcesses = Get-WxPinnedWorkerProcesses
    $workerTask = Get-ScheduledTask -TaskName $script:WxWorkerTaskName -ErrorAction SilentlyContinue
    $workerCount = if ($workerProcesses.Count -gt 0) {
        $workerProcesses.Count
    } elseif ($workerTask -and [string]$workerTask.State -eq "Running") {
        # The interactive task runs elevated. A UAC-filtered SSH token cannot
        # read its ExecutablePath, but the pinned task remains Running for the
        # exact lifetime of the worker wrapper.
        1
    } else {
        0
    }
    $listeners = @(
        Get-NetTCPConnection -LocalPort 2025, 2026 -State Listen -ErrorAction SilentlyContinue
    )
    return [ordered]@{
        session_present = $null -ne $Lease
        session_id = if ($null -ne $Lease) { [string]$Lease.session_id } else { $null }
        task_id = if ($null -ne $Lease) { [string]$Lease.task_id } else { $null }
        state = if ($null -ne $Lease) { [string]$Lease.state } else { "absent" }
        generation = if ($null -ne $Lease) { [long]$Lease.generation } else { 0 }
        expires_at = if ($null -ne $Lease) { [string]$Lease.expires_at } else { $null }
        expired = if ($null -ne $Lease) { Test-WxLeaseExpired -Lease $Lease } else { $false }
        current_user_certificate_count = [int]$counts.current_user
        local_machine_certificate_count = [int]$counts.local_machine
        worker_process_count = [int]$workerCount
        listener_count = $listeners.Count
        firewall_block_enabled = [bool](
            Get-NetFirewallRule -Name "Codex-WxChannel-PoC-Block-Inbound" -ErrorAction SilentlyContinue |
                Where-Object { $_.Enabled -eq "True" -and $_.Action -eq "Block" }
        )
        checked_at = [DateTimeOffset]::UtcNow.ToString("o")
    }
}

function Invoke-WxPinnedCleanup {
    param(
        [Parameter(Mandatory = $true)]$Lease,
        [Parameter(Mandatory = $true)][string]$Reason,
        [ValidateSet("cleaned", "expired")][string]$TerminalState = "cleaned"
    )

    $pendingLease = [ordered]@{
        schema_version = 1
        session_id = [string]$Lease.session_id
        task_id = [string]$Lease.task_id
        generation = [long]$Lease.generation
        state = "cleanup_pending"
        expires_at = [string]$Lease.expires_at
        renewed_at = [string]$Lease.renewed_at
        closed_at = $null
        cleanup_reason = $Reason
    }
    Write-WxAtomicJson -Path $script:WxLeasePath -Value $pendingLease
    try {
        if (Get-ScheduledTask -TaskName $script:WxWorkerTaskName -ErrorAction SilentlyContinue) {
            Stop-ScheduledTask -TaskName $script:WxWorkerTaskName -ErrorAction SilentlyContinue
        }
        if (Get-ScheduledTask -TaskName $script:WxRefreshTaskName -ErrorAction SilentlyContinue) {
            Stop-ScheduledTask -TaskName $script:WxRefreshTaskName -ErrorAction SilentlyContinue
        }
        $workerProcesses = Get-WxPinnedWorkerProcesses
        if ($workerProcesses.Count -gt 0) {
            if (!(Test-Path -LiteralPath $script:WxWorkerPath)) {
                throw "refusing to stop worker because pinned executable is missing"
            }
            if ((Get-FileHash -Algorithm SHA256 -LiteralPath $script:WxWorkerPath).Hash -cne $script:WxExpectedWorkerSha256) {
                throw "refusing to stop worker because executable SHA256 changed"
            }
            foreach ($process in $workerProcesses) {
                Stop-Process -Id $process.ProcessId -Force -ErrorAction Stop
            }
        }
        Start-WxInteractiveCleanupTask
        Write-WxSafeConfig
        if (Test-Path -LiteralPath $script:WxRefreshResultPath) {
            Remove-Item -LiteralPath $script:WxRefreshResultPath -Force
        }
    } catch {
        $failedLease = [ordered]@{
            schema_version = 1
            session_id = [string]$Lease.session_id
            task_id = [string]$Lease.task_id
            generation = [long]$Lease.generation
            state = "cleanup_failed"
            expires_at = [string]$Lease.expires_at
            renewed_at = [string]$Lease.renewed_at
            closed_at = $null
            cleanup_reason = $Reason
            last_error = [string]$_.Exception.Message
        }
        Write-WxAtomicJson -Path $script:WxLeasePath -Value $failedLease
        throw
    }

    $closedAt = [DateTimeOffset]::UtcNow.ToString("o")
    $terminalLease = [ordered]@{
        schema_version = 1
        session_id = [string]$Lease.session_id
        task_id = [string]$Lease.task_id
        generation = [long]$Lease.generation
        state = $TerminalState
        expires_at = [string]$Lease.expires_at
        renewed_at = [string]$Lease.renewed_at
        closed_at = $closedAt
        cleanup_reason = $Reason
    }
    Write-WxAtomicJson -Path $script:WxLeasePath -Value $terminalLease
    Start-Sleep -Milliseconds 500
    $status = Get-WxSanitizedStatus -Lease $terminalLease
    $verified = (
        [int]$status.current_user_certificate_count -eq 0 -and
        [int]$status.local_machine_certificate_count -eq 0 -and
        [int]$status.worker_process_count -eq 0 -and
        [int]$status.listener_count -eq 0
    )
    return [ordered]@{
        ok = $verified
        action = "cleanup"
        reason = $Reason
        status = $status
    }
}
