@echo off
rem EnergiTN - demarrage rapide (apres une premiere installation avec lancer.bat)
chcp 65001 >nul
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (echo Lancez d'abord lancer.bat & pause & exit /b 1)
call ".venv\Scripts\activate.bat"
cd backend
echo Site : http://127.0.0.1:8000/   (Ctrl+C pour arreter)
start "" http://127.0.0.1:8000/
python manage.py runserver
pause
