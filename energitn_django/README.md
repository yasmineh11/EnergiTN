# ÉnergiTN — Plateforme intelligente de suivi et de prévision de la consommation énergétique

## 1. Présentation du projet

**ÉnergiTN** est une application web développée avec Django qui permet de suivre, analyser et prévoir la consommation énergétique des foyers tunisiens grâce à des modèles de Machine Learning.

La plateforme centralise les données énergétiques dans une base de données PostgreSQL et propose différents espaces selon le rôle de l'utilisateur.

### Objectifs

- Suivre la consommation énergétique quotidienne des foyers.
- Visualiser l'historique de consommation.
- Consulter les prévisions énergétiques à court terme.
- Détecter les anomalies de consommation et générer des alertes.
- Regrouper les foyers selon leurs profils de consommation.
- Fournir aux analystes une vue globale des régions et des indicateurs énergétiques.
- Permettre aux administrateurs de gérer les utilisateurs, les foyers et les données.

### Technologies utilisées

| Partie | Technologies |
|---|---|
| Backend | Python, Django |
| Base de données | PostgreSQL |
| Frontend | HTML, CSS, JavaScript, templates Django |
| API | Django REST Framework (si activé dans la configuration) |
| Machine Learning | Python, Pandas, Scikit-learn et bibliothèques du projet ML |
| Gestion du code | Git, GitHub |
| Environnement | Windows 10/11, Visual Studio Code |

---

## 2. Architecture générale

Le projet est organisé autour de deux parties principales :

1. **La partie Machine Learning** : préparation des données, entraînement des modèles, génération des prévisions, profils et anomalies.
2. **La partie Django** : gestion des utilisateurs, stockage des résultats ML, affichage des tableaux de bord et exposition des API.

### Organisation des dossiers

```text
energitn/
│
├── data/
│   └── processed/
│       ├── daily.csv
│       └── ... autres fichiers générés par le pipeline ML
│
├── ml/
│   ├── generate_synthetic.py
│   ├── prepare.py
│   ├── train_forecast.py
│   ├── profiles.py
│   ├── anomalies.py
│   └── ...
│
├── energitn_django/
│   └── backend/
│       ├── manage.py
│       ├── requirements.txt
│       │
│       ├── config/
│       │   ├── settings.py
│       │   └── urls.py
│       │
│       ├── api/
│       │   ├── models.py
│       │   ├── views.py
│       │   ├── services.py
│       │   └── management/
│       │
│       ├── energy/
│       │   ├── models.py
│       │   └── management/
│       │       └── commands/
│       │           └── import_ml_results.py
│       │
│       ├── web/
│       │   ├── views.py
│       │   ├── urls.py
│       │   └── templates/
│       │
│       └── ...
│
├── .gitignore
└── README.md
```

> L'arborescence ci-dessus représente l'organisation logique du projet. Certains fichiers ou dossiers peuvent varier selon la branche et les dernières modifications.

---

## 3. Prérequis

Avant de commencer, installer les outils suivants :

- Python 3.10 ou une version compatible avec les dépendances du projet.
- PostgreSQL.
- pgAdmin (recommandé pour visualiser et gérer la base de données).
- Git.
- Visual Studio Code.
- Un navigateur web.

Vérifier les installations dans PowerShell :

```powershell
python --version
pip --version
git --version
```

Vérifier également que PostgreSQL fonctionne et que pgAdmin permet de se connecter au serveur local.

---

## 4. Récupérer le projet depuis GitHub

Chaque membre de l'équipe doit récupérer sa propre copie du projet.

Ouvrir PowerShell ou le terminal de VS Code :

```powershell
git clone URL_DU_DEPOT_GITHUB
```

Remplacer `URL_DU_DEPOT_GITHUB` par l'adresse réelle du dépôt.

Entrer dans le dossier :

```powershell
cd energitn
```

Pour récupérer les dernières modifications :

```powershell
git pull
```

Pour vérifier la branche actuelle :

```powershell
git branch
```

**Important :** `git pull` récupère le code source et les migrations qui ont été envoyés sur GitHub. Il ne récupère pas automatiquement la base de données PostgreSQL, les comptes utilisateurs ni les données importées.

---

## 5. Créer l'environnement Python

Depuis la racine du projet :

```powershell
python -m venv .venv
```

Activer l'environnement virtuel :

```powershell
.\.venv\Scripts\Activate.ps1
```

