$ErrorActionPreference = "Stop"

$certificatePath = "D:\wx-channel-poc\SunnyRoot-poc.cer"
$resultPath = "D:\wx-channel-poc\cert-install-result.json"
$expectedSha256 = "1A61D4F74DC31D27630B25E37AAF46C364955EDC7A6EA11EB20E4B6B05114E04"
$expectedThumbprint = "D70CD039051F77C30673B8209FC15EFA650ED52C"

if (!(Test-Path -LiteralPath $certificatePath)) {
    throw "SunnyNet certificate file is missing"
}
if ((Get-FileHash -Algorithm SHA256 -LiteralPath $certificatePath).Hash -ne $expectedSha256) {
    throw "SunnyNet certificate SHA256 mismatch"
}
$certificate = New-Object System.Security.Cryptography.X509Certificates.X509Certificate2(
    $certificatePath
)
if ($certificate.Thumbprint -ne $expectedThumbprint) {
    throw "SunnyNet certificate thumbprint mismatch"
}

$existing = Get-ChildItem Cert:\CurrentUser\Root |
    Where-Object Thumbprint -eq $expectedThumbprint
if (!$existing) {
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

$result = [ordered]@{
    thumbprint = $expectedThumbprint
    current_user_count = @(
        Get-ChildItem Cert:\CurrentUser\Root | Where-Object Thumbprint -eq $expectedThumbprint
    ).Count
    local_machine_count = @(
        Get-ChildItem Cert:\LocalMachine\Root | Where-Object Thumbprint -eq $expectedThumbprint
    ).Count
    installed_at = (Get-Date).ToString("o")
}
if ($result.current_user_count -ne 1 -or $result.local_machine_count -ne 0) {
    throw "SunnyNet certificate was not isolated to CurrentUser Root"
}
$result | ConvertTo-Json | Set-Content -LiteralPath $resultPath -Encoding utf8
