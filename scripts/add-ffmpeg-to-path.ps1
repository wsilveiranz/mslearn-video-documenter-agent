# Add FFmpeg (installed via winget) to the user PATH permanently.
# Run this in an elevated (Admin) PowerShell terminal.
#
# Usage:
#   .\add-ffmpeg-to-path.ps1                          # auto-discover from winget
#   .\add-ffmpeg-to-path.ps1 -FfmpegBinDir "C:\tools\ffmpeg\bin"  # explicit path

param(
    [string]$FfmpegBinDir
)

if (-not $FfmpegBinDir) {
    # Auto-discover FFmpeg from the winget package directory
    $wingetBase = Join-Path $env:LOCALAPPDATA "Microsoft\WinGet\Packages"
    if (Test-Path $wingetBase) {
        $ffmpegDirs = Get-ChildItem -Path $wingetBase -Filter "Gyan.FFmpeg*" -Directory -ErrorAction SilentlyContinue
        foreach ($dir in $ffmpegDirs) {
            $found = Get-ChildItem -Path $dir.FullName -Recurse -Filter "ffmpeg.exe" -ErrorAction SilentlyContinue | Select-Object -First 1
            if ($found) {
                $FfmpegBinDir = $found.DirectoryName
                Write-Output "Auto-discovered FFmpeg at: $FfmpegBinDir"
                break
            }
        }
    }
}

if (-not $FfmpegBinDir -or -not (Test-Path (Join-Path $FfmpegBinDir "ffmpeg.exe"))) {
    Write-Error "FFmpeg not found. Specify -FfmpegBinDir or install via: winget install Gyan.FFmpeg"
    exit 1
}

$currentPath = [Environment]::GetEnvironmentVariable("Path", "User")

if ($currentPath -notlike "*$FfmpegBinDir*") {
    [Environment]::SetEnvironmentVariable("Path", "$currentPath;$FfmpegBinDir", "User")
    Write-Output "FFmpeg added to user PATH permanently. Restart your terminal to apply."
} else {
    Write-Output "FFmpeg is already in user PATH."
}
