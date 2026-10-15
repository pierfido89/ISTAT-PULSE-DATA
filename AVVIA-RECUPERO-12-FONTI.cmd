@echo off
setlocal
chcp 65001 >nul
cd /d "%~dp0"
echo PULSE - RECUPERO 12 FONTI UFFICIALI
where py >nul 2>nul
if errorlevel 1 (echo [ERRORE] Python Launcher non disponibile. & pause & exit /b 1)
py -3 -m pip install --quiet requests beautifulsoup4 pytest tzdata
if errorlevel 1 (echo [ERRORE] installazione librerie. & pause & exit /b 1)
py -3 -m pytest -q tests\test_observer_sources_12.py
if errorlevel 1 (echo [ERRORE] test non passati. & pause & exit /b 1)
py -3 scripts\repair_observer_sources_12.py
if errorlevel 1 (echo [ERRORE] acquisizione. & pause & exit /b 1)
echo.
echo Report creati: data\observer_sources_12_status.json e data\observer_articles_12.json
echo Nessun file originale e stato sovrascritto.
pause
