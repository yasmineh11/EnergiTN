from pathlib import Path


def project_root():
    # racine du projet EnergyTN
    return Path(__file__).resolve().parents[3]


def ml_root():
    # dossier contenant les scripts ML
    return project_root() / "ml"


def data_root():
    # dossier contenant les données générées
    return project_root() / "data"
