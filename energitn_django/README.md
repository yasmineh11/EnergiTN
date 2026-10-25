# ÉnergiTN – projet Django unique (foyer + opérateur + API)

Un seul projet relie : connexion/inscription → espace foyer → vue opérateur, alimentés par la même base
(SQLite par défaut, PostgreSQL si `DB_NAME` est défini) et par l'API REST.

## Lancer (Windows : remplacez `source` par `.venv\Scripts\activate`)
    cd backend
    python -m venv .venv && source .venv/bin/activate
    pip install -r requirements.txt
    python manage.py migrate
    python manage.py seed_demo          # données SYNTHÉTIQUES de démonstration + 3 comptes
    python manage.py runserver          # http://127.0.0.1:8000/

Comptes de démo (mot de passe `demo1234`) : `foyer@demo.tn` → /foyer/ · `analyste@demo.tn` → /operateur/ ·
`admin@demo.tn` → /gestion/ (tableau de bord administrateur), puis /operateur/ et /admin/.

## Avec vos résultats ML (au lieu de la démo)
    python manage.py import_results --synthetic ../data/synthetic --processed ../data/processed
Importe households, daily, forecast_h1/h7_predictions, profiles, anomalies_flagged. Si un nom de colonne diffère,
la commande affiche les colonnes disponibles : adaptez `CANDIDATES` dans `api/management/commands/import_results.py`.
Reliez ensuite chaque compte foyer à un foyer dans /admin/ (UserProfile).

## Organisation
- `config/` réglages et routes · `api/` modèles, API REST, import, démo · `web/` pages et templates
- Pages : `/login/`, `/register/`, `/logout/`, `/foyer/`, `/operateur/` ; API : `/api/` (voir `/api/`)
- Rôles (`UserProfile.role`) : foyer (voit uniquement ses données), analyste, admin
- Tests : `python manage.py test api`

## Tableau de bord administrateur (`/gestion/`, rôle admin uniquement)
- **Utilisateurs et rôles** (UC09) : créer un compte, changer le rôle, lier un foyer, activer/désactiver.
- **Jeux de données** (UC14, UC15) : registre des sources (lignes, période, script producteur), bouton « Importer les résultats ML »
  (lit `ML_DATA_DIR`, par défaut `../data/`) et bouton « Générer les données synthétiques » (remplace tout par la démo).
- **Qualité des prévisions** (UC16) : MAPE du modèle, MAPE de la baseline « même jour la semaine dernière », gain, couverture q10–q90,
  erreur par région et par jour (calculées sur les prévisions qui ont une valeur réelle).

## À savoir
- Les pages lisent les données injectées par Django (`json_script`) ; l'API `/api/foyer/dashboard/` et
  `/api/operator/overview/` renvoie les mêmes JSON.
- « Prévision » = les 7 dernières dates de forecast_h1 de la base. Avec les CSV du guide, ce sont les prévisions de la
  période de test (été 2026), pas le futur : pour du futur, ajoutez l'inférence `.joblib` (Option B du guide Django).
- Opérateur : charge d'une région = prévision moyenne par foyer ÷ (record historique ×1,25), puis forme horaire type
  (hypothèse). Capacités en MW et sensibilité à la chaleur : valeurs fictives dans `api/regions.py`.
- Libellés « octobre / septembre » et barème tarifaire des gabarits sont indicatifs (à adapter).
- Données synthétiques : à présenter comme telles. Avant production : `DEBUG=0`, `SECRET_KEY`, `ALLOWED_HOSTS`.
