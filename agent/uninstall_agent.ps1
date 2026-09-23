$ErrorActionPreference = 'Stop'
$TaskName = 'MaterialMind Auto-Sync Agent'
Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false -ErrorAction SilentlyContinue
Write-Host "已移除：$TaskName"
