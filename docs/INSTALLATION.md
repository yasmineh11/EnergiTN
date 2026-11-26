# Installer, lancer et tester ÉnergiTN sur son PC (Windows)

Ce guide est pour un membre de l'équipe qui récupère le projet depuis GitHub. Il faut compter **30 à 45 minutes** la première fois, installations comprises.

---

## 1. Les outils à installer

| Outil | Obligatoire ? | Pourquoi |
|---|---|---|
| **Python 3.12, 3.13 ou 3.14** | Oui | fait tourner Django et les scripts ML |
| **PostgreSQL 16 ou 17** | Oui | la base de données de l'application |
| **Git** | Oui | récupérer le code et envoyer ses modifications |
| Compte **GitHub** | Oui | accéder au dépôt privé (après invitation) |
| Visual Studio Code | conseillé | éditer le code |
| Google Chrome, Edge ou Firefox | Oui | ouvrir le site |

Il n'y a rien d'autre à installer à la main : Django, pandas, scikit-learn, etc. sont installés automatiquement par `lancer.bat` dans un environnement isolé (`.venv`).

### 1.1 Python
1. Télécharger l'installateur sur https://www.python.org/downloads/.
2. **Cocher « Add python.exe to PATH »** sur le premier écran, puis cliquer sur *Install Now*.
3. Vérifier dans un **nouveau** terminal (touche Windows, taper `cmd`, Entrée) :
   ```bat
   python --version
   ```
   La commande doit afficher `Python 3.12.x` ou une version plus récente.

> Si `python` ouvre le Microsoft Store : *Paramètres › Applications › Paramètres avancés des applications › Alias d'exécution d'application*, puis désactiver les deux lignes « python.exe » et « python3.exe ».

### 1.2 PostgreSQL
1. Télécharger l'installateur Windows (EDB) sur https://www.postgresql.org/download/windows/, en version 17.
2. Pendant l'installation :
   - composants : laisser *PostgreSQL Server*, *pgAdmin 4* et *Command Line Tools* ; *Stack Builder* est inutile ;
   - **mot de passe du super-utilisateur `postgres`** : le choisir et **le noter**, `lancer.bat` le demandera ;
   - port : laisser **5432** ;
   - à la fin, décocher « Launch Stack Builder ».
3. PostgreSQL démarre tout seul avec Windows. Pour le vérifier : touche Windows, taper `services.msc`, puis chercher **postgresql-x64-17**. Son état doit être « En cours d'exécution ».

Il n'est **pas** nécessaire de créer la base à la main : le projet la crée lui-même.

### 1.3 Git
1. Télécharger l'installateur sur https://git-scm.com/download/win et garder toutes les options par défaut.
2. Configurer son identité, une seule fois :
   ```bat
   git config --global user.name "Prénom Nom"
   git config --global user.email "email-du-compte-github@exemple.com"
   ```

### 1.4 Accepter l'invitation GitHub
Le propriétaire du dépôt vous invite. Ouvrez l'email de GitHub, ou https://github.com/notifications, puis cliquez sur **Accept invitation**. Sans cette étape, le `git clone` d'un dépôt privé échoue.

---

## 2. Récupérer le code (git clone)

Choisissez un dossier de travail. Évitez OneDrive, qui synchronise des milliers de fichiers inutilement.
```bat
cd C:\
mkdir projets
cd projets
git clone https://github.com/<pseudo>/energitn.git
cd energitn
```
Au premier clone, une fenêtre GitHub s'ouvre : choisissez **Sign in with your browser**.

---

## 3. Premier lancement : `lancer.bat`

Dans le dossier `energitn`, double-cliquez sur **`lancer.bat`**, ou tapez `lancer.bat` dans le terminal.

