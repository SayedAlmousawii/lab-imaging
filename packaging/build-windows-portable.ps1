$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$ProjectRoot = Resolve-Path (Join-Path $ScriptDir "..")
$VenvDir = Join-Path $ProjectRoot ".venv"
$PythonExe = Join-Path $VenvDir "Scripts\python.exe"
$DistDir = Join-Path $ProjectRoot "dist"
$BuildDir = Join-Path $ProjectRoot "build"
$PortableDir = Join-Path $DistDir "LabImagingPortable"
$SpecPath = Join-Path $ScriptDir "LabImaging.spec"

function Find-Python311 {
    $candidates = @(
        @("py", "-3.11"),
        @("python", "")
    )

    foreach ($candidate in $candidates) {
        $command = $candidate[0]
        $argument = $candidate[1]
        try {
            if ($argument) {
                & $command $argument -c "import sys; raise SystemExit(0 if sys.version_info[:2] == (3, 11) else 1)" 2>$null
            } else {
                & $command -c "import sys; raise SystemExit(0 if sys.version_info[:2] == (3, 11) else 1)" 2>$null
            }
            if ($LASTEXITCODE -eq 0) {
                return @($command, $argument)
            }
        } catch {
        }
    }

    throw "Python 3.11 was not found. Install Python 3.11 for Windows, then rerun this script."
}

Write-Host "Lab Imaging portable Windows build"
Write-Host "Project: $ProjectRoot"

if (-not (Test-Path $PythonExe)) {
    $python = Find-Python311
    Write-Host "Creating Python 3.11 virtual environment..."
    if ($python[1]) {
        & $python[0] $python[1] -m venv $VenvDir
    } else {
        & $python[0] -m venv $VenvDir
    }
} else {
    & $PythonExe -c "import sys; raise SystemExit(0 if sys.version_info[:2] == (3, 11) else 1)"
    if ($LASTEXITCODE -ne 0) {
        throw "Existing .venv is not Python 3.11. Remove .venv and rerun this script."
    }
}

Write-Host "Installing dependencies..."
& $PythonExe -m pip install --upgrade pip
& $PythonExe -m pip install -r (Join-Path $ProjectRoot "requirements.txt") pyinstaller

if (Test-Path $PortableDir) {
    Write-Host "Removing previous portable output..."
    Remove-Item -Recurse -Force $PortableDir
}

Write-Host "Running PyInstaller..."
& $PythonExe -m PyInstaller --noconfirm --clean --distpath $DistDir --workpath $BuildDir $SpecPath

if (-not (Test-Path $PortableDir)) {
    throw "PyInstaller did not create $PortableDir"
}

Write-Host "Assembling operator files..."
New-Item -ItemType Directory -Force -Path (Join-Path $PortableDir "config") | Out-Null
New-Item -ItemType Directory -Force -Path (Join-Path $PortableDir "experiments") | Out-Null
New-Item -ItemType Directory -Force -Path (Join-Path $PortableDir "logs") | Out-Null

Copy-Item -Force (Join-Path $ProjectRoot "config\settings.json.example") (Join-Path $PortableDir "config\settings.json.example")
Copy-Item -Force (Join-Path $ScriptDir "Start Lab Imaging.bat") (Join-Path $PortableDir "Start Lab Imaging.bat")
Copy-Item -Force (Join-Path $ScriptDir "README-START-HERE.txt") (Join-Path $PortableDir "README-START-HERE.txt")

Write-Host ""
Write-Host "Portable package ready:"
Write-Host $PortableDir
Write-Host ""
Write-Host "Copy or zip the LabImagingPortable folder for lab use. Do not edit files under _internal."
