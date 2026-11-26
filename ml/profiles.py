"""
ÉnergiTN - Étape 3 ML : profils de consommation des foyers (K-Means).
Lit  : data/synthetic/readings.csv, households.csv, data/processed/daily.csv
Écrit: data/processed/profiles.csv  (household_id, cluster, profil)

Features par foyer : conso moyenne/jour, part du soir (18h-23h), part de nuit (0h-5h),
rapport été/hiver, facteur de charge, sensibilité à la chaleur, rapport week-end/semaine.
Le nombre de groupes k est choisi par le score de silhouette entre 3 et 5 (ou imposé avec --k 4). Les noms sont proposés
automatiquement : RELISEZ-LES et corrigez-les à la main (interprétabilité).
"""
import argparse
from pathlib import Path
import numpy as np, pandas as pd
from sklearn.cluster import KMeans
from sklearn.metrics import silhouette_score, adjusted_rand_score
from sklearn.preprocessing import StandardScaler

ROOT = Path(__file__).resolve().parent.parent
SYN, PROC = ROOT / "data" / "synthetic", ROOT / "data" / "processed"
LABELS = {"mean_day": ("gros consommateur", "petit consommateur"), "evening_share": ("pic du soir marqué", "conso étalée dans la journée"),
          "night_share": ("conso nocturne élevée", "nuits calmes"), "summer_ratio": ("très estival", "peu saisonnier"),
          "heat_sens": ("très sensible à la chaleur", "peu sensible à la chaleur"), "weekend_ratio": ("plus présent le week-end", "régulier")}

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--k", type=int, default=0, help="nombre de profils (0 = choix automatique entre 3 et 5)")
    a = ap.parse_args()
    r = pd.read_csv(SYN / "readings.csv", parse_dates=["timestamp"], usecols=["household_id", "timestamp", "kwh", "is_outage", "is_anomaly"])
    r = r[(r.is_outage == 0) & (r.is_anomaly == 0)].dropna(subset=["kwh"])       # comportement habituel uniquement
    hh = pd.read_csv(SYN / "households.csv")
    d = pd.read_csv(PROC / "daily.csv", parse_dates=["date"])
    d = d[(d.anomaly_day == 0) & d.kwh_day.notna()]
    r["hour"], r["month"] = r.timestamp.dt.hour, r.timestamp.dt.month

    g = r.groupby("household_id")
    tot = g.kwh.sum()
    F = pd.DataFrame({
        "mean_day": d.groupby("household_id").kwh_day.mean(),
        "evening_share": r[r.hour.between(18, 23)].groupby("household_id").kwh.sum() / tot,
        "night_share": r[r.hour <= 5].groupby("household_id").kwh.sum() / tot,
        "summer_ratio": r[r.month.isin([7, 8])].groupby("household_id").kwh.mean() / r[r.month.isin([1, 2])].groupby("household_id").kwh.mean(),
        "load_factor": g.kwh.mean() / g.kwh.quantile(0.99),
        "heat_sens": d.groupby("household_id").apply(lambda x: np.polyfit(x.cdd, x.kwh_day, 1)[0], include_groups=False),
        "weekend_ratio": d[d.is_weekend == 1].groupby("household_id").kwh_day.mean() / d[(d.is_weekend == 0) & (d.is_holiday == 0)].groupby("household_id").kwh_day.mean(),
    }).dropna()
    X = StandardScaler().fit_transform(F)

    scores = {k: silhouette_score(X, KMeans(k, n_init=10, random_state=0).fit_predict(X)) for k in range(3, min(6, len(F)))}
    k = a.k or max(scores, key=scores.get)
    F["cluster"] = KMeans(k, n_init=10, random_state=0).fit_predict(X)
    print("Silhouette par k :", {a: round(b, 2) for a, b in scores.items()}, "-> k =", k, "(imposé)" if a.k else "(choisi)")

    z = (F.drop(columns="cluster") - F.drop(columns="cluster").mean()) / F.drop(columns="cluster").std()
    z["cluster"] = F.cluster
    names = {}
    for c, row in z.groupby("cluster").mean().iterrows():
        top = row.drop(labels=[x for x in row.index if x not in LABELS]).abs().sort_values(ascending=False).index[:2]
        names[c] = " + ".join(LABELS[f][0 if row[f] > 0 else 1] for f in top)
    F["profil"] = F.cluster.map(names)
    out = F.reset_index()[["household_id", "cluster", "profil"]].copy()
    # Colonnes lues par l'interface Django (barres du profil, en pourcentage, entre 0 et 100)
    out["evening_share"] = (100 * F.evening_share.values).round().astype(int)          # part de la consommation entre 18h et 23h
    out["night_share"] = (100 * F.night_share.values).round().astype(int)              # part de la consommation entre 0h et 5h
    out["summer_ratio"] = (100 * F.summer_ratio.values / (1 + F.summer_ratio.values)).round().astype(int)
    # summer_ratio (page) = poids de l'été : 100 x été / (été + hiver), conso moyenne juillet-août contre janvier-février
    # ---- ajouts pour Django (sans changer le regroupement) : les autres caractéristiques du profil
    out["summer_winter_ratio"] = F.summer_ratio.values.round(3)       # rapport été / hiver brut (« 2,5 × »)
    for c in ("mean_day", "load_factor", "heat_sens", "weekend_ratio"):
        out[c] = F[c].values.round(3)
    out.to_csv(PROC / "profiles.csv", index=False)

    # journée type (kWh moyen par heure) : page « Profil » du foyer et forme horaire régionale de l'analyste
    rows = []
    for season, months in (("all", range(1, 13)), ("summer", (6, 7, 8, 9)), ("winter", (12, 1, 2))):
        sh = r[r.month.isin(list(months))].groupby(["household_id", "hour"]).kwh.mean().unstack()
        sh.columns = [f"h{c:02d}" for c in sh.columns]
        rows.append(sh.round(4).assign(season=season).reset_index())
    pd.concat(rows)[["household_id", "season"] + [f"h{h:02d}" for h in range(24)]].to_csv(PROC / "hourly_profiles.csv", index=False)

    print("\nCentres des groupes (valeurs moyennes) :")
    print(F.groupby("cluster").mean(numeric_only=True).round(2).to_string())
    print("\nNoms proposés :", names)
    m = out.merge(hh[["household_id", "persona"]], on="household_id")
    print("\nCorrespondance avec les personas du simulateur (vérification) :")
    print(pd.crosstab(m.profil, m.persona).to_string())
    print("Adjusted Rand Index vs personas :", round(adjusted_rand_score(m.persona, m.cluster), 2), "(1 = identique)")
    # métriques lues par Django (page « Qualité des modèles »)
    import json
    from datetime import datetime
    (ROOT / "models").mkdir(exist_ok=True)
    with open(ROOT / "models" / "profiles_metrics.json", "w", encoding="utf-8") as fh:
        json.dump({"k": int(k), "k_auto": not a.k, "silhouette": {str(x): round(float(y), 3) for x, y in scores.items()},
                   "ari_vs_personas": round(float(adjusted_rand_score(m.persona, m.cluster)), 2),
                   "names": {str(c): n for c, n in names.items()}, "n_households": int(len(F)),
                   "trained_at": datetime.now().isoformat(timespec="seconds")}, fh, ensure_ascii=False, indent=1)
    print(f"-> {PROC / 'profiles.csv'}")

if __name__ == "__main__":
    main()