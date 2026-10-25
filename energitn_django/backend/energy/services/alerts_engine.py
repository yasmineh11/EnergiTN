"""
Règles d'alertes de REPLI côté Django (mêmes seuils que le service .NET). Utilisées si .NET est indisponible,
ou en attendant que le moteur .NET soit prêt. Les seuils sont à calibrer avec les résultats de anomalies.py.
"""


def evaluate(actual, forecast, night_ratio=None):
    ratio = actual / max(forecast, 0.5)
    if ratio > 2.0:
        return {"kind": "overconsumption", "severity": "high", "ratio": round(ratio, 2),
                "message": f"Consommation {ratio:.1f} fois supérieure à la prévision."}
    if ratio > 1.5:
        return {"kind": "overconsumption", "severity": "medium", "ratio": round(ratio, 2),
                "message": f"Consommation {ratio:.1f} fois supérieure à la prévision."}
    if night_ratio is not None and night_ratio > 1.8:
        return {"kind": "night_load", "severity": "medium", "ratio": round(night_ratio, 2),
                "message": f"Consommation de nuit {night_ratio:.1f} fois supérieure à vos habitudes."}
    return None
