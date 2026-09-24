$ErrorActionPreference = 'Stop'
$TaskName = 'MaterialMind Auto-Sync Agent'
$AgentDir = $PSScriptRoot
$Agent = Join-Path $AgentDir 'materialmind_agent.py'

if (-not (Get-Command python -ErrorAction SilentlyContinue)) {
    throw '找不到 Python。請先安裝 Python 3.11+，並勾選 Add Python to PATH。'
}

Write-Host '=== MaterialMind V3 Agent ==='
Write-Host '第一次安裝會要求輸入 Supabase URL、Publishable Key、Email/Password。'
python $Agent --setup

$Action = New-ScheduledTaskAction -Execute 'python' -Argument ('"' + $Agent + '"')
$Trigger = New-ScheduledTaskTrigger -AtLogOn
$Principal = New-ScheduledTaskPrincipal -UserId $env:USERNAME -LogonType Interactive -RunLevel Limited
$Settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -StartWhenAvailable
Register-ScheduledTask -TaskName $TaskName -Action $Action -Trigger $Trigger -Principal $Principal -Settings $Settings -Force | Out-Null
Start-ScheduledTask -TaskName $TaskName
Write-Host "已建立並啟動：$TaskName"
