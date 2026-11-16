param([Parameter(Mandatory=$true)][string]$Actor)
$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
$pythonPath = Join-Path $projectRoot '.venv\Scripts\pythonw.exe'
if (!(Test-Path -LiteralPath $pythonPath)) { throw 'Project virtual environment not found.' }
if ($Actor -notmatch '^[\w.@+-]+$') { throw 'Invalid actor login.' }
$jobPath = Join-Path $projectRoot 'tools\run-performance-job.py'
$taskAction = New-ScheduledTaskAction -Execute $pythonPath -Argument ('"' + $jobPath + '" --actor "' + $Actor + '"') -WorkingDirectory $projectRoot
# The first Monday 00:00 is the intended preparation time; a five-minute retry
# publishes only after approvals and catches machine downtime without duplicates.
$trigger = New-ScheduledTaskTrigger -Once -At (Get-Date).AddMinutes(1) -RepetitionInterval (New-TimeSpan -Minutes 5)
$taskSettings = New-ScheduledTaskSettingsSet -StartWhenAvailable -MultipleInstances IgnoreNew -ExecutionTimeLimit (New-TimeSpan -Hours 1)
$principal = New-ScheduledTaskPrincipal -UserId ([System.Security.Principal.WindowsIdentity]::GetCurrent().Name) -LogonType Interactive -RunLevel Limited
Register-ScheduledTask -TaskName 'SSB Weekly Performance' -Action $taskAction -Trigger $trigger -Settings $taskSettings -Principal $principal -Description 'Prepare completed Tashkent weeks; publish only fully approved scores.' -Force
