"""Les 6 régions du projet (mêmes que fetch_weather.py / generate_synthetic.py).
ml  = nom exact utilisé par la chaîne ML (households.csv, weather.csv, colonnes region_* du modèle)
cap = capacité FICTIVE en MW (hypothèse de scénario pour la vue analyste, à remplacer par des données réelles)
x/y = position sur la carte schématique (viewBox 300 x 380)."""
import unicodedata

REGIONS = [
    {"id": "biz", "fr": "Bizerte", "ar": "بنزرت", "ml": "Bizerte", "cap": 600,  "x": 150, "y": 30},
    {"id": "tun", "fr": "Tunis",   "ar": "تونس",  "ml": "Tunis",   "cap": 1800, "x": 182, "y": 62},
    {"id": "sou", "fr": "Sousse",  "ar": "سوسة",  "ml": "Sousse",  "cap": 900,  "x": 205, "y": 135},
    {"id": "sfx", "fr": "Sfax",    "ar": "صفاقس", "ml": "Sfax",    "cap": 1100, "x": 200, "y": 210},
    {"id": "gab", "fr": "Gabès",   "ar": "قابس",  "ml": "Gabes",   "cap": 700,  "x": 180, "y": 270},
    {"id": "toz", "fr": "Tozeur",  "ar": "توزر",  "ml": "Tozeur",  "cap": 250,  "x": 85,  "y": 255},
]
BY_ID = {r["id"]: r for r in REGIONS}


def norm(s):
    return "".join(c for c in unicodedata.normalize("NFD", str(s).strip().lower())
                   if unicodedata.category(c) != "Mn")


_BY_NORM = {}
for _r in REGIONS:
    _BY_NORM[norm(_r["fr"])] = _r
    _BY_NORM[norm(_r["ml"])] = _r
    _BY_NORM[_r["id"]] = _r


def region_of(name):
    """Retrouve une région à partir de n'importe quelle écriture (Gabès, Gabes, gab…)."""
    return _BY_NORM.get(norm(name)) if name else None
