@echo off
rem Start het Lokalist-weekrapportagedashboard.
rem
rem Wordt aangeroepen door de Task Scheduler-taak 'lokalist-dashboard'
rem (zie scripts\install_dashboard_service.ps1). Handmatig starten hoeft niet.
rem
rem Node leest DASHBOARD_POORT en DASHBOARD_HOST uit de omgeving, niet uit .env.
rem Wil je een andere poort, pas hem hier aan en herstart de taak.

set "DASHBOARD_POORT=80"
set "DASHBOARD_HOST=0.0.0.0"

cd /d "%~dp0..\web" || exit /b 1

set "LOG=%~dp0..\logs\webserver.log"

if not exist "dist\server\index.js" (
  echo [%date% %time%] dist\server\index.js ontbreekt - draai eerst: npm run build >> "%LOG%"
  exit /b 1
)

echo [%date% %time%] dashboard start op %DASHBOARD_HOST%:%DASHBOARD_POORT% >> "%LOG%"
node dist\server\index.js >> "%LOG%" 2>&1
