# Registreert de 'lokalist-weekrapportage' taak in Windows Task Scheduler.
# Uitvoeren op 192.168.4.105 als TRANSPORT\adm-jeroen (elevated PowerShell):
#
#   Set-ExecutionPolicy -Scope Process Bypass
#   .\scripts\install_taskscheduler.ps1
#
# Het script vraagt om het wachtwoord van TRANSPORT\adm-jeroen.

$TaskName       = "lokalist-weekrapportage"
$PythonExe      = "C:\Apps\lokalist-weekrapportage\.venv\Scripts\python.exe"
$Script         = "C:\Apps\lokalist-weekrapportage\scripts\run_weekrapportage.py"
$WorkDir        = "C:\Apps\lokalist-weekrapportage"
$RunAs          = "TRANSPORT\Jeroen"

# --- trigger: elke vrijdag om 23:30 ---
$trigger = New-ScheduledTaskTrigger `
    -Weekly `
    -DaysOfWeek Friday `
    -At "23:30"

# --- actie: python scripts\run_weekrapportage.py ---
$action = New-ScheduledTaskAction `
    -Execute $PythonExe `
    -Argument $Script `
    -WorkingDirectory $WorkDir

# --- instellingen identiek aan mestbak-checker ---
$settings = New-ScheduledTaskSettingsSet `
    -ExecutionTimeLimit (New-TimeSpan -Hours 1) `
    -MultipleInstances IgnoreNew

# --- vraag wachtwoord interactief ---
$wachtwoord = Read-Host "Wachtwoord voor $RunAs" -AsSecureString
$credential  = New-Object System.Management.Automation.PSCredential($RunAs, $wachtwoord)
$plainPw     = $credential.GetNetworkCredential().Password

# --- registreer of vervang bestaande taak ---
Register-ScheduledTask `
    -TaskName $TaskName `
    -Trigger $trigger `
    -Action $action `
    -Settings $settings `
    -RunLevel Highest `
    -User $RunAs `
    -Password $plainPw `
    -Force

Write-Host ""
Write-Host "Taak '$TaskName' geregistreerd. Controleer in Task Scheduler."
Write-Host "Testrun (nu uitvoeren):"
Write-Host "  Start-ScheduledTask -TaskName '$TaskName'"
