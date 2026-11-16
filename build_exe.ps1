# Release build script for RK7 Pro Manager
$ErrorActionPreference = "Stop"
$releaseVersion = "3.1"
$releaseArchive = "./RK7_Pro_Official_v$releaseVersion.zip"

Write-Host "Cleaning up old build artifacts..." -ForegroundColor Cyan
if (Test-Path "./build") { Remove-Item -Recurse -Force "./build" }
if (Test-Path "./dist") { Remove-Item -Recurse -Force "./dist" }

Write-Host "Starting optimized PyInstaller build (Single File, No Console)..." -ForegroundColor Green

$pythonPath = Join-Path $env:USERPROFILE "AppData/Local/Programs/Python/Python312/python.exe"
$pyInstallerArgs = @(
    "-m", "PyInstaller",
    "--onefile",
    "--noconsole",
    "--name", "RK7_Pro_Manager",
    "--version-file", "version_info.txt",
    "--paths", ".",
    "--add-data", "rk7_pro/assets;rk7_pro/assets",
    "--hidden-import", "PySide6.QtCore",
    "--hidden-import", "PySide6.QtWidgets",
    "--hidden-import", "PySide6.QtGui",
    "--hidden-import", "PySide6.QtSvg",
    "--hidden-import", "PySide6.QtWebEngineCore",
    "--hidden-import", "PySide6.QtWebEngineWidgets",
    "--hidden-import", "psutil",
    "--hidden-import", "winshell",
    "rk7_pro/main.py"
)
& $pythonPath @pyInstallerArgs

if ($LASTEXITCODE -ne 0) {
    throw "PyInstaller build failed with exit code $LASTEXITCODE"
}

Copy-Item "./settings.json" "./dist/settings.json" -Force
Copy-Item "./rk7_pro/favorites.json" "./dist/favorites.json" -Force
Copy-Item "./rk7_pro/customization.json" "./dist/customization.json" -Force
if (Test-Path "./rk7_pro/card_backgrounds") {
    Copy-Item "./rk7_pro/card_backgrounds" "./dist/card_backgrounds" -Recurse -Force
}

if (Test-Path $releaseArchive) { Remove-Item -Force $releaseArchive }
Compress-Archive -Path "./dist/*" -DestinationPath $releaseArchive -CompressionLevel Optimal

Write-Host "Release package: $releaseArchive" -ForegroundColor Green

Write-Host ""
Write-Host "Build Successful! RK7 Pro Manager is ready." -ForegroundColor Green
Write-Host "Release Version: $releaseVersion" -ForegroundColor Green
