# Registreert de 'lokalist-dashboard' taak in Windows Task Scheduler, zodat het
# webdashboard zelfstandig draait: start bij het opstarten van de server, blijft
# draaien zonder ingelogde gebruiker, en herstart automatisch na een crash.
#
# Uitvoeren op 192.168.4.105 (Appserver) in een elevated PowerShell:
#
#   Set-ExecutionPolicy -Scope Process Bypass
#   .\scripts\install_dashboard_service.ps1
#
# Het script vraagt om het wachtwoord van TRANSPORT\Jeroen.
#
# LET OP: de taak moet als TRANSPORT\Jeroen draaien, niet als SYSTEM. Het
# dashboard start Python-processen die met Windows Integrated Auth naar SQL
# Server verbinden; als SYSTEM zou dat het computeraccount TRANSPORT\APPSERVER$
# zijn en die heeft geen rechten op MENDRIXDB01.

$TaskName = "lokalist-dashboard"
$Root     = "C:\Apps\lokalist-weekrapportage"
$Starter  = "$Root\scripts\start_dashboard.cmd"
$WorkDir  = "$Root\web"
$Poort    = 80
$RunAs    = "TRANSPORT\Jeroen"

# --- controle vooraf ---------------------------------------------------------

# Zonder verhoogde rechten mislukken de firewallregel en de taakregistratie
# halverwege. Vang dat hier af in plaats van na het wachtwoordprompt.
$identiteit = [Security.Principal.WindowsIdentity]::GetCurrent()
$principal  = New-Object Security.Principal.WindowsPrincipal($identiteit)
if (-not $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
    throw "Dit venster is niet verhoogd. Start PowerShell via rechtsklik > 'Als administrator uitvoeren' en draai het script opnieuw."
}

if (-not (Test-Path $Starter)) {
    throw "Startscript niet gevonden: $Starter"
}

if (-not (Test-Path "$WorkDir\dist\server\index.js")) {
    throw "Het dashboard is nog niet gebouwd. Draai eerst in $WorkDir : npm install; npm run build"
}

if (-not (Get-Command node -ErrorAction SilentlyContinue)) {
    throw "node staat niet in PATH. Installeer Node 22 op deze machine."
}

# Poort 80 kan maar door een programma tegelijk gebruikt worden. Vind hier uit
# of iets anders hem al heeft, voordat de taak stilletjes faalt bij het opstarten.
$bezet = Get-NetTCPConnection -State Listen -LocalPort $Poort -ErrorAction SilentlyContinue
if ($bezet) {
    $procs = $bezet.OwningProcess | Sort-Object -Unique | ForEach-Object {
        (Get-Process -Id $_ -ErrorAction SilentlyContinue).ProcessName
    }
    throw "Poort $Poort is al in gebruik door: $($procs -join ', '). Kies een andere poort in scripts\start_dashboard.cmd."
}

# --- firewall: inkomend verkeer op de poort toestaan --------------------------

$regelNaam = "lokalist-dashboard (TCP-In)"
if (-not (Get-NetFirewallRule -DisplayName $regelNaam -ErrorAction SilentlyContinue)) {
    New-NetFirewallRule `
        -DisplayName $regelNaam `
        -Direction Inbound `
        -Protocol TCP `
        -LocalPort $Poort `
        -Action Allow `
        -Profile Domain `
        -ErrorAction Stop | Out-Null
    Write-Host "Firewallregel '$regelNaam' aangemaakt voor TCP $Poort (Domain-profiel)."
} else {
    Write-Host "Firewallregel '$regelNaam' bestond al."
}

# --- trigger: bij het opstarten van de server ---------------------------------

$trigger = New-ScheduledTaskTrigger -AtStartup
# Kleine marge zodat netwerk en DNS klaar zijn voordat Node bindt.
$trigger.Delay = "PT30S"

# --- actie: scripts\start_dashboard.cmd ---------------------------------------

$action = New-ScheduledTaskAction `
    -Execute $Starter `
    -WorkingDirectory $WorkDir

# --- instellingen: langlopend proces, herstart na een crash -------------------

$settings = New-ScheduledTaskSettingsSet `
    -ExecutionTimeLimit (New-TimeSpan -Seconds 0) `
    -MultipleInstances IgnoreNew `
    -RestartCount 3 `
    -RestartInterval (New-TimeSpan -Minutes 1) `
    -StartWhenAvailable

# --- vraag wachtwoord interactief ---------------------------------------------

$wachtwoord = Read-Host "Wachtwoord voor $RunAs" -AsSecureString
$credential = New-Object System.Management.Automation.PSCredential($RunAs, $wachtwoord)
$plainPw    = $credential.GetNetworkCredential().Password

# --- registreer of vervang bestaande taak -------------------------------------

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
Write-Host "Taak '$TaskName' geregistreerd. Start hem nu zonder te herstarten:"
Write-Host "  Start-ScheduledTask -TaskName '$TaskName'"
Write-Host ""
Write-Host "Controleren:"
Write-Host "  Get-NetTCPConnection -State Listen -LocalPort $Poort"
Write-Host "  Get-Content '$Root\logs\webserver.log' -Tail 20"
Write-Host ""
Write-Host "De naam lokalist.rapport komt van de DNS-server (Domeinserver, 192.168.4.101),"
Write-Host "niet van deze machine. Zie web/README.md, kopje 'Bereikbaar via lokalist.rapport'."
