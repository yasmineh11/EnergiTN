"""{% t 'cle' %} : texte dans la langue de l'utilisateur (cookie lang), avec variables {% t 'cle' n=3 %}."""
from django import template
from web.i18n import tr

register = template.Library()


@register.simple_tag(takes_context=True)
def t(context, key, **kw):
    req = context.get("request")
    lang = "ar" if req is not None and req.COOKIES.get("lang") == "ar" else "fr"
    s = tr(key, lang)
    for k, v in kw.items():
        s = s.replace("{" + k + "}", str(v))
    return s