| Étape affichée | Ce qui se passe | Durée |
|---|---|---|
| `[1/7] Environnement Python` | crée le dossier `.venv` | 10 s |
| `[2/7] Installation des bibliotheques` | installe Django, pandas, scikit-learn, psycopg… | 2 à 5 min |
| `[3/7] Fichier backend\.env` | **demande le mot de passe `postgres`** choisi au 1.2 et le range dans `backend\.env` | — |
| `[4/7] Base PostgreSQL` | crée la base `energitn` | 2 s |
| `[5/7] Donnees et modeles ML` | régénère les données synthétiques et entraîne les modèles (graine 42 : mêmes résultats que tout le monde), puis importe tout et crée les comptes de démo | 3 à 10 min |
| `[6/7] Tests automatiques` | lance les tests ; il faut voir **`Ran 19 tests … OK`** | 1 min |
| `[7/7] Demarrage du site` | ouvre http://127.0.0.1:8000/ | — |

Laissez la fenêtre noire ouverte : c'est le serveur. **Ctrl+C** l'arrête.

> Ne fermez pas la fenêtre pendant l'étape 5, même si elle semble figée : l'entraînement des modèles prend quelques minutes.

### Les fois suivantes
Double-cliquez simplement sur **`demarrer.bat`**.

---

## 4. Vérifier que tout est correct : `verifier.bat`

Double-cliquez sur **`verifier.bat`**. Il faut obtenir :
- `OK` sur toutes les lignes de fichiers (aucun `MANQUANT`) ;
- sous *Base de données utilisée* : **`postgresql - energitn`**. Si c'est `sqlite`, le fichier `backend\.env` est absent ou mal rempli ;
- `Ran 19 tests` puis **`OK`**.

---

## 5. Tester l'application à la main

### Se connecter
Ouvrez http://127.0.0.1:8000/, cliquez sur **Se connecter**, puis saisissez :

| Rôle | Adresse e-mail | Mot de passe |
|---|---|---|
| Foyer | `foyer@demo.tn` | `EnergiTN2026!` |
| Analyste | `analyste@demo.tn` | `EnergiTN2026!` |
| Admin | `admin@demo.tn` | `EnergiTN2026!` |

- Le mot de passe respecte les majuscules (**E**, **TN**) et se termine par **!**.
- Plus rapide : dans l'encadré *Comptes de démonstration*, sous le formulaire, un clic sur **Foyer**, **Analyste** ou **Administrateur** connecte directement.
- Pour changer de rôle : **Déconnexion** en bas de la barre latérale, puis connexion avec un autre compte. Une fenêtre de navigation privée permet aussi d'avoir deux rôles ouverts en même temps.

### 5.1 Espace foyer (`foyer@demo.tn`)
| Page | À vérifier |
|---|---|
| Tableau de bord | 4 cartes en haut (dernier relevé, prévision J+1, facture, comparaison) et la prévision des 7 jours avec les traits d'intervalle. Bouger le curseur « Et si une canicule arrivait ? » : les kWh et la facture augmentent |
| Mes relevés | ajouter un relevé à la main, par exemple 30 kWh : une alerte de surconsommation doit apparaître |
| Ma facture | barème par tranches, simulateur d'économies |
| Profil et alertes | profil K-Means, courbe horaire, liste des alertes |
| Assistant énergie | poser « Pourquoi ma facture augmente ? » : la réponse cite les chiffres du foyer |
| Rapport mensuel | rapport imprimable (Ctrl+P) |
| Langue | bouton « العربية » : toute l'interface passe en arabe, de droite à gauche |

**Tester avec un nouveau foyer :**
1. Se déconnecter, puis cliquer sur **Créer un compte** et choisir **« Suivre mon propre foyer »**.
2. Dans *Mes relevés*, importer (bouton *Importer*) **`docs/exemples/releves_test_1_an.csv`**. Il contient une année avec 3 journées anormales.
3. Revenir au tableau de bord : les prévisions sont calculées pour ce foyer, et les alertes des journées anormales apparaissent.

`docs/exemples/releves_test_30_jours.csv` permet un test plus court : il faut au moins 14 jours de relevés pour obtenir une prévision.

