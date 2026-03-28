@echo off
title SMART2D - Lancement

echo ============================================
echo   SMART2D - Demarrage Backend + Frontend
echo ============================================
echo.

:: Backend dans une nouvelle fenetre
echo [1/2] Lancement du Backend FastAPI (port 8000)...
start "SMART2D Backend" cmd /k "cd /d C:\dossier3\nlp\backend && ..\venv_nlp\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000"

:: Attendre 3s que le backend demarre
timeout /t 3 /nobreak >nul

:: Frontend dans une nouvelle fenetre
echo [2/2] Lancement du Frontend Vite (port 5173)...
start "SMART2D Frontend" cmd /k "set PATH=C:\Program Files\nodejs;%PATH% && cd /d C:\dossier3\nlp\frontend && npm run dev"

:: Attendre 4s que Vite demarre
timeout /t 4 /nobreak >nul

:: Ouvrir le navigateur
echo.
echo Ouverture de http://localhost:5173 ...
start http://localhost:5173

echo.
echo Les deux serveurs tournent dans leurs fenetres separees.
echo Fermez les fenetres "SMART2D Backend" et "SMART2D Frontend" pour tout arreter.
echo.
pause
