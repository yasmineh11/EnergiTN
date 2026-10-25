"""Les 6 régions du projet (mêmes que fetch_weather.py). cap = capacité fictive en MW,
s = sensibilité à la chaleur (hypothèse du scénario), x/y = position sur la carte schématique."""
import unicodedata

REGIONS = [
    {"id": "tun", "fr": "Tunis",   "ar": "تونس",  "cap": 1800, "s": .35, "x": 172, "y": 78},
    {"id": "biz", "fr": "Bizerte", "ar": "بنزرت", "cap": 600,  "s": .30, "x": 140, "y": 34},
    {"id": "sou", "fr": "Sousse",  "ar": "سوسة",  "cap": 900,  "s": .45, "x": 200, "y": 150},
    {"id": "sfx", "fr": "Sfax",    "ar": "صفاقس", "cap": 1100, "s": .50, "x": 196, "y": 225},
    {"id": "gab", "fr": "Gabès",   "ar": "قابس",  "cap": 700,  "s": .60, "x": 172, "y": 305},
    {"id": "toz", "fr": "Tozeur",  "ar": "توزر",  "cap": 250,  "s": .80, "x": 78,  "y": 285},
]

def norm(s):
    return "".join(c for c in unicodedata.normalize("NFD", str(s).strip().lower())
                   if unicodedata.category(c) != "Mn")

_BY_NORM = {norm(r["fr"]): r for r in REGIONS}

def region_of(name):
    return _BY_NORM.get(norm(name))
