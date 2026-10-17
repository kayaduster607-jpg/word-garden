# 本地预览入口；不读取 .env，不向云端上传任何文件。
$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot
$pythonCommand = Get-Command python -ErrorAction SilentlyContinue
$bundledPython = Join-Path $env:USERPROFILE '.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe'
if (Test-Path -LiteralPath $bundledPython) {
    $pythonExe = $bundledPython
} elseif ($pythonCommand) {
    $pythonExe = $pythonCommand.Source
} else {
    throw 'Please install Python 3.11+ first.'
}
$env:WORD_ORIGIN = 'http://localhost:8765'
$env:PYTHONIOENCODING = 'utf-8'
Write-Host 'Open http://localhost:8765 in your browser. Ctrl+C stops the preview.'
& $pythonExe serve.py --dev --port 8765
