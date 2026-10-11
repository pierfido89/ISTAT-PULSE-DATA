# One-time guided installer: no admin, no GitHub runner, no API subscriptions.
# PAT: fine-grained, selected repository only, Contents read/write; protected with DPAPI.
Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"
$Repo = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$StateDir = Join-Path $env:LOCALAPPDATA "IstatPulseEditorialBridge"
$TokenFile = Join-Path $StateDir "github-upload-token.dpapi"
$TargetRepo = "pierfido89/ISTAT-PULSE-EDITORIAL-RESULTS"
$TaskName = "ISTAT PULSE - Laboratorio editoriale locale"
New-Item -ItemType Directory -Path $StateDir -Force | Out-Null

Write-Host ""
Write-Host "=== ISTAT PULSE: CONFIGURAZIONE AUTOMATICA PROTETTA ===" -ForegroundColor Cyan
Write-Host "Il repository Android NON verra modificato."
Write-Host "Nessun self-hosted runner, nessun token nel codice, nessuna API AI a pagamento."
Write-Host ""
$branch = (& git -C $Repo branch --show-current).Trim()
if ($LASTEXITCODE -ne 0 -or $branch -cne "feat/pulse-editorial-ai-1.0") {
    throw "Branch locale non corretto: installazione interrotta."
}
& py (Join-Path $PSScriptRoot "pulse_local_agent.py") --dry-run
if ($LASTEXITCODE -ne 0) { throw "Il controllo locale non e riuscito: installazione interrotta." }

if (!(Test-Path -LiteralPath $TokenFile)) {
    Write-Host ""
    Write-Host "PRIMA AUTORIZZAZIONE: crea il repository su GitHub." -ForegroundColor Yellow
    Write-Host "1. Nome esatto: ISTAT-PULSE-EDITORIAL-RESULTS"
    Write-Host "2. Proprietario: pierfido89"
    Write-Host "3. Visibilita: PRIVATE (NON pubblico)"
    Write-Host "4. Seleziona Add README per inizializzare il branch main."
    Start-Process "https://github.com/new"
    $null = Read-Host "Dopo aver creato il repository privato, premi INVIO qui"
    Write-Host ""
    Write-Host "SECONDA AUTORIZZAZIONE: crea un GitHub Fine-grained personal access token." -ForegroundColor Yellow
    Write-Host "Resource owner: pierfido89"
    Write-Host "Repository access: ONLY selected repositories"
    Write-Host "Seleziona SOLO: ISTAT-PULSE-EDITORIAL-RESULTS"
    Write-Host "Repository permissions: Contents = Read and write; Metadata = Read (obbligatorio)."
    Write-Host "Nessun accesso ad Actions, Administration, Secrets o agli altri repository."
    Write-Host "Imposta una scadenza appropriata: alla scadenza il token andra rinnovato."
    Write-Host "Non incollare MAI il token nella chat."
    Start-Process "https://github.com/settings/personal-access-tokens/new"
    $Secret = Read-Host "Incolla qui il token SOLO in PowerShell (caratteri nascosti)" -AsSecureString
    $Encrypted = ConvertFrom-SecureString -SecureString $Secret
    Set-Content -LiteralPath $TokenFile -Value $Encrypted -Encoding ASCII
    $Secret.Dispose()
    Write-Host "Token cifrato per l'utente Windows corrente."
}
$Secret = ConvertTo-SecureString -String ((Get-Content -LiteralPath $TokenFile -Raw).Trim())
$Ptr = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($Secret)
try { $Token = [Runtime.InteropServices.Marshal]::PtrToStringBSTR($Ptr) }
finally { [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($Ptr) }
try {
    $Headers = @{
        Authorization = "Bearer $Token"
        Accept = "application/vnd.github+json"
        "X-GitHub-Api-Version" = "2022-11-28"
        "User-Agent" = "IstatPulseEditorialBridge/0.2"
    }
    $Identity = Invoke-RestMethod -Method Get -Uri "https://api.github.com/user" -Headers $Headers -TimeoutSec 20
    if ($Identity.login -cne "pierfido89") { throw "Token di un altro account: configurazione bloccata." }
    $Destination = Invoke-RestMethod -Method Get -Uri "https://api.github.com/repos/$TargetRepo" -Headers $Headers -TimeoutSec 20
    if ($Destination.full_name -cne $TargetRepo -or $Destination.private -ne $true -or
        $Destination.default_branch -ne "main") {
        throw "Il repository non e privato, non e quello consentito, o non ha main."
    }
    Write-Host "Identita e repository privato verificati." -ForegroundColor Green
} finally {
    $Headers.Authorization = $null
    $Token = $null
    $Secret.Dispose()
}

$TaskScript = Join-Path $PSScriptRoot "run_scheduled.ps1"
$PowershellExe = Join-Path $PSHOME "powershell.exe"
$Action = New-ScheduledTaskAction -Execute $PowershellExe -Argument ('-NoProfile -NonInteractive -ExecutionPolicy Bypass -File "' + $TaskScript + '"')
$Trigger = New-ScheduledTaskTrigger -Once -At (Get-Date).AddMinutes(3) -RepetitionInterval (New-TimeSpan -Minutes 30) -RepetitionDuration (New-TimeSpan -Days 3650)
$Me = [Security.Principal.WindowsIdentity]::GetCurrent().Name
$Principal = New-ScheduledTaskPrincipal -UserId $Me -LogonType Interactive -RunLevel Limited
$Settings = New-ScheduledTaskSettingsSet -MultipleInstances IgnoreNew -ExecutionTimeLimit (New-TimeSpan -Minutes 40) -StartWhenAvailable -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries
$null = Register-ScheduledTask -TaskName $TaskName -Action $Action -Trigger $Trigger -Principal $Principal -Settings $Settings -Force
$Task = Get-ScheduledTask -TaskName $TaskName
if ($Task.State -eq "Disabled") { throw "L'attivita risulta disabilitata." }
Write-Host ""
Write-Host "CONFIGURAZIONE REGISTRATA." -ForegroundColor Green
Write-Host "Attivita: $TaskName"
Write-Host "Frequenza: 30 minuti, solo con sessione Windows aperta."
Write-Host "Il job GitHub e inizialmente DISABILITATO: Qwen non parte finche non lo autorizzi."
Write-Host "Risultati privati: https://github.com/$TargetRepo"
Write-Host "Arresto: Disable-ScheduledTask -TaskName '$TaskName'"
Write-Host "Log locale: $(Join-Path $StateDir 'last-run.log')"
Write-Host ""
Write-Host "IMPORTANTE: il codice Python NON viene aggiornato automaticamente."
