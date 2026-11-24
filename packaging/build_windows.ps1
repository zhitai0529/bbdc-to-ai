param([string]$Python)

$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
if (-not $Python) {
    $Python = Join-Path $projectRoot '.venv\Scripts\python.exe'
}
if (-not (Get-Command $Python -ErrorAction SilentlyContinue)) {
    throw 'Python was not found. Install project dependencies with setup.bat or specify -Python.'
}

Push-Location -LiteralPath $projectRoot
try {
    Push-Location -LiteralPath (Join-Path $projectRoot 'flutter_ui')
    try {
        flutter build windows --release
        if ($LASTEXITCODE -ne 0) { throw 'Flutter Windows build failed.' }
    } finally {
        Pop-Location
    }
    & $Python -m PyInstaller --clean --noconfirm --workpath build/bbdc-windows --distpath dist packaging/windows.spec
    if ($LASTEXITCODE -ne 0) {
        throw 'Windows packaging failed.'
    }
} finally {
    Pop-Location
}
