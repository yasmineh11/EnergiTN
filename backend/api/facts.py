"""JSON de faits du foyer (rôle C du guide) + base de conseils validée + assistant IA + rapport mensuel.

L'assistant (UC07/UC13) répond UNIQUEMENT à partir de ce JSON de faits et de la base de conseils :
  * si ANTHROPIC_API_KEY est défini : IA générative (réponse rédigée, en français ou en arabe) ;
  * sinon : moteur de règles bilingue qui produit une réponse chiffrée à partir des mêmes faits.
Garde-fous : aide non professionnelle, jamais d'intervention sur l'installation électrique, refus hors périmètre.
"""
import calendar
import json
import logging
import re
import urllib.request
from datetime import date, timedelta

from django.conf import settings
from django.db.models import Avg, Sum

from . import billing
from .models import PERSONAS, Alert, DailyConsumption, Forecast, HouseholdProfile, ModelRun

log = logging.getLogger("energitn")

# --------------------------------------------------------------------------- base de conseils validée
TIPS = {
    "clim26": {"fr": "Réglez la climatisation sur 26 °C et fermez portes et volets aux heures chaudes.",
               "ar": "اضبط المكيّف على 26 °م وأغلق الأبواب والنوافذ في ساعات الحرّ."},
    "shift": {"fr": "Faites tourner lave-linge, fer à repasser et four avant 18 h, hors de la pointe du soir.",
              "ar": "شغّل الغسالة والمكواة والفرن قبل الساعة 18:00، خارج ذروة المساء."},
    "standby": {"fr": "Coupez les appareils en veille la nuit (multiprise à interrupteur) : TV, box, chargeurs.",
                "ar": "افصل الأجهزة في وضع الاستعداد ليلًا (مشترك بمفتاح): التلفاز، الموزّع، الشواحن."},
    "fridge": {"fr": "Réglez le réfrigérateur à 4–5 °C et vérifiez l'étanchéité du joint de porte.",
               "ar": "اضبط الثلاجة على 4–5 °م وتحقق من إحكام مطاط الباب."},
    "heater": {"fr": "Programmez le chauffe-eau électrique en heures creuses et baissez sa consigne à 55 °C.",
               "ar": "برمج سخّان الماء الكهربائي في ساعات خارج الذروة واخفض حرارته إلى 55 °م."},
    "led": {"fr": "Remplacez les dernières ampoules classiques par des LED (jusqu'à 80 % d'économie sur l'éclairage).",
            "ar": "استبدل المصابيح التقليدية المتبقية بمصابيح LED (توفير يصل إلى 80 % في الإنارة)."},
    "fan": {"fr": "Les jours modérés, préférez le ventilateur : il consomme bien moins qu'un climatiseur.",
            "ar": "في الأيام المعتدلة، استعمل المروحة: تستهلك أقل بكثير من المكيّف."},
    "check": {"fr": "Le jour de l'alerte, repérez un appareil resté allumé ; en cas de doute, faites appel à un électricien.",
              "ar": "في يوم التنبيه، ابحث عن جهاز بقي مشغّلًا؛ وعند الشك استعن بكهربائي."},
}
DISCLAIMER = {"fr": "Aide indicative, pas un avis professionnel. N'intervenez pas sur l'installation électrique : contactez un électricien.",
              "ar": "مساعدة إرشادية وليست رأيًا مهنيًا. لا تتدخل في التركيب الكهربائي: اتصل بكهربائي."}
ANOMALY_LABEL = {"surconsommation": ("surconsommation", "استهلاك مفرط"),
                 "consommation_nocturne": ("consommation nocturne anormale", "استهلاك ليلي غير عادي"),
                 "ecart_prevision": ("écart avec la prévision", "فارق عن التوقع")}
MONTHS = {"fr": ["janvier", "février", "mars", "avril", "mai", "juin", "juillet", "août", "septembre", "octobre", "novembre", "décembre"],
          "ar": ["جانفي", "فيفري", "مارس", "أفريل", "ماي", "جوان", "جويلية", "أوت", "سبتمبر", "أكتوبر", "نوفمبر", "ديسمبر"]}


