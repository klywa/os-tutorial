param([ValidateRange(1,65535)][int]$Port = 8765, [switch]$NoBrowser, [switch]$SkipTopicModel)
$ErrorActionPreference = 'Stop'
$launchArgs = @((Join-Path $PSScriptRoot 'frontend/launch.py'), '--port', "$Port")
if ($NoBrowser) { $launchArgs += '--no-browser' }
if ($SkipTopicModel) { $launchArgs += '--skip-topic-model' }
$localPython = Join-Path $PSScriptRoot '.wxq-runtime/Scripts/python.exe'
if (Test-Path -LiteralPath $localPython) {
    & $localPython @launchArgs
} elseif (Get-Command py -ErrorAction SilentlyContinue) {
    & py -3.12 @launchArgs
} elseif (Get-Command python -ErrorAction SilentlyContinue) {
    & python @launchArgs
} else {
    throw 'Install Python 3.12 and Node.js 24, then run this script again.'
}
exit $LASTEXITCODE
