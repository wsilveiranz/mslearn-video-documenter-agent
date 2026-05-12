<#
.SYNOPSIS
    Build the MS Learn Video Documenter VSIX package for private preview distribution.

.DESCRIPTION
    Compiles the TypeScript extension, builds the Python backend into a
    standalone executable via PyInstaller, and produces a .vsix file in
    the release/ directory at the repo root.

.EXAMPLE
    .\scripts\build-vsix.ps1
    .\scripts\build-vsix.ps1 -Version 0.2.0
    .\scripts\build-vsix.ps1 -Version 0.1.1 -SkipCompile
#>

param(
    [string]$Version,
    [switch]$SkipCompile
)

$ErrorActionPreference = 'Stop'

# Resolve paths
$repoRoot = Split-Path -Parent $PSScriptRoot
$extensionDir = Join-Path $repoRoot 'vscode-extension'
$backendDir = Join-Path $repoRoot 'backend'
$releaseDir = Join-Path $repoRoot 'release'
$bundledBackend = Join-Path $extensionDir 'backend'

Write-Host "=== MS Learn Video Documenter VSIX Builder ===" -ForegroundColor Cyan
Write-Host ""

# 0. Override version in package.json if specified
if ($Version) {
    if ($Version -notmatch '^\d+\.\d+\.\d+$') {
        Write-Error "Invalid version format '$Version'. Expected semver: major.minor.patch (e.g., 0.2.0)"
        exit 1
    }
    Write-Host "[0/6] Setting version to $Version..." -ForegroundColor Yellow
    $packageJsonPath = Join-Path $extensionDir 'package.json'
    $packageJson = Get-Content $packageJsonPath -Raw | ConvertFrom-Json
    $packageJson.version = $Version
    $packageJson | ConvertTo-Json -Depth 100 | Set-Content $packageJsonPath -Encoding UTF8
    Write-Host "  Updated package.json version to $Version" -ForegroundColor Gray
}

# 1. Verify prerequisites
Write-Host "[1/6] Checking prerequisites..." -ForegroundColor Yellow

if (-not (Get-Command node -ErrorAction SilentlyContinue)) {
    Write-Error "Node.js is required but not found on PATH."
    exit 1
}

if (-not (Get-Command python -ErrorAction SilentlyContinue)) {
    Write-Error "Python is required but not found on PATH."
    exit 1
}

if (-not (Test-Path (Join-Path $extensionDir 'node_modules'))) {
    Write-Host "  Installing npm dependencies..." -ForegroundColor Gray
    Push-Location $extensionDir
    npm ci --quiet
    Pop-Location
}

# 2. Compile TypeScript
if (-not $SkipCompile) {
    Write-Host "[2/6] Compiling TypeScript..." -ForegroundColor Yellow
    Push-Location $extensionDir
    npm run compile
    if ($LASTEXITCODE -ne 0) {
        Write-Error "TypeScript compilation failed."
        exit 1
    }
    Pop-Location
} else {
    Write-Host "[2/6] Skipping TypeScript compilation (-SkipCompile)" -ForegroundColor DarkGray
}

# 3. Build backend exe with PyInstaller (in a clean venv to avoid bundling unrelated packages)
Write-Host "[3/6] Building backend executable..." -ForegroundColor Yellow

$buildVenv = Join-Path $backendDir '.build-venv'

# Create a fresh build venv
if (Test-Path $buildVenv) {
    Write-Host "  Removing previous build venv..." -ForegroundColor Gray
    Remove-Item -Recurse -Force $buildVenv
}

Write-Host "  Creating isolated build venv..." -ForegroundColor Gray
python -m venv $buildVenv
if ($LASTEXITCODE -ne 0) {
    Write-Error "Failed to create build venv."
    exit 1
}

$venvPip = Join-Path $buildVenv 'Scripts' 'pip.exe'
$venvPython = Join-Path $buildVenv 'Scripts' 'python.exe'

# Install only the app's own dependencies + pyinstaller
Write-Host "  Installing backend dependencies in build venv..." -ForegroundColor Gray
& $venvPip install --quiet -e "$backendDir" pyinstaller 2>&1 | Out-Null
if ($LASTEXITCODE -ne 0) {
    Write-Error "Failed to install dependencies in build venv."
    exit 1
}
Write-Host "  Installed packages:" -ForegroundColor Gray
& $venvPip list --format=columns 2>&1 | Select-String "agent-framework|azure|pyinstaller" | ForEach-Object { Write-Host "    $_" -ForegroundColor DarkGray }

# Run PyInstaller from the clean venv
Push-Location $backendDir
& $venvPython -m PyInstaller --noconfirm backend.spec
if ($LASTEXITCODE -ne 0) {
    Pop-Location
    Write-Error "PyInstaller build failed."
    exit 1
}
Pop-Location

# 3b. Smoke-test the built executable (catches missing hidden imports early)
Write-Host "  Running import smoke test..." -ForegroundColor Gray
$smokeExe = Join-Path $backendDir 'dist' 'backend' 'backend.exe'
$smokeEnv = @{
    'SMOKE_TEST' = '1'
    'PYTHONIOENCODING' = 'utf-8'
}
$smokeProcess = Start-Process -FilePath $smokeExe -ArgumentList @() -Environment $smokeEnv -NoNewWindow -PassThru -RedirectStandardError (Join-Path $backendDir 'dist' 'smoke_stderr.txt') -RedirectStandardOutput (Join-Path $backendDir 'dist' 'smoke_stdout.txt')

