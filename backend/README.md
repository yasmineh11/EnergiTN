# ÉnergiTN — Partie Django (backend)

Plateforme intelligente de suivi et de prévision de la consommation électrique des foyers tunisiens.

## 1. Présentation du projet

ÉnergiTN est une application web développée avec Django. Elle permet de suivre, d'analyser et de prévoir la consommation électrique des foyers tunisiens grâce à des modèles de Machine Learning.

La plateforme centralise les données dans une base PostgreSQL. Elle propose trois espaces selon le rôle de l'utilisateur : foyer, analyste énergétique et administrateur. L'interface est disponible en français et en arabe.

Ce dossier `backend/` contient toute la partie Django : configuration, modèles de données, liaison avec le Machine Learning, API REST et interface web.

### Objectifs

- Suivre la consommation électrique quotidienne des foyers.
- Visualiser l'historique de consommation.
- Prévoir la consommation des 7 prochains jours (J+1 à J+7) avec un intervalle de confiance.
- Détecter les consommations anormales et générer des alertes.
- Estimer la facture selon le barème STEG par tranches.
- Regrouper les foyers selon leur profil de consommation.
- Fournir aux analystes une vue globale de la demande par région.
- Permettre aux administrateurs de gérer les utilisateurs, la chaîne ML et la qualité des modèles.

### Technologies utilisées

| Partie | Technologies |
|---|---|
| Backend | Python 3.12+, Django 5.2 |
| Base de données | PostgreSQL 16 ou 17 (pilote psycopg) |
| Frontend | templates Django, HTML, CSS, JavaScript |
| API | Django REST Framework 3.15 |
| Machine Learning | pandas 3.0.6, numpy 2.5.4, scikit-learn 1.9.1, joblib 1.6.0 |
| Gestion du code | Git, GitHub |
| Environnement | Windows 10/11, Visual Studio Code |

## 2. Architecture générale

Le projet est organisé autour de deux parties :

- **La partie Machine Learning** (`ml/`, à la racine du projet) : génération et préparation des données, entraînement des modèles de prévision, calcul des profils et détection des anomalies. Elle produit des fichiers CSV et JSON dans `data/` et des modèles `.joblib` dans `models/`.
- **La partie Django** (`backend/`) : gestion des utilisateurs, import des résultats ML dans PostgreSQL, calcul des prévisions à partir des modèles `.joblib`, affichage des tableaux de bord et exposition de l'API.

Fonctionnement de la liaison :

```
ml/*.py  →  data/processed/*.csv  →  import_results  →  PostgreSQL  →  pages web et API
ml/*.py  →  models/*.joblib       →  api/ml.py (prévisions)  →  PostgreSQL
```

### Organisation des dossiers

```
energitn/
├── ml/                      scripts Machine Learning
├── data/                    données générées (non versionnées)
├── models/                  modèles .joblib (non versionnés)
└── backend/                 partie Django
    ├── manage.py
    ├── requirements.txt
    ├── .env.example         modèle du fichier de configuration
    ├── config/
    │   ├── settings.py      réglages, lecture du fichier .env
    │   └── urls.py          routes principales
    ├── api/                 cœur métier
    │   ├── models.py        modèles de données (tables)
    │   ├── ml.py            chargement des modèles, prévisions, détection
    │   ├── insights.py      scénario de chaleur, santé et dérive des modèles
    │   ├── pipeline.py      lancement des scripts ml/ depuis l'interface
    │   ├── billing.py       calcul de la facture STEG
    │   ├── facts.py         données et conseils de l'assistant
    │   ├── services.py      calculs des tableaux de bord
    │   ├── views.py         vues de l'API
    │   ├── serializers.py
    │   ├── urls.py          routes de l'API
    │   ├── tests.py         tests automatiques
    │   └── management/commands/
    │       ├── creer_base.py
    │       ├── preparer_ml.py
    │       ├── import_results.py
    │       ├── run_inference.py
    │       └── bootstrap.py
    └── web/                 interface utilisateur
        ├── views.py         pages par rôle
        ├── urls.py          routes des pages
        ├── i18n.py          traductions français / arabe
        ├── templates/       foyer/, analyste/, gestion/, auth.html
        └── static/          css/, js/
```

## 3. Prérequis

Avant de commencer, installer les outils suivants :