Si PowerShell bloque l'activation, exécuter :

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
```

Puis réessayer :

```powershell
.\.venv\Scripts\Activate.ps1
```

Installer les dépendances Django :

```powershell
cd energitn_django\backend
pip install -r requirements.txt
```

Si le projet possède également un fichier de dépendances spécifique au dossier ML, installer ses dépendances dans le même environnement ou suivre les instructions définies dans ce dossier.

Vérifier l'environnement :

```powershell
python --version
pip list
```

---

## 6. Configurer PostgreSQL

### 6.1. Créer la base de données

Chaque membre peut utiliser une base PostgreSQL locale pour son environnement de développement.

Ouvrir pgAdmin :

1. Se connecter au serveur PostgreSQL.
2. Ouvrir la section Databases.
3. Faire un clic droit sur Databases.
4. Choisir Create → Database.
5. Donner le nom suivant :

```text
energitn_db
```

Il faut créer cette base une seule fois sur chaque installation locale.

### 6.2. Configurer la connexion Django

Dans `config/settings.py`, vérifier la configuration de la base de données.

Exemple de configuration PostgreSQL :

```python
DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": "energitn_db",
        "USER": "postgres",
        "PASSWORD": "VOTRE_MOT_DE_PASSE",
        "HOST": "localhost",
        "PORT": "5432",
    }
}
```

Les identifiants doivent correspondre à ceux de votre installation PostgreSQL.

Si le projet utilise un fichier `.env`, renseigner les variables attendues par `settings.py` au lieu d'inscrire les identifiants directement dans le code.

**Sécurité :** ne jamais envoyer son fichier `.env`, son mot de passe PostgreSQL ou ses clés secrètes sur GitHub.

### 6.3. Vérifier la connexion

Dans le terminal, depuis le dossier qui contient `manage.py` :

```powershell
python manage.py shell
```

Puis :

```python
from django.db import connection

print(connection.vendor)
print(connection.settings_dict["NAME"])
print(connection.settings_dict["HOST"])
```

Résultat attendu :

```text
postgresql
energitn_db
localhost
```

Quitter le shell :

```python
exit()
```

---

## 7. Créer les tables de la base de données

Après avoir récupéré le projet et configuré PostgreSQL, il faut créer les tables à partir des migrations Django.

Depuis le dossier contenant `manage.py` :

```powershell
python manage.py showmigrations
```

Appliquer les migrations :

```powershell
python manage.py migrate
```

Pour vérifier les migrations :

```powershell
python manage.py showmigrations
```

Les migrations permettent de créer les tables correspondant aux modèles Django.

**À retenir :**

- Les fichiers de migrations sont récupérés avec Git lorsqu'ils sont correctement ajoutés au dépôt.
- La commande `migrate` crée les tables dans votre propre base PostgreSQL.
- Elle ne remplit pas automatiquement les tables avec les données énergétiques.
- Elle ne crée pas automatiquement les comptes des foyers ni les comptes analystes.

Ne supprimez pas les migrations existantes pour résoudre un problème de synchronisation sans vérifier d'abord l'état de la base.

---

## 8. Comprendre les principales tables

L'application utilise notamment les modèles de l'application `energy`.

| Modèle | Rôle |
|---|---|
| `Region` | Stocke les régions |
| `Household` | Représente les foyers |
| `DailyConsumption` | Stocke les consommations quotidiennes |
| `ModelRun` | Enregistre les exécutions des modèles |
| `Forecast` | Stocke les prévisions énergétiques |
| `Profile` | Stocke les profils ou clusters des foyers |
| `Alert` | Stocke les anomalies et alertes détectées |

### Relations principales

- Un foyer appartient à une région.
- Un foyer possède plusieurs consommations quotidiennes.
- Un foyer peut avoir plusieurs prévisions.
- Un foyer possède un profil de consommation.
- Un foyer peut avoir plusieurs alertes.
- Une prévision peut être associée à une exécution du modèle ML.

Les comptes Django sont stockés dans les tables d'authentification de Django. Le modèle `UserProfile` permet de relier un utilisateur à son rôle et, pour un compte foyer, à un foyer de la table `energy.Household`.

---

## 9. Préparer et importer les données Machine Learning

Les données ML ne sont pas automatiquement téléchargées avec Git si elles ne sont pas versionnées dans le dépôt.

Il faut donc récupérer les fichiers nécessaires au pipeline ML et vérifier qu'ils sont présents dans les dossiers attendus.

### 9.1. Préparer les données

Le pipeline ML comprend notamment les étapes suivantes :

1. Génération ou récupération des données.
2. Préparation et nettoyage des données.
3. Entraînement des modèles de prévision.
4. Génération des prévisions à J+1 et J+7.
5. Création des profils de consommation.
6. Détection des anomalies.

Les scripts concernés sont notamment :

```text
ml/
├── generate_synthetic.py
├── prepare.py
├── train_forecast.py
├── profiles.py
└── anomalies.py
```

Les commandes exactes d'exécution doivent respecter les arguments et l'ordre définis dans les scripts du dossier `ml`.

### 9.2. Vérifier les fichiers générés

Le dossier de données traitées est :

```text
data/processed/
```

Il doit contenir les fichiers CSV attendus par la commande d'importation Django, notamment :

- Les consommations quotidiennes.
- Les prévisions J+1.
- Les prévisions J+7.
- Les profils des foyers.
- Les anomalies détectées.

Le nom exact de chaque fichier doit correspondre à celui attendu par la commande d'importation.

### 9.3. Importer les résultats dans PostgreSQL

La commande utilisée avec succès dans la version actuelle du projet est :

```powershell
python manage.py import_ml_results
```

Cette commande importe les résultats ML dans les modèles Django correspondants.

Lors du dernier import réussi, les résultats étaient :

| Données importées | Nombre |
|---|---:|
| Foyers | 30 |
| Consommations quotidiennes | 30 120 |
| Prévisions J+1 | 13 561 |
| Prévisions J+7 | 13 590 |
| Profils | 30 |
| Alertes | 147 |

Ces nombres correspondent à un jeu de données de démonstration précis. Ils ne sont pas garantis pour chaque nouvelle exécution ou chaque nouveau jeu de données.

**Attention à la commande `import_results` :** l'ancien README mentionnait également :

```powershell
python manage.py import_results
```

Cette commande appartient à un ancien mécanisme d'importation. Pour la version actuelle, utiliser `import_ml_results` si cette commande est bien présente dans la branche récupérée. Ne pas exécuter les deux commandes sans vérifier leurs fonctions et leurs effets sur les données.

### 9.4. Vérifier les données après l'import

Ouvrir le shell Django :

```powershell
python manage.py shell
```

Puis :

```python
from energy.models import (
    Region,
    Household,
    DailyConsumption,
    Forecast,
    Profile,
    Alert
)