# Give the server up to 15 seconds to start and respond to health check
$smokeTimeout = 15
$smokeStart = Get-Date
$smokeHealthy = $false
while (((Get-Date) - $smokeStart).TotalSeconds -lt $smokeTimeout) {
    Start-Sleep -Milliseconds 500
    # Check if process died
    if ($smokeProcess.HasExited) {
        $stderr = Get-Content (Join-Path $backendDir 'dist' 'smoke_stderr.txt') -Raw -ErrorAction SilentlyContinue
        Write-Error "Smoke test FAILED — backend.exe exited with code $($smokeProcess.ExitCode).`n$stderr"
        exit 1
    }
    # Try health endpoint
    try {
        $response = Invoke-WebRequest -Uri 'http://127.0.0.1:8000/api/v1/health' -TimeoutSec 2 -ErrorAction Stop
        if ($response.StatusCode -eq 200) {
            $smokeHealthy = $true
            break
        }
    } catch {
        # Not ready yet
    }
}

# Kill the smoke-test process
Stop-Process -Id $smokeProcess.Id -Force -ErrorAction SilentlyContinue
Start-Sleep -Milliseconds 500

if (-not $smokeHealthy) {
    $stderr = Get-Content (Join-Path $backendDir 'dist' 'smoke_stderr.txt') -Raw -ErrorAction SilentlyContinue
    Write-Error "Smoke test FAILED — backend.exe did not become healthy within ${smokeTimeout}s.`n$stderr"
    exit 1
}
Write-Host "  Smoke test passed — backend.exe starts and responds to health checks." -ForegroundColor Green

# Clean up smoke test output files
Remove-Item -Force (Join-Path $backendDir 'dist' 'smoke_stderr.txt') -ErrorAction SilentlyContinue
Remove-Item -Force (Join-Path $backendDir 'dist' 'smoke_stdout.txt') -ErrorAction SilentlyContinue

# Copy dist/backend/ directory into vscode-extension/backend/
# PyInstaller onedir mode produces a directory with backend.exe + all DLLs
$pyinstallerDir = Join-Path $backendDir 'dist' 'backend'
if (-not (Test-Path $pyinstallerDir)) {
    Write-Error "PyInstaller output directory not found at $pyinstallerDir"
    exit 1
}

if (Test-Path $bundledBackend) {
    Remove-Item -Recurse -Force $bundledBackend
}
Copy-Item -Recurse -Force $pyinstallerDir $bundledBackend

# Verify backend.exe exists in the bundle
$backendExe = Join-Path $bundledBackend 'backend.exe'
if (-not (Test-Path $backendExe)) {
    Write-Error "backend.exe not found in bundled output."
    exit 1
}

$dirSize = [math]::Round(((Get-ChildItem -Recurse $bundledBackend | Measure-Object -Property Length -Sum).Sum) / 1MB, 2)
Write-Host "  Backend directory bundled: $dirSize MB" -ForegroundColor Gray

# 4. Create release directory
Write-Host "[4/6] Preparing release directory..." -ForegroundColor Yellow
if (-not (Test-Path $releaseDir)) {
    New-Item -ItemType Directory -Path $releaseDir -Force | Out-Null
}

# 5. Package VSIX
Write-Host "[5/6] Packaging VSIX..." -ForegroundColor Yellow
Push-Location $extensionDir
npx vsce package --out (Join-Path $releaseDir '/') --allow-missing-repository --skip-license
if ($LASTEXITCODE -ne 0) {
    Pop-Location
    # Clean up bundled backend on failure
    if (Test-Path $bundledBackend) {
        Remove-Item -Recurse -Force $bundledBackend
    }
    Write-Error "VSIX packaging failed."
    exit 1
}
Pop-Location

# 6. Clean up
Write-Host "[6/6] Cleaning up..." -ForegroundColor Yellow
if (Test-Path $bundledBackend) {
    Remove-Item -Recurse -Force $bundledBackend
}
# Clean PyInstaller artifacts and build venv
$pyinstallerBuild = Join-Path $backendDir 'build'
$pyinstallerDist = Join-Path $backendDir 'dist'
$buildVenvClean = Join-Path $backendDir '.build-venv'
if (Test-Path $pyinstallerBuild) { Remove-Item -Recurse -Force $pyinstallerBuild }
if (Test-Path $pyinstallerDist) { Remove-Item -Recurse -Force $pyinstallerDist }
if (Test-Path $buildVenvClean) { Remove-Item -Recurse -Force $buildVenvClean }

# Report results
$vsixFile = Get-ChildItem -Path $releaseDir -Filter '*.vsix' | Sort-Object LastWriteTime -Descending | Select-Object -First 1
if ($vsixFile) {
    Write-Host ""
    Write-Host "=== Build complete ===" -ForegroundColor Green
    Write-Host "VSIX: $($vsixFile.FullName)" -ForegroundColor Green
    Write-Host "Size: $([math]::Round($vsixFile.Length / 1MB, 2)) MB" -ForegroundColor Green
    Write-Host ""
    Write-Host "Install with: code --install-extension `"$($vsixFile.FullName)`"" -ForegroundColor Cyan
} else {
    Write-Error "VSIX file not found in release directory."
    exit 1
}