- Python 3.12 ou plus récent (cocher « Add python.exe to PATH » à l'installation).
- PostgreSQL 16 ou 17 (noter le mot de passe de l'utilisateur `postgres`).
- pgAdmin (installé avec PostgreSQL, recommandé pour visualiser la base).
- Git.
- Visual Studio Code.
- Un navigateur web.

Vérifier les installations dans un terminal :

```bat
python --version
pip --version
git --version
```

Python 3.10 ou 3.11 ne suffit pas : pandas 3 exige une version plus récente.

## 4. Récupérer le projet depuis GitHub

Chaque membre de l'équipe récupère sa propre copie du projet :

```bat
git clone URL_DU_DEPOT_GITHUB
cd energitn
```

Remplacer `URL_DU_DEPOT_GITHUB` par l'adresse réelle du dépôt.

Pour récupérer les dernières modifications :

```bat
git pull
```

Pour vérifier la branche actuelle :

```bat
git branch
```

Important : `git pull` récupère le code source et les migrations. Il ne récupère pas la base PostgreSQL, les comptes utilisateurs, ni les dossiers `data/` et `models/`, qui sont recréés sur chaque ordinateur.

## 5. Créer l'environnement Python

Depuis la racine du projet (`energitn/`) :

```bat
python -m venv .venv
```

Activer l'environnement virtuel :

- dans `cmd` : `.venv\Scripts\activate`
- dans PowerShell : `.\.venv\Scripts\Activate.ps1`

Si PowerShell bloque l'activation :

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
.\.venv\Scripts\Activate.ps1
```

Installer les dépendances. Un seul fichier suffit pour Django et pour le Machine Learning :

```bat
cd backend
pip install -r requirements.txt
```

Les versions de pandas, numpy, scikit-learn et joblib sont figées, car les modèles `.joblib` doivent être relus avec la même version que celle de l'entraînement.

Vérifier l'environnement :

```bat
python --version
pip list
```

Raccourci Windows : le fichier `lancer.bat`, à la racine du projet, exécute automatiquement les étapes 5 à 11.

## 6. Configurer PostgreSQL

### 6.1. Configurer la connexion Django

Les identifiants ne sont pas écrits dans `settings.py`. Celui-ci les lit dans le fichier `backend/.env`.

Créer ce fichier à partir du modèle :

```bat
copy .env.example .env
```

Puis l'ouvrir et renseigner vos identifiants :

```
DB_NAME=energitn
DB_USER=postgres
DB_PASSWORD=VOTRE_MOT_DE_PASSE
DB_HOST=localhost
DB_PORT=5432
```

Si le fichier `.env` est absent, ou si `DB_NAME` est vide, Django utilise SQLite (`db.sqlite3`). C'est pratique pour un test rapide, mais ce n'est pas la configuration du projet.

Sécurité : ne jamais envoyer le fichier `.env` ni son mot de passe PostgreSQL sur GitHub. Le fichier `.env` est déjà exclu par `.gitignore`.

### 6.2. Créer la base de données

Il n'est pas nécessaire de passer par pgAdmin. Depuis le dossier `backend/` :

```bat
python manage.py creer_base
```

Cette commande crée la base décrite dans `.env` (`energitn`, encodage UTF-8). Si la base existe déjà, elle ne fait rien.

Il est aussi possible de la créer dans pgAdmin : clic droit sur *Databases*, puis *Create*, puis *Database*, avec le nom `energitn`.

### 6.3. Vérifier la connexion

```bat
python manage.py shell
```

Puis :

```python
from django.db import connection
print(connection.vendor)
print(connection.settings_dict["NAME"])
print(connection.settings_dict["HOST"])
exit()
```

Résultat attendu :

```
postgresql
energitn
localhost
```

## 7. Créer les tables de la base de données

Les tables sont créées à partir des migrations Django. Depuis le dossier `backend/` :

```bat
python manage.py showmigrations
python manage.py migrate
python manage.py showmigrations
```

À retenir :

- Les fichiers de migrations sont récupérés avec Git (dossier `api/migrations/`).
- `migrate` crée les tables dans votre propre base PostgreSQL.
- `migrate` ne remplit pas les tables avec les données énergétiques (voir section 9).
- `migrate` ne crée aucun compte (voir section 10).
- Ne supprimez jamais les migrations existantes pour résoudre un problème sans vérifier d'abord l'état de la base.

## 8. Comprendre les principales tables

Tous les modèles se trouvent dans l'application `api` (fichier `api/models.py`).

| Modèle | Rôle |
|---|---|
| `Household` | foyer : identifiant (`H001`…), région, profil type, coefficient de climatisation |
| `DailyConsumption` | consommation journalière d'un foyer, en kWh |
| `Forecast` | prévision : `kind="backtest"` (évaluation, avec la valeur réelle) ou `kind="future"` (calculée par Django), horizon en jours, bornes `q10` et `q90` |
| `HouseholdProfile` | profil de consommation K-Means du foyer et ses indicateurs |
| `Alert` | anomalie détectée : type, gravité, kWh observé et attendu, source (`ml` ou `live`) |
| `Weather` | température par région et par jour |
| `Holiday` | jours fériés |
| `Outage` | coupures d'électricité par région |
| `ModelRun` | métriques d'un entraînement (MAPE, couverture, F1…) |
| `TariffBand` | tranches du barème STEG |
| `UserProfile` | rôle d'un utilisateur et, pour un foyer, le foyer qui lui est associé |
| `ChatMessage` | historique de l'assistant |
| `PipelineRun` | exécutions de la chaîne ML lancées depuis l'interface |

### Relations principales

- Un foyer possède plusieurs consommations quotidiennes.
- Un foyer peut avoir plusieurs prévisions et plusieurs alertes.
- Un foyer possède un seul profil de consommation.
- La région est un champ texte du foyer (par exemple `Gabes`). Les noms en français et en arabe sont définis dans `api/regions.py`.
- Les comptes sont stockés dans les tables d'authentification de Django. `UserProfile` relie chaque compte à son rôle et, pour un compte foyer, à un enregistrement de `Household`.

## 9. Préparer et importer les données Machine Learning

Les dossiers `data/` et `models/` ne sont pas versionnés sur GitHub. Ils sont régénérés sur chaque ordinateur par les scripts du dossier `ml/`.

### 9.1. Préparer les données

Depuis le dossier `backend/` :

```bat
python manage.py preparer_ml
```

Cette commande exécute les scripts officiels de `ml/`, dans l'ordre :

1. `generate_synthetic.py` : génère 30 foyers synthétiques (graine 42) à partir de la météo réelle `data/raw/weather.csv`.
2. `prepare.py` : nettoie et agrège les données dans `daily.csv`.
3. `train_forecast.py --horizon 1` : entraîne la prévision J+1.
4. `train_forecast.py --horizon 7` : entraîne la prévision J+7.
5. `profiles.py` : calcule les profils K-Means.
6. `anomalies.py` : détecte les anomalies.

Elle prend 2 à 10 minutes. Si les modèles existent déjà, elle ne fait rien ; l'option `--force` relance toute la chaîne. Grâce à la graine fixe, tous les membres obtiennent exactement les mêmes données.

### 9.2. Vérifier les fichiers générés

Le dossier `data/processed/` doit contenir :

- `daily.csv` : consommations quotidiennes.
- `forecast_h1_predictions.csv` : prévisions J+1.
- `forecast_h7_predictions.csv` : prévisions J+7.
- `profiles.csv` et `hourly_profiles.csv` : profils des foyers.
- `anomalies_flagged.csv` : anomalies détectées.

Le dossier `models/` doit contenir `forecast_h1.joblib`, `forecast_h7.joblib` et les fichiers `*_metrics.json`.

### 9.3. Importer les résultats dans PostgreSQL

```bat
python manage.py import_results
python manage.py run_inference
```

- `import_results` importe les CSV et les métriques dans les tables Django.
- `run_inference` charge les modèles `.joblib` et calcule les prévisions futures (J+1 à J+7) de chaque foyer.

La commande `bootstrap` regroupe tout en une seule étape : migrations, import, prévisions et comptes de démonstration.

```bat
python manage.py bootstrap
```

Résultats d'un import complet :

| Données importées | Nombre |
|---|---|
| Foyers | 30 |
| Consommations quotidiennes | 30 033 |
| Prévisions J+1 (évaluation) | 13 561 |
| Prévisions J+7 (évaluation) | 13 590 |
| Prévisions futures (7 jours × 30 foyers) | 210 |
| Profils | 30 |
| Alertes | 177 |

Remarque : la commande s'appelle bien `import_results`. Il n'existe pas de commande `import_ml_results` dans ce projet.

### 9.4. Vérifier les données après l'import

```bat
python manage.py shell
```

```python
from api.models import Household, DailyConsumption, Forecast, HouseholdProfile, Alert

print("Foyers :", Household.objects.count())
print("Consommations :", DailyConsumption.objects.count())
print("Prévisions :", Forecast.objects.count())
print("Prévisions futures :", Forecast.objects.filter(kind="future").count())
print("Profils :", HouseholdProfile.objects.count())
print("Alertes :", Alert.objects.count())

list(Household.objects.values("household_id", "region")[:10])
exit()
```

### 9.5. Comment Django utilise les modèles ML

Le fichier `api/ml.py` fait le lien entre Django et les modèles :

1. Il charge `forecast_h1.joblib` (pour J+1) et `forecast_h7.joblib` (pour J+2 à J+7).
2. Il reconstruit les 27 variables utilisées à l'entraînement : historique, température, jours fériés, week-end…
3. Il ajoute la base linéaire propre à chaque foyer (modèle hybride de l'équipe).
4. Il calcule la prévision et son intervalle q10–q90.

À chaque nouveau relevé saisi par un foyer, la consommation est comparée à la prévision. Si l'écart est trop important (plus de 3 écarts robustes et plus de 30 %), une alerte est créée, puis les prévisions sont recalculées.

Un test automatique vérifie que Django donne le même résultat que le script `ml/inference.py`.

## 10. Gestion des utilisateurs et des rôles

La plateforme distingue trois rôles.

### 10.1. Foyer

Un utilisateur ayant le rôle foyer :

- accède à son espace personnel (`/foyer/`) ;
- consulte uniquement les données de son foyer ;
- visualise son historique et ses prévisions ;
- saisit ou importe ses relevés (fichier CSV) ;
- consulte sa facture estimée et ses alertes ;
- utilise l'assistant énergie.

Chaque compte foyer doit être associé à un enregistrement existant de `Household`.

### 10.2. Analyste énergétique

Un utilisateur ayant le rôle analyste :

- consulte la demande prévue par région (`/analyste/`) ;
- simule un scénario de chaleur ;
- compare les profils de consommation par région ;
- consulte les anomalies récurrentes et les foyers à surveiller.

Il n'a pas accès à la gestion des comptes.

### 10.3. Administrateur

L'administrateur dispose de tous les accès de l'analyste et de l'espace de gestion (`/gestion/`) :

- création des comptes et modification des rôles ;
- association des comptes aux foyers ;
- activation ou désactivation des comptes ;
- relance de la chaîne ML et suivi de la qualité des modèles ;
- modification du barème ;
- accès à l'administration Django (`/admin/`).

### 10.4. Comptes de démonstration

La commande `bootstrap` crée trois comptes, avec le mot de passe `EnergiTN2026!` :

| Rôle | Adresse e-mail |
|---|---|
| Foyer | `foyer@demo.tn` |
| Analyste | `analyste@demo.tn` |
| Administrateur | `admin@demo.tn` |

Sur la page de connexion, l'encadré « Comptes de démonstration » permet de se connecter en un clic (uniquement en mode développement).

### 10.5. Créer un administrateur

```bat
python manage.py createsuperuser
```

Suivre les instructions du terminal. Un super-utilisateur est reconnu comme administrateur par l'application. Il accède aussi à http://127.0.0.1:8000/admin/.

### 10.6. Créer un compte analyste ou foyer

- **Analyste ou administrateur** : se connecter en administrateur, puis aller dans *Gestion*, *Utilisateurs et rôles*, créer le compte et choisir le rôle.
- **Foyer** : page *Créer un compte*. L'utilisateur choisit un foyer simulé (historique déjà disponible) ou son propre foyer (il importe alors au moins 14 jours de relevés).

Pour associer un utilisateur existant à un foyer depuis le shell Django :

```python
from django.contrib.auth import get_user_model
from api.models import UserProfile, Household

User = get_user_model()
user = User.objects.get(username="foyer_h001@gmail.com")
household = Household.objects.get(household_id="H001")

UserProfile.objects.update_or_create(
    user=user,
    defaults={"role": "foyer", "household": household},
)
```

Sans profil associé à un foyer, l'utilisateur ne peut pas afficher son espace personnel.

Remarque : dans la version actuelle, l'inscription publique est ouverte, mais uniquement pour des comptes foyer. Aucune limite du nombre de comptes foyer n'est programmée. Si l'équipe veut réserver la création des comptes à l'administrateur, cette règle doit être ajoutée côté serveur.

## 11. Lancer l'application Django

Vérifier que :

- l'environnement virtuel est activé ;
- PostgreSQL fonctionne ;
- la base `energitn` existe ;
- les migrations ont été appliquées ;
- les données ML ont été importées.

Depuis le dossier `backend/` :

```bat
python manage.py runserver
```

Ouvrir le navigateur sur http://127.0.0.1:8000/. Pour arrêter le serveur : Ctrl+C.

Raccourci Windows : `demarrer.bat`, à la racine du projet.

### Pages principales

| URL | Description |
|---|---|
| `/` | page d'accueil |
| `/login/` | connexion |
| `/register/` | création d'un compte foyer |
| `/logout/` | déconnexion |
| `/foyer/` | espace du foyer (tableau de bord, relevés, facture, profil, assistant, rapport) |
| `/analyste/` | espace de l'analyste (demande régionale, profils, anomalies) |
| `/gestion/` | espace de gestion de l'administrateur |
| `/admin/` | administration Django |
| `/api/` | API REST |

L'ancienne adresse `/operateur/` redirige vers `/analyste/`.

## 12. API REST

L'API fournit les données utilisées par les tableaux de bord. Elle demande une connexion (session Django). Un foyer n'accède qu'à ses propres données.

### API du foyer

- `GET /api/foyer/dashboard/` : prévisions, alertes et facture du foyer connecté.
- `GET /api/foyer/facts/` : données chiffrées utilisées par l'assistant.
- `POST /api/foyer/readings/` : ajoute un relevé, par exemple `{"date": "2026-10-01", "kwh": 12.4}`.
- `GET /api/foyer/scenario/?delta=4` : prévision si la température augmente de 4 °C.

### API de l'analyste (analyste et administrateur)

- `GET /api/operator/overview/` : demande prévue par région.
- `GET /api/operator/profiles/` : profils de consommation.
- `GET /api/operator/anomalies/` : anomalies.
- `GET /api/models/` : métriques des modèles.
- `GET /api/ml/health/` : état de la liaison entre Django et les modèles ML.

### API commune

- `POST /api/ml/predict/` : recalcule les prévisions d'un foyer (un foyer ne peut recalculer que le sien).
- `GET /api/households/`, `/api/forecasts/`, `/api/profiles/`, `/api/anomalies/` : listes filtrées selon le rôle.

Toutes les routes sont déclarées dans `api/urls.py`.

## 13. Fonctionnalités du tableau de bord de gestion

La page `/gestion/` est réservée à l'administrateur.

### Gestion des utilisateurs

- Création d'un utilisateur.
- Attribution d'un rôle.
- Association à un foyer.
- Activation ou désactivation d'un compte.

### Gestion des données et de la chaîne ML

- Consultation des fichiers de données et des modèles disponibles.
- Relance des scripts du dossier `ml/`, avec un journal affiché en direct.
- Import des résultats et calcul des prévisions.
- Import d'une prévision météo.

### Qualité des modèles

- MAPE du modèle et MAPE de la baseline.
- Gain du modèle par rapport à la baseline.
- Couverture de l'intervalle de prévision.
- Erreurs par région et par jour.
- Surveillance de la dérive (erreur sur les 30 derniers jours).
- Santé de la liaison Django et ML (4 contrôles automatiques).
- Prévision à la demande pour un foyer.

### Barème et référentiel

- Modification des tranches du barème STEG.
- Renommage des profils de consommation.

Résultats actuels des modèles : MAPE J+1 de 9,88 % contre 27,3 % pour la baseline, couverture de l'intervalle 78 %, F1 de la détection d'anomalies 0,67.

## 14. Tests et vérifications

Avant de considérer une installation comme opérationnelle, effectuer les vérifications suivantes.

Vérifier la configuration Django :

```bat
python manage.py check
```

Vérifier les migrations :

```bat
python manage.py showmigrations
```

Lancer les tests :

```bat
python manage.py test api
```

Le résultat attendu est `Ran 19 tests` puis `OK`. Les tests couvrent l'import des données, l'égalité entre Django et `ml/inference.py`, les droits par rôle, la détection d'anomalies, la facture, le scénario de chaleur, l'assistant et l'administration.

Vérifier les données : voir la section 9.4.

Vérifier les accès en se connectant avec :

- un compte foyer ;
- un compte analyste ;
- un compte administrateur.

Chaque utilisateur ne doit voir que les pages de son rôle. Par exemple, un foyer qui ouvre `/gestion/` doit être refusé.

Raccourci Windows : `verifier.bat`, à la racine du projet.

## 15. Travailler en équipe avec Git et GitHub

Le projet est développé par trois membres :

- yasmineh
- yasminel
- tayssir

Chaque membre travaille de préférence sur sa propre branche.

Récupérer les dernières modifications :

```bat
git pull
```

Vérifier la branche actuelle :

```bat
git branch
```

Créer une branche :

```bat
git checkout -b nom_de_la_branche
```

Ajouter les modifications :

```bat
git status
git add .
git status
```

Créer un commit :

```bat
git commit -m "Description des modifications"
```

Envoyer les modifications sur GitHub :

```bat
git push -u origin nom_de_la_branche
```

Récupérer les modifications de la branche principale :

```bat
git checkout main
git pull origin main
git checkout nom_de_la_branche
git merge main
```

En cas de conflit, corriger les fichiers concernés, puis faire un nouveau commit.

Après un `git pull`, selon ce qui a changé :

- `requirements.txt` modifié : `pip install -r requirements.txt`
- `api/models.py` ou `api/migrations/` modifié : `python manage.py migrate`
- un script de `ml/` modifié : `python manage.py preparer_ml --force`, puis `import_results` et `run_inference`

Bonne pratique : ne pas modifier directement la branche `main` sans coordination avec l'équipe. Utiliser des Pull Requests pour relire et intégrer les fonctionnalités.

## 16. Base de données : fonctionnement en équipe

Chaque membre utilise sa propre base PostgreSQL locale :

```
Ordinateur de Yasmine H.  →  energitn
Ordinateur de Yasmine L.  →  energitn
Ordinateur de Tayssir     →  energitn
```

Même si les trois bases portent le même nom, elles sont indépendantes. GitHub ne synchronise pas les bases de données.

### Ce qui est partagé par GitHub

- Le code Python.
- Les modèles Django et les migrations.
- Les templates HTML, le CSS et le JavaScript.
- Les scripts du dossier `ml/`.
- La météo réelle `data/raw/weather.csv`.
- Le fichier `.env.example` et la documentation.

### Ce qui n'est pas partagé

- Le contenu de la base PostgreSQL.
- Les comptes utilisateurs et les mots de passe.
- Le fichier `.env`.
- Les dossiers `data/` et `models/`.

Pour obtenir les mêmes données sur chaque ordinateur, chaque membre exécute `preparer_ml` puis `bootstrap`. Comme la génération utilise une graine fixe, les données obtenues sont identiques.

## 17. Problèmes fréquents et solutions

### Erreur : ModuleNotFoundError

Une bibliothèque Python est manquante, ou l'environnement virtuel n'est pas activé.

```bat
.venv\Scripts\activate
pip install -r requirements.txt
```

### Erreur : password authentication failed

Le mot de passe est incorrect. Corriger `DB_PASSWORD` dans `backend/.env`.

### Erreur : connexion PostgreSQL impossible

Vérifier :

- que le service PostgreSQL est démarré (`services.msc`, service *postgresql-x64-17*) ;
- que la base `energitn` existe (`python manage.py creer_base`) ;
- que l'utilisateur et le mot de passe de `.env` sont corrects ;
- que le port est 5432.

### Erreur : relation does not exist

Une table n'existe pas dans la base utilisée.

```bat
python manage.py migrate
```

Vérifier aussi que Django utilise PostgreSQL et non SQLite (section 6.3).

### Les tableaux de bord sont vides

Vérifier :

- que `preparer_ml` puis `bootstrap` ont été exécutés ;
- que les tables contiennent des enregistrements (section 9.4) ;
- que le compte a le bon rôle ;
- que le compte foyer est relié à un foyer existant.

### « Modèles ML indisponibles » en haut de la page

Les fichiers `models/*.joblib` sont absents. Lancer :

```bat
python manage.py preparer_ml
python manage.py run_inference
```

### Erreur lors de l'import ML

Vérifier que les fichiers de la section 9.2 existent. En cas de doute, relancer `python manage.py preparer_ml --force`.

Aucun chemin absolu n'est écrit dans le code : les dossiers `ml/`, `data/` et `models/` sont trouvés à partir de l'emplacement du projet.

### Erreur avec python manage.py dbshell

Cette commande nécessite le client `psql` dans le PATH. S'il est absent, Django peut quand même communiquer avec PostgreSQL : utiliser pgAdmin ou `python manage.py shell`.

## 18. Sécurité et préparation à la production

Avant de déployer l'application :

- mettre `DEBUG=0` dans `.env` (HTTPS et cookies sécurisés s'activent alors automatiquement) ;
- définir une vraie `SECRET_KEY` dans `.env` ;
- configurer `ALLOWED_HOSTS` ;
- exécuter `python manage.py collectstatic` ;
- supprimer ou modifier les comptes de démonstration ;
- ne jamais publier les mots de passe PostgreSQL ni versionner `.env` ;
- mettre en place des sauvegardes de la base (`pg_dump`).

Les permissions par rôle sont vérifiées côté serveur, dans les vues et dans l'API, et pas seulement dans l'interface.

### Fichier .gitignore du projet

```
data/*
!data/raw/
data/raw/*
!data/raw/weather.csv
models/
.venv/
__pycache__/
*.pyc
backend/db.sqlite3
backend/staticfiles/
backend/.env
.env
```

Les données et les modèles ne sont pas versionnés, car ils sont régénérés à l'identique par `preparer_ml`. Seule la météo réelle est conservée, pour obtenir le même résultat sans connexion Internet.

## 19. Procédure complète pour une nouvelle installation

Ordre recommandé pour chaque membre qui récupère le projet pour la première fois.

Étape 1 — Récupérer le code

```bat
git clone URL_DU_DEPOT_GITHUB
cd energitn
```

Étape 2 — Créer et activer l'environnement Python

```bat
python -m venv .venv
.venv\Scripts\activate
```

Étape 3 — Installer les dépendances

```bat
cd backend
pip install -r requirements.txt
```

Étape 4 — Configurer les identifiants PostgreSQL

```bat
copy .env.example .env
```

Puis renseigner `DB_PASSWORD` dans `.env`.

Étape 5 — Créer la base PostgreSQL

```bat
python manage.py creer_base
```

Étape 6 — Générer les données et les modèles ML

```bat
python manage.py preparer_ml
```

Étape 7 — Créer les tables, importer les données et créer les comptes de démonstration

```bat
python manage.py bootstrap
```

Étape 8 — Créer un administrateur personnel (facultatif)

```bat
python manage.py createsuperuser
```

Étape 9 — Vérifier le projet

```bat
python manage.py check
python manage.py test api
```

Étape 10 — Démarrer le serveur

```bat
python manage.py runserver
```

Accéder à http://127.0.0.1:8000/.

Sous Windows, le fichier `lancer.bat` (à la racine) exécute les étapes 2 à 10 automatiquement.

## 20. Remarques importantes sur les données et les prévisions

- Les consommations sont synthétiques et doivent être présentées comme telles. La météo est réelle (Open-Meteo).
- Les prévisions de type `backtest` servent à évaluer les modèles : elles sont comparées aux valeurs réelles.
- Les prévisions de type `future` sont calculées par Django avec `run_inference`, chaque nuit ou à chaque nouveau relevé.
- Les capacités régionales et le barème STEG (grille du 1er mai 2022) sont des hypothèses documentées, modifiables dans l'interface.
- Les indicateurs de qualité nécessitent des valeurs réelles pour calculer les erreurs.
- Un nouveau foyer réel utilise une droite moyenne tant qu'il n'a pas assez d'historique : ses premières prévisions sont moins précises.

## 21. Conclusion

ÉnergiTN rassemble le traitement des données, les modèles de Machine Learning et une application web Django. Les foyers, les analystes et les administrateurs exploitent ainsi les résultats, chacun dans son espace.

Pour installer le projet sur un nouvel ordinateur, il faut retenir quatre étapes :

1. Récupérer le code depuis GitHub.
2. Installer les dépendances et configurer PostgreSQL (`.env`, `creer_base`).
3. Générer et importer les données ML (`preparer_ml`, `bootstrap`).
4. Lancer le serveur Django.

Commande de démarrage après configuration :

```bat
python manage.py runserver
```

Projet développé dans le cadre du projet ÉnergiTN.