print("Regions :", Region.objects.count())
print("Foyers :", Household.objects.count())
print("Consommations :", DailyConsumption.objects.count())
print("Prévisions :", Forecast.objects.count())
print("Profils :", Profile.objects.count())
print("Alertes :", Alert.objects.count())
```

Pour afficher quelques foyers :

```python
list(Household.objects.values("id", "code", "region__name")[:10])
```

Quitter :

```python
exit()
```

---

## 10. Gestion des utilisateurs et des rôles

La plateforme distingue trois rôles principaux.

### 10.1. Foyer

Un utilisateur ayant le rôle `foyer` :

- Accède à son espace personnel.
- Consulte uniquement les données de son foyer.
- Visualise son historique de consommation.
- Consulte ses prévisions.
- Consulte les alertes qui concernent son foyer.

Chaque compte foyer doit être associé à un enregistrement existant dans `energy.Household`.

### 10.2. Analyste

Un utilisateur ayant le rôle `analyste` :

- Consulte les indicateurs énergétiques.
- Analyse les consommations.
- Consulte les prévisions.
- Compare les régions.
- Consulte les alertes.
- Gère les alertes selon les autorisations prévues dans l'application.

### 10.3. Administrateur

L'administrateur dispose des droits de gestion :

- Création des comptes.
- Modification des rôles.
- Association des comptes aux foyers.
- Activation ou désactivation des comptes.
- Accès à l'administration Django.
- Gestion des données et des utilisateurs.

### 10.4. Créer un administrateur

Pour créer le premier administrateur d'une nouvelle installation :

```powershell
python manage.py createsuperuser
```

Suivre les instructions du terminal.

Accéder ensuite à :

```text
http://127.0.0.1:8000/admin/
```

### 10.5. Créer un compte foyer

La création des comptes foyers doit être effectuée par l'administrateur, conformément aux règles du projet.

Pour associer un utilisateur existant à un foyer depuis le shell Django :

```powershell
python manage.py shell
```

Exemple :

```python
from django.contrib.auth import get_user_model
from api.models import UserProfile
from energy.models import Household