def _r(x, n=1):
    return None if x is None else round(float(x), n)


def model_quality():
    out = {}
    for name in ("forecast_h1", "forecast_h7", "anomalies", "profiles"):
        mr = ModelRun.objects.filter(name=name, is_active=True).first()
        if mr:
            out[name] = mr.metrics
    return out


def recommended_tips(f):
    """Choisit les conseils pertinents selon le profil ML et les alertes du foyer."""
    p, ids = f.get("profile") or {}, []
    if (p.get("heat_sens") or 0) > 0.8 or f.get("hot_days"):
        ids.append("clim26")
    if (p.get("evening_share") or 0) >= 40:
        ids.append("shift")
    if (p.get("night_share") or 0) >= 15 or any(a["type"] == "consommation_nocturne" for a in f.get("alerts", [])):
        ids.append("standby")
    if any(a["type"] == "consommation_nocturne" for a in f.get("alerts", [])):
        ids.append("heater")
    if f.get("alerts"):
        ids.append("check")
    for extra in ("fridge", "fan", "led"):
        if len(ids) >= 4:
            break
        if extra not in ids:
            ids.append(extra)
    return ids[:4]


def household_facts(h):
    """Tout ce que l'IA (et l'interface) a le droit d'utiliser pour parler du foyer."""
    daily = list(DailyConsumption.objects.filter(household=h).order_by("-date").values("date", "kwh", "tmax")[:400])
    if not daily:
        return {"household": h.household_id, "has_data": False}
    daily.reverse()
    last = daily[-1]
    d_last = last["date"]
    last30 = [x["kwh"] for x in daily if x["date"] > d_last - timedelta(days=30)]
    prev30 = [x["kwh"] for x in daily if d_last - timedelta(days=60) < x["date"] <= d_last - timedelta(days=30)]
    avg30 = sum(last30) / len(last30)
    avg_prev = sum(prev30) / len(prev30) if prev30 else None

    fut = list(Forecast.objects.filter(household=h, kind="future").order_by("target_date"))
    fc = [{"date": f.target_date.isoformat(), "pred": _r(f.predicted_kwh, 2), "q10": _r(f.q10, 2), "q90": _r(f.q90, 2),
           "tmax": _r(f.tmax_used), "weather": f.weather_source, "model": f.model_name} for f in fut]
    peak = max(fc, key=lambda x: x["pred"]) if fc else None
    width = (sum((x["q90"] - x["q10"]) / max(x["pred"], 0.5) for x in fc) / len(fc)) if fc else None
    confidence = None if width is None else ("haute" if width < 0.25 else "moyenne" if width < 0.5 else "faible")

    # mois en cours (celui du dernier relevé) : consommé + prévu + moyenne récente pour les jours restants
    # période = mois du lendemain du dernier relevé (si le mois est complet, on estime le mois suivant)
    d_next = d_last + timedelta(days=1)
    m0 = d_next.replace(day=1)
    ndays = calendar.monthrange(m0.year, m0.month)[1]
    mtd = sum(x["kwh"] for x in daily if x["date"] >= m0)
    elapsed = (d_last - m0).days + 1 if d_last >= m0 else 0
    rest = [x for x in fc if x["date"][:7] == m0.isoformat()[:7]]
    left = ndays - elapsed
    projection = mtd + sum(x["pred"] for x in rest) + max(0, left - len(rest)) * avg30
    bill = billing.estimate(projection, ndays)

    pm_end = m0 - timedelta(days=1)
    prev_month = [x["kwh"] for x in daily if x["date"].year == pm_end.year and x["date"].month == pm_end.month]

    prof = getattr(h, "profile", None)
    profile = None
    peers = None
    if prof:
        profile = {"name": prof.profil, "cluster": prof.cluster, "mean_day": _r(prof.mean_day, 2),
                   "evening_share": _r(prof.evening_share), "night_share": _r(prof.night_share),
                   "summer_ratio": _r(prof.summer_ratio, 2), "load_factor": _r(prof.load_factor, 2),
                   "heat_sens": _r(prof.heat_sens, 2), "weekend_ratio": _r(prof.weekend_ratio, 2)}
        same = HouseholdProfile.objects.filter(cluster=prof.cluster)
        agg = same.aggregate(m=Avg("mean_day"), e=Avg("evening_share"), n=Avg("night_share"), s=Avg("heat_sens"))
        vals = sorted(x for x in same.values_list("mean_day", flat=True) if x is not None)
        rank = sum(v <= (prof.mean_day or 0) for v in vals)
        peers = {"n": same.count(), "mean_day": _r(agg["m"], 2), "evening_share": _r(agg["e"]),
                 "night_share": _r(agg["n"]), "heat_sens": _r(agg["s"], 2),
                 "rank_pct": round(100 * rank / len(vals)) if vals else None}

    alerts = [{"date": a.date.isoformat(), "type": a.anomaly_type, "severity": a.severity, "kwh": _r(a.kwh),
               "expected": _r(a.expected_kwh), "ratio": _r(a.ratio, 2), "source": a.source}
              for a in Alert.objects.filter(household=h, is_resolved=False).order_by("-date")[:5]]
    hot_days = [x for x in fc if (x["tmax"] or 0) >= 35]
    q = model_quality().get("forecast_h1", {})
    reg = h.region_info or {}
    f = {
        "has_data": True, "household": h.household_id, "synthetic": h.is_synthetic,
        "region": {"fr": reg.get("fr", h.region), "ar": reg.get("ar", h.region)},
        "persona": {"fr": PERSONAS.get(h.persona, (h.persona, h.persona))[0], "ar": PERSONAS.get(h.persona, (h.persona, h.persona))[1]},
        "data_until": d_last.isoformat(),
        "last_day": {"date": d_last.isoformat(), "kwh": _r(last["kwh"], 2), "tmax": _r(last["tmax"])},
        "avg_30d": _r(avg30, 2), "avg_prev_30d": _r(avg_prev, 2),
        "trend_30d_pct": _r((avg30 / avg_prev - 1) * 100) if avg_prev else None,
        "month": {"label_idx": m0.month - 1, "year": m0.year, "consumed_kwh": _r(mtd), "days_elapsed": elapsed,
                  "forecast_days": len(rest),
                  "days_in_month": ndays, "projection_kwh": _r(projection), "bill": bill,
                  "prev_month_kwh": _r(sum(prev_month)) if prev_month else None},
        "forecast": fc, "peak": peak, "confidence": confidence,
        "profile": profile, "peers": peers, "alerts": alerts,
        "alerts_open": Alert.objects.filter(household=h, is_resolved=False).count(),
        "hot_days": [{"date": x["date"], "tmax": x["tmax"]} for x in hot_days],
        "model": {"mape_pct": (q.get("test", {}).get("ensemble") or {}).get("MAPE_%"),
                  "baseline_mape_pct": (q.get("test", {}).get("baseline (même jour sem. dernière)") or {}).get("MAPE_%"),
                  "coverage_pct": _r((q.get("interval_coverage") or 0) * 100) if q else None},
    }
    f["tips"] = recommended_tips(f)
    return f


