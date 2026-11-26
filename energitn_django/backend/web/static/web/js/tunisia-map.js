
/* ============================================================
   ÉNERGITN — CARTE INTERACTIVE DE LA TUNISIE
   Fichier : static/web/js/tunisia-map.js

   Dépendances :
   - Leaflet 1.9.4
   - GeoJSON des gouvernorats tunisiens

   HTML nécessaire :
   - #map
   - #map_status

   API publique :
   TunisiaMap.init(options)
   TunisiaMap.render(regions, selectedId, lang, governorates)
   TunisiaMap.setLanguage(lang)
   TunisiaMap.getMap()
   TunisiaMap.getSelectedRegion()

   Régions modélisées :
   tun, biz, sou, sfx, gab, toz
============================================================ */

(function () {
    "use strict";

    /* ========================================================
       1. CONFIGURATION
    ======================================================== */

    const CONFIG = {
        mapId: "map",
        statusId: "map_status",

        geojsonUrl:
            "/static/web/geo/tunisia-governorates-medium.geojson",

        center: [34.0, 9.5],
        zoom: 6,

        thresholds: {
            normal: 0.80,
            critical: 0.92
        },

        colors: {
            normal: "#16a36a",
            warning: "#e9a323",
            critical: "#dc443d",
            unavailable: "#aebbc0",
            border: "#ffffff",
            selected: "#12303b"
        },

        marker: {
            minRadius: 9,
            maxRadius: 24,
            baseRadius: 9,
            radiusFactor: 15
        }
    };


    /* ========================================================
       2. COORDONNÉES DES SIX RÉGIONS
    ======================================================== */

    const REGION_COORDINATES = {
        tun: [36.8065, 10.1815],
        biz: [37.2744, 9.8739],
        sou: [35.8256, 10.6369],
        sfx: [34.7406, 10.7603],
        gab: [33.8815, 10.0982],
        toz: [33.9197, 8.1335]
    };
/* ========================================================
   CORRESPONDANCE GOUVERNORATS / RÉGIONS MODÉLISÉES
======================================================== */

const GOVERNORATE_TO_REGION = {
    "tunis": "tun",
    "tunisia": "tun",
    "تونس": "tun",

    "bizerte": "biz",
    "bizerta": "biz",
    "بنزرت": "biz",

    "sousse": "sou",
    "سوسة": "sou",

    "sfax": "sfx",
    "صفاقس": "sfx",

    "gabes": "gab",
    "gabès": "gab",
    "قابس": "gab",

    "tozeur": "toz",
    "توزر": "toz"
};

    /* ========================================================
       3. TRADUCTIONS
    ======================================================== */

    const TRANSLATIONS = {
        fr: {
            loading: "Chargement des gouvernorats...",
            loaded: "gouvernorats chargés",
            geoError: "Erreur de chargement du GeoJSON",
            leafletError: "Leaflet n'est pas chargé.",
            mapError: "Carte indisponible.",

            normal: "Normal",
            warning: "Vigilance",
            critical: "Critique",
            unavailable: "Données indisponibles",

            usage: "Taux de charge",
            demand: "Demande estimée",
            capacity: "Capacité",
            temperature: "Température",
            risk: "Niveau de risque",

            noData:
                "Aucune donnée énergétique disponible pour ce gouvernorat.",

            regionNote:
                "Centre indicatif de la région modélisée.",

            governorateNote:
                "Données propres à ce gouvernorat.",

            missingGovernorateData:
                "Les données détaillées de ce gouvernorat ne sont pas encore disponibles.",

            noRegionData:
                "Aucune donnée disponible pour cette région.",

            unknownGovernorate: "Gouvernorat inconnu",

            selected: "Région sélectionnée"
        },

        ar: {
            loading: "جاري تحميل الولايات...",
            loaded: "ولايات تم تحميلها",
            geoError: "خطأ في تحميل ملف الخريطة",
            leafletError: "Leaflet غير محمّل.",
            mapError: "الخريطة غير متاحة.",

            normal: "عادي",
            warning: "يقظة",
            critical: "حرج",
            unavailable: "البيانات غير متوفرة",

            usage: "نسبة الحمل",
            demand: "الطلب التقديري",
            capacity: "القدرة",
            temperature: "درجة الحرارة",
            risk: "مستوى الخطر",

            noData:
                "لا توجد بيانات طاقية متاحة لهذه الولاية.",

            regionNote:
                "مركز تقريبي للمنطقة النموذجية.",

            governorateNote:
                "بيانات خاصة بهذه الولاية.",

            missingGovernorateData:
                "البيانات التفصيلية لهذه الولاية غير متوفرة حاليا.",

            noRegionData:
                "لا توجد بيانات متاحة لهذه المنطقة.",

            unknownGovernorate: "ولاية غير معروفة",

            selected: "المنطقة المحددة"
        }
    };


    /* ========================================================
       4. ÉTAT DE LA CARTE
    ======================================================== */

    let map = null;

    let governorateLayer = null;

    let markerLayer = null;

    let geojsonLoaded = false;

    let initialized = false;

    let currentRegions = [];

    let currentGovernorates = [];

    let selectedRegion = null;

    let currentLanguage = "fr";

    let onRegionSelect = null;

    let resizeTimer = null;


    /* ========================================================
       5. OUTILS DOM
    ======================================================== */

    function getElement(id) {
        return document.getElementById(id);
    }

    function setStatus(message) {
        const element = getElement(CONFIG.statusId);

        if (element) {
            element.textContent = message;
        }
    }


    /* ========================================================
       6. SÉCURISATION HTML
    ======================================================== */

    function escapeHTML(value) {
        return String(value ?? "").replace(
            /[&<>"']/g,
            function (character) {
                return {
                    "&": "&amp;",
                    "<": "&lt;",
                    ">": "&gt;",
                    '"': "&quot;",
                    "'": "&#39;"
                }[character];
            }
        );
    }


    /* ========================================================
       7. NORMALISATION DES NOMS
    ======================================================== */

    function normalizeName(value) {
        return String(value || "")
            .normalize("NFD")
            .replace(/[\u0300-\u036f]/g, "")
            .toLowerCase()
            .trim()
            .replace(/[_-]+/g, " ")
            .replace(/\s+/g, " ");
    }


    /* ========================================================
       8. TRADUCTIONS ET FORMATAGE
    ======================================================== */

    function tr(key) {
        return (
            TRANSLATIONS[currentLanguage][key] ||
            TRANSLATIONS.fr[key] ||
            key
        );
    }

    function numberFormat(value) {
        if (
            value === null ||
            value === undefined ||
            value === "" ||
            !Number.isFinite(Number(value))
        ) {
            return "N/D";
        }

        return Number(value).toLocaleString(
            currentLanguage === "ar" ? "ar-TN" : "fr-TN",
            {
                maximumFractionDigits: 1
            }
        );
    }

    function percentageFormat(value) {
        if (
            value === null ||
            value === undefined ||
            value === "" ||
            !Number.isFinite(Number(value))
        ) {
            return "N/D";
        }

        return Math.round(Number(value) * 100) + " %";
    }

    function normalizeUsage(value) {
        if (
            value === null ||
            value === undefined ||
            value === "" ||
            !Number.isFinite(Number(value))
        ) {
            return null;
        }

        let usage = Number(value);

        // Accepte 85 ou 0.85.
        if (usage > 1 && usage <= 100) {
            usage = usage / 100;
        }

        return usage;
    }


    /* ========================================================
       9. COULEURS SELON LE TAUX DE CHARGE
    ======================================================== */

    function getUsageColor(usage) {
        usage = normalizeUsage(usage);

        if (usage === null) {
            return CONFIG.colors.unavailable;
        }

        if (usage >= CONFIG.thresholds.critical) {
            return CONFIG.colors.critical;
        }

        if (usage >= CONFIG.thresholds.normal) {
            return CONFIG.colors.warning;
        }

        return CONFIG.colors.normal;
    }

    function getUsageStatus(usage) {
        usage = normalizeUsage(usage);

        if (usage === null) {
            return tr("unavailable");
        }

        if (usage >= CONFIG.thresholds.critical) {
            return tr("critical");
        }

        if (usage >= CONFIG.thresholds.normal) {
            return tr("warning");
        }

        return tr("normal");
    }


    /* ========================================================
       10. DONNÉES DES RÉGIONS MODÉLISÉES
    ======================================================== */

    function getRegionData(regionId) {
        return currentRegions.find(function (item) {
            return (
                item &&
                item.r &&
                String(item.r.id) === String(regionId)
            );
        }) || null;
    }

    function getRegionName(region) {
        if (!region) {
            return "";
        }

        return (
            currentLanguage === "ar"
                ? region.ar
                : region.fr
        ) || region.fr || region.id || "";
    }


    /* ========================================================
       11. DONNÉES DES GOUVERNORATS
       
       IMPORTANT :
       Les données des gouvernorats sont indépendantes
       des données des six régions modélisées.

       Format accepté :
       {
           code: "TN-11",
           name_fr: "Tunis",
           name_ar: "تونس",
           usage: 0.85,
           demand_mw: 1020,
           capacity_mw: 1200,
           temperature: 34,
           risk: "warning"
       }
    ======================================================== */

 function getGovernorateProperties(feature) {
    return feature && feature.properties
        ? feature.properties
        : {};
}

/* Récupère tous les noms possibles du GeoJSON.
   On ne dépend pas uniquement de la langue sélectionnée. */
function getGovernorateNames(feature) {
    const p = getGovernorateProperties(feature);

    const candidates = [
        p.name_fr,
        p.NAME_FR,
        p.name_ar,
        p.NAME_AR,
        p.name,
        p.NAME,
        p.NAME_1,
        p.NAME_2,
        p.shapeName,
        p.name_en,
        p.NAME_EN,
        p.governorate,
        p.admin
    ];

    return candidates
        .filter(value =>
            value !== null &&
            value !== undefined &&
            String(value).trim() !== ""
        )
        .map(value => String(value).trim());
}

function getGovernorateName(feature) {
    const names = getGovernorateNames(feature);

    if (names.length > 0) {
        return names[0];
    }

    return tr("unknownGovernorate");
}

/* Identifie si le polygone correspond à l'une
   des six régions du projet. */
function getMappedRegionId(feature) {
    const names = getGovernorateNames(feature);

    for (const name of names) {
        const normalized = normalizeName(name);

        if (GOVERNORATE_TO_REGION[normalized]) {
            return GOVERNORATE_TO_REGION[normalized];
        }

        // Recherche également les noms arabes tels quels.
        if (GOVERNORATE_TO_REGION[name]) {
            return GOVERNORATE_TO_REGION[name];
        }
    }

    return null;
}

function getGovernorateCode(feature) {
    const p = getGovernorateProperties(feature);

    const candidates = [
        p.code,
        p.CODE,
        p.iso_3166_2,
        p.ISO_3166_2,
        p.iso,
        p.ISO,
        p.id,
        p.ID,
        feature ? feature.id : null
    ];

    for (const value of candidates) {
        if (value !== null && value !== undefined) {
            const code = String(value).trim().toUpperCase();

            if (code.startsWith("TN-")) {
                return code;
            }
        }
    }

    return "";
}

/* Cherche d'abord une vraie donnée de gouvernorat.
   Si elle n'existe pas, utilise la donnée de la région
   modélisée correspondante. */
function findGovernorateData(feature) {
    const code = getGovernorateCode(feature);
    const names = getGovernorateNames(feature).map(normalizeName);

    // 1. Données détaillées propres au gouvernorat,
    // si elles sont disponibles ultérieurement.
    const detailedData = currentGovernorates.find(function (item) {
        if (!item) return false;

        const itemCode = String(
            item.code || item.governorate_code || ""
        ).trim().toUpperCase();

        if (code && itemCode && code === itemCode) {
            return true;
        }

        const itemNames = [
            item.name_fr,
            item.name_ar,
            item.name,
            item.governorate
        ]
            .filter(Boolean)
            .map(normalizeName);

        return itemNames.some(name => names.includes(name));
    });

    if (detailedData) {
        return {
            ...detailedData,
            dataSource: "governorate"
        };
    }

    // 2. Sinon, recherche la région modélisée associée.
    const regionId = getMappedRegionId(feature);

    if (!regionId) {
        return null;
    }

    const regionItem = getRegionData(regionId);

    if (!regionItem || !regionItem.r) {
        return null;
    }

    return {
        code: code,
        name_fr: regionItem.r.fr,
        name_ar: regionItem.r.ar,

        usage: regionItem.u ?? null,

        demand_mw: regionItem.mw ?? null,

        capacity_mw: regionItem.r.cap ?? null,

        temperature:
            regionItem.temperature ??
            regionItem.temp ??
            null,

        risk: getUsageStatus(regionItem.u),

        dataSource: "region"
    };
}

function getGovernorateUsage(item) {
    if (!item) {
        return null;
    }

    return normalizeUsage(
        item.usage ??
        item.load_ratio ??
        item.utilization ??
        item.charge
    );
}  
    /* ========================================================
       12. STYLE DES POLYGONES GEOJSON
    ======================================================== */

    function styleGovernorate(feature) {
        const item = findGovernorateData(feature);

        const usage = getGovernorateUsage(item);

        const color = getUsageColor(usage);

        return {
            color: CONFIG.colors.border,

            weight: 1.5,

            opacity: 1,

            fillColor: color,

            fillOpacity: usage === null ? 0.40 : 0.78
        };
    }


    /* ========================================================
       13. POPUP DES GOUVERNORATS
    ======================================================== */

    function governoratePopupContent(feature) {
        const item = findGovernorateData(feature);

        const name = getGovernorateName(feature);

        if (!item) {
            return `
                <div class="governorate-popup">

                    <strong>${escapeHTML(name)}</strong>

                    <div class="usage"
                         style="color:${CONFIG.colors.unavailable}">
                        N/D
                    </div>

                    <p>
                        ${escapeHTML(tr("missingGovernorateData"))}
                    </p>

                    <small>
                        ${escapeHTML(tr("noData"))}
                    </small>

                </div>
            `;
        }

        const usage = getGovernorateUsage(item);

        const color = getUsageColor(usage);

        const demand =
            item.demand_mw ??
            item.mw ??
            item.demand ??
            null;

        const capacity =
            item.capacity_mw ??
            item.capacity ??
            null;

        const temperature =
            item.temperature ??
            item.temperature_c ??
            null;

        const risk =
            item.risk ||
            getUsageStatus(usage);

        return `
            <div class="governorate-popup">

                <strong>${escapeHTML(name)}</strong>

                <div class="usage" style="color:${color}">
                    ${percentageFormat(usage)}
                </div>

                <div>
                    ${escapeHTML(tr("usage"))} :
                    <b>${escapeHTML(getUsageStatus(usage))}</b>
                </div>

                <div>
                    ${escapeHTML(tr("demand"))} :
                    <b>${numberFormat(demand)} MW</b>
                </div>

                <div>
                    ${escapeHTML(tr("capacity"))} :
                    <b>${numberFormat(capacity)} MW</b>
                </div>

                <div>
                    ${escapeHTML(tr("temperature"))} :
                    <b>
                        ${
                            temperature === null
                                ? "N/D"
                                : numberFormat(temperature) + " °C"
                        }
                    </b>
                </div>

                <div>
                    ${escapeHTML(tr("risk"))} :
                    <b>${escapeHTML(risk)}</b>
                </div>

                <small>
                    ${escapeHTML(tr("governorateNote"))}
                </small>

            </div>
        `;
    }


    /* ========================================================
       14. INTERACTIONS DES GOUVERNORATS
    ======================================================== */

function onEachGovernorate(feature, layer) {
    layer.on("mouseover", function () {
        layer.setStyle({
            weight: 3,
            color: CONFIG.colors.selected,
            fillOpacity: 0.9
        });

        if (layer.bringToFront) {
            layer.bringToFront();
        }
    });

    layer.on("mouseout", function () {
        if (governorateLayer) {
            governorateLayer.resetStyle(layer);
        }
    });

    layer.on("click", function () {
        const regionId = getMappedRegionId(feature);

        // Si le gouvernorat correspond à une région
        // modélisée, on synchronise la sélection.
        if (regionId && getRegionData(regionId)) {
            selectedRegion = regionId;

            if (typeof onRegionSelect === "function") {
                onRegionSelect(regionId);
            }

            updateMarkerStyles();
            updatePolygonStyles();
        }

        layer.bindPopup(
            governoratePopupContent(feature)
        ).openPopup();
    });
}

    /* ========================================================
       15. MISE À JOUR DES POLYGONES
    ======================================================== */

    function updatePolygonStyles() {
        if (!governorateLayer || !geojsonLoaded) {
            return;
        }

        governorateLayer.setStyle(styleGovernorate);
    }


    /* ========================================================
       16. POPUP DES SIX RÉGIONS
    ======================================================== */

    function markerPopupContent(item) {
        const region = item.r;

        const name = getRegionName(region);

        const usage = normalizeUsage(item.u);

        const color = getUsageColor(usage);

        const demand = item.mw ?? null;

        const capacity = region.cap ?? null;

        const temperature =
            item.temperature ??
            item.temp ??
            null;

        return `
            <div class="governorate-popup">

                <strong>${escapeHTML(name)}</strong>

                <div class="usage" style="color:${color}">
                    ${percentageFormat(usage)}
                </div>

                <div>
                    ${escapeHTML(tr("usage"))} :
                    <b>${escapeHTML(getUsageStatus(usage))}</b>
                </div>

                <div>
                    ${escapeHTML(tr("demand"))} :
                    <b>${numberFormat(demand)} MW</b>
                </div>

                <div>
                    ${escapeHTML(tr("capacity"))} :
                    <b>${numberFormat(capacity)} MW</b>
                </div>

                <div>
                    ${escapeHTML(tr("temperature"))} :
                    <b>
                        ${
                            temperature === null
                                ? "N/D"
                                : numberFormat(temperature) + " °C"
                        }
                    </b>
                </div>

                <small>
                    ${escapeHTML(tr("regionNote"))}
                </small>

            </div>
        `;
    }


    /* ========================================================
       17. MISE À JOUR DES SIX MARQUEURS
    ======================================================== */

    function updateMarkerStyles() {
        if (!markerLayer || !window.L) {
            return;
        }

        markerLayer.clearLayers();

        currentRegions.forEach(function (item) {
            if (!item || !item.r) {
                return;
            }

            const region = item.r;

            const position =
                REGION_COORDINATES[region.id];

            if (!position) {
                return;
            }

            const usage = normalizeUsage(item.u);

            const color = getUsageColor(usage);

            const isSelected =
                selectedRegion === region.id;

            const radius = usage === null
                ? CONFIG.marker.baseRadius
                : Math.max(
                    CONFIG.marker.minRadius,
                    Math.min(
                        CONFIG.marker.maxRadius,
                        CONFIG.marker.baseRadius +
                        Math.max(0, usage) *
                        CONFIG.marker.radiusFactor
                    )
                );

            const marker = window.L.circleMarker(
                position,
                {
                    radius: radius,

                    color: isSelected
                        ? CONFIG.colors.selected
                        : "#ffffff",

                    weight: isSelected ? 4 : 2,

                    fillColor: color,

                    fillOpacity: 0.95
                }
            );

            marker.addTo(markerLayer);

            const name = getRegionName(region);

            marker.bindTooltip(
                `${escapeHTML(name)} · ${percentageFormat(usage)}`,
                {
                    direction: "top",
                    sticky: true
                }
            );

            marker.bindPopup(
                markerPopupContent(item)
            );

            marker.on("click", function () {
                selectedRegion = region.id;

                if (typeof onRegionSelect === "function") {
                    onRegionSelect(region.id);
                }

                updateMarkerStyles();

                updatePolygonStyles();

                // Le marqueur est recréé pendant la mise à jour.
                // On ouvre donc la popup du nouveau marqueur.
                openRegionPopup(region.id);
            });
        });
    }


    /* ========================================================
       18. OUVRIR LA POPUP D'UNE RÉGION
    ======================================================== */

    function openRegionPopup(regionId) {
        if (!markerLayer) {
            return;
        }

        markerLayer.eachLayer(function (marker) {
            // Le marqueur contient son identifiant dans ses options.
            if (marker.options.regionId === regionId) {
                marker.openPopup();
            }
        });
    }


    /* ========================================================
       19. CHARGEMENT DU GEOJSON
    ======================================================== */

    async function loadGovernorates() {
        setStatus(tr("loading"));

        try {
            const response = await fetch(
                CONFIG.geojsonUrl,
                {
                    method: "GET",

                    headers: {
                        "Accept":
                            "application/geo+json, application/json"
                    },

                    cache: "default"
                }
            );

            if (!response.ok) {
                throw new Error(
                    "HTTP " + response.status
                );
            }

            const geojson = await response.json();

            if (
                !geojson ||
                !Array.isArray(geojson.features)
            ) {
                throw new Error(
                    "Format GeoJSON invalide."
                );
            }

            if (!governorateLayer) {
                throw new Error(
                    "Couche GeoJSON non initialisée."
                );
            }

            governorateLayer.clearLayers();

            governorateLayer.addData(geojson);

            geojsonLoaded = true;

            const bounds = governorateLayer.getBounds();

            if (bounds.isValid()) {
                map.fitBounds(
                    bounds,
                    {
                        padding: [20, 20]
                    }
                );
            }

            updatePolygonStyles();

            updateMarkerStyles();

            setStatus(
                geojson.features.length +
                " " +
                tr("loaded")
            );

            console.info(
                "[ÉnergiTN] GeoJSON chargé :",
                geojson.features.length,
                "gouvernorats."
            );

            if (geojson.features.length > 0) {
                console.info(
                    "[ÉnergiTN] Exemple de propriétés GeoJSON :",
                    geojson.features[0].properties
                );
            }

        } catch (error) {
            console.error(
                "[ÉnergiTN] Erreur GeoJSON :",
                error
            );

            setStatus(
                tr("geoError") + " : " + error.message
            );
        }
    }


    /* ========================================================
       20. INITIALISATION LEAFLET
    ======================================================== */

    function init(options) {
        options = options || {};

        if (typeof options.onRegionSelect === "function") {
            onRegionSelect = options.onRegionSelect;
        }

        if (
            options.lang === "fr" ||
            options.lang === "ar"
        ) {
            currentLanguage = options.lang;
        }

        const container = getElement(CONFIG.mapId);

        if (!container) {
            console.error(
                "[ÉnergiTN] Élément #map introuvable."
            );
            return;
        }

        if (typeof window.L === "undefined") {
            setStatus(tr("leafletError"));

            console.error(
                "[ÉnergiTN] Leaflet est indisponible."
            );

            return;
        }

        if (initialized && map) {
            map.invalidateSize();
            return;
        }

        map = window.L.map(
            CONFIG.mapId,
            {
                scrollWheelZoom: true,
                zoomControl: true
            }
        ).setView(
            CONFIG.center,
            CONFIG.zoom
        );

        window.L.tileLayer(
            "https://tile.openstreetmap.de/{z}/{x}/{y}.png",
            {
                maxZoom: 19,

                attribution:
                    '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors'
            }
        ).addTo(map);

        governorateLayer = window.L.geoJSON(
            null,
            {
                style: styleGovernorate,
                onEachFeature: onEachGovernorate
            }
        ).addTo(map);

        markerLayer = window.L.layerGroup().addTo(map);

        initialized = true;

        loadGovernorates();

        window.setTimeout(function () {
            if (map) {
                map.invalidateSize();
            }
        }, 300);

        window.addEventListener(
            "resize",
            function () {
                window.clearTimeout(resizeTimer);

                resizeTimer = window.setTimeout(
                    function () {
                        if (map) {
                            map.invalidateSize();
                        }
                    },
                    200
                );
            }
        );
    }


    /* ========================================================
       21. RENDU ET ACTUALISATION
       
       regions :
       [
           {
               r: { id, fr, ar, cap },
               u: 0.85,
               mw: 1020
           }
       ]

       governorates :
       [
           {
               code: "TN-11",
               name_fr: "Tunis",
               name_ar: "تونس",
               usage: 0.85,
               demand_mw: 1020,
               capacity_mw: 1200,
               temperature: 34
           }
       ]
    ======================================================== */

    function render(
        regions,
        selectedId,
        lang,
        governorates
    ) {
        if (Array.isArray(regions)) {
            currentRegions = regions;
        }

        if (selectedId !== undefined) {
            selectedRegion = selectedId;
        }

        if (lang === "fr" || lang === "ar") {
            currentLanguage = lang;
        }

        if (Array.isArray(governorates)) {
            currentGovernorates = governorates;
        }

        if (!map) {
            return;
        }

        updatePolygonStyles();

        updateMarkerStyles();
    }


    /* ========================================================
       22. CHANGEMENT DE LANGUE
    ======================================================== */

    function setLanguage(lang) {
        if (lang !== "fr" && lang !== "ar") {
            return;
        }

        currentLanguage = lang;

        updatePolygonStyles();

        updateMarkerStyles();

        if (map) {
            map.invalidateSize();
        }
    }


    /* ========================================================
       23. SÉLECTION EXTERNE D'UNE RÉGION
    ======================================================== */

    function selectRegion(regionId) {
        selectedRegion = regionId;

        updatePolygonStyles();

        updateMarkerStyles();

        openRegionPopup(regionId);
    }


    /* ========================================================
       24. API PUBLIQUE
    ======================================================== */

    window.TunisiaMap = {
        init: init,

        render: render,

        setLanguage: setLanguage,

        selectRegion: selectRegion,

        getMap: function () {
            return map;
        },

        getSelectedRegion: function () {
            return selectedRegion;
        },

        getGovernorateData: function () {
            return currentGovernorates;
        },

        getRegionData: function () {
            return currentRegions;
        }
    };

})();