### 5.2 Espace analyste (`analyste@demo.tn`)
| Page | À vérifier |
|---|---|
| Demande régionale | choisir J+1…J+7, bouger *Scénario de chaleur* et *Heure* : les barres et la carte changent |
| Profils de consommation | répartition des profils par région |
| Anomalies et coupures | anomalies récurrentes, foyers à surveiller |

### 5.3 Espace administrateur (`admin@demo.tn`)
| Page | À vérifier |
|---|---|
| Utilisateurs et rôles | créer un compte **analyste** ou **administrateur**, puis s'y connecter |
| Données et chaîne ML | relancer la chaîne : le journal défile en direct, puis l'import et l'inférence s'exécutent |
| Qualité des modèles | MAPE 9,88 %, santé de la liaison **4/4 contrôles OK**, courbe de dérive, bouton de prévision à la demande |
| Barème et référentiel | modifier un prix de tranche : la facture du foyer change |

---

## 6. Travailler au quotidien avec Git

```bat
cd C:\projets\energitn
git pull
```
Après un `git pull`, faites selon ce qui a changé :

| Si les autres ont modifié… | Commande (dans `backend`, avec `.venv` activé*) |
|---|---|
| `backend/requirements.txt` | `pip install -r requirements.txt` |
| `backend/api/models.py` ou un dossier `migrations/` | `python manage.py migrate` |
| un script de `ml/` | `python manage.py preparer_ml --force` puis `python manage.py import_results` puis `python manage.py run_inference` |
| le reste (pages, CSS, vues) | rien : relancer `demarrer.bat` |

\* Pour activer `.venv` dans un terminal `cmd` :
```bat
cd C:\projets\energitn
.venv\Scripts\activate
cd backend
```

Pour envoyer son travail, toujours sur une branche :
```bat
git checkout -b feature/ma-modification
git add .
git commit -m "Ajoute …"
git push -u origin feature/ma-modification
```
Ouvrez ensuite une **Pull Request** sur GitHub, que le reste de l'équipe relit avant de fusionner dans `main`.

> Ne jamais envoyer `backend\.env` : il contient votre mot de passe. Le `.gitignore` l'exclut déjà, ne forcez pas son ajout.

---

## 7. Problèmes fréquents

| Message | Cause | Solution |
|---|---|---|
| `'python' n'est pas reconnu…` | Python n'est pas dans le PATH | réinstaller Python en cochant *Add to PATH*, puis rouvrir le terminal |
| `password authentication failed for user "postgres"` | mauvais mot de passe dans `.env` | ouvrir `backend\.env` avec le Bloc-notes et corriger `DB_PASSWORD=` |
| `connection refused` / `could not connect to server` | PostgreSQL arrêté | `services.msc`, puis *postgresql-x64-17* › Démarrer |
| `database "energitn" does not exist` | base non créée | `python manage.py creer_base` (dans `backend`, `.venv` activé) |
| `verifier.bat` affiche `sqlite` | `backend\.env` absent | relancer `lancer.bat` : il le recrée en demandant le mot de passe |
| `No module named 'django'` | `.venv` non activé | utiliser `demarrer.bat`, ou `.venv\Scripts\activate` avant les commandes |
| `…activate.ps1 cannot be loaded` (PowerShell) | politique d'exécution | utiliser `cmd` au lieu de PowerShell, ou `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned` |
| `Error: That port is already in use` | un autre serveur tourne déjà | fermer l'autre fenêtre, ou `python manage.py runserver 8001` |
| `Échec de l'étape « … »` pendant `preparer_ml` | erreur d'un script ML | lire le message affiché, puis relancer `python manage.py preparer_ml --force` |
| Message « Votre session a changé… » | connexion dans un autre onglet (jeton CSRF périmé) | recommencer l'action : c'est sans conséquence |
| `Repository not found` au `git clone` | invitation non acceptée | accepter l'invitation GitHub (1.4) |
| `pip install` échoue sur pandas ou numpy | Python trop ancien | installer Python 3.12 ou plus récent, supprimer le dossier `.venv`, relancer `lancer.bat` |