User = get_user_model()

user = User.objects.get(username="foyer_h001@gmail.com")
household = Household.objects.get(code="H001")

profile, created = UserProfile.objects.update_or_create(
    user=user,
    defaults={
        "role": "foyer",
        "household": household
    }
)
```

Adapter le nom d'utilisateur et le code du foyer selon les données disponibles.

Cette association est importante : sans profil correctement configuré et sans foyer associé, l'utilisateur ne pourra pas accéder correctement à son espace personnel.

### 10.6. Limiter les comptes foyers

La règle fonctionnelle prévue pour le projet est de limiter le nombre de comptes foyers à trois au maximum.

La vérification de cette limite doit être effectuée côté serveur lors de la création des comptes, et pas uniquement dans l'interface graphique.

Les comptes doivent être créés par l'administrateur. L'inscription publique doit être désactivée si elle n'est plus prévue dans la version finale.

---

## 11. Lancer l'application Django

Vérifier que :

- L'environnement virtuel est activé.
- PostgreSQL fonctionne.
- La base `energitn_db` existe.
- Les migrations ont été appliquées.
- Les données ML ont été importées si nécessaire.

Depuis le dossier contenant `manage.py` :

```powershell
python manage.py runserver
```

Ouvrir le navigateur :

```text
http://127.0.0.1:8000/
```

### Pages principales

| URL | Description |
|---|---|
| `/login/` | Connexion |
| `/logout/` | Déconnexion |
| `/foyer/` | Espace du foyer |
| `/operateur/` | Tableau de bord de l'analyste / opérateur |
| `/gestion/` | Tableau de bord de gestion |
| `/admin/` | Administration Django |
| `/api/` | Accès aux routes API, selon la configuration |

La disponibilité de chaque page dépend du routage et des permissions configurés dans la branche utilisée.

---

## 12. API REST

Le projet expose des routes API permettant de récupérer les informations utilisées par les tableaux de bord.

Exemples de routes présentes dans l'architecture du projet :

```text
/api/foyer/dashboard/
/api/operator/overview/
/api/
```

### API du foyer

```text
/api/foyer/dashboard/
```

Elle fournit les informations nécessaires au tableau de bord d'un foyer connecté.

### API de l'analyste

```text
/api/operator/overview/
```

Elle fournit une vue globale des données énergétiques, notamment les consommations, les prévisions et les informations par région.

Les routes nécessitent les permissions et l'authentification définies dans Django.

Pour consulter toutes les routes disponibles, vérifier les fichiers `urls.py` des applications `config`, `api` et `web`.

---

## 13. Fonctionnalités du tableau de bord de gestion

La page `/gestion/` est destinée à l'administrateur.

Elle regroupe les fonctionnalités de gestion prévues pour le projet.

### Gestion des utilisateurs

- Création d'un utilisateur.
- Attribution d'un rôle.
- Association à un foyer.
- Activation ou désactivation d'un compte.

### Gestion des jeux de données

- Consultation des données disponibles.
- Suivi des sources de données.
- Importation des résultats ML.
- Génération de données synthétiques si la commande correspondante est disponible.

### Qualité des prévisions

Les indicateurs prévus permettent notamment d'évaluer :

- Le MAPE du modèle.
- Le MAPE d'une baseline.
- Le gain du modèle par rapport à la baseline.
- La couverture des intervalles de prévision.
- Les erreurs par région.
- Les erreurs par jour.

Les métriques calculées dépendent de la présence de valeurs réelles associées aux prévisions.

---

## 14. Tests et vérifications

Avant de considérer une installation comme opérationnelle, effectuer les vérifications suivantes.

### Vérifier la configuration Django

```powershell
python manage.py check
```

### Vérifier les migrations

```powershell
python manage.py showmigrations
```

### Lancer les tests

```powershell
python manage.py test
```

L'ancien README mentionnait :

```powershell
python manage.py test api
```

Cette commande peut être utilisée pour tester uniquement l'application `api`, si les tests correspondants sont présents.

### Vérifier les données

```powershell
python manage.py shell
```

```python
from energy.models import Household, DailyConsumption, Forecast, Alert

