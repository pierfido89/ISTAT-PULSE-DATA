# Fixed local entrypoint for Windows Task Scheduler. No auto-updates or shell from GitHub.
Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"
$Root = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$StateDir = Join-Path $env:LOCALAPPDATA "IstatPulseEditorialBridge"
New-Item -ItemType Directory -Force -Path $StateDir | Out-Null
$LogPath = Join-Path $StateDir "last-run.log"
$Mutex = New-Object System.Threading.Mutex($false, "Local\ISTATPULSE_EDITORIAL_BRIDGE")
$Acquired = $false
try {
    $Acquired = $Mutex.WaitOne(0)
    if (!$Acquired) { exit 0 }
    $Now = (Get-Date).ToUniversalTime().ToString("o")
    ("START " + $Now) | Out-File -FilePath $LogPath -Encoding UTF8 -Append
    # Executable path is fixed and local. Job JSON cannot change it.
    $Py = (Get-Command py.exe -ErrorAction Stop).Source
    & $Py (Join-Path $PSScriptRoot "pulse_local_agent.py") --once 2>&1 |
        Out-File -FilePath $LogPath -Encoding UTF8 -Append
    ("WRITER_EXIT " + $LASTEXITCODE) | Out-File -FilePath $LogPath -Encoding UTF8 -Append
    & (Join-Path $PSScriptRoot "upload_results.ps1") -Quiet 2>&1 |
        Out-File -FilePath $LogPath -Encoding UTF8 -Append
    ("END " + (Get-Date).ToUniversalTime().ToString("o")) |
        Out-File -FilePath $LogPath -Encoding UTF8 -Append
} catch {
    ("ERROR " + (Get-Date).ToUniversalTime().ToString("o") + " " + $_.Exception.Message) |
        Out-File -FilePath $LogPath -Encoding UTF8 -Append
    exit 2
} finally {
    if ($Acquired) { $Mutex.ReleaseMutex() }
    $Mutex.Dispose()
}