# --------------------------------------------------------------------------- assistant : moteur de règles
INTENTS = [
    ("facture", r"factur|bill|montant|prix|payer|tarif|tranche|فاتور|فاتوره|ثمن|سعر|خلاص|شريحة|الكونتور"),
    ("alerte", r"alert|anomal|inhabituel|anormal|bizarre|explique|تنبيه|شذوذ|غير عادي|اشرح|علاش"),
    ("prevision", r"prév|prevision|demain|semaine|futur|prochain|pic|توقع|غدا|غدوة|الأسبوع|ذروة|الجاي"),
    ("profil", r"profil|habitude|soir|nuit|catégorie|ملف|عادات|المساء|الليل|صنف"),
    ("comparaison", r"compar|voisin|similaire|moyenne|autres|قارن|مقارنة|الجيران|الآخرين|متوسط"),
    ("conseil", r"réduire|reduire|conseil|économ|econom|baisser|astuce|moins|خفض|نصيحة|نصائح|توفير|نقص|نقلل|اقتصاد"),
    ("salut", r"^(bonjour|salut|bonsoir|hello|salam|مرحبا|السلام|عسلامة|أهلا)\b"),
]


def detect_intent(q):
    ql = q.lower()
    for name, rx in INTENTS:
        if re.search(rx, ql):
            return name
    return None


