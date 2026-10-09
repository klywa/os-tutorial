param([int]$Port = 8765, [switch]$NoBrowser)
$ErrorActionPreference = 'Stop'
$frontendRoot = $PSScriptRoot
$projectRoot = Split-Path $frontendRoot -Parent
$pythonPath = Join-Path $projectRoot '.wxq-runtime/Scripts/python.exe'
if (!(Test-Path -LiteralPath $pythonPath)) { throw '请先安装 wanxiangqi-knowledge 的本地运行环境。' }
Push-Location $frontendRoot
try {
    if (!(Test-Path -LiteralPath 'node_modules')) {
        & npm.cmd ci
        if ($LASTEXITCODE -ne 0) { throw '前端依赖安装失败' }
    }
    & npm.cmd run build
    if ($LASTEXITCODE -ne 0) { throw '前端构建失败' }
    $serverArgs = @((Join-Path $frontendRoot 'server.py'), '--port', "$Port")
    if (!$NoBrowser) { $serverArgs += '--open-browser' }
    & $pythonPath @serverArgs
} finally { Pop-Location }
