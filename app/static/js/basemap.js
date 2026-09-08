/*
 * basemap.js — Fond de carte SCRIBE, source unique.
 *
 * Ce fichier est charge a l identique par l instance (index.html) et par le
 * collecteur de supervision, qui le sert depuis ce meme chemin. Il n existe
 * donc plus qu une seule declaration de couche de fond dans tout le projet :
 * lorsqu un fournisseur change ses conditions, un seul endroit est a corriger.
 *
 * Le serveur decide quel fond utiliser (voir core/basemap.py). Le navigateur
 * se contente de rendre ce qu on lui indique, et de basculer sur le repli
 * mondial si les tuiles ne repondent pas.
 *
 * Deux modes :
 *   raster  Leaflet natif, aucune dependance supplementaire (defaut)
 *   vector  MapLibre GL charge a la demande, uniquement si demande
 */

(function (global) {
  "use strict";

  var CFG_URL = "/api/v1/config/basemap";

  // Repli code en dur : si meme l appel de configuration echoue, la carte doit
  // s afficher. Sans clef, couverture mondiale.
  var SECOURS = {
    id: "osm",
    label: "OpenStreetMap",
    mode: "raster",
    url: "https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png",
    attribution: "\u00a9 OpenStreetMap contributors",
    maxZoom: 19,
    reason: "configuration serveur injoignable"
  };

  var _promesse = null;

  function config() {
    if (_promesse) return _promesse;
    if (global.SCRIBE_BASEMAP_CFG) {
      _promesse = Promise.resolve(global.SCRIBE_BASEMAP_CFG);
      return _promesse;
    }
    _promesse = fetch(CFG_URL, { credentials: "same-origin" })
      .then(function (r) { return r.ok ? r.json() : SECOURS; })
      .catch(function () { return SECOURS; });
    return _promesse;
  }

  function chargerScript(src) {
    return new Promise(function (ok, ko) {
      var s = document.createElement("script");
      s.src = src;
      s.onload = ok;
      s.onerror = function () { ko(new Error("chargement impossible : " + src)); };
      document.head.appendChild(s);
    });
  }

  function chargerCss(href) {
    var l = document.createElement("link");
    l.rel = "stylesheet";
    l.href = href;
    document.head.appendChild(l);
  }

  // MapLibre n est telecharge que si le mode vectoriel est reellement demande.
  var _maplibre = null;
  function chargerMapLibre() {
    if (_maplibre) return _maplibre;
    chargerCss("https://unpkg.com/maplibre-gl@4.7.1/dist/maplibre-gl.css");
    _maplibre = chargerScript("https://unpkg.com/maplibre-gl@4.7.1/dist/maplibre-gl.js")
      .then(function () {
        return chargerScript("https://unpkg.com/@maplibre/maplibre-gl-leaflet@0.0.22/leaflet-maplibre-gl.js");
      });
    return _maplibre;
  }

  function coucheRaster(cfg) {
    var opts = { attribution: cfg.attribution, maxZoom: cfg.maxZoom || 19 };
    if (cfg.maxNativeZoom) opts.maxNativeZoom = cfg.maxNativeZoom;
    return L.tileLayer(cfg.url, opts);
  }

  function couche(cfg) {
    if (cfg.mode === "vector") {
      return chargerMapLibre().then(function () {
        return L.maplibreGL({ style: cfg.url, attribution: cfg.attribution });
      });
    }
    return Promise.resolve(coucheRaster(cfg));
  }

  /*
   * Surveille les erreurs de tuiles et bascule sur le repli mondial si la
   * source principale ne repond pas.
   *
   * Limite assumee : une degradation silencieuse (HTTP 200 accompagne d un
   * filigrane, comme CARTO en aout 2026) reste indetectable cote client. Seul
   * un fond local garantit contre ce cas.
   */
  function surveiller(map, principale, cfg) {
    if (!cfg.fallback || cfg.id === "osm" || cfg.offline) return;
    var erreurs = 0;
    var bascule = false;
    principale.on("tileerror", function () {
      erreurs += 1;
      if (bascule || erreurs < 6) return;
      bascule = true;
      try {
        map.removeLayer(principale);
        coucheRaster(cfg.fallback).addTo(map);
        if (global.console) {
          console.warn("[basemap] " + cfg.id + " injoignable, repli sur OpenStreetMap");
        }
      } catch (e) { /* la carte reste utilisable sans fond */ }
    });
  }

  /*
   * Point d entree unique.
   *
   *   scribeBasemap.init(map)                    fond seul
   *   scribeBasemap.init(map, {control: true})   + selecteur de couches
   *
   * Retourne une promesse resolue avec la configuration appliquee.
   */
  function init(map, options) {
    options = options || {};
    return config().then(function (cfg) {
      return couche(cfg).then(function (principale) {
        principale.addTo(map);
        surveiller(map, principale, cfg);

        if (options.control) {
          var fonds = {};
          fonds["\u2b1c " + cfg.label] = principale;
          if (cfg.id !== "osm" && cfg.fallback) {
            fonds["\uD83D\uDDFA OpenStreetMap"] = coucheRaster(cfg.fallback);
          }
          if (cfg.satellite) {
            fonds["\uD83D\uDEF0 Satellite"] = coucheRaster(cfg.satellite);
          }
          L.control.layers(fonds, {}, {
            position: options.position || "topright",
            collapsed: options.collapsed === true
          }).addTo(map);
        }
        return cfg;
      });
    }).catch(function (e) {
      // Dernier filet : la carte ne doit jamais rester vide.
      try { coucheRaster(SECOURS).addTo(map); } catch (err) {}
      if (global.console) console.warn("[basemap] repli de secours", e);
      return SECOURS;
    });
  }

  global.scribeBasemap = { init: init, config: config, SECOURS: SECOURS };
})(window);