def _n(x, lang, d=1):
    if x is None:
        return "–"
    s = f"{x:,.{d}f}".replace(",", " ")
    return s.replace(".", ",") if lang == "fr" else s


def _date(iso, lang):
    d = date.fromisoformat(iso)
    return f"{d.day} {MONTHS[lang][d.month - 1]}"


def rules_answer(q, f, lang):
    if not f.get("has_data"):
        return ("Je n'ai pas encore de relevés pour votre foyer. Ajoutez vos relevés dans « Mes relevés » et je pourrai vous répondre."
                if lang == "fr" else "لا توجد بعد قراءات لأسرتك. أضف قراءاتك في « قراءاتي » وسأجيبك.")
    it = detect_intent(q)
    m, b = f["month"], f["month"]["bill"]
    mon = MONTHS[lang][m["label_idx"]]
    tip = lambda i: TIPS[i][lang]
    if it == "salut":
        return ("Bonjour ! Je connais votre consommation, vos prévisions, votre profil et vos alertes. "
                "Demandez-moi par exemple pourquoi votre facture augmente ou comment réduire votre consommation."
                if lang == "fr" else "مرحبًا! أعرف استهلاكك وتوقعاتك وملفك وتنبيهاتك. اسألني مثلًا لماذا ترتفع فاتورتك أو كيف تخفض استهلاكك.")
    if it == "facture":
        if lang == "fr":
            s = (f"Pour {mon}, vous avez consommé {_n(m['consumed_kwh'], lang, 0)} kWh en {m['days_elapsed']} jours. " if m["days_elapsed"] else f"Pour {mon}, ")
            s += (f"{'A' if m['days_elapsed'] else 'a'}vec les prévisions du modèle, la projection est de {_n(m['projection_kwh'], lang, 0)} kWh, soit environ "
                 f"{_n(b['total'], lang, 0)} DT hors taxes (tranche « {b['band_label']} », {_n(b['price'], lang, 3)} DT/kWh).")
            if b.get("next_band") and b["next_band"]["room_kwh"] < 40:
                s += f" Attention : {_n(b['next_band']['room_kwh'], lang, 0)} kWh de plus et toute votre consommation passerait au tarif supérieur."
            if b.get("prev_band") and b["prev_band"]["save_kwh"] < 60:
                s += f" Bonne nouvelle : en économisant {_n(b['prev_band']['save_kwh'], lang, 0)} kWh vous repasseriez dans la tranche inférieure (≈ {_n(b['prev_band']['saving_dt'], lang, 0)} DT de moins)."
            if f["profile"] and f["profile"]["heat_sens"]:
                s += f" Chez vous, chaque degré au-dessus de 24 °C ajoute environ {_n(f['profile']['heat_sens'], lang, 2)} kWh par jour."
        else:
            s = (f"في {mon} استهلكت {_n(m['consumed_kwh'], lang, 0)} ك.و.س خلال {m['days_elapsed']} يومًا. " if m["days_elapsed"] else f"في {mon}، ")
            s += (f"مع توقعات النموذج، يُقدَّر الاستهلاك بـ {_n(m['projection_kwh'], lang, 0)} ك.و.س، أي حوالي {_n(b['total'], lang, 0)} د.ت دون أداءات "
                 f"(الشريحة « {b['band_label']} »، {_n(b['price'], lang, 3)} د.ت/ك.و.س).")
            if b.get("next_band") and b["next_band"]["room_kwh"] < 40:
                s += f" انتبه: {_n(b['next_band']['room_kwh'], lang, 0)} ك.و.س إضافية تجعل كامل استهلاكك بالسعر الأعلى."
            if b.get("prev_band") and b["prev_band"]["save_kwh"] < 60:
                s += f" خبر جيد: بتوفير {_n(b['prev_band']['save_kwh'], lang, 0)} ك.و.س تعود إلى الشريحة الأدنى (≈ {_n(b['prev_band']['saving_dt'], lang, 0)} د.ت أقل)."
            if f["profile"] and f["profile"]["heat_sens"]:
                s += f" عندك، كل درجة فوق 24 °م تضيف حوالي {_n(f['profile']['heat_sens'], lang, 2)} ك.و.س يوميًا."
        return s
    if it == "alerte":
        if not f["alerts"]:
            return ("Aucune alerte en cours : votre consommation récente reste dans vos habitudes." if lang == "fr"
                    else "لا توجد تنبيهات حالية: استهلاكك الأخير ضمن عاداتك.")
        a = f["alerts"][0]
        lab = ANOMALY_LABEL.get(a["type"], (a["type"], a["type"]))[0 if lang == "fr" else 1]
        if lang == "fr":
            s = f"Le {_date(a['date'], lang)}, la détection a signalé une {lab} (gravité {a['severity']})"
            if a["kwh"] and a["expected"]:
                s += f" : {_n(a['kwh'], lang)} kWh mesurés pour {_n(a['expected'], lang)} kWh attendus (×{_n(a['ratio'], lang, 2)})"
            s += ". " + (tip("standby") if a["type"] == "consommation_nocturne" else tip("check"))
        else:
            s = f"يوم {_date(a['date'], lang)} رُصد {lab} (خطورة {a['severity']})"
            if a["kwh"] and a["expected"]:
                s += f": {_n(a['kwh'], lang)} ك.و.س مقابل {_n(a['expected'], lang)} ك.و.س متوقعة (×{_n(a['ratio'], lang, 2)})"
            s += ". " + (tip("standby") if a["type"] == "consommation_nocturne" else tip("check"))
        return s
    if it == "prevision":
        if not f["forecast"]:
            return ("Pas encore de prévision : il faut au moins 14 jours de relevés." if lang == "fr"
                    else "لا يوجد توقع بعد: يلزم 14 يومًا من القراءات على الأقل.")
        p, fc = f["peak"], f["forecast"][0]
        if lang == "fr":
            s = (f"Demain ({_date(fc['date'], lang)}), le modèle prévoit {_n(fc['pred'], lang)} kWh "
                 f"(entre {_n(fc['q10'], lang)} et {_n(fc['q90'], lang)}). Le pic des 7 prochains jours est attendu le "
                 f"{_date(p['date'], lang)} avec {_n(p['pred'], lang)} kWh")
            s += f" ({_n(p['tmax'], lang, 0)} °C prévus)." if p.get("tmax") else "."
            if f["hot_days"]:
                s += " Des journées chaudes arrivent : " + tip("clim26")
        else:
            s = (f"غدًا ({_date(fc['date'], lang)}) يتوقع النموذج {_n(fc['pred'], lang)} ك.و.س "
                 f"(بين {_n(fc['q10'], lang)} و{_n(fc['q90'], lang)}). الذروة خلال الأيام السبعة متوقعة يوم "
                 f"{_date(p['date'], lang)} بـ {_n(p['pred'], lang)} ك.و.س")
            s += f" ({_n(p['tmax'], lang, 0)} °م متوقعة)." if p.get("tmax") else "."
            if f["hot_days"]:
                s += " أيام حارة قادمة: " + tip("clim26")
        return s
    if it == "profil":
        p = f["profile"]
        if not p:
            return "Votre profil sera calculé lors du prochain passage de profiles.py." if lang == "fr" else "سيُحسب ملفك عند التشغيل القادم لـ profiles.py."
        if lang == "fr":
            return (f"Votre profil : « {p['name']} ». Vous consommez en moyenne {_n(p['mean_day'], lang)} kWh/jour, "
                    f"dont {_n(p['evening_share'], lang, 0)} % le soir (18 h–23 h) et {_n(p['night_share'], lang, 0)} % la nuit. "
                    f"En été vous consommez {_n(p['summer_ratio'], lang)} fois plus qu'en hiver.")
        return (f"ملفك: « {p['name']} ». تستهلك في المتوسط {_n(p['mean_day'], lang)} ك.و.س يوميًا، "
                f"منها {_n(p['evening_share'], lang, 0)} % مساءً (18–23) و{_n(p['night_share'], lang, 0)} % ليلًا. "
                f"في الصيف تستهلك {_n(p['summer_ratio'], lang)} مرة أكثر من الشتاء.")
    if it == "comparaison":
        pe, p = f["peers"], f["profile"]
        if not pe:
            return "Comparaison indisponible sans profil." if lang == "fr" else "المقارنة غير متاحة دون ملف."
        diff = (p["mean_day"] / pe["mean_day"] - 1) * 100 if pe["mean_day"] else 0
        if lang == "fr":
            return (f"Parmi les {pe['n']} foyers au profil semblable, la moyenne est de {_n(pe['mean_day'], lang)} kWh/jour ; "
                    f"vous êtes à {_n(p['mean_day'], lang)} kWh/jour ({'+' if diff >= 0 else ''}{_n(diff, lang, 0)} %). "
                    f"{'Vous faites partie des plus économes du groupe.' if diff < -5 else 'Il y a une marge de progrès : ' + tip(f['tips'][0]) if diff > 5 else 'Vous êtes dans la moyenne du groupe.'}")
        return (f"من بين {pe['n']} أسرة ذات ملف مشابه، المتوسط {_n(pe['mean_day'], lang)} ك.و.س يوميًا؛ "
                f"وأنت عند {_n(p['mean_day'], lang)} ك.و.س ({'+' if diff >= 0 else ''}{_n(diff, lang, 0)} %). "
                f"{'أنت من الأكثر اقتصادًا في المجموعة.' if diff < -5 else 'هناك مجال للتحسن: ' + tip(f['tips'][0]) if diff > 5 else 'أنت في متوسط المجموعة.'}")
    if it == "conseil":
        head = "Voici les conseils les plus utiles pour votre foyer :" if lang == "fr" else "هذه أنسب النصائح لأسرتك:"
        return head + "\n" + "\n".join(f"{i + 1}. {tip(t)}" for i, t in enumerate(f["tips"]))
    return ("Je réponds aux questions sur votre facture, vos prévisions, votre profil, vos alertes et les économies d'énergie. "
            "Essayez une des questions proposées." if lang == "fr"
            else "أجيب عن الأسئلة المتعلقة بفاتورتك وتوقعاتك وملفك وتنبيهاتك وتوفير الطاقة. جرّب أحد الأسئلة المقترحة.")