print(Household.objects.count())
print(DailyConsumption.objects.count())
print(Forecast.objects.count())
print(Alert.objects.count())
```

### Vérifier le tableau de bord

Tester les accès avec :

- Un compte foyer associé à un foyer existant.
- Un compte analyste.
- Un compte administrateur.

Vérifier que chaque utilisateur ne voit que les fonctionnalités autorisées pour son rôle.

---

## 15. Travailler en équipe avec Git et GitHub

Le projet est développé par trois membres :

- `yasmineh`
- `yasminel`
- `tayssir`

Chaque membre travaille de préférence sur sa propre branche.

### Récupérer les dernières modifications

```powershell
git pull
```

### Vérifier la branche actuelle

```powershell
git branch
```

### Créer une branche

```powershell
git checkout -b nom_de_la_branche
```

Exemple :

```powershell
git checkout -b yasminel
```

### Ajouter les modifications

```powershell
git status
git add .
git status
```

### Créer un commit

```powershell
git commit -m "Description des modifications"
```

### Envoyer les modifications sur GitHub

```powershell
git push -u origin nom_de_la_branche
```

Exemple :

```powershell
git push -u origin yasminel
```

### Récupérer les modifications de la branche principale

Si la branche principale du dépôt est `main` :

```powershell
git checkout main
git pull origin main
```

Puis revenir à sa branche :

```powershell
git checkout nom_de_la_branche
```

Intégrer les changements de `main` si nécessaire :

```powershell
git merge main
```

En cas de conflit, résoudre les fichiers concernés, puis effectuer un nouveau commit.

**Bonne pratique :** ne pas modifier directement la branche principale sans coordination avec l'équipe. Utiliser des Pull Requests pour relire et intégrer les fonctionnalités.

---

## 16. Base de données : fonctionnement en équipe

Chaque membre peut disposer de sa propre base PostgreSQL locale.

Exemple :

```text
Ordinateur de Yasmine H.  → energitn_db
Ordinateur de Yasmine L.  → energitn_db
Ordinateur de Tayssir     → energitn_db
```

Même si les trois bases portent le même nom, elles sont indépendantes.

GitHub ne synchronise pas les bases de données.

### Ce qui est partagé par GitHub

- Le code Python.
- Les modèles Django.
- Les migrations.
- Les templates HTML, CSS et JavaScript.
- Les scripts ML versionnés.
- Les fichiers de configuration non sensibles.
- La documentation.

### Ce qui n'est pas automatiquement partagé

- Les données PostgreSQL.
- Les comptes utilisateurs.
- Les mots de passe.
- Les données importées dans la base.
- Les fichiers de données non versionnés.
- Les résultats ML non versionnés.

Pour obtenir les mêmes données sur chaque ordinateur, chaque membre doit disposer des fichiers nécessaires puis exécuter les migrations et la commande d'importation.

Pour une démonstration commune ou un environnement de test, une base PostgreSQL hébergée peut être configurée. Il faudra alors gérer les accès et les identifiants de manière sécurisée.

---

## 17. Problèmes fréquents et solutions

### Erreur : `ModuleNotFoundError`

Une bibliothèque Python est manquante.

Solution :

```powershell
pip install -r requirements.txt
```

Vérifier que le bon environnement virtuel est activé.

### Erreur : connexion PostgreSQL impossible

Vérifier :

- Que le serveur PostgreSQL est démarré.
- Que la base `energitn_db` existe.
- Que le nom d'utilisateur et le mot de passe sont corrects.
- Que le port est correct, généralement `5432`.
- Que les paramètres de `settings.py` correspondent à votre configuration.

### Erreur : `relation does not exist`

Une table n'existe pas dans la base utilisée.

Solution :

```powershell
python manage.py showmigrations
python manage.py migrate
```

Vérifier également que Django utilise bien PostgreSQL et non une ancienne base SQLite.

### Les tableaux de bord sont vides

Vérifier :

1. Que les données ML ont été importées.
2. Que les tables contiennent des enregistrements.
3. Que le compte est associé au bon rôle.
4. Que le compte foyer est relié à un foyer existant.
5. Que les vues utilisent les modèles et les champs actuels de l'application `energy`.

### Erreur lors de l'import ML

Vérifier :

- Que les fichiers CSV existent.
- Que les noms de fichiers sont corrects.
- Que les colonnes attendues sont présentes.
- Que le chemin des données est correctement configuré.
- Que les données correspondent aux modèles Django.

Ne pas modifier les chemins de manière absolue dans le code. Le projet doit pouvoir être exécuté depuis différents ordinateurs.

### Erreur avec `python manage.py dbshell`

Cette commande nécessite le client PostgreSQL `psql` installé et accessible dans le PATH.

Si `psql` n'est pas installé, cela ne signifie pas nécessairement que Django ne peut pas communiquer avec PostgreSQL. Utiliser pgAdmin ou le shell Django pour vérifier les données.

---

## 18. Sécurité et préparation à la production

Avant de déployer l'application :

- Désactiver le mode debug : `DEBUG=False`.
- Utiliser une véritable `SECRET_KEY` conservée dans une variable d'environnement.
- Configurer correctement `ALLOWED_HOSTS`.
- Ne jamais publier les mots de passe PostgreSQL.
- Ne pas versionner `.env`.
- Protéger les pages selon les rôles.
- Désactiver l'inscription publique si seuls les administrateurs peuvent créer des comptes.
- Vérifier les permissions d'accès aux données des foyers.
- Mettre en place des sauvegardes de la base PostgreSQL.
- Utiliser HTTPS en production.
- Vérifier les fichiers statiques et médias lors du déploiement.

### Exemple de `.gitignore`

```gitignore
# Environnement Python
.venv/
venv/
__pycache__/
*.py[cod]

