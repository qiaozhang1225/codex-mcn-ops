$ErrorActionPreference = "Stop"
. (Join-Path $PSScriptRoot "wx-channel-session-common.ps1")

$lease = Read-WxLease
if ($null -eq $lease -or [string]$lease.state -ne "cleanup_pending") {
    throw "interactive Channels cleanup requires a cleanup_pending lease"
}
Assert-WxPinnedArtifacts
Remove-WxPinnedCertificate
