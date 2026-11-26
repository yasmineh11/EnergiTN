# Étape 2 — assemble le template Django partials/tn_map.html à partir de tn.json
# Usage : python gen.py   puis copier tn_map.html dans backend/web/templates/partials/
import json
d=json.load(open("tn.json"))
W,H,P=d["W"],d["H"],d["pts"]
# position du symbole ÉnergiTN (centre-ouest, choisie pour l'équilibre du dessin, pas une ville)
hub=(150.0,120.0)
# nom français, nom arabe, côté du nom (1 = à droite du point, -1 = à gauche)
names={"biz":("Bizerte","بنزرت",-1),"tun":("Tunis","تونس",1),"sou":("Sousse","سوسة",1),"sfx":("Sfax","صفاقس",1),"gab":("Gabès","قابس",1),"toz":("Tozeur","توزر",-1)}
lines=[]; nodes=[]
for i,(k,(x,y)) in enumerate(P.items()):
    hx,hy=hub
    mx,my=(hx+x)/2,(hy+y)/2
    # courbe douce : point de contrôle décalé perpendiculairement
    dx,dy=x-hx,y-hy; L=(dx*dx+dy*dy)**.5 or 1
    cx,cy=mx-dy/L*18,my+dx/L*18
    lines.append(f'<path class="tnm-link" d="M{hx:.1f} {hy:.1f}Q{cx:.1f} {cy:.1f} {x} {y}" style="animation-delay:{i*.35:.2f}s"/>')
    fr,ar,side=names[k]
    tx=x+side*11; anchor="start" if side>0 else "end"
    nodes.append(f'''<g class="tnm-node" style="animation-delay:{i*.35:.2f}s"><circle class="tnm-ring" cx="{x}" cy="{y}" r="5"/><circle class="tnm-dot" cx="{x}" cy="{y}" r="4.2"/>
<text class="tnm-lab" x="{tx:.1f}" y="{y+4:.1f}" text-anchor="{anchor}">{{% if lang == 'ar' %}}{ar}{{% else %}}{fr}{{% endif %}}</text></g>''')
svg=f'''{{% load tr %}}{{% comment %}}Carte de la Tunisie (contour Natural Earth 1:10m, projection Mercator) + symbole ÉnergiTN.
Paramètre : tone = "light" (accueil) ou "dark" (page de connexion).{{% endcomment %}}
<svg class="tnm tnm-{{{{ tone|default:'light' }}}}" viewBox="0 0 {W} {H}" role="img" aria-label="{{% t 'map_alt' %}}">
<defs>
  <linearGradient id="tnm-fill-{{{{ tone|default:'light' }}}}" x1="0" y1="0" x2="0.4" y2="1"><stop offset="0" class="tnm-s1"/><stop offset="1" class="tnm-s2"/></linearGradient>
  <pattern id="tnm-dots-{{{{ tone|default:'light' }}}}" width="7" height="7" patternUnits="userSpaceOnUse"><circle cx="1.5" cy="1.5" r="1" class="tnm-dotgrid"/></pattern>
  <radialGradient id="tnm-glow-{{{{ tone|default:'light' }}}}"><stop offset="0" class="tnm-g1"/><stop offset="1" class="tnm-g2"/></radialGradient>
  <clipPath id="tnm-clip-{{{{ tone|default:'light' }}}}"><path d="{d["tn"]}"/></clipPath>
</defs>
<text class="tnm-sea" x="0" y="0" text-anchor="middle" transform="translate({W-4} 250) rotate(-90)">{{% if lang == 'ar' %}}البحر الأبيض المتوسط{{% else %}}Mer Méditerranée{{% endif %}}</text>
<path class="tnm-shadow" d="{d["tn"]}" transform="translate(4 7)"/>
<path class="tnm-land" d="{d["tn"]}" fill="url(#tnm-fill-{{{{ tone|default:'light' }}}})"/>
<rect width="{W}" height="{H}" fill="url(#tnm-dots-{{{{ tone|default:'light' }}}})" clip-path="url(#tnm-clip-{{{{ tone|default:'light' }}}})"/>
<path class="tnm-coast" d="{d["tn"]}"/>
<circle cx="{hub[0]}" cy="{hub[1]}" r="70" fill="url(#tnm-glow-{{{{ tone|default:'light' }}}})"/>
{"".join(lines)}
{"".join(nodes)}
<g class="tnm-hub" transform="translate({hub[0]} {hub[1]})">
  <circle class="tnm-hub-pulse" r="22"/>
  <circle class="tnm-hub-bg" r="21"/>
  <use href="#logo" x="-13" y="-13" width="26" height="26" class="tnm-hub-logo"/>
</g>
</svg>'''
open("tn_map.html","w",encoding="utf-8").write(svg)
print(len(svg))
