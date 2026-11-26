@echo off
rem EnergiTN - verification : fichiers presents, base utilisee, tests
chcp 65001 >nul
cd /d "%~dp0"
echo ===== Fichiers du projet
for %%F in (
  "backend\manage.py"
  "backend\.env"
  "backend\web\urls.py"
  "backend\web\templates\partials\tn_map.html"
  "backend\api\ml.py"
  "ml\inference.py"
  "models\forecast_h1.joblib"
  "models\forecast_h7.joblib"
  "data\processed\daily.csv"
  "data\synthetic\readings.csv"
) do (
  if exist %%F (echo   OK        %%~F) else (echo   MANQUANT  %%~F)
)
findstr /c:"tn_map" "backend\web\templates\landing.html" >nul && (echo   OK        carte de la Tunisie sur la page d'accueil) || (echo   MANQUANT  carte de la Tunisie sur la page d'accueil)
findstr /c:"apply_linear_base" "backend\api\ml.py" >nul && (echo   OK        modele ML hybride de l'equipe branche dans Django) || (echo   MANQUANT  modele ML hybride)
if not exist ".venv\Scripts\python.exe" (echo. & echo Lancez d'abord lancer.bat & pause & exit /b 1)
call ".venv\Scripts\activate.bat"
cd backend
echo.
echo ===== Base de donnees utilisee
python manage.py shell -v 0 -c "from django.db import connection as c; print('  ', c.vendor, '-', c.settings_dict['NAME'])"
echo.
echo ===== Tests automatiques (19)
python manage.py test api
pause