# --------------------------------------------------------------------------- assistant : IA générative
SYSTEM = {
    "fr": ("Tu es l'assistant énergie d'ÉnergiTN, plateforme tunisienne de maîtrise de la consommation électrique. "
           "Réponds en français simple, en 120 mots maximum, au foyer à partir UNIQUEMENT du JSON de faits et des conseils fournis. "
           "Cite les chiffres utiles (kWh, DT, dates). N'invente aucun chiffre. Si la question sort du périmètre "
           "(facture, consommation, prévisions, profil, alertes, économies d'énergie), dis-le poliment et propose ces sujets. "
           "Ne conseille jamais d'intervenir sur l'installation électrique. Les données sont synthétiques (prototype)."),
    "ar": ("أنت مساعد الطاقة في منصة ÉnergiTN التونسية. أجب بالعربية الفصحى المبسطة وفي 120 كلمة على الأكثر، "
           "اعتمادًا فقط على ملف الوقائع والنصائح المقدمة. اذكر الأرقام المفيدة ولا تخترع أي رقم. إذا خرج السؤال عن "
           "المجال (الفاتورة، الاستهلاك، التوقعات، الملف، التنبيهات، توفير الطاقة) فقل ذلك بلطف واقترح هذه المواضيع. "
           "لا تنصح أبدًا بالتدخل في التركيب الكهربائي. البيانات اصطناعية (نموذج أولي)."),
}


