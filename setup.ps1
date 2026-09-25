[CmdletBinding()]
param(
    [string]$Venv = ".venv",
    [switch]$WithDev
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

$py = Get-Command py -ErrorAction SilentlyContinue
if (-not $py) {
    throw "Python Launcher (py.exe) was not found. Install 64-bit Python 3.11 first."
}

& py -3.11 -c "import sys; assert sys.version_info[:2] == (3, 11), sys.version"
if ($LASTEXITCODE -ne 0) {
    throw "Python 3.11 is required."
}

if (-not (Test-Path $Venv)) {
    & py -3.11 -m venv $Venv
    if ($LASTEXITCODE -ne 0) { throw "Virtual environment creation failed." }
}

$python = Join-Path $Venv "Scripts\python.exe"
$installTarget = if ($WithDev) { ".[dev]" } else { "." }
& $python -m pip install -e $installTarget
if ($LASTEXITCODE -ne 0) { throw "Package installation failed." }

& $python -m vera_ark doctor
if ($LASTEXITCODE -ne 0) { throw "Runtime diagnostics failed." }

Write-Host "VERA ARK installed into $Venv. Controller mode is dry-run only."
