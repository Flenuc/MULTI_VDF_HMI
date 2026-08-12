# Lanzador Windows (PowerShell) — SAJ PDM-30 Gestor de Parametros
$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

$exeCandidates = @(
    Join-Path $PSScriptRoot "dist\SAJ_PDM30_Gestor.exe"
    Join-Path $PSScriptRoot "dist\windows\SAJ_PDM30_Gestor.exe"
)
foreach ($exe in $exeCandidates) {
    if (Test-Path $exe) {
        Start-Process -FilePath $exe -WorkingDirectory $PSScriptRoot
        exit 0
    }
}

$py = Get-Command python -ErrorAction SilentlyContinue
if (-not $py) {
    Write-Host "ERROR: Python no esta en el PATH." -ForegroundColor Red
    exit 1
}

$venvPy = Join-Path $PSScriptRoot ".venv\Scripts\python.exe"
if (-not (Test-Path $venvPy)) {
    Write-Host "Creando entorno virtual..."
    python -m venv (Join-Path $PSScriptRoot ".venv")
    & $venvPy -m pip install -U pip
    & $venvPy -m pip install -r (Join-Path $PSScriptRoot "requirements.txt")
}

& $venvPy (Join-Path $PSScriptRoot "main.py") @args
