Describe "WeChat Channels acquisition session script contract" {
    BeforeAll {
        $scriptsDir = Split-Path -Parent $PSScriptRoot
        $paths = [ordered]@{
            common = Join-Path $scriptsDir "wx-channel-session-common.ps1"
            manage = Join-Path $scriptsDir "manage-wx-channel-session.ps1"
            cleanup = Join-Path $scriptsDir "cleanup-wx-channel-session.ps1"
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
        $sources.manage | Should Match 'ValidateSet\("Open", "Renew", "Status", "Close", "Recover"\)'
        foreach ($action in @("Open", "Renew", "Status", "Close", "Recover")) {
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
        $sources.common | Should Match "C5CFF437248220EDD113403987E6C3005136A23AEE2B410E09736DD26BD2B0EA"
        $sources.common | Should Match "wx_channel_cloud_hardened_v5.6.9.exe"
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
        $sources.common | Should Match 'certutil\.exe -user -delstore Root \$script:WxExpectedCertificateThumbprint'
    }

    It "records cleanup pending and failed states before retry" {
        $sources.common | Should Match 'state = "cleanup_pending"'
        $sources.common | Should Match 'state = "cleanup_failed"'
        $sources.watchdog | Should Match 'Reason "lease_timeout"'
        $sources.watchdog | Should Match 'TerminalState "expired"'
    }
}
