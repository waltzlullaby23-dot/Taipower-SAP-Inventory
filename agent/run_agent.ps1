$ErrorActionPreference = 'Stop'
$agent = Join-Path $PSScriptRoot 'materialmind_agent.py'
if (-not (Get-Command python -ErrorAction SilentlyContinue)) {
    throw '找不到 Python。請先安裝 Python 3.11+，並勾選 Add Python to PATH。'
}
python $agent
