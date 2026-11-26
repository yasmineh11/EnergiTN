import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent          # backend/
PROJECT_DIR = BASE_DIR.parent                               # energitn/ (contient ml/, data/, models/)


def _load_env(path):
    """Lit backend/.env (lignes CLE=valeur) sans dépendance externe.
    Les variables déjà définies dans le terminal restent prioritaires."""
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


_load_env(BASE_DIR / ".env")

SECRET_KEY = os.getenv("SECRET_KEY", "dev-only-change-me")
DEBUG = os.getenv("DEBUG", "1") == "1"
ALLOWED_HOSTS = os.getenv("ALLOWED_HOSTS", "127.0.0.1,localhost,testserver").split(",")

INSTALLED_APPS = [
    "django.contrib.admin", "django.contrib.auth", "django.contrib.contenttypes",
    "django.contrib.sessions", "django.contrib.messages", "django.contrib.staticfiles",
    "django.contrib.humanize",
    "rest_framework", "api", "web",
]
MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]
ROOT_URLCONF = "config.urls"
TEMPLATES = [{
    "BACKEND": "django.template.backends.django.DjangoTemplates",
    "DIRS": [], "APP_DIRS": True,
    "OPTIONS": {"context_processors": [
        "django.template.context_processors.request",
        "django.contrib.auth.context_processors.auth",
        "django.contrib.messages.context_processors.messages",
        "web.context.shell",
    ]},
}]
WSGI_APPLICATION = "config.wsgi.application"

# SQLite par défaut ; PostgreSQL si DB_NAME est défini (mots de passe via variables d'environnement)
if os.getenv("DB_NAME"):
    DATABASES = {"default": {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": os.getenv("DB_NAME"), "USER": os.getenv("DB_USER", "postgres"),
        "PASSWORD": os.getenv("DB_PASSWORD", ""), "HOST": os.getenv("DB_HOST", "localhost"),
        "PORT": os.getenv("DB_PORT", "5432"),
        "CONN_MAX_AGE": 60,
        "OPTIONS": {"client_encoding": "UTF8"},
        "TEST": {"NAME": os.getenv("DB_TEST_NAME", f"test_{os.getenv('DB_NAME')}")},
    }}
else:
    DATABASES = {"default": {"ENGINE": "django.db.backends.sqlite3", "NAME": BASE_DIR / "db.sqlite3",
                             "OPTIONS": {"timeout": 20}}}

# NF07 : mots de passe robustes (hachage PBKDF2 par défaut de Django)
AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator", "OPTIONS": {"min_length": 8}},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

LANGUAGE_CODE = "fr"
TIME_ZONE = "Africa/Tunis"
USE_I18N = True
USE_TZ = True
STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"
LOGIN_URL = "/login/"

SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_AGE = 60 * 60 * 8
X_FRAME_OPTIONS = "DENY"
if not DEBUG:   # production : HTTPS obligatoire
    SECURE_SSL_REDIRECT = True
    SESSION_COOKIE_SECURE = CSRF_COOKIE_SECURE = True
    SECURE_HSTS_SECONDS = 31536000
    SECURE_CONTENT_TYPE_NOSNIFF = True

REST_FRAMEWORK = {
    "DEFAULT_PERMISSION_CLASSES": ["rest_framework.permissions.IsAuthenticated"],
    "DEFAULT_PAGINATION_CLASS": "rest_framework.pagination.LimitOffsetPagination",
    "PAGE_SIZE": 200,
}

# ---- Liaison avec la chaîne ML (dossier energitn/ du guide) ----
ML_DATA_DIR = Path(os.getenv("ML_DATA_DIR", PROJECT_DIR / "data"))        # synthetic/ et processed/
ML_MODELS_DIR = Path(os.getenv("ML_MODELS_DIR", PROJECT_DIR / "models"))  # *.joblib et *_metrics.json
ML_SCRIPTS_DIR = Path(os.getenv("ML_SCRIPTS_DIR", PROJECT_DIR / "ml"))    # scripts du guide

# ---- Assistant IA générative (optionnel) ----
# Sans clé, l'assistant répond avec un moteur de règles ancré sur les mêmes faits (aucune donnée envoyée).
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
LLM_MODEL = os.getenv("LLM_MODEL", "claude-haiku-5-5")
LLM_TIMEOUT = float(os.getenv("LLM_TIMEOUT", "9"))

LOGGING = {"version": 1, "disable_existing_loggers": False,
           "handlers": {"console": {"class": "logging.StreamHandler"}},
           "loggers": {"energitn": {"handlers": ["console"], "level": "INFO"}}}

# Jeton CSRF périmé (autre onglet, retour arrière) : page claire au lieu de l'erreur 403 technique
CSRF_FAILURE_VIEW = "web.views.csrf_failure"
