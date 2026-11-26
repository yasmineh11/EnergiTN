"""Crée la base PostgreSQL indiquée dans backend/.env si elle n'existe pas encore.

    python manage.py creer_base

Se connecte à la base système « postgres » avec DB_USER / DB_PASSWORD, puis
CREATE DATABASE <DB_NAME> ENCODING 'UTF8'. Sans effet si la base existe déjà
ou si le projet utilise SQLite (pas de DB_NAME).
"""
import os

from django.core.management.base import BaseCommand, CommandError


class Command(BaseCommand):
    help = "Crée la base PostgreSQL de backend/.env si elle n'existe pas."

    def handle(self, *args, **opts):
        name = os.getenv("DB_NAME")
        if not name:
            self.stdout.write("Pas de DB_NAME : le projet utilise SQLite, rien à créer.")
            return
        try:
            import psycopg
            from psycopg import sql
        except ImportError as e:
            raise CommandError("psycopg manquant : pip install -r requirements.txt") from e
        params = dict(dbname="postgres", user=os.getenv("DB_USER", "postgres"), password=os.getenv("DB_PASSWORD", ""),
                      host=os.getenv("DB_HOST", "localhost"), port=os.getenv("DB_PORT", "5432"))
        try:
            with psycopg.connect(**params, autocommit=True, connect_timeout=8) as c:
                if c.execute("SELECT 1 FROM pg_database WHERE datname = %s", [name]).fetchone():
                    self.stdout.write(self.style.SUCCESS(f"✓ La base « {name} » existe déjà"))
                    return
                c.execute(sql.SQL("CREATE DATABASE {} ENCODING 'UTF8' TEMPLATE template0").format(sql.Identifier(name)))
                self.stdout.write(self.style.SUCCESS(f"✓ Base « {name} » créée"))
        except psycopg.OperationalError as e:
            msg = str(e)
            if "password authentication failed" in msg:
                hint = "mot de passe refusé : vérifiez DB_USER / DB_PASSWORD dans backend\\.env"
            elif "Connection refused" in msg or "could not connect" in msg or "timeout" in msg.lower():
                hint = "PostgreSQL ne répond pas : démarrez le service (services.msc > postgresql-x64-…)"
            else:
                hint = msg.strip().splitlines()[0]
            raise CommandError(f"Connexion à PostgreSQL impossible — {hint}") from None
