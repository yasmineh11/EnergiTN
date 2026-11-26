// Étape 1 — contour de la Tunisie (Natural Earth 1:10m) projeté en Mercator → tn.json
// Usage : npm install world-atlas@2 topojson-client d3-geo   puis   node make.mjs
import fs from "fs";
import {feature} from "topojson-client";
import {geoMercator, geoPath} from "d3-geo";

const topo = JSON.parse(fs.readFileSync("node_modules/world-atlas/countries-10m.json"));
const pays = feature(topo, topo.objects.countries).features;      // TopoJSON → GeoJSON
const tn = pays.find(f => f.id === "788");                         // 788 = code ISO de la Tunisie

const W = 320, H = 440;                                            // taille du dessin (pixels)
const proj = geoMercator().fitExtent([[18, 14], [W - 18, H - 14]], tn);   // la Tunisie remplit le cadre
const path = geoPath(proj).digits(1);                              // contour → chemin SVG (1 décimale)

// villes des 6 régions suivies : [longitude, latitude]
const villes = {biz: [9.87, 37.27], tun: [10.18, 36.80], sou: [10.64, 35.83],
                sfx: [10.76, 34.74], gab: [10.10, 33.88], toz: [8.13, 33.92]};
const pts = Object.fromEntries(Object.entries(villes).map(([k, v]) => [k, proj(v).map(x => +x.toFixed(1))]));

fs.writeFileSync("tn.json", JSON.stringify({W, H, tn: path(tn), pts}));
console.log("tn.json écrit :", path(tn).length, "caractères de contour", pts);
