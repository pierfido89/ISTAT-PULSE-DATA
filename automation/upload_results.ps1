# Upload ONLY quarantined editorial reports to a verified private GitHub repo.
# Token is single-repository, fine-grained and encrypted with Windows DPAPI.
param([switch]$Quiet)
Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"
$Root = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$Outbox = Join-Path $Root "workbench\local-automation-outbox"
$SecureFolder = Join-Path $env:LOCALAPPDATA "IstatPulseEditorialBridge"
$TokenFile = Join-Path $SecureFolder "github-upload-token.dpapi"
$TargetRepo = "pierfido89/ISTAT-PULSE-EDITORIAL-RESULTS"
$ApiBase = "https://api.github.com/repos/$TargetRepo"
if (!(Test-Path -LiteralPath $TokenFile) -or !(Test-Path -LiteralPath $Outbox)) { return }

function Get-Sha256([byte[]]$Bytes) {
    $Hasher = [Security.Cryptography.SHA256]::Create()
    try { return ([BitConverter]::ToString($Hasher.ComputeHash($Bytes))).Replace("-","").ToLowerInvariant() }
    finally { $Hasher.Dispose() }
}
$SecureToken = ConvertTo-SecureString -String ((Get-Content -LiteralPath $TokenFile -Raw).Trim())
$Ptr = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($SecureToken)
try { $Token = [Runtime.InteropServices.Marshal]::PtrToStringBSTR($Ptr) }
finally { [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($Ptr) }
try {
    $Headers = @{
        Authorization = "Bearer $Token"
        Accept = "application/vnd.github+json"
        "X-GitHub-Api-Version" = "2022-11-28"
        "User-Agent" = "IstatPulseEditorialBridge/0.2"
    }
    $TargetRepoData = Invoke-RestMethod -Method Get -Uri $ApiBase -Headers $Headers -TimeoutSec 20
    if ($TargetRepoData.full_name -cne $TargetRepo -or $TargetRepoData.private -ne $true) {
        throw "Destinazione non privata o diversa da quella consentita: upload bloccato."
    }
    if ($TargetRepoData.default_branch -ne "main") {
        throw "Il repository risultati deve avere branch predefinito main: upload bloccato."
    }
    function Confirm-OrCreateFile([string]$RemotePath, [byte[]]$Bytes) {
        if ($Bytes.Length -gt 750000) { throw "File maggiore di 750 KB: upload bloccato" }
        $Uri = "$ApiBase/contents/$RemotePath"
        $Existing = $null
        try { $Existing = Invoke-RestMethod -Method Get -Uri $Uri -Headers $Headers -TimeoutSec 20 }
        catch {
            $Status = [int]$_.Exception.Response.StatusCode
            if ($Status -ne 404) { throw }
        }
        if ($null -ne $Existing) {
            if ($Existing.encoding -ne "base64" -or !$Existing.content) { throw "File remoto non verificabile" }
            $OldBytes = [Convert]::FromBase64String(($Existing.content -replace "\s", ""))
            if ((Get-Sha256 $OldBytes) -cne (Get-Sha256 $Bytes)) {
                throw "Conflitto su $RemotePath: nessuna sovrascrittura"
            }
            return
        }
        $Payload = @{
            message = "editorial-lab: archive quarantined result $RemotePath"
            branch = "main"
            content = [Convert]::ToBase64String($Bytes)
        } | ConvertTo-Json -Compress
        $null = Invoke-RestMethod -Method Put -Uri $Uri -Headers $Headers -Body $Payload -ContentType "application/json" -TimeoutSec 45
    }

    foreach ($ReportFile in (Get-ChildItem -LiteralPath $Outbox -Filter "*.report.json" -File)) {
        $JobId = $ReportFile.Name -replace "\.report\.json$", ""
        if ($JobId -cnotmatch "^[a-z0-9](?:[a-z0-9-]{0,46}[a-z0-9])?$") { continue }
        $Marker = Join-Path $Outbox ($JobId + ".uploaded")
        if (Test-Path -LiteralPath $Marker) { continue }
        $ResultFile = Join-Path $Outbox ($JobId + ".json")
        if (!(Test-Path -LiteralPath $ResultFile)) { continue }
        try {
            $Report = Get-Content -LiteralPath $ReportFile.FullName -Raw | ConvertFrom-Json
            $Result = Get-Content -LiteralPath $ResultFile -Raw | ConvertFrom-Json
            if ($Report.job_id -cne $JobId -or $Report.status -cne "needs_human_review" -or
                $Report.published -ne $false -or $Report.human_review_required -ne $true -or
                $Report.model_expected -cne "qwen3.5:9b" -or
                $Result.published -ne $false -or
                $Result.cannot_promote_without_human_check -ne $true -or
                @($Result.rewrite_results).Count -ne [int]$Report.limit) {
                throw "Controlli di quarantena falliti"
            }
            $ResultBytes = [IO.File]::ReadAllBytes($ResultFile)
            $ReportBytes = [IO.File]::ReadAllBytes($ReportFile.FullName)
            if ((Get-Sha256 $ResultBytes) -cne $Report.result_sha256) {
                throw "SHA256 risultato non corrispondente"
            }
            Confirm-OrCreateFile -RemotePath "runs/$JobId/result.json" -Bytes $ResultBytes
            Confirm-OrCreateFile -RemotePath "runs/$JobId/report.json" -Bytes $ReportBytes
            Set-Content -LiteralPath $Marker -Value ("Uploaded " + (Get-Date).ToUniversalTime().ToString("o")) -Encoding UTF8
            if (!$Quiet) { Write-Host "Risultato archiviato privatamente: $JobId" }
        } catch {
            Write-Warning "Upload $JobId non completato: $($_.Exception.Message)"
            # Retry next pass; never fall back to public upload.
        }
    }
} finally {
    $Headers.Authorization = $null
    $Token = $null
    $SecureToken.Dispose()
}