def llm_call(system, messages, max_tokens=500):
    body = json.dumps({"model": settings.LLM_MODEL, "max_tokens": max_tokens, "system": system,
                       "messages": messages}).encode()
    req = urllib.request.Request("https://api.anthropic.com/v1/messages", data=body, method="POST", headers={
        "x-api-key": settings.ANTHROPIC_API_KEY, "anthropic-version": "2023-06-01", "content-type": "application/json"})
    with urllib.request.urlopen(req, timeout=settings.LLM_TIMEOUT) as r:
        data = json.loads(r.read())
    return "".join(b.get("text", "") for b in data.get("content", [])).strip()


def answer(q, f, lang, history=()):
    """Retourne (texte, moteur). L'IA générative est utilisée si une clé est configurée, sinon les règles."""
    lang = "ar" if lang == "ar" else "fr"
    if settings.ANTHROPIC_API_KEY and f.get("has_data"):
        try:
            tips = {k: TIPS[k][lang] for k in TIPS}
            ctx = f"FAITS DU FOYER (JSON) :\n{json.dumps(f, ensure_ascii=False)}\n\nCONSEILS VALIDÉS :\n{json.dumps(tips, ensure_ascii=False)}"
            msgs = [{"role": "user", "content": ctx}, {"role": "assistant", "content": "Compris."}]
            for m in list(history)[-6:]:
                msgs.append({"role": m["role"], "content": m["content"]})
            msgs.append({"role": "user", "content": q})
            text = llm_call(SYSTEM[lang], msgs)
            if text:
                return text, "llm"
        except Exception as e:     # réseau, quota, modèle : on retombe sur les règles
            log.warning("Assistant IA indisponible, repli sur les règles : %s", e)
    return rules_answer(q, f, lang), "regles"


