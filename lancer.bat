@echo off
rem ======================================================================
rem  EnergiTN - premiere installation complete (double-cliquer ce fichier)
rem  1) environnement Python  2) bibliotheques  3) fichier .env
rem  4) base PostgreSQL  5) import ML + previsions  6) tests  7) site web
rem ======================================================================
chcp 65001 >nul
cd /d "%~dp0"
echo.
echo [1/7] Environnement Python (.venv)
if not exist ".venv\Scripts\python.exe" (
    python -m venv .venv || (echo ERREUR : Python introuvable. Installez Python 3.12 ou plus. & pause & exit /b 1)
)
call ".venv\Scripts\activate.bat"
cd backend

echo [2/7] Installation des bibliotheques (quelques minutes la premiere fois)
python -m pip install -q --upgrade pip
pip install -q -r requirements.txt || (echo ERREUR pendant pip install & pause & exit /b 1)

echo [3/7] Fichier backend\.env
if exist ".env" (
    echo     .env deja present
    goto env_ok
)
set "PGPASS="
set /p "PGPASS=    Mot de passe de l'utilisateur postgres (Entree = 123) : "
if not defined PGPASS set "PGPASS=123"
> .env echo DB_NAME=energitn
>> .env echo DB_USER=postgres
>> .env echo DB_PASSWORD=%PGPASS%
>> .env echo DB_HOST=localhost
>> .env echo DB_PORT=5432
echo     .env cree (modifiable dans backend\.env)
:env_ok

echo [4/7] Base PostgreSQL
python manage.py creer_base || (echo. & echo Verifiez que PostgreSQL est demarre et le mot de passe dans backend\.env & pause & exit /b 1)

echo [5/7] Donnees et modeles ML (regeneres apres un git clone : 2 a 10 min)
python manage.py preparer_ml || (pause & exit /b 1)
echo       Import des resultats ML, previsions .joblib, comptes de demo (1 a 3 min)
python manage.py bootstrap || (pause & exit /b 1)

echo [6/7] Tests automatiques
python manage.py test api || (echo ATTENTION : des tests ont echoue, voir ci-dessus & pause)

echo [7/7] Demarrage du site : http://127.0.0.1:8000/
echo     Comptes : foyer@demo.tn / analyste@demo.tn / admin@demo.tn   mot de passe : EnergiTN2026!
echo     Pour arreter : Ctrl+C
start "" http://127.0.0.1:8000/
python manage.py runserver
pause
