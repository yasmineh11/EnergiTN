# Corrections apportées au projet

## Chaîne ML (dossier `ml/`)
| Problème | Correction |
|---|---|
| **Règle n°1 du guide violée** : `train_forecast.py` entraînait sur `anomaly_day == 0` (vérité terrain) | `prepare.py` calcule `robust_outlier` sans supervision (écart à la médiane glissante / MAD, après retrait de l'effet chaleur) ; l'entraînement l'utilise. `anomaly_day` ne sert plus qu'à noter. |
| `anomalies.py` calibrait sigma et entraînait l'Isolation Forest sur les jours `anomaly_day == 0` | sigma robuste (MAD) sur toute la validation ; Isolation Forest sur toute la validation. |
| `profiles.py` filtrait `is_anomaly == 0` | jours atypiques écartés via `robust_outlier`. |
| Intervalle q10–q90 sous-couvrant en été (68 %) | marge de calibration **relative** (proportionnelle à la prévision) : 73 % sur le test. |
| `profiles.csv` sans caractéristiques, aucune journée type | `profiles.csv` contient les 7 caractéristiques ; nouveau `hourly_profiles.csv` ; `profiles_metrics.json`. |
| `profiles.csv` et `anomalies_flagged.csv` absents du dossier livré | chaîne relancée en entier. |
| Pas de MAPE (demandé par NF05), métriques incomplètes | MAPE ajoutée, gain vs baseline, dates, effectifs, version scikit-learn. |
| `.joblib` de 91 Mo | compression : 32 Mo. |

Conséquence honnête : le MAPE J+1 passe de ≈ 3,9 % (avec fuite de la vérité terrain) à **4,29 %** (sans fuite), contre **27,5 %** pour la baseline.

## Django
| Problème | Correction |
|---|---|
| Aucun `.joblib` chargé : les « prévisions » étaient des CSV d'évaluation rejoués | `api/ml.py` : inférence réelle (J+1 par `forecast_h1`, J+2→J+7 par `forecast_h7`), parité vérifiée avec l'entraînement (écart moyen 0,002 kWh). |
| `import_results` ne trouvait pas la colonne réelle `kwh_day` → page Qualité vide | import réécrit sur les colonnes exactes du guide. |
| Table `ModelRun` absente (demandée par le guide) | ajoutée, alimentée par les `*_metrics.json`. |
| Gravités incohérentes (`haute`/`moyenne` vs `medium`) | normalisées. |
| Saisie/import des relevés absents (BF02, UC01) | page « Mes relevés » + API `POST /api/foyer/readings/` ; détection d'anomalie à la saisie (UC06) puis recalcul des prévisions. |
| Assistant par mots-clés, réponses figées | JSON de faits + base de conseils validée ; IA générative si `ANTHROPIC_API_KEY`, sinon moteur de règles bilingue chiffré ; historique conservé (UC07). |
| Textes figés dans l'interface (« Foyer 07 · Sfax », « 46 % », « Rapport de septembre », confiance « 90 % ») | tout est calculé à partir des données. |
| Bug vue « Jour » (`[18,19,20,21].filter(i=>0)`) et forme horaire inventée | journée type réelle issue des relevés horaires. |
| Charge régionale fondée sur une forme horaire et une sensibilité fictives | formes horaires et sensibilité à la chaleur apprises par `profiles.py`. |
| Mot de passe 6 caractères, déconnexion en GET | validateurs Django (8 caractères, mots courants refusés), déconnexion en POST, cookies sécurisés en production. |
| Inscription : foyer simulé attribué au hasard | choix entre foyer simulé (région choisie) et vrai foyer (région, type, climatisation). |
| Barème « indicatif » codé en dur | barème STEG 2022 par défaut, modifiable par l'admin. |

## Version 3 (novembre 2026) — fautes corrigées
| Problème | Correction |
|---|---|
| Cartes de droite décalées de 18 px (« À surveiller », « Carte de charge », « Baseline »…) : la règle CSS `.panel + .panel` s'appliquait aussi dans les grilles | règle neutralisée dans les grilles |
| « Facture estimée **de octobre** », « de avril », « de août » | élision automatique en français (« d'octobre ») |
| « **Demain** 1 oct. » alors que nous sommes le 11 novembre (données arrêtées au 30 septembre) | « Demain » seulement si c'est vraiment demain, sinon **J+1 … J+7** (ruban, carte « Prévision J+1 », analyste) |
| Assistant : « Alertes en cours : 5 » alors que le menu affiche 10 (liste tronquée à 5 utilisée comme compteur) | compteur réel `alerts_open` |
| Dates d'entraînement incohérentes (25 oct. dans « Modèles actifs », 26 oct. dans le tableau) : date UTC tronquée | conversion en heure locale Africa/Tunis |
| `date.today()` (heure du serveur) pour refuser les relevés futurs | `timezone.localdate()` (fuseau du projet) |
| « 1 foyers liés sur 30 » ; en arabe « الأسرةs » (pluriel construit avec + « s ») | pluriel géré dans les deux langues |
| Carte de chaleur heure × région presque monochrome (échelle 0→max) | échelle min→max : heures creuses et pic lisibles |
| Légende « Bande claire » alors que l'intervalle n'était presque pas visible | intervalle q10–q90 dessiné en moustache ; légende mise à jour |
| Mobile : fond de la barre latérale visible derrière le contenu ; valeurs kWh du ruban superposées | corrigé |

## Version 4 (25 novembre 2026) — intégration de la chaîne ML v2 de l'équipe (GitHub `yasmineh11/EnergiTN`)
**Repris tel quel** : `generate_synthetic.py`, `prepare.py` (heure de reprise après coupure exclue, journée estimée par profil horaire),
`train_forecast.py` (modèle hybride droite par foyer + arbres, `--weather-error 2`), `profiles.py`, `anomalies.py`, `inference.py`.
La chaîne relancée reproduit exactement les fichiers de l'équipe (`daily.csv`, `profiles.csv`, métriques J+1 et J+7 identiques).

**Ajouté sans changer les modèles** (sorties dont Django a besoin) :
| Script | Ajout |
|---|---|
| `train_forecast.py` | `MAPE_%`, version scikit-learn, date d'entraînement, gain vs baseline dans `*_metrics.json` ; `.joblib` compressé |
| `profiles.py` | colonnes `mean_day`, `load_factor`, `heat_sens`, `weekend_ratio`, `summer_winter_ratio` ; `hourly_profiles.csv` ; `profiles_metrics.json` |

**Django adapté** : `api/ml.py` (variable `lin_base` + prédiction hybride identique à `ml/inference.py`), jumeau numérique (la droite suit la chaleur),
import des nouveaux formats (`anomaly_metrics.json`, `summer_ratio` en %), chaîne lancée depuis l'admin avec `--weather-error 2`,
test de parité Django = `inference.py`. **PostgreSQL** : lecture de `backend/.env`, `psycopg[binary]` dans `requirements.txt`.

**Points à discuter avec l'équipe** :
1. **`anomaly_day` (vérité terrain) sert à choisir les jours d'entraînement** dans `train_forecast.py`, `profiles.py` et `anomalies.py`.
   Le guide la réserve à l'évaluation (« ne faites pas apprendre au modèle la colonne is_anomaly »). La v3 l'avait corrigé avec
   `robust_outlier` (voir plus haut) ; la v2 de l'équipe revient à l'ancienne méthode. Effet : scores un peu optimistes.
2. **Les fichiers d'anomalies du dépôt GitHub ne correspondent pas aux prévisions du dépôt** (écarts de prévision jusqu'à 4,6 kWh) :
   ils viennent d'une exécution antérieure. Après relance dans l'ordre : F1 0,67 (et non 0,74 comme dans `anomaly_metrics.json` du dépôt).
3. Les `.joblib` et `readings.csv` ne sont pas sur GitHub (`.gitignore`) : chaque membre doit relancer la chaîne, ou les partager par Drive.
