param([int]$Port = 8765, [switch]$NoBrowser, [switch]$SkipTopicModel)
$ErrorActionPreference = 'Stop'
& (Join-Path (Split-Path $PSScriptRoot -Parent) 'start.ps1') -Port $Port -NoBrowser:$NoBrowser -SkipTopicModel:$SkipTopicModel
exit $LASTEXITCODE
