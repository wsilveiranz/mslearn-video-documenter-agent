# Add FFmpeg (installed via winget) to the user PATH permanently.
# Run this in an elevated (Admin) PowerShell terminal.

$ffmpegPath = "C:\Users\wsilveira\AppData\Local\Microsoft\WinGet\Packages\Gyan.FFmpeg_Microsoft.Winget.Source_8wekyb3d8bbwe\ffmpeg-8.1.1-full_build\bin"

if (-not (Test-Path "$ffmpegPath\ffmpeg.exe")) {
    Write-Error "FFmpeg not found at: $ffmpegPath"
    exit 1
}

$currentPath = [Environment]::GetEnvironmentVariable("Path", "User")

if ($currentPath -notlike "*$ffmpegPath*") {
    [Environment]::SetEnvironmentVariable("Path", "$currentPath;$ffmpegPath", "User")
    Write-Output "FFmpeg added to user PATH permanently. Restart your terminal to apply."
} else {
    Write-Output "FFmpeg is already in user PATH."
}
