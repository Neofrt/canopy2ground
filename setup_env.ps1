$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
$Venv = Join-Path $Root ".venv"
$VenvPython = Join-Path $Venv "Scripts\python.exe"

function Test-Python312 {
    param(
        [Parameter(Mandatory=$true)][string]$Exe,
        [string[]]$PrefixArgs = @()
    )
    try {
        $version = & $Exe @PrefixArgs -c "import sys; print(str(sys.version_info.major) + '.' + str(sys.version_info.minor))" 2>$null
        if ($LASTEXITCODE -eq 0 -and (($version | Select-Object -Last 1).Trim() -eq "3.12")) {
            return $true
        }
    } catch {}
    return $false
}

function Resolve-Python312 {
    $pythonCmd = Get-Command python -ErrorAction SilentlyContinue
    if ($pythonCmd -and (Test-Python312 -Exe $pythonCmd.Source)) {
        return @{ Exe = $pythonCmd.Source; PrefixArgs = @() }
    }

    $localPython = Join-Path $env:LOCALAPPDATA "Programs\Python\Python312\python.exe"
    if ((Test-Path $localPython) -and (Test-Python312 -Exe $localPython)) {
        return @{ Exe = $localPython; PrefixArgs = @() }
    }

    $pyCmd = Get-Command py -ErrorAction SilentlyContinue
    if ($pyCmd -and (Test-Python312 -Exe $pyCmd.Source -PrefixArgs @("-3.12"))) {
        return @{ Exe = $pyCmd.Source; PrefixArgs = @("-3.12") }
    }

    $python3Cmd = Get-Command python3 -ErrorAction SilentlyContinue
    if ($python3Cmd -and (Test-Python312 -Exe $python3Cmd.Source)) {
        return @{ Exe = $python3Cmd.Source; PrefixArgs = @() }
    }

    throw @"
Python 3.12 was not found by the Canopy2Ground bootstrap.

Check the Python that already works on this machine:
    python --version

If needed, point Canopy2Ground directly to Python 3.12:
    `$env:C2G_PYTHON = 'C:\path\to\python.exe'
    .\run.ps1
"@
}

if (-not (Test-Path $VenvPython)) {
    Write-Host "Virtual environment not found. Preparing first run..."

    if (Test-Path $Venv) {
        Write-Host "Removing incomplete .venv from a previous failed setup..."
        Remove-Item -Recurse -Force $Venv
    }

    if ($env:C2G_PYTHON) {
        if (-not (Test-Path $env:C2G_PYTHON)) {
            throw "C2G_PYTHON points to a file that does not exist: $env:C2G_PYTHON"
        }
        if (-not (Test-Python312 -Exe $env:C2G_PYTHON)) {
            throw "C2G_PYTHON must point to a Python 3.12 executable."
        }
        $resolved = @{ Exe = $env:C2G_PYTHON; PrefixArgs = @() }
    } else {
        $resolved = Resolve-Python312
    }

    $BasePython = $resolved.Exe
    $PrefixArgs = @($resolved.PrefixArgs)
    Write-Host "Using Python 3.12: $BasePython $($PrefixArgs -join ' ')"
    Write-Host "Creating virtual environment in .venv ..."
    & $BasePython @PrefixArgs -m venv $Venv
    if ($LASTEXITCODE -ne 0) {
        throw "Failed to create .venv (exit code $LASTEXITCODE)."
    }
    if (-not (Test-Path $VenvPython)) {
        throw "Virtual environment creation finished without .venv\Scripts\python.exe."
    }
}

Write-Host "Updating pip inside .venv ..."
& $VenvPython -m pip install --upgrade pip
if ($LASTEXITCODE -ne 0) { throw "pip upgrade failed (exit code $LASTEXITCODE)." }

Write-Host "Installing Canopy2Ground dependencies inside .venv ..."
& $VenvPython -m pip install -r (Join-Path $Root "requirements.txt")
if ($LASTEXITCODE -ne 0) { throw "Dependency installation failed (exit code $LASTEXITCODE)." }

Write-Host "Running unit tests ..."
& $VenvPython -m unittest discover -s (Join-Path $Root "tests") -v
if ($LASTEXITCODE -ne 0) { throw "Unit tests failed (exit code $LASTEXITCODE)." }

Write-Host "Virtual environment ready: $Venv"