# --------------------------------------------------------------------------- rapport mensuel (BF09)
def available_months(h):
    ds = DailyConsumption.objects.filter(household=h).dates("date", "month", order="DESC")
    return [d.strftime("%Y-%m") for d in ds]


def monthly_report(h, ym, lang="fr"):
    y, m = map(int, ym.split("-"))
    start, ndays = date(y, m, 1), calendar.monthrange(y, m)[1]
    end = date(y, m, ndays)
    rows = list(DailyConsumption.objects.filter(household=h, date__range=(start, end)).order_by("date").values("date", "kwh", "tmax"))
    if not rows:
        return None
    pstart = (start - timedelta(days=1)).replace(day=1)
    prev = DailyConsumption.objects.filter(household=h, date__range=(pstart, start - timedelta(days=1))).aggregate(s=Sum("kwh"), a=Avg("kwh"))
    tot = sum(r["kwh"] for r in rows)
    avg = tot / len(rows)
    peak = max(rows, key=lambda r: r["kwh"])
    low = min(rows, key=lambda r: r["kwh"])
    hot = [r for r in rows if (r["tmax"] or 0) >= 35]
    we = [r["kwh"] for r in rows if r["date"].weekday() >= 5]
    wd = [r["kwh"] for r in rows if r["date"].weekday() < 5]
    alerts = list(Alert.objects.filter(household=h, date__range=(start, end)).order_by("date"))
    bill = billing.estimate(tot * ndays / len(rows), ndays)
    trend = (avg / prev["a"] - 1) * 100 if prev["a"] else None
    f = household_facts(h)
    p = f.get("profile") or {}
    L = lang if lang in ("fr", "ar") else "fr"
    mon = f"{MONTHS[L][m - 1]} {y}"
    hl = []
    if L == "fr":
        if trend is not None:
            hl.append(f"{'Hausse' if trend > 0 else 'Baisse'} de {_n(abs(trend), L, 0)} % de la consommation moyenne par rapport au mois précédent.")
        hl.append(f"Jour le plus chargé : {_date(peak['date'].isoformat(), L)} avec {_n(peak['kwh'], L)} kWh"
                  + (f" ({_n(peak['tmax'], L, 0)} °C)." if peak["tmax"] else "."))
        if hot:
            hl.append(f"{len(hot)} jour(s) à 35 °C ou plus : ils ont représenté {_n(sum(r['kwh'] for r in hot) / tot * 100, L, 0)} % de la consommation du mois.")
        hl.append(f"{len(alerts)} journée(s) anormale(s) détectée(s)." if alerts else "Aucune consommation anormale détectée ce mois-ci.")
        if we and wd:
            hl.append(f"Le week-end, vous consommez {_n(sum(we) / len(we) - sum(wd) / len(wd), L)} kWh/jour de plus qu'en semaine." if sum(we) / len(we) > sum(wd) / len(wd)
                      else "Votre consommation du week-end est proche de celle de la semaine.")
        if p.get("evening_share"):
            hl.append(f"Le soir (18 h–23 h) concentre {_n(p['evening_share'], L, 0)} % de votre consommation habituelle.")
    else:
        if trend is not None:
            hl.append(f"{'ارتفاع' if trend > 0 else 'انخفاض'} بنسبة {_n(abs(trend), L, 0)} % في متوسط الاستهلاك مقارنة بالشهر السابق.")
        hl.append(f"أكثر يوم استهلاكًا: {_date(peak['date'].isoformat(), L)} بـ {_n(peak['kwh'], L)} ك.و.س"
                  + (f" ({_n(peak['tmax'], L, 0)} °م)." if peak["tmax"] else "."))
        if hot:
            hl.append(f"{len(hot)} يوم بحرارة 35 °م أو أكثر: مثّلت {_n(sum(r['kwh'] for r in hot) / tot * 100, L, 0)} % من استهلاك الشهر.")
        hl.append(f"رُصد {len(alerts)} يوم غير عادي." if alerts else "لم يُرصد أي استهلاك غير عادي هذا الشهر.")
        if we and wd:
            hl.append(f"في نهاية الأسبوع تستهلك {_n(sum(we) / len(we) - sum(wd) / len(wd), L)} ك.و.س يوميًا أكثر من أيام العمل." if sum(we) / len(we) > sum(wd) / len(wd)
                      else "استهلاكك في نهاية الأسبوع قريب من أيام العمل.")
        if p.get("evening_share"):
            hl.append(f"المساء (18–23) يمثّل {_n(p['evening_share'], L, 0)} % من استهلاكك المعتاد.")
    ids = list(f.get("tips") or [])
    if hot and "clim26" not in ids:
        ids.insert(0, "clim26")
    summary = None
    if settings.ANTHROPIC_API_KEY:
        try:
            stats = {"mois": mon, "total_kwh": round(tot, 1), "moyenne_kwh_jour": round(avg, 2), "evolution_pct": _r(trend),
                     "facture_estimee_dt": bill["total"], "faits_marquants": hl}
            summary = llm_call(SYSTEM[L], [{"role": "user", "content":
                               ("Rédige le paragraphe d'introduction (60 mots max) du rapport mensuel à partir de : " if L == "fr"
                                else "اكتب فقرة تمهيدية (60 كلمة على الأكثر) للتقرير الشهري انطلاقًا من: ") + json.dumps(stats, ensure_ascii=False)}], 250)
        except Exception as e:
            log.warning("Rapport : IA indisponible (%s)", e)
    if not summary:
        summary = (f"En {mon}, votre foyer a consommé {_n(tot, L, 0)} kWh, soit {_n(avg, L)} kWh par jour en moyenne. "
                   f"Facture estimée : {_n(bill['total'], L, 0)} DT hors taxes." if L == "fr" else
                   f"في {mon} استهلكت أسرتك {_n(tot, L, 0)} ك.و.س، أي {_n(avg, L)} ك.و.س يوميًا في المتوسط. "
                   f"الفاتورة المقدّرة: {_n(bill['total'], L, 0)} د.ت دون أداءات.")
    return {"month": ym, "label": mon, "days": len(rows), "complete": len(rows) == ndays,
            "total": round(tot, 1), "avg": round(avg, 2), "trend_pct": _r(trend), "prev_total": _r(prev["s"]),
            "peak": {"date": peak["date"].isoformat(), "kwh": _r(peak["kwh"], 2)},
            "low": {"date": low["date"].isoformat(), "kwh": _r(low["kwh"], 2)},
            "series": [{"date": r["date"].isoformat(), "kwh": _r(r["kwh"], 2), "tmax": _r(r["tmax"])} for r in rows],
            "alerts": [{"date": a.date.isoformat(), "type": a.anomaly_type, "severity": a.severity} for a in alerts],
            "bill": bill, "highlights": hl, "summary": summary,
            "tips": [TIPS[i][L] for i in ids[:4]], "disclaimer": DISCLAIMER[L]}
