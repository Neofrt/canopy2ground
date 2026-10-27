$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
$VenvPython = Join-Path $Root ".venv\Scripts\python.exe"

if (-not (Test-Path $VenvPython)) {
    & (Join-Path $Root "setup_env.ps1")
}

if (-not (Test-Path $VenvPython)) {
    throw "Virtual environment is not usable: $VenvPython was not created."
}

& $VenvPython (Join-Path $Root "run_pipeline.py") --root $Root @args
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
