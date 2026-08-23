Describe "WeChat Channels acquisition session script contract" {
    BeforeAll {
        $scriptsDir = Split-Path -Parent $PSScriptRoot
        $paths = [ordered]@{
            common = Join-Path $scriptsDir "wx-channel-session-common.ps1"
            manage = Join-Path $scriptsDir "manage-wx-channel-session.ps1"
            cleanup = Join-Path $scriptsDir "cleanup-wx-channel-session.ps1"
            interactive_cleanup = Join-Path $scriptsDir "interactive-cleanup-wx-channel-session.ps1"
            refresh = Join-Path $scriptsDir "refresh-wechat-channels.ps1"
            watchdog = Join-Path $scriptsDir "watch-wx-channel-session-lease.ps1"
            bootstrap = Join-Path $scriptsDir "bootstrap-wx-channel-session.ps1"
            worker = Join-Path $scriptsDir "start-wx-channel-worker.ps1"
        }
        $sources = @{}
        foreach ($name in $paths.Keys) {
            $sources[$name] = Get-Content -LiteralPath $paths[$name] -Raw -Encoding utf8
        }
    }

    It "ships every production session script" {
        foreach ($path in $paths.Values) {
            Test-Path -LiteralPath $path | Should Be $true
        }
    }

    It "supports every task-bound session action" {
        $sources.manage | Should Match 'ValidateSet\("Open", "Renew", "Status", "Close", "Recover", "Refresh"\)'
        foreach ($action in @("Open", "Renew", "Status", "Close", "Recover", "Refresh")) {
            $sources.manage | Should Match "Invoke-Wx$action"
        }
        $sources.manage | Should Match "Assert-WxSessionIdentity"
        $sources.manage | Should Match "ExpectedGeneration"
    }

    It "reads worker secrets from stdin rather than command parameters" {
        $parameterBlock = ($sources.manage -split '\$ErrorActionPreference = "Stop"', 2)[0]
        $parameterBlock | Should Not Match "cloud_secret"
        $parameterBlock | Should Not Match "secret_token"
        $parameterBlock | Should Not Match "hub_url"
        $sources.manage | Should Match '\[Console\]::In.ReadToEnd\(\)'
    }

    It "pins certificate and worker identities" {
        $sources.common | Should Match "1A61D4F74DC31D27630B25E37AAF46C364955EDC7A6EA11EB20E4B6B05114E04"
        $sources.common | Should Match "D70CD039051F77C30673B8209FC15EFA650ED52C"
        $sources.common | Should Match "9681B3777A677D491BE15E248065909F78593A013C211C4176444D8F5B960584"
        $sources.common | Should Match "wx_channel_cloud_hardened_v5.6.9_share_v1.exe"
        $sources.common | Should Match "DEV-IyZU9C5DDMKxsY36"
        $sources.common | Should Match "GetFullPath"
    }

    It "uses a named mutex and atomic same-directory replacement" {
        $sources.common | Should Match 'Global\\CodexWxChannelSessionLeaseV1'
        $sources.common | Should Match "Write-WxAtomicJson"
        $sources.common | Should Match "Move-Item -LiteralPath"
        foreach ($name in @("manage", "cleanup", "watchdog", "bootstrap", "worker")) {
            $sources[$name] | Should Match "Enter-WxSessionMutex"
            $sources[$name] | Should Match "Exit-WxSessionMutex"
        }
    }

    It "never calls the broad PoC teardown or broad worker name matching" {
        $combined = $sources.Values -join "`n"
        $combined | Should Not Match "cleanup-wx-channel-poc.ps1"
        $combined | Should Not Match 'wx_channel_cloud\*\.exe'
        $combined | Should Not Match 'Get-Process\s+-Name\s+wx_channel'
        $sources.common | Should Match 'HKEY_CURRENT_USER\\Software\\Microsoft\\SystemCertificates'
        $sources.common | Should Match 'Remove-Item -LiteralPath \$certificateRegistryPath -Recurse -Force'
        $sources.common | Should Not Match 'certutil\.exe.*-delstore'
    }

    It "records cleanup pending and failed states before retry" {
        $sources.common | Should Match 'state = "cleanup_pending"'
        $sources.common | Should Match 'state = "cleanup_failed"'
        $sources.watchdog | Should Match 'Reason "lease_timeout"'
        $sources.watchdog | Should Match 'TerminalState "expired"'
    }

    It "dispatches the interactive worker through schtasks" {
        $sources.manage | Should Match 'schtasks\.exe /Run /TN \$script:WxWorkerTaskName'
        $sources.manage | Should Not Match 'Start-ScheduledTask -TaskName \$script:WxWorkerTaskName'
        $sources.manage | Should Match 'listener_count -gt 0'
        $sources.common | Should Match 'workerTask.State -eq "Running"'
        $sources.worker | Should Match 'Install-WxPinnedCertificate'
        $sources.manage | Should Not Match 'Install-WxPinnedCertificate'
        $sources.common | Should Match 'Start-WxInteractiveCleanupTask'
        $sources.interactive_cleanup | Should Match 'Remove-WxPinnedCertificate'
        $sources.refresh | Should Match 'SendKeys\("\^r"\)'
    }
}
