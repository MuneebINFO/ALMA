@echo off
rem ---------------------------------------------------------------------------
rem Lance Alma en application fenetree, sans fenetre de console.
rem Double-cliquez sur ce fichier, ou utilisez le raccourci cree par
rem   python creer_raccourci.py
rem ---------------------------------------------------------------------------
setlocal
set "RACINE=%~dp0"
set "PYW=%RACINE%.venv\Scripts\pythonw.exe"

if exist "%PYW%" (
    start "" "%PYW%" "%RACINE%gui.py" %*
) else (
    rem Pas d environnement virtuel : on tente le Python du systeme.
    start "" pythonw "%RACINE%gui.py" %*
)
endlocal
