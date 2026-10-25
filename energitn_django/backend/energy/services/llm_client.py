"""
Assistant IA générative : explique les faits calculés par le système, en français ou en arabe.
La clé API est lue dans la variable d'environnement ANTHROPIC_API_KEY (jamais dans le code ni sur GitHub).
Installation : pip install anthropic
"""
import json

from django.conf import settings

SYSTEM = """Tu es l'assistant d'ÉnergiTN, une plateforme qui aide les foyers tunisiens à comprendre leur consommation d'électricité.
Règles strictes :
- Réponds dans la langue de la question (français ou arabe), avec des phrases courtes et simples.
- Utilise UNIQUEMENT les chiffres du JSON fourni. N'invente aucun chiffre, aucune date, aucun tarif. Si l'information n'y est pas, dis-le.
- Tu es une aide, pas un avis professionnel. Ne conseille jamais d'intervenir sur l'installation électrique ;
  en cas de doute sur un appareil ou l'installation, recommande de contacter un professionnel qualifié.
- Donne des conseils concrets d'économie d'énergie adaptés au profil et à la région du foyer.
- Les données du foyer sont confidentielles ; n'en parle à personne d'autre."""


def answer(question, facts, max_tokens=700):
    import anthropic                                   # importé ici : l'app Django démarre même sans le paquet
    client = anthropic.Anthropic()                      # lit ANTHROPIC_API_KEY
    msg = client.messages.create(
        model=settings.LLM_MODEL, max_tokens=max_tokens, system=SYSTEM,
        messages=[{"role": "user", "content":
                   f"Données du foyer (JSON) :\n{json.dumps(facts, ensure_ascii=False, default=str)}\n\nQuestion : {question}"}])
    return "".join(b.text for b in msg.content if b.type == "text")
