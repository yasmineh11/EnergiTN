"""Estimation de la facture (BF04).
Barème par défaut : grille STEG entrée en vigueur le 1er mai 2022 (tranches de consommation ANNUELLE,
prix de la tranche appliqué à toute la consommation), d'après webdo.tn (13/05/2022).
À VÉRIFIER auprès de la STEG : l'administrateur peut modifier le barème (table TariffBand).
Montants hors TVA, redevances et contributions."""
from decimal import Decimal

DEFAULT_BANDS = [
    ("≤ 2 400 kWh/an", 2400, Decimal("0.181")),
    ("2 401 – 3 600 kWh/an", 3600, Decimal("0.223")),
    ("3 601 – 6 000 kWh/an", 6000, Decimal("0.338")),
    ("> 6 000 kWh/an", None, Decimal("0.419")),
]
SOURCE = "Barème STEG du 1er mai 2022 (webdo.tn) · hors taxes et redevances · à vérifier"


def bands():
    from .models import TariffBand
    rows = list(TariffBand.objects.order_by("order"))
    if rows:
        return [(b.label, b.max_kwh_year, b.price_dt) for b in rows]
    return DEFAULT_BANDS


def ensure_default_bands():
    from .models import TariffBand
    if not TariffBand.objects.exists():
        TariffBand.objects.bulk_create([TariffBand(label=l, max_kwh_year=m, price_dt=p, order=i)
                                        for i, (l, m, p) in enumerate(DEFAULT_BANDS)])


def estimate(kwh, days=30):
    """Montant estimé pour `kwh` consommés sur `days` jours."""
    bs = bands()
    annual = kwh * 365 / max(days, 1)
    idx = next((i for i, (_, mx, _) in enumerate(bs) if mx is None or annual <= mx), len(bs) - 1)
    label, mx, price = bs[idx]
    total = float(price) * kwh
    out = {"kwh": round(kwh, 1), "days": days, "annual": round(annual), "band": idx, "band_label": label,
           "price": float(price), "total": round(total, 2), "source": SOURCE,
           "bands": [{"label": l, "max": m, "price": float(p)} for l, m, p in bs]}
    # seuil de tranche : combien de kWh avant de basculer (le nouveau prix s'appliquerait à TOUT)
    if mx is not None and idx + 1 < len(bs):
        room = mx * days / 365 - kwh
        nxt = float(bs[idx + 1][2])
        out["next_band"] = {"room_kwh": round(max(room, 0), 1), "price": nxt,
                            "jump_dt": round((kwh + max(room, 0)) * (nxt - float(price)), 2)}
    if idx > 0:
        prev_max = bs[idx - 1][1]
        need = kwh - prev_max * days / 365
        out["prev_band"] = {"save_kwh": round(need, 1), "price": float(bs[idx - 1][2]),
                            "saving_dt": round(total - float(bs[idx - 1][2]) * (kwh - need), 2)}
    return out
