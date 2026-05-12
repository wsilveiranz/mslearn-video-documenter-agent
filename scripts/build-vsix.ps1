<#
.SYNOPSIS
    Build the MS Learn Video Documenter VSIX package for private preview distribution.

.DESCRIPTION
    Compiles the TypeScript extension, bundles the Python backend source,
    and produces a .vsix file in the release/ directory at the repo root.

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

# 3. Copy backend source into extension directory for bundling
Write-Host "[3/6] Bundling backend source..." -ForegroundColor Yellow

if (Test-Path $bundledBackend) {
    Remove-Item -Recurse -Force $bundledBackend
}

New-Item -ItemType Directory -Path $bundledBackend -Force | Out-Null

# Copy backend source files (exclude dev artifacts)
$backendItems = @(
    @{ Source = (Join-Path $backendDir 'src'); Dest = (Join-Path $bundledBackend 'src') },
    @{ Source = (Join-Path $backendDir 'pyproject.toml'); Dest = (Join-Path $bundledBackend 'pyproject.toml') },
    @{ Source = (Join-Path $backendDir '.env.example'); Dest = (Join-Path $bundledBackend '.env.example') }
)

foreach ($item in $backendItems) {
    if (Test-Path $item.Source) {
        if ((Get-Item $item.Source).PSIsContainer) {
            Copy-Item -Recurse -Force $item.Source $item.Dest
        } else {
            Copy-Item -Force $item.Source $item.Dest
        }
        Write-Host "  Copied: $($item.Source | Split-Path -Leaf)" -ForegroundColor Gray
    } else {
        Write-Warning "  Missing: $($item.Source)"
    }
}

# Clean up Python caches from the copy
Get-ChildItem -Path $bundledBackend -Recurse -Directory -Filter '__pycache__' | Remove-Item -Recurse -Force -ErrorAction SilentlyContinue
Get-ChildItem -Path $bundledBackend -Recurse -Filter '*.pyc' | Remove-Item -Force -ErrorAction SilentlyContinue
Get-ChildItem -Path $bundledBackend -Recurse -Directory -Filter '*.egg-info' | Remove-Item -Recurse -Force -ErrorAction SilentlyContinue

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

# 6. Clean up bundled backend from extension directory
Write-Host "[6/6] Cleaning up..." -ForegroundColor Yellow
if (Test-Path $bundledBackend) {
    Remove-Item -Recurse -Force $bundledBackend
}

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
