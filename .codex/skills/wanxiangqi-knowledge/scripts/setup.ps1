param([string]$PythonPath, [switch]$SkipModel)
$ErrorActionPreference = 'Stop'
$wxqRoot = (Resolve-Path (Join-Path $PSScriptRoot '../../../..')).Path
$wxqVenv = Join-Path $wxqRoot '.wxq-runtime'
$wxqPython = Join-Path $wxqVenv 'Scripts/python.exe'
if (-not (Test-Path -LiteralPath $wxqPython)) {
    if (-not $PythonPath) {
        $wxqCandidates = @((Get-Command python -ErrorAction SilentlyContinue).Source)
        $wxqCandidates += (Join-Path $env:USERPROFILE '.cache/codex-runtimes/codex-primary-runtime/dependencies/python/python.exe')
        foreach ($wxqCandidate in $wxqCandidates) {
            if ($wxqCandidate -and (Test-Path -LiteralPath $wxqCandidate)) {
                $wxqVersion = & $wxqCandidate -c 'import sys; print(chr(46).join(map(str,sys.version_info[:2])))'
                if ($LASTEXITCODE -eq 0 -and $wxqVersion -match '^3\.(10|11|12|13)$') {
                    $PythonPath = $wxqCandidate
                    break
                }
            }
        }
    }
    if (-not $PythonPath) { throw 'Provide -PythonPath for Python 3.10-3.13.' }
    & $PythonPath -m venv $wxqVenv
    if ($LASTEXITCODE -ne 0) { throw 'venv creation failed' }
}
& $wxqPython -m pip install -r (Join-Path $PSScriptRoot 'requirements.txt')
if ($LASTEXITCODE -ne 0) { throw 'dependency installation failed' }
& $wxqPython -c 'import imageio_ffmpeg, faster_whisper, yt_dlp; print(imageio_ffmpeg.get_ffmpeg_exe())'
if ($LASTEXITCODE -ne 0) { throw 'dependency verification failed' }
if (-not $SkipModel) {
    $wxqModels = Join-Path $wxqVenv 'models'
    & $wxqPython (Join-Path $PSScriptRoot 'download_model.py') $wxqModels
    if ($LASTEXITCODE -ne 0) { throw 'large-v3 download failed; rerun setup to resume' }
}
