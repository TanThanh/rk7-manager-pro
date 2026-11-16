# Build the current WebView app as a clean portable release.
$ErrorActionPreference = "Stop"

# Terminate running instances if any to prevent file lock
Stop-Process -Name "RK7_Pro_Manager_WebView" -Force -ErrorAction SilentlyContinue
Start-Sleep -Milliseconds 800

$projectDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$releaseDir = Join-Path $projectDir "release-webview"
$workDir = Join-Path $projectDir "build-webview"
$exeName = "RK7_Pro_Manager_WebView.exe"
$archive = Join-Path $releaseDir "RK7_Pro_Manager_WebView.zip"

Set-Location $projectDir
New-Item -ItemType Directory -Path $releaseDir -Force | Out-Null

$python = (Get-Command python -ErrorAction Stop).Source
& $python -m PyInstaller `
    --noconfirm `
    --clean `
    --onefile `
    --windowed `
    --name "RK7_Pro_Manager_WebView" `
    --version-file (Join-Path $projectDir "version_info.txt") `
    --distpath $releaseDir `
    --workpath $workDir `
    --specpath $workDir `
    --paths $projectDir `
    --add-data "$(Join-Path $projectDir 'web_ui');web_ui" `
    --add-data "$(Join-Path $projectDir 'rk7_pro\bin');rk7_pro/bin" `
    --add-data "$(Join-Path $projectDir 'master_refs');master_refs" `
    --add-data "$(Join-Path $projectDir 'invoice_templates');invoice_templates" `
    --add-data "$(Join-Path $projectDir 'sql_connections.json');." `
    --add-data "$(Join-Path $projectDir 'api_connections.json');." `
    --add-data "$(Join-Path $projectDir 'auth_users.json');." `
    --add-data "$(Join-Path $projectDir 'rk7_pro');rk7_pro" `
    --hidden-import "webview.platforms.edgechromium" `
    --hidden-import "clr" `
    "main_webview.py"

if ($LASTEXITCODE -ne 0) {
    throw "PyInstaller build failed with exit code $LASTEXITCODE"
}

# Package the executable and external support folders
$exePath = Join-Path $releaseDir $exeName
$destBin = Join-Path $releaseDir "rk7_pro\bin"
New-Item -ItemType Directory -Path $destBin -Force | Out-Null
Copy-Item -Path (Join-Path $projectDir "rk7_pro\bin\*") -Destination $destBin -Force

# Copy database & master nexus configurations if present
if (Test-Path (Join-Path $projectDir "sql_connections.json")) {
    Copy-Item (Join-Path $projectDir "sql_connections.json") (Join-Path $releaseDir "sql_connections.json") -Force
}
if (Test-Path (Join-Path $projectDir "api_connections.json")) {
    Copy-Item (Join-Path $projectDir "api_connections.json") (Join-Path $releaseDir "api_connections.json") -Force
}
if (Test-Path (Join-Path $projectDir "auth_users.json")) {
    Copy-Item (Join-Path $projectDir "auth_users.json") (Join-Path $releaseDir "auth_users.json") -Force
}
if (Test-Path (Join-Path $projectDir "settings.json")) {
    Copy-Item (Join-Path $projectDir "settings.json") (Join-Path $releaseDir "settings.json") -Force
}
if (Test-Path (Join-Path $projectDir "master_refs")) {
    $destRefs = Join-Path $releaseDir "master_refs"
    New-Item -ItemType Directory -Path $destRefs -Force | Out-Null
    Copy-Item -Path (Join-Path $projectDir "master_refs\*") -Destination $destRefs -Recurse -Force
}
if (Test-Path (Join-Path $projectDir "invoice_templates")) {
    $destTemplates = Join-Path $releaseDir "invoice_templates"
    New-Item -ItemType Directory -Path $destTemplates -Force | Out-Null
    Copy-Item -Path (Join-Path $projectDir "invoice_templates\*") -Destination $destTemplates -Recurse -Force
}

if (Test-Path -LiteralPath $archive) { Remove-Item -LiteralPath $archive -Force }
$packageItems = @($exePath, (Join-Path $releaseDir "rk7_pro"))
if (Test-Path (Join-Path $releaseDir "master_refs")) { $packageItems += (Join-Path $releaseDir "master_refs") }
if (Test-Path (Join-Path $releaseDir "invoice_templates")) { $packageItems += (Join-Path $releaseDir "invoice_templates") }
if (Test-Path (Join-Path $releaseDir "sql_connections.json")) { $packageItems += (Join-Path $releaseDir "sql_connections.json") }
if (Test-Path (Join-Path $releaseDir "api_connections.json")) { $packageItems += (Join-Path $releaseDir "api_connections.json") }
if (Test-Path (Join-Path $releaseDir "auth_users.json")) { $packageItems += (Join-Path $releaseDir "auth_users.json") }
if (Test-Path (Join-Path $releaseDir "settings.json")) { $packageItems += (Join-Path $releaseDir "settings.json") }

Compress-Archive -Path $packageItems -DestinationPath $archive -CompressionLevel Optimal

Write-Host "Executable: $exePath" -ForegroundColor Green
Write-Host "Clean archive: $archive" -ForegroundColor Green
