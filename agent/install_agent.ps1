$ErrorActionPreference = 'Stop'
$TaskName = 'MaterialMind Auto-Sync Agent'
$Agent = Join-Path $PSScriptRoot 'materialmind_agent.py'
$Python = (Get-Command python -ErrorAction Stop).Source
Write-Host '第一步：建立 Agent 設定並登入 Supabase（若尚未設定）...'
python $Agent --setup
$Action = New-ScheduledTaskAction -Execute $Python -Argument ('"' + $Agent + '"') -WorkingDirectory $PSScriptRoot
$Trigger = New-ScheduledTaskTrigger -AtLogOn
$Settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries
Register-ScheduledTask -TaskName $TaskName -Action $Action -Trigger $Trigger -Settings $Settings -Description 'MaterialMind: automatically scans the SAP inventory Excel folder and syncs new daily snapshots to Supabase.' -Force
Write-Host "已建立 Windows 登入自動啟動工作：$TaskName"
Write-Host "Supabase 登入資訊已在安裝階段設定；refresh token 使用 Windows DPAPI 加密保存。"
Start-ScheduledTask -TaskName $TaskName
