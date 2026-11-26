# Registre des jeux de données (NF11)

| Fichier | Origine | Licence | Nature | Produit par |
|---|---|---|---|---|
| `data/raw/weather.csv` | Open-Meteo, API Archive (6 villes : Tunis, Sfax, Sousse, Gabès, Tozeur, Bizerte) | CC BY 4.0 (Open-Meteo) | **Observée** | `fetch_weather.py` |
| `data/synthetic/households.csv` | Simulateur ÉnergiTN | Projet | **Synthétique** | `generate_synthetic.py --seed 42` |
| `data/synthetic/readings.csv` | Simulateur (relevés horaires, anomalies injectées, coupures, trous) | Projet | **Synthétique** | `generate_synthetic.py --seed 42` |
| `data/synthetic/holidays_used.csv` | Jours fériés tunisiens : fixes + religieux saisis à la main | Domaine public | Référence — **dates religieuses 2024 et 2025 à vérifier** | `generate_synthetic.py` |
| `data/synthetic/outages_used.csv` | Coupures simulées (probabilité croissante au-delà de 33 °C) | Projet | **Synthétique — hypothèse non calibrée** | `generate_synthetic.py` |
| `data/processed/daily.csv` | Nettoyage des relevés | Projet | Synthétique | `prepare.py` |
| `data/processed/forecast_h{1,7}_predictions.csv` | Prévu contre réel (validation + test) | Projet | Synthétique | `train_forecast.py` |
| `data/processed/profiles.csv`, `hourly_profiles.csv` | K-Means + journées types | Projet | Synthétique | `profiles.py` |
| `data/processed/anomalies_flagged.csv` | Jours signalés | Projet | Synthétique | `anomalies.py` |
| Barème d'électricité (table `TariffBand`) | Grille STEG du 1er mai 2022, relayée par webdo.tn (13/05/2022) | — | Référence — **à vérifier auprès de la STEG** | saisie admin |
| Relevés saisis/importés par les foyers | Utilisateurs de la plateforme | Données personnelles | Réelle (si utilisée par un vrai foyer) | espace foyer |

Les capacités régionales en MW (`api/regions.py`) sont **fictives** : la vue analyste exprime la charge en % du record historique.
Les scores (≈ 4 % d'erreur) viennent de la simplicité du simulateur et ne prouvent rien sur de vrais foyers : le résultat qui compte est l'écart avec la baseline.