# Variables sensibles
.env

# Base locale
db.sqlite3

# IDE
.vscode/

# Fichiers système
.DS_Store
Thumbs.db

# Logs
*.log
```

Ne pas ajouter les fichiers CSV, modèles entraînés ou autres résultats ML au `.gitignore` sans vérifier s'ils doivent être distribués à l'équipe. Les données nécessaires à l'installation doivent être fournies par un moyen adapté.

---

## 19. Procédure complète pour une nouvelle installation

Voici l'ordre recommandé pour chaque membre de l'équipe qui récupère le projet pour la première fois.

### Étape 1 — Récupérer le code

```powershell
git clone URL_DU_DEPOT_GITHUB
cd energitn
```

### Étape 2 — Créer et activer l'environnement Python

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
```

### Étape 3 — Installer les dépendances

```powershell
cd energitn_django\backend
pip install -r requirements.txt
```

### Étape 4 — Créer la base PostgreSQL

Créer une base nommée :

```text
energitn_db
```

### Étape 5 — Configurer les identifiants PostgreSQL

Renseigner les paramètres attendus par `settings.py` ou le fichier `.env`.

### Étape 6 — Appliquer les migrations

```powershell
python manage.py migrate
```

### Étape 7 — Importer les données ML

Placer les fichiers nécessaires dans les dossiers attendus, puis exécuter :

```powershell
python manage.py import_ml_results
```

Cette étape est nécessaire pour disposer des données énergétiques importées dans la base.

### Étape 8 — Créer un administrateur

```powershell
python manage.py createsuperuser
```

### Étape 9 — Vérifier le projet

```powershell
python manage.py check
python manage.py test
```

### Étape 10 — Démarrer le serveur

```powershell
python manage.py runserver
```

Accéder à :

```text
http://127.0.0.1:8000/
```

---

## 20. Remarques importantes sur les données et les prévisions

- Les données synthétiques doivent être clairement identifiées comme telles.
- Les résultats importés correspondent aux fichiers générés par le pipeline ML.
- Les prévisions stockées dans la base ne sont pas nécessairement des prévisions futures calculées au moment de la consultation.
- Pour produire de nouvelles prévisions futures, il faut exécuter le pipeline d'inférence prévu dans le projet.
- Les valeurs de capacité régionale, les profils horaires ou les paramètres indicatifs doivent être documentés comme hypothèses lorsqu'ils ne proviennent pas de données réelles.
- Les indicateurs de qualité des prévisions nécessitent des valeurs réelles pour calculer les erreurs.

---

## 21. Conclusion

ÉnergiTN rassemble le traitement des données énergétiques, les modèles de Machine Learning et une application web Django permettant aux foyers, aux analystes et aux administrateurs d'exploiter les résultats.

Pour installer le projet sur un nouvel ordinateur, il faut retenir quatre étapes essentielles :

1. Récupérer le code depuis GitHub.
2. Installer les dépendances et configurer PostgreSQL.
3. Appliquer les migrations et importer les données ML.
4. Créer les comptes nécessaires et lancer le serveur Django.

**Commande de démarrage après configuration :**

```powershell
python manage.py runserver
```

Projet développé dans le cadre du projet ÉnergiTN.