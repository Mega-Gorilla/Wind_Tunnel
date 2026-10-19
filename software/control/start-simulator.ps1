param([switch]$NoBrowser)
$ErrorActionPreference='Stop'
Push-Location $PSScriptRoot
try {
    $simulationPython = Join-Path $PSScriptRoot '.venv\Scripts\python.exe'
    if (-not (Test-Path -LiteralPath $simulationPython)) {
        throw 'READMEの手順で専用Python環境を作成してください。'
    }
    if ($NoBrowser) { & $simulationPython -m windtunnel }
    else { & $simulationPython -m windtunnel --open }
    if ($LASTEXITCODE -ne 0) { throw "模擬アプリ終了コード: $LASTEXITCODE" }
} finally { Pop-Location }
