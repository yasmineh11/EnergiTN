# Carte de la Tunisie (page d'accueil et page de connexion)

Génère `backend/web/templates/partials/tn_map.html` à partir du contour réel de la Tunisie
(Natural Earth 1:10m, domaine public), projeté en Mercator avec d3-geo.

    npm install world-atlas@2 topojson-client d3-geo
    node make.mjs        # -> tn.json  (contour SVG + positions des 6 villes)
    python gen.py        # -> tn_map.html
    copy /Y tn_map.html ..\..\backend\web\templates\partials\tn_map.html

Ajouter une ville : `villes` dans make.mjs + `names` (français, arabe) dans gen.py.
Couleurs et animations : classes `.tnm-…` dans backend/web/static/css/energitn.css.
