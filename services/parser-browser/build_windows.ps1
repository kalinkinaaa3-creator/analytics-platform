$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot
if (-not (Test-Path -LiteralPath '.build-venv\Scripts\python.exe')) {
    python -m venv .build-venv
    if ($LASTEXITCODE -ne 0) { throw 'Could not create build environment' }
}
& .\.build-venv\Scripts\python.exe -m pip install -r requirements-build.txt
if ($LASTEXITCODE -ne 0) { throw 'Could not install build dependencies' }
& .\.build-venv\Scripts\python.exe .\build_windows.py
if ($LASTEXITCODE -ne 0) { throw 'Build failed' }
