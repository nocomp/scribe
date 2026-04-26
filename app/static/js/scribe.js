/* SCRIBE — script principal extrait de index.html en v2186a.
 * Concaténation des blocs <script> inline (sans src) précédemment dans index.html.
 * En 2186b on découpera ce fichier par module (core, incidents, cellule, ...). */

// Bandeau MODE EXERCICE — lu depuis config.js
(function() {
  try {
    if (typeof SCRIBE_CONFIG !== 'undefined' && SCRIBE_CONFIG.exercice_mode) {
      var banner = document.getElementById('exo-mode-banner');
      var sigle = document.getElementById('exo-sigle-label');
      if (banner) {
        banner.style.display = 'flex';
        document.body.classList.add('exo-mode');
      }
      if (sigle && SCRIBE_CONFIG.exercice_sigle) {
        sigle.textContent = SCRIBE_CONFIG.exercice_sigle;
      }
    }
  } catch(e) {}
})();
function declareJoueurPret() {
  var btn = document.getElementById('exo-pret-btn');
  var username = (typeof currentUser !== 'undefined' && currentUser) ? currentUser.display_name : 'Joueur';
  var sigle = (typeof SCRIBE_CONFIG !== 'undefined') ? (SCRIBE_CONFIG.exercice_sigle || SCRIBE_CONFIG.etablissement?.sigle || '?') : '?';
  // Pousser vers le collecteur exercice via la fédération
  var fedUrl = '';
  try { fedUrl = SCRIBE_CONFIG.federation?.collecteur_url?.replace('/api/push', '') || ''; } catch(e) {}
  if (!fedUrl) { alert('Collecteur exercice non configuré'); return; }
  var fedTok = '';
  try { fedTok = SCRIBE_CONFIG.federation?.token || ''; } catch(e) {}
  fetch(fedUrl + '/api/exercice/joueur-pret', {
    method: 'POST',
    headers: {'Authorization': 'Bearer ' + fedTok, 'Content-Type': 'application/json'},
    body: JSON.stringify({sigle: sigle, username: username})
  }).then(function(r) {
    if (r.ok) {
      if (btn) { btn.textContent = '✓ PRÊT'; btn.classList.add('ready'); btn.disabled = true; }
    } else {
      alert('Erreur déclaration — réessayez');
    }
  }).catch(function() {
    // Fallback : juste confirmer visuellement
    if (btn) { btn.textContent = '✓ PRÊT'; btn.classList.add('ready'); btn.disabled = true; }
  });
}

/* ════════════════════════════════════════════════════════════ */

// Anti-FOUC : appliquer le thème avant le rendu — clair par défaut
(function(){
  var t = localStorage.getItem('scribe_theme');
  if(t !== 'dark') document.body.classList.add('light');
})();

/* ════════════════════════════════════════════════════════════ */

// Auto-diagnostic JSZip après chargement
window.addEventListener('load', function(){
  setTimeout(function(){
    var el = document.getElementById('az-log-content');
    if(el){
      var msg = window.JSZip
        ? '[AUTO] JSZip ' + (JSZip.version||'?') + ' chargé — uploads ZIP activés'
        : '[AUTO] ERREUR: JSZip non disponible !';
      var color = window.JSZip ? '#4ade80' : '#ef4444';
      var t = new Date().toLocaleTimeString('fr-FR');
      el.innerHTML += '<span style="color:'+color+'">'+t+' '+msg+'</span><br>';
    }
  }, 1500);
});

/* ═══════════════════ SCRIBE Notifications (v2.3.87) ═══════════════════
 * Enregistrement du Service Worker (pour Web Push) + lecteur audio
 * différencié par urgence. Silencieux si pas configuré côté serveur.
 * ════════════════════════════════════════════════════════════════════ */
(function(){
  // 1. Enregistrer le Service Worker si supporté (sans forcer l'abonnement).
  //    L'abonnement Web Push est fait par la page /api/v1/notifications/ui
  //    avec consentement explicite de l'utilisateur.
  if ('serviceWorker' in navigator) {
    navigator.serviceWorker.register('/static/service-worker.js').catch(function(e){
      console.warn('SCRIBE SW register failed:', e);
    });
  }

  // 2. Audio différencié pour notifs in-app (quand onglet SCRIBE ouvert).
  //    Utilise WebAudio API pour générer les sons — pas de fichiers MP3 à
  //    distribuer. Le triangle hospitalier = 2 tons distincts courts.
  var _audioCtx = null;
  function _getAudioCtx() {
    if (_audioCtx) return _audioCtx;
    try { _audioCtx = new (window.AudioContext || window.webkitAudioContext)(); }
    catch(e) { return null; }
    return _audioCtx;
  }

  function _beep(freq, duration, volume) {
    var ctx = _getAudioCtx();
    if (!ctx) return;
    if (ctx.state === 'suspended') ctx.resume().catch(function(){});
    var osc = ctx.createOscillator();
    var gain = ctx.createGain();
    osc.type = 'triangle';  // onde triangulaire (moins agressive que square)
    osc.frequency.value = freq;
    gain.gain.setValueAtTime(0, ctx.currentTime);
    gain.gain.linearRampToValueAtTime(volume || 0.3, ctx.currentTime + 0.01);
    gain.gain.linearRampToValueAtTime(0, ctx.currentTime + duration);
    osc.connect(gain); gain.connect(ctx.destination);
    osc.start();
    osc.stop(ctx.currentTime + duration);
  }

  /**
   * Joue un son en fonction de l'urgence.
   * 1 = info      → silence (pas de son)
   * 2 = vigilance → 1 bip simple (800Hz, 150ms)
   * 3 = alerte    → 2 bips courts (1000Hz, 100ms chacun, pause 80ms)
   * 4 = critique  → triangle hospitalier (880Hz + 1100Hz alternés, 3x)
   */
  window.scribePlayNotifSound = function(urgency) {
    if (!localStorage.getItem('scribe_sound_unlocked')) return;  // pas autorisé
    var volume = parseFloat(localStorage.getItem('scribe_sound_volume') || '0.5');
    urgency = parseInt(urgency, 10) || 2;
    switch (urgency) {
      case 1: return;
      case 2:
        _beep(800, 0.15, volume);
        break;
      case 3:
        _beep(1000, 0.1, volume);
        setTimeout(function(){ _beep(1000, 0.1, volume); }, 180);
        break;
      case 4:
        // Triangle hospitalier : 2 tons alternés répétés 3x
        var seq = [
          [880, 0.12], [1100, 0.12],
          [880, 0.12], [1100, 0.12],
          [880, 0.18], [1100, 0.18],
        ];
        var t = 0;
        seq.forEach(function(p){
          setTimeout(function(){ _beep(p[0], p[1], volume); }, t);
          t += p[1] * 1000 + 30;
        });
        break;
    }
  };

  // 3. Raccourci pour déverrouiller l'audio au 1er clic utilisateur
  //    (contrainte navigateur : autoplay interdit sans interaction).
  document.addEventListener('click', function unlock() {
    if (localStorage.getItem('scribe_sound_unlocked')) {
      document.removeEventListener('click', unlock); return;
    }
    var ctx = _getAudioCtx();
    if (ctx && ctx.state === 'suspended') ctx.resume().catch(function(){});
    localStorage.setItem('scribe_sound_unlocked', '1');
    document.removeEventListener('click', unlock);
  }, {once: false});

  // 4. Écoute des messages depuis le SW (optionnel, pour sync UI en direct)
  if ('serviceWorker' in navigator) {
    navigator.serviceWorker.addEventListener('message', function(ev) {
      if (ev.data && ev.data.type === 'scribe-notif') {
        window.scribePlayNotifSound(ev.data.urgency || 2);
        // v2.3.90 — Rafraîchir l'UI pour voir le nouvel incident/message
        // immédiatement (sinon il faut attendre le cycle refreshAll).
        try { if (typeof refreshAll === 'function') refreshAll(); } catch(e) {}
      }
    });
  }
})();

/* ════════════════════════════════════════════════════════════ */

/* ═══════════════════ SCRIBE v4 ════════════════════════ */

let map, markers = {};
let allIncidents = [], allDecisions = [];
let incAttachments = {};  // cache PJ par incident id
let selectedUrgency = 1, selectedCrise = "CYBER";
let jalonsList = [];
let annuaireMode = 'normal';

const URG_LABELS = {1:'VEILLE',2:'ALERTE',3:'CRISE',4:'CRITIQUE'};
const STATUSES   = ['SIGNALÉ','ANALYSE','RÉSOLUTION','RÉSOLU'];

// ── ANNUAIRE DATA ─────────────────────────────────────
// ════════════════════════════════════════════════════════
//  i18n — Internationalisation
//  Charge les traductions depuis /api/v1/i18n/{langue}
//  La langue est définie dans config.js (clé "langue")
// ════════════════════════════════════════════════════════
let LANG = {};
let LANG_CODE = 'fr';

async function loadI18n() {
  // v2307 — Priorité à la langue définie globalement dans l'instance via
  // l'admin (endpoint /api/v1/i18n/current). Fallback sur SCRIBE_CONFIG.langue
  // (fichier config.js statique généré au setup) puis 'fr'.
  let code = 'fr';
  try {
    const cur = await fetch('/api/v1/i18n/current').then(r => r.json()).catch(() => null);
    if (cur && cur.code) code = cur.code;
    else if (typeof SCRIBE_CONFIG !== 'undefined' && SCRIBE_CONFIG.langue) code = SCRIBE_CONFIG.langue;
  } catch(e) {
    if (typeof SCRIBE_CONFIG !== 'undefined' && SCRIBE_CONFIG.langue) code = SCRIBE_CONFIG.langue;
  }
  LANG_CODE = code;
  try {
    const r = await apiFetch(`/api/v1/i18n/${code}`);
    if (r.ok) {
      LANG = await r.json();
      // Mettre à jour l'attribut lang du document
      document.documentElement.setAttribute('lang', code);
      // Appliquer les traductions aux éléments statiques
      applyI18nDOM();
    }
  } catch(e) {
    console.warn('i18n: impossible de charger la langue', code, e);
  }
}

// t(key) — récupère une traduction par chemin "section.cle"
// ex: t('nav.veille') → 'VEILLE' ou 'WATCH'
function t(path, fallback) {
  const parts = path.split('.');
  let val = LANG;
  for (const p of parts) {
    if (!val || typeof val !== 'object') return fallback || path;
    val = val[p];
  }
  return (val !== undefined && val !== null) ? String(val) : (fallback || path);
}

// Appliquer les traductions aux éléments avec data-i18n="section.cle"
function applyI18nDOM() {
  document.querySelectorAll('[data-i18n]').forEach(el => {
    const key = el.getAttribute('data-i18n');
    const translated = t(key);
    if (translated && translated !== key) {
      if (el.tagName === 'INPUT' || el.tagName === 'TEXTAREA') {
        if (el.hasAttribute('placeholder')) el.placeholder = translated;
      } else {
        el.textContent = translated;
      }
    }
  });
  document.querySelectorAll('[data-i18n-placeholder]').forEach(el => {
    const key = el.getAttribute('data-i18n-placeholder');
    const translated = t(key);
    if (translated && translated !== key) el.placeholder = translated;
  });
  // v2307-hotfix — data-i18n-label : remplace uniquement le premier text
  // node de l'élément, préserve les enfants (utile pour boutons avec
  // <span> badge ou icônes). Permet de traduire la navigation principale
  // sans écraser les compteurs de badges.
  document.querySelectorAll('[data-i18n-label]').forEach(el => {
    const key = el.getAttribute('data-i18n-label');
    const translated = t(key);
    if (!translated || translated === key) return;
    // Remplacer le premier nœud texte (souvent "📋 INCIDENTS" ou "🏥 SOINS")
    const icon = el.getAttribute('data-i18n-icon') || '';
    const newText = icon ? `${icon} ${translated}` : translated;
    // Trouver le premier text node et le remplacer
    let done = false;
    for (const n of el.childNodes) {
      if (n.nodeType === Node.TEXT_NODE) {
        n.nodeValue = newText;
        done = true;
        break;
      }
    }
    // Si pas de text node trouvé, insérer en premier enfant
    if (!done) el.insertBefore(document.createTextNode(newText), el.firstChild);
  });
}

// ════════════════════════════════════════════════════════

// Téléphonie nominale (interne 4 chiffres)
// Annuaires chargés depuis config.js (généré par setup.py)
const ANNUAIRE_NORMAL  = (typeof SCRIBE_CONFIG !== 'undefined') ? SCRIBE_CONFIG.annuaire_normal  : [];
const ANNUAIRE_SECOURS = (typeof SCRIBE_CONFIG !== 'undefined') ? SCRIBE_CONFIG.annuaire_secours : [];

// ── INIT ─────────────────────────────────────────────
document.addEventListener('DOMContentLoaded', async () => {
  startClock();
  await loadI18n();
  applyScribeConfig();
  // initMap/loadSites/refreshAll sont appelés APRÈS login (voir window.load + doLogin)
});

// ── CONFIG DYNAMIQUE (depuis config.js généré par setup.py) ──────────
function applyScribeConfig() {
  if (typeof SCRIBE_CONFIG === 'undefined') return;

  // Titre de la page et brand
  const etab = SCRIBE_CONFIG.etablissement || {};
  if (etab.nom) {
    document.title = `SCRIBE | ${etab.nom}`;
    const sigleEl = document.getElementById('etab-sigle');
    if (sigleEl && etab.sigle) sigleEl.textContent = etab.sigle;
    // Mire de login : nom configurable
    const sub = document.getElementById('login-subtitle');
    if (sub) {
      const tagline = SCRIBE_CONFIG.login_tagline || (etab.nom.toUpperCase() + ' — CRISIS OS');
      sub.textContent = tagline;
    }
  }

  // Badge fournisseur IA — chargé après login pour éviter 401 au démarrage
  // (voir loadIaBadge() appelée depuis window.load après restauration session)

  // Peupler le select des directeurs (formulaire déclaration)
  const selDir = document.getElementById('directeur_crise');
  if (selDir && SCRIBE_CONFIG.directeurs && SCRIBE_CONFIG.directeurs.length) {
    SCRIBE_CONFIG.directeurs.forEach(d => {
      const opt = document.createElement('option');
      opt.value = d.nom;
      opt.textContent = `${d.nom} (${d.abreviation})`;
      selDir.appendChild(opt);
    });
  }

  // Peupler le filtre directeur (barre de filtres)
  const selFDir = document.getElementById('f-directeur');
  if (selFDir && SCRIBE_CONFIG.directeurs && SCRIBE_CONFIG.directeurs.length) {
    SCRIBE_CONFIG.directeurs.forEach(d => {
      const opt = document.createElement('option');
      opt.value = d.nom;
      opt.textContent = `${d.nom.split(' ').pop()} (${d.abreviation})`;
      selFDir.appendChild(opt);
    });
  }
}

function startClock() {
  setInterval(() => document.getElementById('clock').textContent = new Date().toLocaleTimeString('fr-FR'), 1000);
}

// ── NAV ──────────────────────────────────────────────
function openPluginTab(pluginId, tabId, btn) {
  localStorage.setItem('scribe_last_tab', tabId);
  localStorage.setItem('scribe_last_plugin', pluginId);
  // Ouvre un onglet de plugin dynamique
  document.querySelectorAll('.tab-content').forEach(t => t.classList.remove('active'));
  document.querySelectorAll('.tab-btn').forEach(b => b.classList.remove('active'));
  const tab = document.getElementById(tabId);
  if (tab) tab.classList.add('active');
  if (btn) btn.classList.add('active');
  // v2312-hotfix — Marquer les items plugin comme "vus" pour résorber le badge.
  if (pluginId === 'brancardage') {
    (async () => {
      try {
        const r = await apiFetch('/api/v1/brancardage/missions', { headers: authHeaders() });
        if (r.ok) {
          const missions = await r.json();
          const viewedKey = 'scribe_brancardage_viewed_ids';
          const viewed = new Set(JSON.parse(localStorage.getItem(viewedKey) || '[]'));
          (missions || []).forEach(m => viewed.add(m.id));
          // Garder max 500 entrées
          const arr = [...viewed].slice(-500);
          localStorage.setItem(viewedKey, JSON.stringify(arr));
          const b = document.getElementById('plugin-badge-brancardage');
          if (b) b.style.display = 'none';
        }
      } catch(e) {}
    })();
  }
}

function openTab(id, btn) {
  localStorage.setItem('scribe_last_tab', id);
  document.querySelectorAll('.tab-content').forEach(t => t.classList.remove('active'));
  document.querySelectorAll('.tab-btn').forEach(b => b.classList.remove('active'));
  document.getElementById(id).classList.add('active');
  btn.classList.add('active');
  if (id === 'tab-dashboard') { loadDashboard(); return; }
  if (id === 'tab-veille') {
    setTimeout(() => {
      if (!map) return;
      map.invalidateSize();
      const lls = Object.values(markers).map(m => m.getLatLng());
      if (lls.length > 1) { try { map.fitBounds(L.latLngBounds(lls).pad(0.15)); } catch(e){} }
    }, 250);
  }
  if (id === 'tab-transferts') loadTransferts();
  if (id === 'tab-rex')       populateRexIncidentSelect();
  if (id === 'tab-soins') {
    loadServiceStatuses().then(renderTransverses);
    renderSoins();
    setTimeout(() => renderSoinsTimeline(allIncidents), 50);
    setTimeout(() => { if (mapSoins) mapSoins.invalidateSize(); renderSoinsTrList(); }, 200);
  }
  if (id === 'tab-cellule')   {
    loadPresences(); loadDecisions();
    // v2307 — Marquer les décisions de la journée comme "vues" pour
    // résorber le badge CELLULE.
    try {
      const viewedKey = 'scribe_cellule_viewed_ids';
      const viewed = new Set(JSON.parse(localStorage.getItem(viewedKey) || '[]'));
      const today = new Date(); today.setHours(0,0,0,0);
      (allDecisions || []).forEach(d => {
        if (d && d.timestamp) {
          const dt = new Date(d.timestamp);
          if (dt >= today) viewed.add(d.id);
        }
      });
      localStorage.setItem(viewedKey, JSON.stringify([...viewed]));
      // Masquer le badge immédiatement
      const badge = document.getElementById('cellule-badge');
      if (badge) badge.style.display = 'none';
    } catch(e) {}
  }
  if (id === 'tab-releve')    loadConsignes();
  if (id === 'tab-annuaire')  renderAnnuaire();
}

// ── CARTE ────────────────────────────────────────────
// Attributions cartographiques conformes (v2.0.1) :
//   - OpenStreetMap : © OpenStreetMap contributors, ODbL
//     https://www.openstreetmap.org/copyright
//   - CartoDB : © OpenStreetMap contributors, © CARTO
//     https://carto.com/attributions
//   - Esri World Imagery : Tiles © Esri
//     https://www.esri.com/en-us/legal/terms/data-attributions
let mapSoins = null;
function initMap() {
  map = L.map('map', {zoomControl:true}).setView([45.9, 6.1], 10);
  const _osmLayer = L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png',
    {attribution:'&copy; <a href="https://www.openstreetmap.org/copyright" target="_blank" rel="noopener">OpenStreetMap</a> contributors', maxZoom:19});
  const _cartoLight = L.tileLayer('https://{s}.basemaps.cartocdn.com/light_all/{z}/{x}/{y}{r}.png',
    {attribution:'&copy; <a href="https://www.openstreetmap.org/copyright" target="_blank" rel="noopener">OpenStreetMap</a> contributors &copy; <a href="https://carto.com/attributions" target="_blank" rel="noopener">CARTO</a>', maxZoom:19});
  const _satellite = L.tileLayer('https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}',
    {attribution:'Tiles &copy; <a href="https://www.esri.com/" target="_blank" rel="noopener">Esri</a> &mdash; Source: Esri, Maxar, Earthstar Geographics, and the GIS User Community', maxZoom:19});
  const _baseLayers = {'⬜ Clair': _cartoLight, '🗺 OSM': _osmLayer, '🛰 Satellite': _satellite};
  _cartoLight.addTo(map);
  L.control.layers(_baseLayers, {}, {position:'topright', collapsed:false}).addTo(map);
  // Resize observer : invalide la carte quand le conteneur change de taille
  if (window.ResizeObserver) {
    new ResizeObserver(() => { if (map) map.invalidateSize(); }).observe(document.getElementById('map'));
  }
  // Carte soins — initialisée séparément, synchronisée avec la carte principale
  const mapSoinsEl = document.getElementById('map-soins');
  if (mapSoinsEl) {
    mapSoins = L.map('map-soins', {zoomControl:true}).setView([45.9, 6.1], 10);
    L.tileLayer('https://{s}.basemaps.cartocdn.com/light_all/{z}/{x}/{y}{r}.png',
      {attribution:'&copy; <a href="https://www.openstreetmap.org/copyright" target="_blank" rel="noopener">OpenStreetMap</a> contributors &copy; <a href="https://carto.com/attributions" target="_blank" rel="noopener">CARTO</a>', maxZoom:19}).addTo(mapSoins);
    // Synchroniser zoom/center avec la carte principale
    map.on('moveend zoomend', () => {
      if (mapSoins) mapSoins.setView(map.getCenter(), map.getZoom(), {animate:false});
    });
    if (window.ResizeObserver) {
      new ResizeObserver(() => { if (mapSoins) mapSoins.invalidateSize(); }).observe(mapSoinsEl);
    }
    // Afficher les marqueurs de sites sur la carte soins
    setTimeout(() => renderSoinsMapMarkers(), 500);
  }
}

let _appInitDone = false;
// ── NAV DYNAMIQUE selon plugins actifs ──────────────────────────────────────
// Mapping plugin_id → id du bouton d'onglet dans la barre de nav
const PLUGIN_TAB_MAP = {
  'cellule':    'tab-btn-cellule',
  'releve':     'tab-btn-releve',
  'rex':        'tab-btn-rex',
  'annuaire':   'tab-btn-annuaire',
  'capacite':   'tab-btn-capacite',
  'communique': 'tab-btn-communique',
  'transferts': 'tab-btn-soins',
  'messagerie': 'tab-btn-messagerie',
  'inter_ght':  'tab-btn-declarations',
  'albert':     'tab-btn-analyse',
};

// ── TABLEAU DE BORD DÉCISIONNEL ────────────────────────────────────────────
let _dbInterval = null;

async function loadDashboard() {
  await Promise.all([
    loadDBIncidents(), loadDBCapacite(), loadDBTransferts(),
    loadDBMessages(), loadDBG7(), loadDBTasks(), loadDBMsgs()
  ]);
  const el = document.getElementById('db-lastupdate');
  if (el) el.textContent = new Date().toLocaleTimeString('fr-FR', {hour:'2-digit',minute:'2-digit'});
}

async function loadDBIncidents() {
  try {
    const r = await apiFetch('/api/v1/sitrep/history');
    if (!r.ok) return;
    const data = await r.json();
    const actifs = (data||[]).filter(i => !i.resolved && !i.resolu);
    const n3 = actifs.filter(i => (i.urgence||i.urgency||0) >= 3).length;
    const el = document.getElementById('db-incidents');
    const sub = document.getElementById('db-incidents-sub');
    if (el) { el.textContent = actifs.length; el.style.color = actifs.length > 0 ? 'var(--red)' : 'var(--text)'; }
    if (sub) sub.textContent = n3 > 0 ? n3 + ' critique(s)' : actifs.length ? 'Aucun critique' : 'Aucun incident';
    // Main courante
    const mc = document.getElementById('db-mc');
    if (mc) {
      const recent = [...data].sort((a,b)=>new Date(b.created_at||0)-new Date(a.created_at||0)).slice(0,5);
      mc.innerHTML = recent.length ? recent.map(i => {
        const dt = i.created_at ? parseUTC(i.created_at).toLocaleTimeString('fr-FR',{hour:'2-digit',minute:'2-digit'}) : '—';
        const cols = ['','#22c55e','#fbbf24','#f97316','#ef4444'];
        const col = cols[Math.min((i.urgence||i.urgency||1), 4)];
        const label = (i.fait || i.fact || i.type_crise || i.crisis_type || 'Incident').substring(0,55);
        return `<div style="display:flex;gap:7px;align-items:flex-start">
          <span style="font-family:var(--mono);font-size:9px;color:var(--muted);flex-shrink:0;padding-top:1px">${dt}</span>
          <span style="width:3px;border-radius:2px;background:${col};flex-shrink:0;align-self:stretch;min-height:14px"></span>
          <span style="font-family:var(--mono);font-size:10px;color:var(--text);line-height:1.4">${label}</span>
        </div>`;
      }).join('')
      : '<div style="font-family:var(--mono);font-size:10px;color:var(--muted)">Aucun incident déclaré</div>';
    }
  } catch(e) {}
}

async function loadDBCapacite() {
  try {
    const r = await apiFetch('/api/v1/capacite/synthese');
    if (!r.ok) return;
    const data = await r.json();
    // Format retourné : {site: {pole: {lits_total, lits_vides_h/f/i, statut_pole}}}
    let total = 0, vides = 0;
    const polesFlat = [];
    Object.entries(data).forEach(([site, poles]) => {
      Object.entries(poles).forEach(([pole, d]) => {
        const t = d.lits_total || 0;
        const v = (d.lits_vides_h||0)+(d.lits_vides_f||0)+(d.lits_vides_i||0);
        total += t; vides += v;
        polesFlat.push({nom:pole, site, total:t, vides:v, statut:d.statut_pole||'inconnu'});
      });
    });
    const occ = total - vides;
    const pct = total > 0 ? Math.round(occ/total*100) : 0;
    const col = pct >= 90 ? 'var(--red)' : pct >= 75 ? '#d97706' : '#22c55e';
    const el  = document.getElementById('db-capacite');
    const sub = document.getElementById('db-capacite-sub');
    if (el)  { el.textContent = total>0 ? pct+'%' : '—'; el.style.color = total>0?col:'var(--text)'; }
    if (sub) { sub.textContent = total>0 ? occ+' / '+total+' lits occupés' : 'Aucune donnée'; }
    const polesEl = document.getElementById('db-poles');
    if (polesEl) {
      if (!polesFlat.length) { polesEl.innerHTML='<div style="font-family:var(--mono);font-size:10px;color:var(--muted)">Aucune donnée de capacité</div>'; return; }
      const colStat = {critique:'#ef4444',tension:'#f59e0b',normal:'#22c55e',ferme:'#6b7280',inconnu:'#94a3b8'};
      polesEl.innerHTML = polesFlat.slice(0,7).map(p => {
        const pp = p.total > 0 ? Math.round((p.total-p.vides)/p.total*100) : 0;
        const pc = colStat[p.statut]||'#94a3b8';
        return `<div style="display:flex;align-items:center;gap:8px;margin-bottom:4px">
          <span style="font-family:var(--mono);font-size:9px;color:var(--muted);width:130px;flex-shrink:0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap">${p.nom}</span>
          <div style="flex:1;height:11px;background:var(--surface2);border-radius:2px;overflow:hidden">
            <div style="width:${pp}%;height:11px;background:${pc};border-radius:2px"></div>
          </div>
          <span style="font-family:var(--mono);font-size:9px;color:${pc};width:30px;text-align:right">${pp}%</span>
        </div>`;
      }).join('');
    }
  } catch(e) {
    const el=document.getElementById('db-capacite'); if(el) el.textContent='—';
    const p=document.getElementById('db-poles'); if(p) p.innerHTML='<div style="font-family:var(--mono);font-size:10px;color:var(--muted)">Module capacité non disponible</div>';
  }
}
async function loadDBTransferts() {
  try {
    const r = await apiFetch('/api/v1/transferts');
    if (!r.ok) return;
    const data = await r.json();
    const en_cours = (data||[]).filter(t => t.statut === 'EN_COURS');
    const el  = document.getElementById('db-transferts');
    const sub = document.getElementById('db-transferts-sub');
    if (el) { el.textContent = en_cours.length; el.style.color = en_cours.length ? '#c084fc' : 'var(--text)'; }
    if (sub) {
      const dests = [...new Set(en_cours.map(t => t.etablissement_destination).filter(Boolean))];
      sub.textContent = dests.length ? '→ ' + dests.slice(0,3).join(', ') : 'Aucun transfert en cours';
    }
  } catch(e) {}
}

async function loadDBMessages() {
  try {
    const r = await apiFetch('/api/v1/messagerie/non-lus');
    if (!r.ok) return;
    const data = await r.json();
    const el  = document.getElementById('db-messages');
    const sub = document.getElementById('db-messages-sub');
    if (el) { el.textContent = data.count || 0; el.style.color = (data.count||0) > 0 ? '#22c55e' : 'var(--text)'; }
    if (sub) sub.textContent = (data.count||0) > 0 ? 'À lire' : 'Aucun message';
  } catch(e) {}
}

async function loadDBG7() {
  const el = document.getElementById('db-g7');
  if (!el) return;
  try {
    const r = await apiFetch('/api/v1/federation/status');
    if (!r.ok || !(await r.clone().json()).collecteur_url) {
      el.innerHTML = '<div style="font-family:var(--mono);font-size:10px;color:var(--muted)">Fédération non configurée</div>';
      return;
    }
    const fed = await r.json();
    const collBase = fed.collecteur_url.replace('/api/push','');
    const rs = await fetch(collBase+'/api/summary', {headers:{'Authorization':'Bearer '+(fed.token||'')}});
    if (!rs.ok) { el.innerHTML='<div style="font-family:var(--mono);font-size:10px;color:var(--muted)">Collecteur indisponible</div>'; return; }
    const sites = await rs.json();
    const colMap = {CRITIQUE:'#ef4444',CRISE:'#f97316',ALERTE:'#f59e0b',NOMINAL:'#22c55e',INCONNU:'#6b7280'};
    el.innerHTML = sites.map(s => {
      const col = colMap[s.niveau_global]||'#6b7280';
      const label = s.niveau_global||'INCONNU';
      const bg = {CRITIQUE:'rgba(239,68,68,.1)',CRISE:'rgba(249,115,22,.1)',ALERTE:'rgba(245,158,11,.1)',NOMINAL:'rgba(34,197,94,.1)'}[s.niveau_global]||'var(--surface2)';
      return `<div style="display:flex;align-items:center;justify-content:space-between;padding:4px 0;border-bottom:1px solid var(--border)">
        <span style="font-family:var(--mono);font-size:10px;font-weight:700;color:var(--text)">${s.sigle||s.nom||'—'}</span>
        <span style="font-family:var(--mono);font-size:8px;padding:2px 7px;border-radius:4px;background:${bg};color:${col}">${label}</span>
      </div>`;
    }).join('');
  } catch(e) { el.innerHTML='<div style="font-family:var(--mono);font-size:10px;color:var(--muted)">—</div>'; }
}

async function loadDBTasks() {
  const el = document.getElementById('db-tasks');
  if (!el) return;
  try {
    const r = await apiFetch('/api/v1/tasks/');
    if (!r.ok) return;
    const data = await r.json();
    const pending = (data||[]).filter(t => t.statut !== 'DONE' && t.col !== 'done').slice(0,5);
    el.innerHTML = pending.length ? pending.map(t => {
      const cols = {4:'#ef4444',3:'#f97316',2:'#fbbf24',1:'#22c55e'};
      const col = cols[t.priorite]||'var(--muted)';
      const label = (t.title||t.titre||t.contenu||'Tâche').substring(0,50);
      return `<div style="display:flex;align-items:flex-start;gap:7px">
        <span style="width:8px;height:8px;border-radius:50%;background:${col};flex-shrink:0;margin-top:2px"></span>
        <span style="font-family:var(--mono);font-size:10px;color:var(--text);line-height:1.4">${label}</span>
      </div>`;
    }).join('')
    : '<div style="font-family:var(--mono);font-size:10px;color:#22c55e">Aucune tâche en attente</div>';
  } catch(e) {}
}

async function loadDBMsgs() {
  const el = document.getElementById('db-msgs');
  if (!el) return;
  try {
    const r = await apiFetch('/api/v1/messagerie?boite=reception');
    if (!r.ok) return;
    const data = await r.json();
    const recent = (data||[]).filter(m => !m.lu).slice(0,4);
    el.innerHTML = recent.length ? recent.map(m => {
      const dt = m.created_at ? parseUTC(m.created_at).toLocaleTimeString('fr-FR',{hour:'2-digit',minute:'2-digit'}) : '—';
      return `<div style="padding:5px 8px;background:var(--surface2);border-radius:4px;border-left:2px solid #003189">
        <div style="display:flex;justify-content:space-between;margin-bottom:2px">
          <span style="font-family:var(--mono);font-size:9px;font-weight:700;color:var(--text)">${m.expediteur_nom||'—'}</span>
          <span style="font-family:var(--mono);font-size:9px;color:var(--muted)">${dt}</span>
        </div>
        <div style="font-family:var(--mono);font-size:9px;color:var(--muted);overflow:hidden;text-overflow:ellipsis;white-space:nowrap">${(m.sujet||'(sans objet)').substring(0,45)}</div>
      </div>`;
    }).join('')
    : '<div style="font-family:var(--mono);font-size:10px;color:var(--muted)">Aucun message non lu</div>';
  } catch(e) {}
}


async function applyPluginNav() {
  try {
    const r = await apiFetch('/api/v1/plugins/active');
    if (!r.ok) return;
    const activePlugins = await r.json();
    const activeIds = new Set(activePlugins.map(p => p.id));

    // 1. Masquer les onglets statiques des plugins inactifs
    Object.entries(PLUGIN_TAB_MAP).forEach(([pluginId, btnId]) => {
      const btn = document.getElementById(btnId);
      if (!btn) return;
      btn.style.display = activeIds.has(pluginId) ? '' : 'none';
    });

    // 2. Créer dynamiquement les onglets des plugins uploadés (non statiques)
    const nav = document.getElementById('main-nav');
    const appContent = document.getElementById('app-content');
    if (!nav || !appContent) return;

    activePlugins.forEach(p => {
      if (!p.has_tab || !p.tab_id) return;
      // Skip si ce plugin a déjà un bouton statique (dans PLUGIN_TAB_MAP)
      if (p.id in PLUGIN_TAB_MAP) return;
      // Skip si un bouton dynamique existe déjà
      if (document.getElementById('tab-btn-' + p.id)) return;

      // Créer le bouton de nav
      const btn = document.createElement('button');
      btn.className = 'tab-btn';
      btn.id = 'tab-btn-' + p.id;
      // v2312-hotfix — Injecter un span badge inline pour les plugins qui
      // en ont besoin (brancardage notamment). Tous les plugins ont leur
      // span vide ; seuls les plugins listés plus bas sont rafraîchis
      // activement via refreshAll.
      const _badgeHtml = '<span id="plugin-badge-' + p.id + '" style="display:none;background:#f97316;color:#fff;font-size:9px;padding:1px 5px;border-radius:10px;margin-left:4px;font-weight:700"></span>';
      btn.innerHTML = (p.icon || '📦') + ' ' + (p.label || p.id.toUpperCase()) + _badgeHtml;
      btn.onclick = function() { openPluginTab(p.id, p.tab_id, btn); };
      // Insérer avant le bouton INTER-GHT (fin de nav)
      const interGht = document.getElementById('tab-btn-declarations');
      if (interGht) nav.insertBefore(btn, interGht);
      else nav.appendChild(btn);

      // Créer le conteneur d'onglet si absent
      if (!document.getElementById(p.tab_id)) {
        const tabDiv = document.createElement('div');
        tabDiv.id = p.tab_id;
        tabDiv.className = 'tab-content';
        tabDiv.style.cssText = 'flex-direction:column;padding:0;overflow:hidden';
        // Charger l'interface du plugin (fetch + inject HTML, pas d'iframe → pas de CSP)
        if (p.api_prefix) {
          const uiUrl = p.api_prefix + '/ui';
          const tok = localStorage.getItem('scribe_token') || '';
          // Charger le plugin dans une iframe isolée — résout tous les problèmes de scope JS et CSP
          tabDiv.style.cssText = 'flex-direction:column;overflow:hidden;padding:0;flex:1;min-height:0';
          tabDiv.innerHTML = '';
          const iframe = document.createElement('iframe');
          iframe.style.cssText = 'width:100%;height:100%;border:none;flex:1;display:block;min-height:0';
          iframe.src = uiUrl + '?token=' + encodeURIComponent(tok);
          tabDiv.appendChild(iframe);
        } else {
          tabDiv.innerHTML = '<div style="padding:40px;text-align:center;font-family:var(--mono);font-size:10px;color:var(--muted)">' + (p.icon||'📦') + ' ' + (p.label||p.id) + '</div>';
        }
        appContent.appendChild(tabDiv);
      }
    });
  } catch(e) {
    // Silencieux
  }

  // Écouter les messages de l'iframe chat (badge notification)
  if (!window._chatMsgListenerSet) {
    window._chatMsgListenerSet = true;
    window.addEventListener('message', function(ev) {
      if (!ev.data || ev.data.type !== 'scribe-chat-new-msg') return;
      // Trouver le bouton nav du plugin chat
      var chatBtn = document.getElementById('tab-btn-chat') ||
                    document.getElementById('dyn-tab-btn-chat');
      if (!chatBtn) {
        // Chercher parmi tous les boutons dynamiques
        document.querySelectorAll('[id^="dyn-tab-btn-"]').forEach(function(b) {
          if (b.textContent.toLowerCase().includes('chat')) chatBtn = b;
        });
      }
      if (chatBtn) {
        var badge = chatBtn.querySelector('.chat-notif-badge');
        if (!badge) {
          badge = document.createElement('span');
          badge.className = 'chat-notif-badge';
          badge.style.cssText = 'display:inline-block;min-width:16px;height:16px;' +
            'background:#e1000f;color:#fff;border-radius:8px;font-size:9px;' +
            'font-weight:700;line-height:16px;text-align:center;padding:0 4px;' +
            'margin-left:5px;vertical-align:middle;';
          badge.textContent = '';
          chatBtn.appendChild(badge);
        }
        var count = parseInt(badge.dataset.count || '0') + 1;
        badge.dataset.count = count;
        badge.textContent = count > 9 ? '9+' : count;
        badge.style.display = 'inline-block';
      }
    });
    // Effacer le badge quand on ouvre le chat
    document.addEventListener('click', function(ev) {
      var btn = ev.target.closest && ev.target.closest('[id*="chat"]');
      if (btn) {
        var badge = btn.querySelector('.chat-notif-badge');
        if (badge) { badge.dataset.count = '0'; badge.style.display = 'none'; }
      }
    });
  }
}

async function initAfterLogin() {
  if (_appInitDone) return;
  _appInitDone = true;
  // Afficher l'interface d'abord
  const hdr = document.getElementById('main-header');
  const nav = document.getElementById('main-nav');
  const app = document.getElementById('app-content');
  if (hdr) hdr.style.display = '';
  if (nav) nav.style.display = '';
  if (app) { app.style.display='flex'; app.style.flex='1'; app.style.flexDirection='column'; app.style.overflow='hidden'; app.style.minHeight='0'; }
  // Laisser le DOM se rendre avant initMap
  await new Promise(r => setTimeout(r, 50));
  initMap();
  await loadSites();
  await loadUfToPole();
  await refreshAll();
  // Mode exercice : poll plus rapide pour que l'indicateur niveau global
  // réagisse vite aux stimuli injectés (3s au lieu de 12s en mode normal).
  var _refreshMs = 12000;
  try {
    if (typeof SCRIBE_CONFIG !== 'undefined' && SCRIBE_CONFIG.exercice_mode) {
      _refreshMs = 3000;
    }
  } catch(e) {}
  setInterval(refreshAll, _refreshMs);
  renderAnnuaire();
  loadIaBadge();
  await applyPluginNav();
  // Dashboard : charger les données et lancer le rafraîchissement
  loadDashboard();
  if (_dbInterval) clearInterval(_dbInterval);
  _dbInterval = setInterval(() => {
    if (document.getElementById('tab-dashboard')?.classList.contains('active')) loadDashboard();
  }, 30000);

  await loadTransfertsEntrants();
  // Forcer recalcul taille carte après affichage
  setTimeout(() => { if (map) map.invalidateSize(); }, 300);
}

function parseUTC(s) {
  // Les dates du serveur sont en UTC sans 'Z' — corriger
  if (!s) return null;
  if (s.includes('Z') || s.includes('+')) return new Date(s);
  return new Date(s.includes('T') ? s + 'Z' : s.replace(' ', 'T') + 'Z');
}

function markerColor(n) {
  return !n ? '#4ade80' : n<=2 ? '#fbbf24' : n<=5 ? '#f87171' : '#c084fc';
}

// v2183 — Couleur de la pastille de site sur la carte, basée sur la pire
// urgence constatée OU la présence d'un incident à impact fonctionnel.
// Remplace markerColor(count) qui ne regardait que le nombre et laissait
// un site en vert alors qu'une panne urgence 2 impact_fn=true tournait.
function markerColorForSite(incidentsOfSite) {
  if (!incidentsOfSite || !incidentsOfSite.length) return '#4ade80';  // vert nominal
  const maxUrg = Math.max(...incidentsOfSite.map(i => i.urgency || 0));
  const hasOps = incidentsOfSite.some(i => i.type_crise === 'CYBER' || i.impact_fonctionnel === true);
  // Règle : si urgency >= 3 ou CRITIQUE → rouge/violet
  //         si urgency === 2 ou (impact_fn && urgency >= 1) → orange
  //         sinon jaune (incident mineur uniquement clinique)
  if (maxUrg >= 4) return '#c084fc';   // violet CRITIQUE
  if (maxUrg >= 3) return '#f87171';   // rouge CRISE
  if (maxUrg >= 2 || hasOps)  return '#f59e0b';   // orange ALERTE ou panne opé
  return '#fbbf24';                    // jaune VEILLE
}

// ── LAYER AMBULANCES (toggle + OSRM) ─────────────────────────────────────────
// ── CARTE SOINS — markers sites et transferts ────────────────────────────────
let _soinsMarkers = [];
let _soinsTransferts = [];

async function renderSoinsMapMarkers() {
  if (!mapSoins) return;
  // Nettoyer
  _soinsMarkers.forEach(m => m.remove()); _soinsMarkers = [];
  _soinsTransferts.forEach(m => m.remove()); _soinsTransferts = [];

  // v2196 — Agréger sites locaux + sites de tous les établissements G7
  // (via collecteur-sites et /api/summary du collecteur fédéré). Avant,
  // seuls les sites locaux étaient affichés → 1 seul point bleu par
  // instance exercice (chaque instance n'a qu'1-2 sites seedés).
  // Maintenant on voit TOUS les établissements participants + leurs sites.
  const allPoints = [];
  const seen = new Set(); // évite doublons par nom|lat|lng

  function _addPoint(nom, lat, lng, couleur, etabSigle) {
    if (!nom || lat == null || lng == null) return;
    const key = `${nom}|${(+lat).toFixed(4)}|${(+lng).toFixed(4)}`;
    if (seen.has(key)) return;
    seen.add(key);
    allPoints.push({nom, lat: +lat, lng: +lng, couleur: couleur || '#3b82f6', etab: etabSigle || ''});
  }

  // 1. Sites locaux (allSites)
  const mySigle = (SCRIBE_CONFIG?.etablissement?.sigle) || '';
  (allSites || []).forEach(s => _addPoint(s.nom, s.latitude, s.longitude, '#3b82f6', mySigle));

  // 2. Sites de tous les GHT connus du collecteur local (via federation/collecteur-sites)
  try {
    const rcs = await apiFetch('/api/v1/federation/collecteur-sites').catch(() => null);
    if (rcs && rcs.ok) {
      const cs = await rcs.json();
      cs.forEach(s => {
        const isLocal = (s.sigle || '').toUpperCase() === mySigle.toUpperCase();
        _addPoint(s.nom, s.lat, s.lng, isLocal ? '#3b82f6' : '#8b5cf6', s.sigle);
      });
    }
  } catch(e) {}

  // 3. Fallback via /api/summary du collecteur distant (cas fédération G7 active)
  try {
    if (_fedStatus?.ready && _fedStatus?.collecteur_url) {
      const collBase = _fedStatus.collecteur_url.replace('/api/push', '');
      // v2200 — Ajouter le token fédération. Sans ça, le collecteur renvoyait
      // 401 et polluait la console joueur ("GET /api/summary 401").
      // Si pas de token, on skip silencieusement (pas de fédération active).
      const fedTok = _fedStatus.token || '';
      if (!fedTok) throw new Error('no-fed-token');
      const r = await fetch(collBase + '/api/summary', {
        headers: {'Authorization': 'Bearer ' + fedTok},
        signal: AbortSignal.timeout(3000)
      });
      if (r.ok) {
        const summary = await r.json();
        summary.forEach(etab => {
          const sig = (etab.sigle || '').toUpperCase();
          const isLocal = sig === mySigle.toUpperCase();
          const couleur = isLocal ? '#3b82f6' : '#8b5cf6';
          (etab.sites || []).forEach(s => _addPoint(s.nom, s.latitude, s.longitude, couleur, sig));
          // Marqueur établissement lui-même (si coords) — utile si pas de sites
          if (etab.latitude && etab.longitude && !(etab.sites || []).length) {
            _addPoint(etab.sigle || etab.nom, etab.latitude, etab.longitude, couleur, sig);
          }
        });
      }
    }
  } catch(e) {}

  // Rendu
  allPoints.forEach(p => {
    const icon = L.divIcon({className:'',
      html:`<div style="width:12px;height:12px;border-radius:50%;background:${p.couleur};border:2px solid #fff;box-shadow:0 0 6px ${p.couleur}"></div>`,
      iconSize:[12,12],iconAnchor:[6,6]});
    const label = p.etab ? `<b>${p.nom}</b><br><span style="font-family:monospace;font-size:9px;opacity:.7">${p.etab}</span>` : `<b>${p.nom}</b>`;
    const m = L.marker([p.lat, p.lng], {icon})
      .bindTooltip(label, {sticky:true}).addTo(mapSoins);
    _soinsMarkers.push(m);
  });

  // Zoom auto sur tous les marqueurs
  if (_soinsMarkers.length && mapSoins) {
    try {
      const lls = _soinsMarkers.map(m => m.getLatLng());
      if (lls.length > 1) mapSoins.fitBounds(L.latLngBounds(lls).pad(0.3));
      else mapSoins.setView(lls[0], 11);
    } catch(e) {}
  }
  // Afficher les transferts EN_COURS avec trajectoire OSRM
  await renderSoinsTransferts();
  // Rafraîchir toutes les 30s
  setTimeout(renderSoinsMapMarkers, 30000);
}

async function renderSoinsTransferts() {
  if (!mapSoins) return;
  _soinsTransferts.forEach(m => m.remove()); _soinsTransferts = [];

  const enCours = [...trData, ...trIncoming].filter(t => t.statut === 'EN_COURS' && t.eta);
  if (!enCours.length) return;

  // Index GPS — clé = nom site (minuscule) ou sigle établissement (minuscule)
  const gpsIdx = {};
  const monSigleLocal = (SCRIBE_CONFIG?.etablissement?.sigle || '').toLowerCase();
  const coordsLocaux = [];
  allSites.forEach(s => {
    if (s.latitude && s.longitude) {
      gpsIdx[s.nom.toLowerCase()] = [+s.latitude, +s.longitude];
      coordsLocaux.push([+s.latitude, +s.longitude]);
    }
  });
  // Indexer aussi le sigle local → centroïde des sites locaux
  if (monSigleLocal && coordsLocaux.length) {
    const clat = coordsLocaux.reduce((a,c)=>a+c[0],0)/coordsLocaux.length;
    const clng = coordsLocaux.reduce((a,c)=>a+c[1],0)/coordsLocaux.length;
    gpsIdx[monSigleLocal] = [clat, clng];
  }

  // Source 1 : collecteur-sites (API locale, toujours dispo, contient lat/lng par site exact)
  try {
    const rcs = await apiFetch('/api/v1/federation/collecteur-sites').catch(()=>null);
    if (rcs && rcs.ok) {
      const cs = await rcs.json();
      const sigleCoords = {};
      cs.forEach(s => {
        if (s.lat && s.lng) {
          gpsIdx[s.nom.toLowerCase()] = [+s.lat, +s.lng];
          if (!sigleCoords[s.sigle]) sigleCoords[s.sigle] = [];
          sigleCoords[s.sigle].push([+s.lat, +s.lng]);
        }
      });
      Object.entries(sigleCoords).forEach(([sigle, coords]) => {
        const clat = coords.reduce((a,c)=>a+c[0],0)/coords.length;
        const clng = coords.reduce((a,c)=>a+c[1],0)/coords.length;
        gpsIdx[sigle.toLowerCase()] = [clat, clng];
      });
    }
  } catch(e) {}

  // Source 2 : /api/summary collecteur distant (complément)
  try {
    if (_fedStatus?.ready && _fedStatus?.collecteur_url) {
      const collBase = _fedStatus.collecteur_url.replace('/api/push','');
      const r = await fetch(collBase + '/api/summary', {signal: AbortSignal.timeout(3000)});
      if (r.ok) {
        const summary = await r.json();
        summary.forEach(etab => {
          const sigle = (etab.sigle||'').toLowerCase();
          const sitesCoords = [];
          (etab.sites||[]).forEach(s => {
            if (s.latitude && s.longitude) {
              gpsIdx[s.nom.toLowerCase()] = [+s.latitude, +s.longitude];
              sitesCoords.push([+s.latitude, +s.longitude]);
            }
          });
          if (sigle && sitesCoords.length && !gpsIdx[sigle]) {
            const clat = sitesCoords.reduce((a,c)=>a+c[0],0)/sitesCoords.length;
            const clng = sitesCoords.reduce((a,c)=>a+c[1],0)/sitesCoords.length;
            gpsIdx[sigle] = [clat, clng];
          }
          if (etab.latitude && etab.longitude && sigle) gpsIdx[sigle] = [+etab.latitude, +etab.longitude];
        });
      }
    }
  } catch(e) {}

  // findCoords : 1) exact, 2) sigle partiel (min 5 chars, évite faux positifs courts)
  const findCoords = n => {
    if (!n) return null;
    const k = n.toLowerCase().trim();
    if (gpsIdx[k]) return gpsIdx[k];
    // Cherche un sigle qui est contenu dans k (ex: "ghtlmb" dans "ghtlmb — site")
    const exactSigle = Object.entries(gpsIdx).find(([key]) =>
      key.length >= 5 && k === key
    );
    if (exactSigle) return exactSigle[1];
    // Fuzzy uniquement si la clé est longue et suffisamment discriminante
    const fuzzy = Object.entries(gpsIdx).find(([key]) =>
      key.length >= 6 && k.length >= 6 && (k.startsWith(key.substring(0,6)) || key.startsWith(k.substring(0,6)))
    );
    return fuzzy ? fuzzy[1] : null;
  };

  const ambIcon = L.divIcon({className:'',
    html:'<div style="font-size:22px;text-shadow:0 0 6px rgba(249,115,22,.9)">🚑</div>',
    iconSize:[24,24],iconAnchor:[12,12]});
  const depIcon = L.divIcon({className:'',
    html:'<div style="width:8px;height:8px;border-radius:50%;background:#60a5fa;border:2px solid #fff"></div>',
    iconSize:[8,8],iconAnchor:[4,4]});
  const arrIcon = L.divIcon({className:'',
    html:'<div style="width:8px;height:8px;border-radius:50%;background:#4ade80;border:2px solid #fff"></div>',
    iconSize:[8,8],iconAnchor:[4,4]});

  // v2204 — Offset léger si plusieurs transferts sur le même couloir O→D,
  // pour que les ambulances et les lignes ne se superposent pas exactement.
  // Auparavant : 2 transferts A→B sur carte affichent un seul marqueur visible.
  const _couloirCount = {};
  for (const t of enCours) {
    const key = (t.etablissement_origine||'')+'>'+(t.etablissement_destination||'');
    _couloirCount[key] = (_couloirCount[key]||0) + 1;
  }
  const _couloirIdx = {}; // compteur courant par couloir
  for (const t of enCours) {
    const orig = findCoords(t.site_origine || t.etablissement_origine);
    const dest = findCoords(t.site_destination || t.etablissement_destination);
    if (!orig || !dest) continue;

    const key = (t.etablissement_origine||'')+'>'+(t.etablissement_destination||'');
    const idxCouloir = (_couloirIdx[key] = (_couloirIdx[key]||0));
    _couloirIdx[key]++;
    // Offset perpendiculaire à la direction : 0 pour le 1er, +/-0.002° pour les suivants
    const totalOnRoute = _couloirCount[key];
    let offLat = 0, offLng = 0;
    if (totalOnRoute > 1) {
      // Direction O→D
      const dx = dest[1]-orig[1], dy = dest[0]-orig[0];
      const norm = Math.sqrt(dx*dx+dy*dy) || 1;
      // Normale perpendiculaire
      const perpLat = dx/norm, perpLng = -dy/norm;
      const spread = 0.003; // ~300m
      // index 0 = centre, 1 = +spread, 2 = -spread, 3 = +2*spread, etc.
      const slot = idxCouloir === 0 ? 0 : (idxCouloir%2===1 ? Math.ceil(idxCouloir/2) : -Math.ceil(idxCouloir/2));
      offLat = perpLat*spread*slot;
      offLng = perpLng*spread*slot;
    }

    const etaStr = (parseUTC(t.eta)||new Date(0)).toLocaleTimeString('fr-FR',{hour:'2-digit',minute:'2-digit'});
    const now = Date.now();
    const depStr = t.horodatage_depart || t.created_at;
    const dep = depStr ? (parseUTC(depStr)||{}).getTime()||null : null;
    const etaMs = t.eta ? (parseUTC(t.eta)||{}).getTime()||0 : 0;
    // Calculer la progression réelle
    let progress = 0.01; // départ par défaut
    if (dep && etaMs > dep && etaMs > now) {
      const totalDur = etaMs - dep;
      const elapsed = now - dep;
      progress = Math.max(0.01, Math.min(0.97, elapsed / totalDur));
    }

    // Obtenir la trajectoire via OSRM
    let coords = null;
    let dureeMin = null;
    try {
      const osrm = await fetch(
        `https://router.project-osrm.org/route/v1/driving/${orig[1]},${orig[0]};${dest[1]},${dest[0]}?overview=full&geometries=geojson`,
        {signal: AbortSignal.timeout(5000)}
      );
      if (osrm.ok) {
        const d = await osrm.json();
        const route = d.routes?.[0];
        if (route) {
          coords = route.geometry.coordinates.map(([lng,lat]) => [lat,lng]);
          dureeMin = Math.round(route.duration / 60);
        }
      }
    } catch(e) {}

    // Données patient : affichées uniquement sur la carte locale (RGPD — pas transmises au collecteur)
    const patientLine = t.nom ? `<br>👤 ${t.nom} ${t.prenom||''}${t.ipp ? ' · IPP ' + t.ipp : ''}` : '';
    const tooltip = `🚑 <b>${t.etablissement_origine} → ${t.etablissement_destination}</b><br>` +
      `${t.unite_origine||''} → ${t.unite_destination||''}<br>` +
      `⏱ ETA : ${etaStr}` +
      (dureeMin ? `<br>🗺 Trajet : ~${dureeMin} min` : '') +
      patientLine +
      (t.commentaire ? `<br>📋 ${t.commentaire}` : '');

    if (coords && coords.length >= 2) {
      // v2204 — Appliquer offset à tous les points si plusieurs transferts
      const coordsOffset = totalOnRoute > 1
        ? coords.map(c => [c[0]+offLat, c[1]+offLng])
        : coords;
      const line = L.polyline(coordsOffset, {color:'#f97316',weight:3,opacity:.8,dashArray:'8 5'}).addTo(mapSoins);
      line.bindTooltip(tooltip, {sticky:true});
      _soinsTransferts.push(line);
      // Position ambulance selon progression
      const idx = Math.floor(progress * (coordsOffset.length-1));
      const amb = L.marker(coordsOffset[idx], {icon:ambIcon}).addTo(mapSoins);
      amb.bindTooltip(tooltip, {sticky:true});
      _soinsTransferts.push(amb);
    } else {
      const origO = [orig[0]+offLat, orig[1]+offLng];
      const destO = [dest[0]+offLat, dest[1]+offLng];
      const line = L.polyline([origO,destO], {color:'#f97316',weight:2,opacity:.5,dashArray:'6 6'}).addTo(mapSoins);
      _soinsTransferts.push(line);
    }
    // Marqueurs départ/arrivée
    const d = L.marker(orig, {icon:depIcon}).bindTooltip(`🔵 Départ : ${t.etablissement_origine}`).addTo(mapSoins);
    const a = L.marker(dest, {icon:arrIcon}).bindTooltip(`🟢 Arrivée : ${t.etablissement_destination}`).addTo(mapSoins);
    _soinsTransferts.push(d, a);
  }
}

let _ambulanceLayerOn = false;
let _ambulanceMarkers = [];
let _ambulanceLines   = [];
let _ambulanceTimer   = null;

function toggleAmbulanceLayer() {
  _ambulanceLayerOn = !_ambulanceLayerOn;
  const btn = document.getElementById('btn-ambulance-layer');
  if (btn) {
    btn.style.background  = _ambulanceLayerOn ? 'rgba(251,191,36,.15)' : 'transparent';
    btn.style.borderColor = _ambulanceLayerOn ? '#fbbf24' : 'var(--border2)';
    btn.style.color       = _ambulanceLayerOn ? '#fbbf24' : 'var(--muted)';
  }
  if (_ambulanceLayerOn) { renderAmbulanceLayer(); _ambulanceTimer = setInterval(renderAmbulanceLayer, 15000); }
  else { clearInterval(_ambulanceTimer); _ambulanceTimer = null; _clearAmbulanceLayer(); }
}

function _clearAmbulanceLayer() {
  _ambulanceMarkers.forEach(m => map && m.remove());
  _ambulanceLines.forEach(l => map && l.remove());
  _ambulanceMarkers = []; _ambulanceLines = [];
}

// ── LISTE TRANSFERTS dans le panneau SOINS ───────────────────────────────────
function renderSoinsTrList() {
  const list = document.getElementById('soins-tr-list');
  const count = document.getElementById('soins-tr-count');
  if (!list) return;
  const actifs = [...trData.filter(t => ['EN_COURS','EN_PREPARATION'].includes(t.statut)),
                  ...trIncoming];
  if (count) count.textContent = actifs.length ? `${actifs.length} transfert${actifs.length>1?'s':''}` : '';
  if (!actifs.length) {
    list.innerHTML = '<div style="font-family:var(--mono);font-size:9px;color:var(--muted);padding:8px;text-align:center">Aucun transfert actif</div>';
    return;
  }
  list.innerHTML = actifs.map(t => {
    const isIn = !t.nom; // transfert entrant = pas de données patient
    const col = {EN_PREPARATION:'#fbbf24',EN_COURS:'#60a5fa',ARRIVE:'#4ade80',ANNULE:'#6b7280'}[t.statut] || '#6b7280';
    const etaStr = t.eta ? (parseUTC(t.eta)||new Date(0)).toLocaleTimeString('fr-FR',{hour:'2-digit',minute:'2-digit'}) : null;
    const diffMs = t.eta ? (parseUTC(t.eta) - new Date()) : null;
    const diffMin = diffMs ? Math.round(diffMs/60000) : null;
    return `<div style="padding:7px 8px;border-bottom:1px solid var(--border);border-left:3px solid ${col}">
      <div style="font-family:var(--mono);font-size:9px;font-weight:700;color:var(--text)">${isIn?'📡 ':''} ${t.etablissement_origine||'?'} → ${t.site_destination||t.etablissement_destination||'?'}</div>
      <div style="font-family:var(--mono);font-size:8px;color:var(--muted);margin-top:2px">${t.unite_origine||''} → ${t.unite_destination||''}</div>
      ${etaStr ? `<div style="font-family:var(--mono);font-size:8px;color:${diffMs&&diffMs>0?'#fbbf24':'#f87171'};margin-top:2px">⏱ ETA ${etaStr}${diffMin!==null?(diffMs>0?' — dans '+diffMin+' min':' — en retard'):''}</div>` : ''}
      <div style="font-family:var(--mono);font-size:7px;color:var(--muted2);margin-top:2px">${t.statut.replace('_',' ')}</div>
    </div>`;
  }).join('');
}

async function renderAmbulanceLayer() {
  if (!map || !_ambulanceLayerOn) return;
  _clearAmbulanceLayer();
  const now30 = Date.now() - 30 * 60000;
  const enCours = [...trData, ...trIncoming].filter(t => {
    if (t.statut !== 'EN_COURS') return false;
    if (t.eta) { const etaMs = (parseUTC(t.eta)||new Date(0)).getTime(); if (etaMs < now30) return false; }
    return true;
  });
  if (!enCours.length) return;

  // Index GPS : sites locaux
  const gpsIdx = {};
  const _monSigleLocal = (SCRIBE_CONFIG?.etablissement?.sigle || '').toLowerCase();
  const _coordsLocaux = [];
  allSites.forEach(s => {
    if (s.latitude && s.longitude) {
      gpsIdx[s.nom.toLowerCase()] = [s.latitude, s.longitude];
      _coordsLocaux.push([+s.latitude, +s.longitude]);
    }
  });
  // Sigle local → centroïde des sites locaux (pour transferts entrants vers soi)
  if (_monSigleLocal && _coordsLocaux.length) {
    const _clat = _coordsLocaux.reduce((a,c)=>a+c[0],0)/_coordsLocaux.length;
    const _clng = _coordsLocaux.reduce((a,c)=>a+c[1],0)/_coordsLocaux.length;
    gpsIdx[_monSigleLocal] = [_clat, _clng];
  }

  // Source 1 : collecteur-sites (API locale, toujours dispo, lat/lng par site exact)
  try {
    const rcs = await apiFetch('/api/v1/federation/collecteur-sites').catch(()=>null);
    if (rcs && rcs.ok) {
      const cs = await rcs.json();
      const sigleCoords = {};
      cs.forEach(s => {
        if (s.lat && s.lng) {
          gpsIdx[s.nom.toLowerCase()] = [+s.lat, +s.lng];
          if (!sigleCoords[s.sigle]) sigleCoords[s.sigle] = [];
          sigleCoords[s.sigle].push([+s.lat, +s.lng]);
        }
      });
      Object.entries(sigleCoords).forEach(([sigle, coords]) => {
        const clat = coords.reduce((a,c)=>a+c[0],0)/coords.length;
        const clng = coords.reduce((a,c)=>a+c[1],0)/coords.length;
        gpsIdx[sigle.toLowerCase()] = [clat, clng];
      });
    }
  } catch(e) {}

  // Source 2 : /api/summary collecteur distant (complément)
  try {
    if (_fedStatus?.ready && _fedStatus?.collecteur_url) {
      const collBase = _fedStatus.collecteur_url.replace('/api/push','');
      const r = await fetch(collBase + '/api/summary', {signal: AbortSignal.timeout(3000)});
      if (r.ok) {
        const summary = await r.json();
        summary.forEach(etab => {
          const sigle = (etab.sigle||'').toLowerCase();
          const sitesCoords = [];
          (etab.sites||[]).forEach(s => {
            if (s.latitude && s.longitude) {
              gpsIdx[s.nom.toLowerCase()] = [+s.latitude, +s.longitude];
              sitesCoords.push([+s.latitude, +s.longitude]);
            }
          });
          if (sigle && sitesCoords.length && !gpsIdx[sigle]) {
            const clat = sitesCoords.reduce((a,c)=>a+c[0],0)/sitesCoords.length;
            const clng = sitesCoords.reduce((a,c)=>a+c[1],0)/sitesCoords.length;
            gpsIdx[sigle] = [clat, clng];
          }
          if (etab.latitude && etab.longitude && sigle) gpsIdx[sigle] = [+etab.latitude, +etab.longitude];
        });
      }
    }
  } catch(e) {}

  // findCoords : exact d'abord, fuzzy sur 6 chars seulement
  const findCoords = n => {
    if (!n) return null;
    const k = n.toLowerCase().trim();
    if (gpsIdx[k]) return gpsIdx[k];
    const fuzzy = Object.entries(gpsIdx).find(([key]) =>
      key.length >= 6 && k.length >= 6 && (k.startsWith(key.substring(0,6)) || key.startsWith(k.substring(0,6)))
    );
    return fuzzy ? fuzzy[1] : null;
  };
  const depIcon = L.divIcon({className:'',html:'<div style="width:10px;height:10px;border-radius:50%;background:#60a5fa;border:2px solid #fff;box-shadow:0 0 4px #60a5fa"></div>',iconSize:[10,10],iconAnchor:[5,5]});
  const arrIcon = L.divIcon({className:'',html:'<div style="width:10px;height:10px;border-radius:50%;background:#4ade80;border:2px solid #fff;box-shadow:0 0 4px #4ade80"></div>',iconSize:[10,10],iconAnchor:[5,5]});
  const ambIcon = L.divIcon({className:'',html:'<div style="position:relative"><div style="position:absolute;width:40px;height:40px;border-radius:50%;background:rgba(249,115,22,.25);animation:pulse 1.5s infinite;top:-20px;left:-20px"></div><div style="font-size:28px;line-height:1;position:relative;text-shadow:0 0 8px rgba(249,115,22,.9)">🚑</div></div>',iconSize:[32,32],iconAnchor:[16,16]});
  for (const t of enCours) {
    const orig=findCoords(t.site_origine||t.etablissement_origine); const dest=findCoords(t.site_destination||t.etablissement_destination);
    if (!orig||!dest) continue;
    let coords=null;
    try {
      const r=await fetch(`https://router.project-osrm.org/route/v1/driving/${orig[1]},${orig[0]};${dest[1]},${dest[0]}?overview=full&geometries=geojson`,{signal:AbortSignal.timeout(4000)});
      if(r.ok){const d=await r.json();coords=d.routes?.[0]?.geometry?.coordinates?.map(([lng,lat])=>[lat,lng]);}
    } catch(e) {}
    let progress=0.01;
    const _depStr=t.horodatage_depart||t.created_at;
    if(_depStr&&t.eta){
      const _dep=(parseUTC(_depStr)||{}).getTime()||0,_eta=(parseUTC(t.eta)||{}).getTime()||0;
      if(_eta>_dep&&_eta>_now) progress=Math.max(0.01,Math.min(0.97,(_now-_dep)/(_eta-_dep)));
    }
    const etaStr=t.eta?(parseUTC(t.eta)||new Date(0)).toLocaleTimeString('fr-FR',{hour:'2-digit',minute:'2-digit'}):'—';
    const tel = t.commentaire ? `<br>📞 ${t.commentaire}` : '';
    const patLine = t.nom ? `<br>👤 ${t.nom} ${t.prenom||''}${t.ipp ? ' · IPP ' + t.ipp : ''}` : '';
    const tip=`🚑 ${t.etablissement_origine||''}→${t.etablissement_destination||''}<br>${t.unite_origine||''}→${t.unite_destination||''}<br>⏱ ETA : ${etaStr}${patLine}${tel}`;
    if (coords&&coords.length>=2) {
      const line=L.polyline(coords,{color:'#f97316',weight:3,opacity:.75,dashArray:'8 6'}).addTo(map);
      line.bindTooltip(tip,{sticky:true}); _ambulanceLines.push(line);
      const idx=Math.floor(progress*(coords.length-1));
      const amb=L.marker(coords[idx],{icon:ambIcon}).addTo(map); amb.bindTooltip(tip,{sticky:true}); _ambulanceMarkers.push(amb);
    } else {
      const line=L.polyline([orig,dest],{color:'#f97316',weight:2,opacity:.5,dashArray:'6 8'}).addTo(map); line.bindTooltip(tip,{sticky:true}); _ambulanceLines.push(line);
    }
    _ambulanceMarkers.push(L.marker(orig,{icon:depIcon}).bindTooltip(`🔵 Départ : ${t.etablissement_origine}`).addTo(map));
    _ambulanceMarkers.push(L.marker(dest,{icon:arrIcon}).bindTooltip(`🟢 Arrivée : ${t.etablissement_destination}`).addTo(map));
  }
}


function updateMap(bySite) {
  // v2183 — on ne se base plus sur le seul count. Pour chaque site on
  // regarde les incidents actifs correspondants dans allIncidents et on
  // calcule la couleur en fonction de la pire urgence + présence d'impact
  // fonctionnel, cohérent avec le bandeau global et le panneau SOINS.
  const sm = Object.fromEntries(bySite.map(s=>[s.site,s.count]));
  const incsBySite = {};
  (allIncidents || []).forEach(i => {
    if (i.status === 'RÉSOLU' || i.status === 'ARCHIVÉ') return;
    const key = i.site_id;
    if (!incsBySite[key]) incsBySite[key] = [];
    incsBySite[key].push(i);
  });
  Object.entries(markers).forEach(([nom,m]) => {
    const c = sm[nom]||0;
    const incsSite = incsBySite[nom] || [];
    const col = markerColorForSite(incsSite);
    // Badge opérationnel si panne infra
    const hasOps = incsSite.some(i => i.type_crise === 'CYBER' || i.impact_fonctionnel === true);
    const ring = hasOps ? ';box-shadow:0 0 0 3px rgba(239,68,68,.35),0 0 8px '+col : ';box-shadow:0 0 8px '+col;
    m.setIcon(L.divIcon({className:'',
      html:`<div style="width:13px;height:13px;border-radius:50%;background:${col};border:2px solid rgba(255,255,255,.3)${ring}"></div>`,
      iconSize:[13,13],iconAnchor:[6,6]}));
    const opsTxt = hasOps ? '<br><b style="color:#ef4444">⚙ Impact opérationnel</b>' : '';
    m.setPopupContent(`<b>${nom}</b><br>${c} incident(s) ouvert(s)${opsTxt}`);
  });
}

let allSites = [];  // stockage global des sites

async function loadSites() {
  try {
    const sites = await (await apiFetch('/api/v1/cartographie/sites')).json();
    allSites = sites;  // stocker globalement
    ['site_id','f-site'].forEach(id => {
      const sel = document.getElementById(id);
      if(sel) sites.forEach(s => sel.add(new Option(s.nom, s.nom)));
    });
    const latlngs = [];
    sites.forEach(s => {
      const m = L.marker([s.latitude,s.longitude]).addTo(map).bindPopup(`<b>${s.nom}</b>`);
      markers[s.nom] = m;
      if (s.latitude && s.longitude) latlngs.push([s.latitude, s.longitude]);
    });
    if (latlngs.length > 1) {
      map.fitBounds(L.latLngBounds(latlngs).pad(0.15));
    } else if (latlngs.length === 1) {
      map.setView(latlngs[0], 13);
    }
  } catch(e) {}
}

let allUFList = []; // [{code_uf, libelle, pole}]
let ufDropdownIdx = -1;

async function loadUF() {
  const site = document.getElementById('site_id').value;
  allUFList = [];
  clearUF();
  if (!site) return;
  try {
    const units = await (await apiFetch(`/api/v1/cartographie/${encodeURIComponent(site)}/units`)).json();
    allUFList = units;
  } catch(e) {}
}

// ── Multi-UF : liste des UF sélectionnées ──
let _ufSelected = []; // [{code, libelle}]

function _ufRenderTags() {
  const container = document.getElementById('uf-tags');
  if (!container) return;
  container.innerHTML = _ufSelected.map((u, i) =>
    `<span style="display:inline-flex;align-items:center;gap:4px;background:var(--blue-dim);border:1px solid rgba(37,99,235,.4);border-radius:4px;padding:2px 7px;font-family:var(--mono);font-size:9px;color:#60a5fa">
      ${u.code} — ${u.libelle}
      <span onclick="_ufRemove(${i})" style="cursor:pointer;color:var(--muted);font-size:11px;line-height:1;margin-left:2px">✕</span>
    </span>`
  ).join('');
  document.getElementById('unite_fonctionnelle').value = _ufSelected.map(u => u.code).join(', ');
}

function _ufRemove(idx) {
  _ufSelected.splice(idx, 1);
  _ufRenderTags();
}

function ufAddCurrent() {
  const hidden = document.getElementById('unite_fonctionnelle');
  const search = document.getElementById('uf_search');
  const code = hidden.dataset.pendingCode;
  const libelle = hidden.dataset.pendingLibelle;
  if (!code) { toast('Sélectionner une UF dans la liste', 'warn'); return; }
  if (_ufSelected.find(u => u.code === code)) { search.value=''; return; }
  _ufSelected.push({code, libelle: libelle || code});
  _ufRenderTags();
  search.value = '';
  delete hidden.dataset.pendingCode;
  delete hidden.dataset.pendingLibelle;
  document.getElementById('uf-dropdown').style.display = 'none';
}

function filterUFList() {
  const q = document.getElementById('uf_search').value.trim().toLowerCase();
  showUFDropdown(q);
}

function showUFDropdown(q = '') {
  const dd = document.getElementById('uf-dropdown');
  if (!allUFList.length) { dd.style.display='none'; return; }
  const filtered = q
    ? allUFList.filter(u =>
        u.code_uf.toLowerCase().startsWith(q) ||
        u.libelle.toLowerCase().includes(q)
      ).slice(0, 40)
    : allUFList.slice(0, 40);

  if (!filtered.length) { dd.style.display='none'; return; }
  ufDropdownIdx = -1;
  dd.innerHTML = filtered.map((u,i) =>
    `<div class="uf-dd-item" data-code="${u.code_uf}" data-idx="${i}"
      onmousedown="selectUF('${u.code_uf}','${u.libelle.replace(/'/g,"\\'")}')">
      <span style="font-family:var(--mono);font-size:11px;font-weight:700;color:#60a5fa;min-width:42px;display:inline-block">${u.code_uf}</span>
      <span style="font-size:11px;color:var(--text)">${u.libelle}</span>
    </div>`
  ).join('');
  dd.style.display = 'block';
}

function selectUF(code, libelle) {
  document.getElementById('uf_search').value = `${code} — ${libelle}`;
  // Stocker en pending pour ajout par le bouton +
  const hidden = document.getElementById('unite_fonctionnelle');
  hidden.dataset.pendingCode = code;
  hidden.dataset.pendingLibelle = libelle;
  document.getElementById('uf-dropdown').style.display = 'none';
}

function clearUF() {
  document.getElementById('uf_search').value = '';
  const hidden = document.getElementById('unite_fonctionnelle');
  hidden.value = '';
  delete hidden.dataset.pendingCode;
  delete hidden.dataset.pendingLibelle;
  document.getElementById('uf-dropdown').style.display = 'none';
  _ufSelected = [];
  _ufRenderTags();
}

function ufKeyNav(e) {
  const dd = document.getElementById('uf-dropdown');
  const items = dd.querySelectorAll('.uf-dd-item');
  if (!items.length) return;
  if (e.key === 'ArrowDown') {
    ufDropdownIdx = Math.min(ufDropdownIdx+1, items.length-1);
    items.forEach((el,i) => el.style.background = i===ufDropdownIdx ? 'var(--surface3)':'');
    e.preventDefault();
  } else if (e.key === 'ArrowUp') {
    ufDropdownIdx = Math.max(ufDropdownIdx-1, 0);
    items.forEach((el,i) => el.style.background = i===ufDropdownIdx ? 'var(--surface3)':'');
    e.preventDefault();
  } else if (e.key === 'Enter' && ufDropdownIdx >= 0) {
    const item = items[ufDropdownIdx];
    selectUF(item.dataset.code, item.textContent.trim().split('—').slice(1).join('—').trim());
    e.preventDefault();
  } else if (e.key === 'Tab' && ufDropdownIdx >= 0) {
    // Tab = sélectionner + ajouter directement
    const item = items[ufDropdownIdx];
    selectUF(item.dataset.code, item.textContent.trim().split('—').slice(1).join('—').trim());
    ufAddCurrent();
    e.preventDefault();
  } else if (e.key === 'Escape') {
    dd.style.display = 'none';
  }
}

// Fermer dropdown si clic ailleurs
document.addEventListener('click', e => {
  if (!e.target.closest('#uf_search') && !e.target.closest('#uf-dropdown'))
    document.getElementById('uf-dropdown').style.display = 'none';
});


// ── REFRESH ──────────────────────────────────────────
async function refreshAll() {
  try {
    const [incidents, stats, decisions] = await Promise.all([
      apiFetch('/api/v1/sitrep/history').then(r=>r.json()),
      apiFetch('/api/v1/sitrep/stats').then(r=>r.json()),
      apiFetch('/api/v1/cellule/decisions').then(r=>r.json()).catch(()=>[]),
    ]);
    allIncidents = incidents;
    allDecisions = decisions;
    // v2196 — Mise à jour badge compteur à côté du menu INCIDENTS
    // (compte les incidents non résolus, comme le badge transferts).
    try {
      const ouverts = (incidents || []).filter(i =>
        i && i.status !== 'RÉSOLU' && i.status !== 'ARCHIVÉ'
      ).length;
      const badge = document.getElementById('incidents-badge');
      if (badge) {
        badge.textContent = ouverts;
        badge.style.display = ouverts ? 'inline' : 'none';
      }
    } catch(e) {}

    // v2307 — Badge CELLULE : nombre de décisions prises aujourd'hui et
    // non encore "vues" par l'utilisateur (stockage localStorage des ids
    // vus — on considère qu'une décision est "vue" dès que l'onglet
    // CELLULE a été ouvert). Permet de signaler discrètement qu'une
    // décision a été prise par un autre membre de la cellule sans
    // polluer l'inbox.
    try {
      const badge = document.getElementById('cellule-badge');
      if (badge) {
        const viewedKey = 'scribe_cellule_viewed_ids';
        const viewed = new Set(JSON.parse(localStorage.getItem(viewedKey) || '[]'));
        const today = new Date();
        today.setHours(0,0,0,0);
        const recent = (decisions || []).filter(d => {
          if (!d || !d.timestamp) return false;
          const dt = new Date(d.timestamp);
          return dt >= today && !viewed.has(d.id);
        });
        const n = recent.length;
        badge.textContent = n;
        badge.style.display = n ? 'inline' : 'none';
      }
    } catch(e) {}

    // v2309-hotfix — Badge COMMUNIQUÉ désactivé temporairement. La route
    // /api/v1/communique/actif n'est pas implémentée dans cette version
    // du plugin et le 404 polluait la console navigateur en permanence
    // (pas masquable côté JS — Chrome log les 4xx peu importe le handling).
    // Le badge sera réactivé quand le plugin exposera une route d'état.
    // En attendant : badge toujours masqué, aucun call réseau.
    try {
      const badge = document.getElementById('communique-badge');
      if (badge) badge.style.display = 'none';
    } catch(e) {}

    // v2311 — Badge CAPACITÉ : nombre d'unités avec une déclaration
    // "tension" ou "critique" non encore vues par l'utilisateur.
    // Logique alignée sur CELLULE (localStorage des IDs vus).
    // Permet de signaler qu'un service a basculé (typiquement suite à
    // un stimulus capacité d'exercice), sans que l'utilisateur ait
    // besoin de regarder l'onglet en permanence.
    // v2312-hotfix : diagnostic console si échec + détection élargie via
    // les champs booléens alerte_lits/rh/materiel.
    try {
      const r = await apiFetch('/api/v1/capacite/referentiel', {
        headers: authHeaders()
      });
      if (r.ok) {
        const unites = await r.json();
        const badge = document.getElementById('capacite-badge');
        if (badge && Array.isArray(unites)) {
          const viewedKey = 'scribe_capacite_viewed_ids';
          const viewed = new Set(JSON.parse(localStorage.getItem(viewedKey) || '[]'));
          // Unité "en alerte" :
          //   1. Statut texte dégradé (tension/critique/ferme/insuffisant/degrade/hs)
          //   2. OU flag booléen alerte_lits/rh/materiel
          //   3. OU tension_activee=true (mode crise formel)
          const degradeStatuts = new Set([
            'tension','critique','ferme',
            'insuffisant','degrade',
            'hs',
          ]);
          const alertes = unites.filter(u => {
            const d = u && u.derniere_declaration;
            if (!d) return false;
            if (degradeStatuts.has(d.statut_lits)) return true;
            if (degradeStatuts.has(d.statut_rh)) return true;
            if (degradeStatuts.has(d.statut_materiel)) return true;
            if (d.alerte_lits || d.alerte_rh || d.alerte_materiel) return true;
            if (d.tension_activee) return true;
            return false;
          });
          const nouvelles = alertes.filter(u => {
            const d = u.derniere_declaration;
            // Clé de vue : id unité + timestamp déclaration, pour ne pas
            // masquer un nouveau changement d'état d'une unité déjà vue.
            const key = u.id + ':' + (d.horodatage || d.timestamp || '');
            return !viewed.has(key);
          });
          const n = nouvelles.length;
          badge.textContent = n;
          badge.style.display = n ? 'inline' : 'none';
          // Diagnostic : log si on a des alertes mais pas de badge visible
          if (alertes.length > 0 && n === 0) {
            console.debug('[SCRIBE capacite-badge] ' + alertes.length + ' alerte(s) capacité, toutes vues — badge masqué');
          }
          if (alertes.length === 0 && unites.some(u => u.derniere_declaration)) {
            console.debug('[SCRIBE capacite-badge] ' + unites.filter(u=>u.derniere_declaration).length + ' déclaration(s) trouvée(s), aucune en tension. Exemple statuts :',
              unites.filter(u=>u.derniere_declaration).slice(0,3).map(u => ({
                unite: u.service_nom || u.nom,
                lits: u.derniere_declaration.statut_lits,
                rh: u.derniere_declaration.statut_rh,
                mat: u.derniere_declaration.statut_materiel,
                al: [u.derniere_declaration.alerte_lits, u.derniere_declaration.alerte_rh, u.derniere_declaration.alerte_materiel]
              }))
            );
          }
        }
      } else {
        console.warn('[SCRIBE capacite-badge] GET /capacite/referentiel: HTTP ' + r.status);
      }
    } catch(e) {
      console.warn('[SCRIBE capacite-badge] Erreur:', e);
    }

    // v2312-hotfix — Badge BRANCARDAGE : nombre de missions actives
    // (statut ≠ TERMINE/ANNULE) non encore vues. Signale qu'une mission
    // de transport a été créée (typiquement via un stimulus brancardage
    // pendant un exercice), sans que l'utilisateur ait besoin d'avoir
    // l'onglet BRANCARDAGE ouvert en permanence.
    // v2314 : injection robuste du span badge — si le plugin a été
    // chargé AVANT la création du span dynamique (cas SSO autotoken où
    // l'ordre de chargement est différent), on injecte le span à la
    // volée dans le bouton plugin.
    try {
      const r = await apiFetch('/api/v1/brancardage/missions', {
        headers: authHeaders()
      });
      if (r.ok) {
        const missions = await r.json();
        // Chercher le span ; s'il n'existe pas, l'injecter dans le bouton
        let badge = document.getElementById('plugin-badge-brancardage');
        if (!badge) {
          const btn = document.getElementById('tab-btn-brancardage');
          if (btn) {
            badge = document.createElement('span');
            badge.id = 'plugin-badge-brancardage';
            badge.style.cssText = 'display:none;background:#f97316;color:#fff;font-size:9px;padding:1px 5px;border-radius:10px;margin-left:4px;font-weight:700';
            btn.appendChild(badge);
          }
        }
        if (badge && Array.isArray(missions)) {
          const viewedKey = 'scribe_brancardage_viewed_ids';
          const viewed = new Set(JSON.parse(localStorage.getItem(viewedKey) || '[]'));
          const ouvertes = missions.filter(m =>
            m && m.statut !== 'TERMINE' && m.statut !== 'ANNULE'
          );
          const nouvelles = ouvertes.filter(m => !viewed.has(m.id));
          const n = nouvelles.length;
          badge.textContent = n;
          badge.style.display = n ? 'inline' : 'none';
          // Diagnostic v2314
          if (missions.length > 0 && n === 0 && ouvertes.length > 0) {
            console.debug('[SCRIBE brancardage-badge] ' + ouvertes.length + ' mission(s) actives, toutes vues');
          }
          if (missions.length === 0) {
            console.debug('[SCRIBE brancardage-badge] 0 mission dans la base');
          }
        } else if (!badge) {
          console.warn('[SCRIBE brancardage-badge] Ni span badge ni bouton tab-btn-brancardage trouvés — plugin actif ?');
        }
      } else {
        console.warn('[SCRIBE brancardage-badge] GET /brancardage/missions: HTTP ' + r.status);
        const badge = document.getElementById('plugin-badge-brancardage');
        if (badge) badge.style.display = 'none';
      }
    } catch(e) {
      console.warn('[SCRIBE brancardage-badge] Erreur:', e);
    }
    // v2200 — loadTasks() en fire-and-forget pour tenir le badge kanban à
    // jour même hors onglet Kanban. Pas d'await : n'impacte pas le refresh.
    loadTasks().catch(function(){});
    // Charger les PJ pour tous les incidents
    const pjResults = await Promise.all(
      incidents.map(i => apiFetch(`/api/v1/attachments/${i.id}`).then(r=>r.json()).catch(()=>[]))
    );
    incidents.forEach((inc, idx) => { incAttachments[inc.id] = pjResults[idx] || []; });
    updateKPIs(stats);
    updateLevel(stats);
    updateMap(stats.by_site||[]);
    applyFilters();
    // Rafraîchir les transferts entrants depuis le collecteur (toutes les 12s)
    const prevIds = new Set(trIncoming.map(t => `${t.id_local}_${t.ght_emetteur}_${t.statut}`));
    await loadTransfertsEntrants();
    const nouveaux = trIncoming.filter(t =>
      !prevIds.has(`${t.id_local}_${t.ght_emetteur}_${t.statut}`)
    );
    if (nouveaux.length) {
      trRender();
      trUpdateBadge();
      nouveaux.forEach(t => {
        if (t.statut === 'EN_COURS' || t.statut === 'EN_PREPARATION') {
          toast(`📡 Transfert entrant : ${t.etablissement_origine} → ${t.unite_destination}`, 'ok');
        }
      });
    }
    // Mettre à jour SOINS en temps réel si l'onglet est actif
    if (document.getElementById('tab-soins').classList.contains('active')) {
      renderSoins();
    }
  } catch(e) { console.error('refreshAll error:', e); }
}

function updateKPIs(s) {
  document.getElementById('kpi-total').textContent    = s.total||0;
  document.getElementById('kpi-critical').textContent = s.critical||0;
  document.getElementById('kpi-open').textContent     = s.ouverts||0;
  document.getElementById('kpi-cyber').textContent    = s.cyber||0;
  document.getElementById('kpi-sani').textContent     = s.sanitaire||0;
}

function updateLevel(s) {
  const el = document.getElementById('incident-level');
  const c=s.critical||0, o=s.ouverts||0;
  if(c>0){el.className='black';el.textContent='CRITIQUE';}
  else if(o>=3){el.className='red';el.textContent='CRISE';}
  else if(o>=1){el.className='amber';el.textContent='ALERTE';}
  else{el.className='green';el.textContent='SITUATION NORMALE';}
}

// ── TIMELINE ─────────────────────────────────────────
function setStatusTab(btn, status) {
  document.getElementById('f-status').value = status;
  document.querySelectorAll('.status-tab').forEach(b => b.classList.remove('active'));
  btn.classList.add('active');
  applyFilters();
}

function updateStatusTabCounts() {
  // Compter les incidents par statut
  const counts = {};
  (allIncidents || []).forEach(i => {
    counts[i.status] = (counts[i.status] || 0) + 1;
  });
  // "Actifs" = tout sauf RÉSOLU et ARCHIVÉ
  const actifs = (allIncidents || []).filter(i => i.status !== 'RÉSOLU' && i.status !== 'ARCHIVÉ').length;
  const el0 = document.getElementById('stab-count-');
  if (el0) el0.textContent = actifs || '';
  ['SIGNALÉ','ANALYSE','RÉSOLUTION','RÉSOLU','ARCHIVÉ'].forEach(s => {
    const el = document.getElementById('stab-count-' + s);
    if (el) el.textContent = counts[s] || '';
  });
}

function applyFilters() {
  const site = document.getElementById('f-site').value;
  const dir  = document.getElementById('f-directeur').value;
  const urg  = document.getElementById('f-urgency').value;
  const sta  = document.getElementById('f-status').value;
  const typ  = document.getElementById('f-type').value;
  updateStatusTabCounts();
  renderTimeline(allIncidents.filter(i=>
    (!site || i.site_id===site) &&
    (!dir  || (i.directeur_crise||'')===dir) &&
    (!urg  || String(i.urgency)===urg) &&
    // Par défaut (aucun filtre) : exclure RÉSOLU et ARCHIVÉ
    (sta ? i.status===sta : (i.status!=='RÉSOLU' && i.status!=='ARCHIVÉ')) &&
    (!typ  || i.type_crise===typ)
  ));
}

function resetFilters() {
  ['f-site','f-directeur','f-urgency','f-status','f-type'].forEach(id=>document.getElementById(id).value='');
  renderTimeline(allIncidents);
}

function renderTimeline(list) {
  const el = document.getElementById('timeline');
  if (!list.length) { el.innerHTML='<div class="empty-state">Aucun incident déclaré</div>'; return; }
  el.innerHTML = list.map(h => buildCard(h)).join('');
  // Restaurer l'état déplié (perdu par innerHTML = ...) pour toutes les cartes
  // dont l'ID est dans _expandedIncidents. Évite que les cartes se referment
  // toutes seules à chaque refresh (3s en mode exercice, 12s en prod).
  if (typeof _expandedIncidents !== 'undefined') {
    _expandedIncidents.forEach(function(id) {
      var card = document.getElementById('inc-' + id);
      if (card) {
        card.classList.add('expanded');
        var btn = card.querySelector('.inc-toggle-btn');
        if (btn) btn.textContent = '▼';
      }
    });
  }
}

function buildCard(h) {
  const ts = new Date(h.timestamp).toLocaleString('fr-FR',{day:'2-digit',month:'2-digit',hour:'2-digit',minute:'2-digit'});
  // Statuts disponibles dans le select (RÉSOLU/ARCHIVÉ via bouton dédié)
  const STATUSES_SELECT = ['SIGNALÉ','ANALYSE','RÉSOLUTION'];
  const opts = STATUSES_SELECT.map(s=>`<option value="${s}"${h.status===s?' selected':''}>${s}</option>`).join('');
  const urgLbl = URG_LABELS[h.urgency]||h.urgency;
  // Pièces jointes — chargées en cache
  const pjHTML = (incAttachments[h.id]||[]).length > 0
    ? `<div class="pj-list">${(incAttachments[h.id]).map(a=>{
        const ext = a.filename.split('.').pop().toUpperCase();
        const url = '/uploads/' + encodeURIComponent(a.filename.replace(/ /g,'_').replace(/^/,''));
        // reconstruct url as stored by server: {id}_{filename}
        const serverName = h.id + '_' + a.filename.replace(/ /g,'_');
        return `<a class="pj-chip" href="/uploads/${encodeURIComponent(serverName)}" target="_blank" onclick="event.stopPropagation()" title="${a.filename}">
          <span class="pj-ext">${ext}</span>${a.filename.length > 20 ? a.filename.substring(0,18)+'…' : a.filename}
        </a>`;
      }).join('')}</div>`
    : '';

  // Jalons
  let jalonsHTML='';
  if(h.jalons){try{
    const js=JSON.parse(h.jalons), tot=js.length, done=js.filter(j=>j.done).length, pct=tot?Math.round(done/tot*100):0;
    jalonsHTML=`<div class="jalons-section">
      <div class="jalons-title">⏱ JALONS — ${pct}%</div>
      <div class="progress-bar"><div class="progress-fill" style="width:${pct}%"></div></div>
      ${js.map((j,i)=>`<div class="jalon-item">
        <input type="checkbox" class="jalon-cb"${j.done?' checked':''} onchange="toggleJalon(${h.id},${i},this.checked)" onclick="event.stopPropagation()">
        <span class="jalon-label${j.done?' jalon-done':''}">${j.label}</span>
        ${j.done_at?`<span class="jalon-time">${new Date(j.done_at).toLocaleTimeString('fr-FR',{hour:'2-digit',minute:'2-digit'})}</span>`:''}
      </div>`).join('')}
    </div>`;}catch(e){}}

  // Projection
  let projHTML='';
  if(h.estimated_resolution && h.status!=='RÉSOLU'){
    const eta=new Date(h.estimated_resolution), now=new Date(), dm=Math.round((eta-now)/60000);
    const ds=dm>0?(dm>=60?`dans ${Math.floor(dm/60)}h${String(dm%60).padStart(2,'0')}`:`dans ${dm} min`):'DÉPASSÉE';
    projHTML=`<div class="projection-section">
      <div class="proj-title">📊 PROJECTION RETOUR NORMAL</div>
      <div class="proj-row"><span class="proj-label">Résolution estimée:</span><span class="proj-val">${eta.toLocaleString('fr-FR',{day:'2-digit',month:'2-digit',hour:'2-digit',minute:'2-digit'})}</span></div>
      <div class="proj-eta">${ds}</div>
      ${h.completion_percent?`<div class="proj-row"><span class="proj-label">Avancement:</span><span class="proj-val">${h.completion_percent}%</span></div>`:''}
    </div>`;
  }

  // v2199 — Rebrand : "AVIS ALBERT AI" devient "ANALYSE SCRIBE"
  let alHTML='';
  if(h.albert_avis){
    alHTML=`<div class="albert-inline">
      <div class="albert-inline-title">🧠 ANALYSE SCRIBE</div>
      <div class="albert-inline-body">${h.albert_avis}</div>
    </div>`;}

  const resBadge=h.resolved_at?`<span class="resolved-badge">✓ ${new Date(h.resolved_at).toLocaleString('fr-FR',{day:'2-digit',month:'2-digit',hour:'2-digit',minute:'2-digit'})}</span>`:'';

  const dirBadge=h.directeur_crise?`<span class="inc-dir">${h.directeur_crise.split(' ').slice(-1)[0]}</span>`:'';

  const detail=[
    h.analyse?`<div><b>Analyse:</b> ${h.analyse}</div>`:'',
    h.moyens_engages?`<div><b>Moyens:</b> ${h.moyens_engages}</div>`:'',
    h.intervenant_nom?`<div><b>Intervenant:</b> ${h.intervenant_nom} ${h.intervenant_contact||''}</div>`:'',
  ].join('');

  // ── Mini-toolbar actions rapides (v2181) ─────────────────────────────
  // Compte jalons done/total pour le badge mini
  let _jDone = 0, _jTot = 0;
  if (h.jalons) { try {
    const _jj = JSON.parse(h.jalons);
    _jTot = _jj.length; _jDone = _jj.filter(x => x.done).length;
  } catch(e) {} }
  const jMiniHTML = _jTot > 0
    ? `<span class="inc-jalon-mini${_jDone===_jTot?' done':''}"
            onclick="event.stopPropagation();toggleExpand(document.getElementById('inc-${h.id}'))"
            title="${_jDone}/${_jTot} jalons — cliquer pour ouvrir">⏱ ${_jDone}/${_jTot}</span>`
    : '';

  // Select statut compact — même options que le gros en bas de carte
  const QUICK_STATUSES = ['SIGNALÉ','ANALYSE','RÉSOLUTION'];
  const qOpts = QUICK_STATUSES.map(s=>`<option value="${s}"${h.status===s?' selected':''}>${s}</option>`).join('');
  const quickStatusHTML = (h.status !== 'RÉSOLU' && h.status !== 'ARCHIVÉ')
    ? `<select class="inc-quick-status" onchange="updateStatus(${h.id},this.value)" onclick="event.stopPropagation()" title="Changer le statut">${qOpts}</select>`
    : `<span class="inc-quick-btn" style="opacity:.6" title="Statut ${h.status}">${h.status}</span>`;

  // Bouton ✓ Résoudre (actions principales sans ouvrir la carte)
  const quickResolveHTML = (h.status !== 'RÉSOLU' && h.status !== 'ARCHIVÉ')
    ? `<button class="inc-quick-btn success"
               onclick="event.stopPropagation();resoudreEtArchiver(${h.id},event)"
               title="Résoudre et archiver">✓ Résoudre</button>`
    : '';

  const quickBarHTML = `<span class="inc-quick">${jMiniHTML}${quickStatusHTML}${quickResolveHTML}</span>`;

  // v2199 — Bouton "Conseil SCRIBE" mis en avant dans le header de l'incident.
  // Libellé explicite, couleur violette distinctive (capitalise l'IA), toujours
  // visible (pas seulement après avoir ouvert le détail).
  // Si un avis SCRIBE existe déjà, le bouton devient "🧠 Nouvelle analyse".
  const hasAvis = !!h.albert_avis;
  const scribeBtnLabel = hasAvis ? '🧠 Nouvelle analyse' : '🧠 Conseil SCRIBE';
  const scribeBtnTitle = hasAvis
    ? 'Relancer une analyse SCRIBE sur cet incident'
    : 'Demander une analyse et des recommandations à SCRIBE';
  const scribeHeaderBtn = (h.status !== 'ARCHIVÉ') ? `
    <button class="inc-scribe-btn" data-inc-id="${h.id}"
      onclick="askAlbertIncidentById(this.dataset.incId,event)"
      title="${scribeBtnTitle}">${scribeBtnLabel}</button>` : '';

  return `<div class="incident-item urgency-${h.urgency}" id="inc-${h.id}">
    <div class="inc-header">
      <button class="inc-toggle-btn" onclick="toggleExpand(document.getElementById('inc-${h.id}'))" title="Ouvrir/Fermer">▶</button>
      <span class="inc-urg urg-${h.urgency}">${urgLbl}</span>
      <span class="inc-type type-${h.type_crise}">${h.type_crise}</span>
      ${dirBadge}
      <span class="inc-site" title="${h.site_id}${h.unite_fonctionnelle?' | '+h.unite_fonctionnelle:''}">${h.site_id}${h.unite_fonctionnelle?' / '+h.unite_fonctionnelle.split(',').map(u=>u.trim()).filter(Boolean).join(' · '):''}</span>
      <span class="inc-time">${ts}</span>
      <span style="font-family:var(--mono);font-size:9px;color:var(--muted);background:var(--surface3);padding:1px 5px;border-radius:3px;flex-shrink:0">#${h.id}</span>
      ${quickBarHTML}
      ${scribeHeaderBtn}
    </div>
    <div class="inc-fait">${h.fait}</div>
    ${pjHTML}
    <div class="inc-detail">
      ${detail}${jalonsHTML}${projHTML}${alHTML}
      <div class="inc-status-row">
        <select onchange="updateStatus(${h.id},this.value)" onclick="event.stopPropagation()">${opts}</select>
        ${resBadge}
        <span class="inc-declarant">→ ${h.declarant_nom||'?'}</span>
        <div class="btn-row-small">
          <button class="btn-sm green" onclick="uploadFor(${h.id},event)" title="Ajouter pièce jointe">📎</button>
          <button class="btn-sm red" onclick="deleteInc(${h.id},event)">🗑</button>
          <button class="btn-sm" style="color:#a78bfa;border-color:#7c3aed" data-inc-id="${h.id}" onclick="quickCreateTaskById(this.dataset.incId,event)" title="Créer tâche Kanban">📋</button>
          <button class="btn-sm" style="color:#4ade80;border-color:#16a34a" onclick="quickRex(${h.id},event)" title="Générer rapport / REX">📄</button>
          ${h.status !== 'RÉSOLU' && h.status !== 'ARCHIVÉ' ? '<button class="btn-sm" style="color:#fff;background:#059669;border-color:#059669;font-weight:700" onclick="resoudreEtArchiver(' + h.id + ',event)" title="Résoudre et archiver cet incident">✓ Résoudre</button>' : ''}
        </div>
      </div>
      <!-- Widget édition UF -->
      <div id="uf-edit-${h.id}" style="margin-top:6px;padding-top:6px;border-top:1px solid var(--border)" onclick="event.stopPropagation()">
        <div style="font-family:var(--mono);font-size:8px;color:var(--muted);letter-spacing:1px;margin-bottom:4px">UNITÉS FONCTIONNELLES IMPACTÉES</div>
        <div id="uf-edit-tags-${h.id}" style="display:flex;flex-wrap:wrap;gap:4px;margin-bottom:5px">${_renderUfTags(h.id, h.unite_fonctionnelle||'')}</div>
        <div style="display:flex;gap:4px;align-items:center">
          <input id="uf-add-input-${h.id}" type="text" placeholder="Ajouter une UF..."
            style="flex:1;font-family:var(--mono);font-size:10px;padding:3px 7px;background:var(--surface2);border:1px solid var(--border2);border-radius:4px;color:var(--text)"
            oninput="incUfFilter(${h.id},this.value)"
            onkeydown="if(event.key==='Enter'){incUfAdd(${h.id},event);}"
            autocomplete="off">
          <button onclick="incUfAdd(${h.id},event)"
            style="font-family:var(--mono);font-size:9px;padding:3px 9px;background:var(--surface2);border:1px solid var(--border2);border-radius:4px;color:var(--muted2);cursor:pointer">＋ Ajouter</button>
        </div>
        <div id="uf-add-dd-${h.id}" style="display:none;margin-top:2px;max-height:120px;overflow-y:auto;background:var(--surface2);border:1px solid var(--border2);border-radius:4px;font-family:var(--mono);font-size:10px"></div>
      </div>
    </div>
  </div>`;
}

// Génère le HTML des tags UF sans template littéral imbriqué (évite SyntaxError)
function _renderUfTags(id, ufStr) {
  return (ufStr||'').split(',').map(function(u){return u.trim();}).filter(Boolean).map(function(u){
    var esc = u.replace(/'/g, "\\'");
    return '<span style="display:inline-flex;align-items:center;gap:4px;background:var(--blue-dim);border:1px solid rgba(37,99,235,.4);border-radius:4px;padding:2px 7px;font-family:var(--mono);font-size:9px;color:#60a5fa">'
      + u
      + '<span onclick="incUfRemove(' + id + ',\'' + esc + '\',event)" style="cursor:pointer;color:var(--muted);font-size:10px;margin-left:3px">✕</span>'
      + '</span>';
  }).join('');
}

// Set global des incidents actuellement dépliés. Préservé entre les re-renders
// (renderTimeline recrée tout le HTML à chaque refresh et ferait retomber
//  toutes les cartes à l'état fermé sinon).
var _expandedIncidents = new Set();

function toggleExpand(el) {
  el.classList.toggle('expanded');
  const btn = el.querySelector('.inc-toggle-btn');
  if (btn) btn.textContent = el.classList.contains('expanded') ? '▼' : '▶';
  // Mémoriser l'état pour survivre aux re-renders
  var id = el.id.replace(/^inc-/, '');
  if (id) {
    if (el.classList.contains('expanded')) _expandedIncidents.add(id);
    else _expandedIncidents.delete(id);
  }
}

// ── Gestion UF sur incident existant ─────────────────────────────────────────
async function _incUfSave(id, newUfStr) {
  const r = await apiFetch('/api/v1/sitrep/' + id + '/uf', {
    method: 'PUT',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({unite_fonctionnelle: newUfStr})
  });
  if (!r.ok) { toast('Erreur mise à jour UF', 'err'); return false; }
  // Mettre à jour en mémoire locale
  const inc = allIncidents.find(i => i.id === id);
  if (inc) inc.unite_fonctionnelle = newUfStr;
  toast('UF mise à jour ✓', 'ok');
  return true;
}

async function incUfRemove(id, code, event) {
  event.stopPropagation();
  const inc = allIncidents.find(i => i.id === id);
  if (!inc) return;
  const ufs = (inc.unite_fonctionnelle || '').split(',').map(u => u.trim()).filter(Boolean);
  const newUfs = ufs.filter(u => u !== code);
  const newStr = newUfs.join(', ');
  const ok = await _incUfSave(id, newStr);
  if (ok) {
    // Rafraîchir le rendu du widget sans recharger tout
    var tagsDiv = document.getElementById('uf-edit-tags-' + id);
    if (tagsDiv) { tagsDiv.innerHTML = _renderUfTags(id, newStr); }
    // Mettre à jour l'en-tête
    var header = document.querySelector('#inc-' + id + ' .inc-site');
    if (header) {
      var siteId = inc.site_id || '';
      header.textContent = siteId + (newStr ? ' / ' + newUfs.join(' · ') : '');
    }
  }
}

function incUfFilter(id, q) {
  const dd = document.getElementById('uf-add-dd-' + id);
  if (!q || q.length < 1) { dd.style.display = 'none'; return; }
  const filtered = allUFList.filter(u =>
    u.code_uf.toLowerCase().includes(q.toLowerCase()) ||
    u.libelle.toLowerCase().includes(q.toLowerCase())
  ).slice(0, 15);
  if (!filtered.length) { dd.style.display = 'none'; return; }
  dd.innerHTML = filtered.map(function(u){
    return '<div onmousedown="incUfSelect(' + id + ',\'' + u.code_uf + '\',event)"'
      + ' style="padding:4px 8px;cursor:pointer;border-bottom:1px solid var(--border)">'
      + '<span style="color:#60a5fa;margin-right:6px">' + u.code_uf + '</span>' + u.libelle
      + '</div>';
  }).join('');
  dd.style.display = 'block';
}

async function incUfSelect(id, code, event) {
  event.stopPropagation();
  const input = document.getElementById('uf-add-input-' + id);
  if (input) input.value = code;
  const dd = document.getElementById('uf-add-dd-' + id);
  if (dd) dd.style.display = 'none';
  await incUfAdd(id, event, code);
}

async function incUfAdd(id, event, forceCode) {
  event.stopPropagation();
  const input = document.getElementById('uf-add-input-' + id);
  const code = (forceCode || (input ? input.value.trim() : '')).toUpperCase();
  if (!code) return;
  const inc = allIncidents.find(i => i.id === id);
  if (!inc) return;
  const ufs = (inc.unite_fonctionnelle || '').split(',').map(u => u.trim()).filter(Boolean);
  if (ufs.includes(code)) { if (input) input.value = ''; return; }
  ufs.push(code);
  const newStr = ufs.join(', ');
  const ok = await _incUfSave(id, newStr);
  if (ok) {
    if (input) input.value = '';
    const dd2 = document.getElementById('uf-add-dd-' + id);
    const dd = dd2;
    if (dd) dd.style.display = 'none';
    var tagsDiv2 = document.getElementById('uf-edit-tags-' + id);
    if (tagsDiv2) { tagsDiv2.innerHTML = _renderUfTags(id, newStr); }
    var header2 = document.querySelector('#inc-' + id + ' .inc-site');
    if (header2) {
      var siteId2 = inc.site_id || '';
      header2.textContent = siteId2 + (newStr ? ' / ' + ufs.join(' · ') : '');
    }
  }
}



// ── SERVICES TRANSVERSES (Sécurité physique / Logistique) ─────────────────
let serviceStatuses = [];   // cache des statuts chargés depuis l'API

async function loadServiceStatuses() {
  try {
    const r = await apiFetch('/api/v1/cartographie/service-status');
    serviceStatuses = await r.json();
  } catch(e) { serviceStatuses = []; }
}

function renderTransverses() {
  const section = document.getElementById('transverses-section');
  if (!section) return;
  if (!serviceStatuses.length) {
    section.innerHTML = '';
    return;
  }
  const ICONS = { securite_physique: '🔒', logistique: '📦' };
  const cardsHtml = serviceStatuses.map(s => {
    const icon   = ICONS[s.service_id] || '⚙️';
    const isOk   = s.statut === 'OK';
    const isDeg  = s.statut === 'DEGRADE';
    const isCrit = s.statut === 'CRITIQUE';
    const ts     = s.updated_at ? new Date(s.updated_at).toLocaleTimeString('fr-FR') : '';
    return `<div class="service-card">
      <div class="service-card-header">
        <span class="service-name">${icon} ${s.libelle}</span>
        <div class="service-badge-btns">
          <button class="${isOk   ? 'active-ok'       : 'inactive'}"
                  onclick="setServiceStatus('${s.service_id}','OK',this)"
                  title="Opérationnel">✓ OK</button>
          <button class="${isDeg  ? 'active-degrade'  : 'inactive'}"
                  onclick="setServiceStatus('${s.service_id}','DEGRADE',this)"
                  title="Mode dégradé">⚡ DÉGRADÉ</button>
          <button class="${isCrit ? 'active-critique'  : 'inactive'}"
                  onclick="setServiceStatus('${s.service_id}','CRITIQUE',this)"
                  title="Impact critique">⚠ CRITIQUE</button>
        </div>
      </div>
      <textarea class="service-comment" rows="1"
        placeholder="Commentaire..."
        onblur="saveServiceComment('${s.service_id}', this.value)"
        >${s.commentaire || ''}</textarea>
      <span class="service-updated" id="svc-ts-${s.service_id}">${ts ? 'Mis à jour : ' + ts : ''}</span>
    </div>`;
  }).join('');

  section.innerHTML = `
    <div class="transverses-title">🔧 Services transverses</div>
    <div class="transverses-grid">${cardsHtml}</div>`;
}

async function setServiceStatus(serviceId, statut, btn) {
  // Optimistic UI
  const card = btn.closest('.service-card');
  card.querySelectorAll('.service-badge-btns button').forEach(b => {
    b.className = 'inactive';
  });
  const cls = statut === 'OK' ? 'active-ok' : statut === 'DEGRADE' ? 'active-degrade' : 'active-critique';
  btn.className = cls;

  const comment = card.querySelector('.service-comment').value;
  try {
    const r = await apiFetch(`/api/v1/cartographie/service-status/${serviceId}`, {
      method: 'PUT',
      headers: {'Content-Type': 'application/json', 'Authorization': 'Bearer ' + (localStorage.getItem('scribe_token') || '')},
      body: JSON.stringify({ statut, commentaire: comment })
    });
    if (!r.ok) throw new Error('Erreur serveur');
    // Mettre à jour le cache
    const idx = serviceStatuses.findIndex(s => s.service_id === serviceId);
    if (idx >= 0) { serviceStatuses[idx].statut = statut; }
    const tsEl = document.getElementById('svc-ts-' + serviceId);
    if (tsEl) tsEl.textContent = 'Mis à jour : ' + new Date().toLocaleTimeString('fr-FR');
    toast('Statut mis à jour ✓', 'ok');
  } catch(e) {
    toast('Erreur mise à jour : ' + e.message, 'err');
    // Rollback visuel
    await loadServiceStatuses();
    renderTransverses();
  }
}

async function saveServiceComment(serviceId, comment) {
  const svc = serviceStatuses.find(s => s.service_id === serviceId);
  if (!svc) return;
  try {
    await apiFetch(`/api/v1/cartographie/service-status/${serviceId}`, {
      method: 'PUT',
      headers: {'Content-Type': 'application/json', 'Authorization': 'Bearer ' + (localStorage.getItem('scribe_token') || '')},
      body: JSON.stringify({ statut: svc.statut, commentaire: comment })
    });
    const idx = serviceStatuses.findIndex(s => s.service_id === serviceId);
    if (idx >= 0) serviceStatuses[idx].commentaire = comment;
  } catch(e) { /* silencieux */ }
}

// ── SOINS ─────────────────────────────────────────────
// Map UF -> pôle chargée depuis l'API (basée sur les libellés BDD)
let ufToPoleMap = {};

// Variables timeline (déclarées ici pour être accessibles par renderSoins)
const PIN_COLORS = { 4:'#f87171', 3:'#fb923c', 2:'#fbbf24', 1:'#60a5fa' };
const URGENCY_DEFAULT_H = { 4:72, 3:24, 2:8, 1:2 };
let tlNow = Date.now();
let tlRangeMs = 72 * 3600000;
let tlProjectedMs = 0;
let tlIncidentETAs = [];
let tlDragging = false;

async function loadUfToPole() {
  try {
    const r = await apiFetch('/api/v1/cartographie/uf-to-pole');
    ufToPoleMap = await r.json();
  } catch(e) { console.warn('uf-to-pole:', e); }
}

const POLES_LIST = [
  'CANCEROLOGIE','CARDIOVASCULAIRE','CHIRURGIE ANESTHESIE','DNA','FME',
  'GERIATRIE','MEDECINE','MEDICO-TECHNIQUE ET REEDUCATION','SANTE MENTALE',
  'SANTE PUBLIQUE ET COMMUNAUTAIRE','SOINS CRITIQUES','URGENCES','IFSI','SUPPORT'
];

function _getPoleForIncident(incident) {
  const ufRaw = (incident.unite_fonctionnelle || '').trim();
  // Support multi-UF : "1001, 1002" → ["1001", "1002"]
  const ufList = ufRaw.split(',').map(u => u.trim()).filter(Boolean);

  // Priorité 0 : une des UF est directement un nom de pôle exact
  for (const uf of ufList) {
    if (POLES_LIST.includes(uf)) return uf;
  }
  // Priorité 1 : code UF exact → map vers pôle (supporte multi-UF)
  for (const uf of ufList) {
    if (ufToPoleMap[uf]) return ufToPoleMap[uf];
  }
  // Priorité 2 : chercher des codes UF numériques dans unite_fonctionnelle ET le texte libre
  const hay = (ufRaw + ' ' + (incident.fait||'') + ' ' + (incident.analyse||'')).toUpperCase();
  const ufMatch = hay.match(/\b(\d{3,5})\b/g);
  if (ufMatch) {
    for (const m of ufMatch) {
      if (ufToPoleMap[m]) return ufToPoleMap[m];
    }
  }
  // Priorité 3 : mots-clés dans le texte de l'incident (fallback robuste)
  const POLE_KW = {
    'CHIRURGIE ANESTHESIE': ['BLOC','CHIR','ANESTHES','ORTHO','TRAUMA','ORL','OPHTALMOL','VISCERAL','NEUROCHIR'],
    'SOINS CRITIQUES':      ['REANIMATION','RÉANIMATION','REA ','USI','USIP','SIPO','SOINS CRITIQUES','SOINS INTENSIF'],
    'URGENCES':             ['URGENCE','SMUR','SAMU','UHCD','UPUM','SAUV'],
    'MEDECINE':             ['CARDIOL','PNEUMOL','NEUROLOG','HEPATO','GASTRO','NEPHRO','HEMATO','INFECTI','RHUMATO','DERMATO','MEDECINE INTERNE'],
    'CARDIOVASCULAIRE':     ['CARDIO','CORONAR','USIC'],
    'FME':                  ['MATERNIT','GYNECO','NEONAT','OBSTET','SAGE-FEMME','PÉDIATR','PEDIATR'],
    'CANCEROLOGIE':         ['CANCERO','ONCOLOG','RADIOTHER','CHIMIO'],
    'GERIATRIE':            ['GERIATR','EHPAD','USLD','PALLIAT','GÉRIATR'],
    'SANTE MENTALE':        ['PSYCHIATR','ADDICTOL','PSY ','UPUP'],
    'MEDICO-TECHNIQUE ET REEDUCATION': ['LABORATOIR','IMAGERIE','SCANNER','PHARMA','REEDUCATION','KINÉ','KINE'],
    'SUPPORT':              ['INFORMATIQUE','DSI','LOGISTIQUE','CUISINE','BLANCHISS','DIRECTION'],
    'URGENCES':             ['SAU ','SAU,','URGENCES'],
  };
  for (const [pole, kws] of Object.entries(POLE_KW)) {
    if (kws.some(kw => hay.includes(kw))) return pole;
  }
  // Priorité 4 : site_id → rattacher au pôle le plus probable du site
  // (dernier recours — affiche au moins quelque chose dans SOINS)
  const site = (incident.site_id || '').toUpperCase();
  if (site.includes('JULIEN')) return 'MEDECINE';
  if (site.includes('RUMILLY')) return 'MEDECINE';
  return null;
}

function renderSoins() {
  // Ne pas écraser le label si on est en mode projection
  if (!tlProjectedMs) {
    document.getElementById('soins-last-update').textContent = `Mis à jour: ${new Date().toLocaleTimeString('fr-FR')}`;
  }
  renderTransverses();
  const grid = document.getElementById('soins-grid');
  const fStatut = document.getElementById('f-statut')?.value || '';
  const openInc = allIncidents.filter(i => i.status !== 'RÉSOLU' && (fStatut === 'ARCHIVÉ' ? i.status === 'ARCHIVÉ' : i.status !== 'ARCHIVÉ'));

  // Grouper par pôle via la map UF
  const incByPole = {};
  POLES_LIST.forEach(p => incByPole[p] = []);
  openInc.forEach(i => {
    const pole = _getPoleForIncident(i);
    if (pole && incByPole[pole] !== undefined) incByPole[pole].push(i);
  });

  grid.innerHTML = POLES_LIST.map(pole => {
    const linked = incByPole[pole];

    // Sémantique panneau SOINS (v2182) : il reflète l'état de FONCTIONNEMENT
    // opérationnel du pôle, PAS la gravité clinique des patients pris en charge.
    // Règle :
    //   - Incidents CYBER → pannes SI : impactent l'état opérationnel.
    //   - Incidents avec payload.impact_fonctionnel = true → impact explicite.
    //   - Incidents SANITAIRE sans impact_fonctionnel → affichés comme
    //     "événements en cours" mais ne changent PAS le badge (hémorragie =
    //     événement clinique, pas panne du bloc).
    //   - Le statut capacitaire (capData) peut aggraver le badge via
    //     capUpdateSoinsStatuts() (appelé juste après le rendu).
    const opsInc = linked.filter(i =>
      i.type_crise === 'CYBER' || i.impact_fonctionnel === true
    );
    const sanitInc = linked.filter(i =>
      !(i.type_crise === 'CYBER' || i.impact_fonctionnel === true)
    );
    const maxUrg = opsInc.length ? Math.max(...opsInc.map(i => i.urgency)) : 0;
    let statusClass, statusLabel;
    if (maxUrg >= 3)      { statusClass='soins-critique'; statusLabel='⚠ CRITIQUE'; }
    else if (maxUrg >= 2) { statusClass='soins-degrade';  statusLabel='⚡ MODE DÉGRADÉ'; }
    else if (maxUrg >= 1) { statusClass='soins-degrade';  statusLabel='⚡ INCIDENT'; }
    else                  { statusClass='soins-ok';        statusLabel='✓ OPÉRATIONNEL'; }

    // Jauge verticale de charge sanitaire (v2182) : compte les incidents
    // SANITAIRE/cliniques actifs liés au pôle pour donner une idée du
    // volume d'opérations en cours. Sert à prioriser le retour à la normale
    // lors d'une panne cyber : un service chargé à 100% est prioritaire.
    const chargeNiveau = Math.min(sanitInc.length, 5);
    const chargePct = chargeNiveau * 20;  // 0, 20, 40, 60, 80, 100
    const chargeColor = chargePct >= 80 ? '#ef4444'
                      : chargePct >= 60 ? '#f97316'
                      : chargePct >= 40 ? '#fbbf24'
                      : chargePct >= 20 ? '#84cc16'
                      : '#22c55e';
    const chargeLabel = chargePct === 0 ? 'Calme'
                      : chargePct <= 40 ? 'Normal'
                      : chargePct <= 60 ? 'Chargé'
                      : chargePct <= 80 ? 'Saturé'
                      : 'Surchargé';
    const chargeGaugeHTML = `<div class="soins-charge-gauge" title="Charge sanitaire : ${sanitInc.length} op(s) en cours — ${chargeLabel}">
      <div class="soins-charge-fill" style="height:${chargePct}%;background:${chargeColor}"></div>
      <span class="soins-charge-count">${sanitInc.length || ''}</span>
    </div>`;

    const incItems = linked.slice(0,3).map(i => {
      const ufStr = (i.unite_fonctionnelle||'').split(',').map(u=>u.trim()).filter(Boolean).join(' · ');
      const isOps = i.type_crise === 'CYBER' || i.impact_fonctionnel === true;
      const icon = isOps ? '⚙' : '🏥';  // indiquer visuellement ops vs clinique
      return `<div class="soins-incident-link${isOps?' soins-inc-ops':''}" title="${i.fait.replace(/"/g,'&quot;')}" style="cursor:help">
        <span>${icon} [${URG_LABELS[i.urgency]}]</span>
        ${i.fait.substring(0,60)}${i.fait.length>60?'…':''}
        ${ufStr ? `<span style="font-family:var(--mono);font-size:9px;color:var(--muted)"> ${ufStr}</span>` : ''}
      </div>`;
    }).join('');

    return `<div class="soins-card">
      <div class="soins-card-header">
        <span class="soins-pole-name">${pole}</span>
        <span class="soins-status-badge ${statusClass}">${statusLabel}</span>
      </div>
      <div class="soins-card-body">
        <div style="display:flex;gap:10px;align-items:stretch">
          ${chargeGaugeHTML}
          <div style="flex:1;min-width:0">
            ${linked.length ? incItems : '<span class="soins-empty">Aucun incident lié</span>'}
            ${linked.length > 3 ? `<div style="font-family:var(--mono);font-size:10px;color:var(--muted);margin-top:4px">+${linked.length-3} autres</div>` : ''}
          </div>
        </div>
      </div>
    </div>`;
  }).join('');

  // Redessiner la timeline si le tab soins est actif (après rendu du DOM)
  if (document.getElementById('tab-soins').classList.contains('active')) {
    requestAnimationFrame(() => renderSoinsTimeline(allIncidents));
  }
  // Appliquer les statuts capacitaires sur les cartes fraîchement rendues
  if (capData && capData.length > 0) {
    requestAnimationFrame(() => capUpdateSoinsStatuts());
  }
}

function closeSoinsAlbert() {
  document.getElementById('soins-albert-panel').style.display = 'none';
}

async function askAlbertSoins() {
  const openInc = allIncidents.filter(i => i.status !== 'RÉSOLU');
  if (!openInc.length) { toast('Aucun incident ouvert à analyser', 'err'); return; }

  // Charger le contexte cellule pour calibrer la réponse Albert
  let presences = [], decisions = [];
  try {
    presences = await (await apiFetch('/api/v1/cellule/presences')).json();
    const dList = await (await apiFetch('/api/v1/cellule/decisions')).json();
    decisions = dList.map(d => d.contenu);
    allDecisions = dList;
  } catch(e) {}

  const celluleActive = presences.length > 0;

  // Résumé des pôles impactés
  const incByPole = {};
  openInc.forEach(i => { const p=_getPoleForIncident(i); if(p){if(!incByPole[p])incByPole[p]=[];incByPole[p].push(i);} });
  const polesResume = Object.entries(incByPole)
    .map(([p,inc])=>`${p}: ${inc.length} incident(s) urgence max ${Math.max(...inc.map(i=>i.urgency))}`)
    .join('\n');

  // Ajouter l'état des services transverses au résumé des pôles
  const svcResume = serviceStatuses.map(s =>
    `[SERVICE TRANSVERSE] ${s.libelle} : ${s.statut}${s.commentaire ? ' — ' + s.commentaire : ''}`
  ).join('\n');
  const polesEtServices = [polesResume, svcResume].filter(Boolean).join('\n');

  toast('⏳ Assistant IA analyse...','ok');
  try {
    const res = await apiFetch('/api/v1/albert/situation-globale', {
      method:'POST', headers:{'Content-Type':'application/json'},
      body: JSON.stringify({
        incidents: openInc.map(i=>({fait:i.fait,analyse:i.analyse||'',status:i.status,urgency:i.urgency,type_crise:i.type_crise,site_id:i.site_id})),
        decisions,
        contexte: celluleActive
          ? `Cellule de crise activée — ${presences.length} personne(s) présente(s).`
          : 'AUCUNE cellule de crise activée. Situation de veille. Ne pas recommander d\'activation si non justifiée.',
        poles_impactes: polesEtServices || 'Aucun pôle directement identifié',
        services_transverses: serviceStatuses.map(s =>
          `${s.libelle} : ${s.statut}${s.commentaire ? ' ('+s.commentaire+')' : ''}`
        ).join('\n') || ''
      })
    });
    if (!res.ok) { const e=await res.json(); throw new Error(e.detail||'Erreur'); }
    const data = await res.json();

    // Panel latéral — ne cache PAS la grille
    const panel = document.getElementById('soins-albert-panel');
    document.getElementById('soins-albert-body').textContent = data.analyse || '';
    const lvl = data.niveau_global || 'ANALYSE';
    const lvlEl = document.getElementById('soins-albert-level');
    const c = lvl==='CRITIQUE'||lvl==='CRISE'?'#f87171':lvl==='ALERTE'?'#fbbf24':'#4ade80';
    lvlEl.textContent=lvl; lvlEl.style.color=c; lvlEl.style.background='rgba(0,0,0,.3)';
    document.getElementById('soins-albert-source').textContent = data.source||'';
    panel.style.display = 'flex';
    toast('Analyse reçue ✓','ok');
  } catch(e) { toast('IA: '+e.message,'err'); }
}


// ── TIMELINE PROJECTION ──────────────────────────────────────────────────────
// Architecture :
//  - Axe temps : NOW → farthestETA+20% (ou NOW+72h si aucun ETA)
//  - Pins = incidents avec ETA ou estimation par urgence
//  - Slider cursor déplace un "instant projeté" → recalcule les badges de pôles
//  - ETA global = dernier instant où tous les incidents sont résolus

function _buildIncidentETAs(incidents) {
  const now = Date.now();
  return incidents
    .filter(i => i.status !== 'RÉSOLU')
    .map(i => {
      const pole = _getPoleForIncident(i);
      let etaMs;
      if (i.estimated_resolution) {
        etaMs = new Date(i.estimated_resolution).getTime() - now;
        if (etaMs < 0) etaMs = 5 * 60000; // passé → dans 5min
      } else {
        // Estimation par urgence
        etaMs = URGENCY_DEFAULT_H[i.urgency] * 3600000;
      }
      const hasETA = !!i.estimated_resolution;
      return {
        id: i.id,
        pole,
        urgency: i.urgency,
        etaMs,
        hasETA,
        fait: i.fait
      };
    });
}

function _fmtDelta(ms) {
  if (ms < 0) return 'dépassé';
  const h = Math.floor(ms / 3600000);
  const m = Math.floor((ms % 3600000) / 60000);
  if (h === 0) return `${m}min`;
  if (m === 0) return `${h}h`;
  return `${h}h${String(m).padStart(2,'0')}`;
}

function _fmtAbsolute(ms) {
  const d = new Date(Date.now() + ms);
  return d.toLocaleDateString('fr-FR', {day:'2-digit',month:'2-digit'}) + ' ' +
         d.toLocaleTimeString('fr-FR', {hour:'2-digit',minute:'2-digit'});
}

function renderSoinsTimeline(incidents) {
  tlNow = Date.now();
  tlIncidentETAs = _buildIncidentETAs(incidents);

  const wrap  = document.getElementById('tl-track-wrap');
  const ticks = document.getElementById('tl-ticks');
  if (!wrap) return;

  // Calcul de la plage
  const maxEtaMs = tlIncidentETAs.length
    ? Math.max(...tlIncidentETAs.map(t => t.etaMs))
    : 72 * 3600000;
  tlRangeMs = Math.max(maxEtaMs * 1.25, 4 * 3600000); // 25% de marge, min 4h

  // Nettoyage pins existants
  wrap.querySelectorAll('.tl-pin').forEach(el => el.remove());

  const railEl = wrap.querySelector('.tl-rail');
  const railW  = railEl ? railEl.offsetWidth : wrap.offsetWidth - 4;

  // ── PINS ──
  tlIncidentETAs.forEach(t => {
    const pct = Math.min(t.etaMs / tlRangeMs, 1) * 100;
    const col = PIN_COLORS[t.urgency] || '#94a3b8';
    const pin = document.createElement('div');
    pin.className = 'tl-pin';
    pin.style.left = pct + '%';
    pin.innerHTML = `
      <div class="tl-pin-dot" style="background:${col};border-color:${col}"></div>
      <div class="tl-pin-label">U${t.urgency}${t.pole ? ' · ' + t.pole.split(' ')[0] : ''}</div>
      <div class="tl-pin-tooltip">
        <b>${t.fait.substring(0,40)}${t.fait.length>40?'…':''}</b><br>
        ETA : ${_fmtAbsolute(t.etaMs)} (dans ${_fmtDelta(t.etaMs)})
        ${t.hasETA ? '' : '<br><i style="color:#94a3b8">⚠ Estimation auto</i>'}
        ${t.pole ? `<br>Pôle : ${t.pole}` : ''}
      </div>`;
    wrap.appendChild(pin);
  });

  // ── TICKS ──
  const NB_TICKS = 7;
  ticks.innerHTML = '';
  for (let i = 0; i <= NB_TICKS; i++) {
    const pct = (i / NB_TICKS) * 100;
    const ms  = (i / NB_TICKS) * tlRangeMs;
    const tick = document.createElement('div');
    tick.className = 'tl-tick';
    tick.style.left = pct + '%';
    tick.innerHTML = `<div class="tl-tick-line"></div>${i===0?'Maintenant':_fmtDelta(ms)}`;
    ticks.appendChild(tick);
  }

  // ── ETA GLOBAL ──
  const etaEl = document.getElementById('tl-eta-global');
  if (tlIncidentETAs.length) {
    const maxEta  = Math.max(...tlIncidentETAs.map(t => t.etaMs));
    const hasAll  = tlIncidentETAs.every(t => t.hasETA);
    etaEl.textContent = `Retour normal estimé : ${_fmtAbsolute(maxEta)} (dans ${_fmtDelta(maxEta)})${hasAll?'':' ⚠'}`;
    etaEl.className = 'tl-eta-global ' + (hasAll ? 'tl-eta-ok' : 'tl-eta-pending');
  } else {
    etaEl.textContent = '— Aucun incident ouvert';
    etaEl.className   = 'tl-eta-global tl-eta-unknown';
  }

  // Curseur à sa position mémorisée (ou NOW par défaut)
  _moveCursor(tlProjectedMs / tlRangeMs * 100, false);
}

function _moveCursor(pct, updateCards = true) {
  pct = Math.max(0, Math.min(100, pct));
  tlProjectedMs = (pct / 100) * tlRangeMs;

  const cursor   = document.getElementById('tl-cursor');
  const filled   = document.getElementById('tl-rail-filled');
  if (cursor) cursor.style.left = pct + '%';
  if (filled) filled.style.width = pct + '%';

  if (updateCards) _updateCardsForProjection(tlProjectedMs);
}

function _updateCardsForProjection(offsetMs) {
  // Pour chaque pôle, regarder si TOUS ses incidents seront résolus à t=offsetMs
  const poleStatus = {};
  POLES_LIST.forEach(p => poleStatus[p] = { maxUrg: 0, anyPending: false });

  tlIncidentETAs.forEach(t => {
    if (!t.pole || !poleStatus[t.pole]) return;
    const resolved = offsetMs >= t.etaMs;
    if (!resolved) {
      poleStatus[t.pole].anyPending = true;
      poleStatus[t.pole].maxUrg = Math.max(poleStatus[t.pole].maxUrg, t.urgency);
    }
  });

  // Mettre à jour les badges visuellement
  document.querySelectorAll('.soins-card').forEach(card => {
    const poleName = card.querySelector('.soins-pole-name')?.textContent?.trim();
    if (!poleName || !poleStatus[poleName]) return;
    const badge  = card.querySelector('.soins-status-badge');
    if (!badge) return;
    const st = poleStatus[poleName];
    if (!st.anyPending) {
      // Projection : retour à la normale
      badge.className = 'soins-status-badge soins-ok';
      badge.textContent = '✓ OPÉRATIONNEL';
      card.style.opacity = offsetMs > 0 ? '0.7' : '1';
    } else {
      // Toujours impacté à cet instant
      if (st.maxUrg >= 3) { badge.className='soins-status-badge soins-critique'; badge.textContent='⚠ CRITIQUE'; }
      else                 { badge.className='soins-status-badge soins-degrade'; badge.textContent='⚡ MODE DÉGRADÉ'; }
      card.style.opacity = '1';
    }
  });

  // Afficher l'instant projeté dans le header si ≠ 0
  const lbl = document.getElementById('soins-last-update');
  if (lbl) {
    if (offsetMs > 0) {
      lbl.textContent = `⏩ Projection : +${_fmtDelta(offsetMs)} — ${_fmtAbsolute(offsetMs)}`;
      lbl.style.color = '#fbbf24';
    } else {
      lbl.textContent = `Mis à jour: ${new Date().toLocaleTimeString('fr-FR')}`;
      lbl.style.color = '';
    }
  }
}

// ── Drag sur le curseur ────────────────────────────────
(function initTimelineDrag() {
  let startX = 0, startPct = 0;

  function getRailBounds() {
    const rail = document.getElementById('tl-track-wrap');
    if (!rail) return { left: 0, width: 1 };
    const r = rail.getBoundingClientRect();
    return { left: r.left, width: r.width };
  }

  function onPointerMove(e) {
    if (!tlDragging) return;
    const { left, width } = getRailBounds();
    const x = (e.touches ? e.touches[0].clientX : e.clientX);
    const pct = ((x - left) / width) * 100;
    _moveCursor(pct);
  }

  function onPointerUp() {
    tlDragging = false;
    document.removeEventListener('mousemove', onPointerMove);
    document.removeEventListener('mouseup', onPointerUp);
    document.removeEventListener('touchmove', onPointerMove);
    document.removeEventListener('touchend', onPointerUp);
  }

  document.addEventListener('DOMContentLoaded', () => {
    const cursor = document.getElementById('tl-cursor');
    const rail   = document.getElementById('tl-track-wrap');
    if (!cursor || !rail) return;

    // Drag sur le curseur
    cursor.addEventListener('mousedown', e => {
      tlDragging = true;
      e.preventDefault();
      document.addEventListener('mousemove', onPointerMove);
      document.addEventListener('mouseup', onPointerUp);
    });
    cursor.addEventListener('touchstart', e => {
      tlDragging = true;
      document.addEventListener('touchmove', onPointerMove, {passive:true});
      document.addEventListener('touchend', onPointerUp);
    });

    // Clic direct sur le rail
    rail.addEventListener('click', e => {
      if (e.target === cursor) return;
      const r = rail.getBoundingClientRect();
      const pct = ((e.clientX - r.left) / r.width) * 100;
      _moveCursor(pct);
    });
  });
})();


async function toggleJalon(id, idx, checked) {
  const inc = allIncidents.find(i=>i.id===id);
  if(!inc||!inc.jalons) return;
  const js=JSON.parse(inc.jalons);
  js[idx].done=checked; js[idx].done_at=checked?new Date().toISOString():null;
  await apiFetch(`/api/v1/sitrep/${id}/jalons`,{method:'PUT',headers:{'Content-Type':'application/json'},body:JSON.stringify({jalons:js})});
  // Rafraîchir sans fermer la fiche courante
  await refreshAll();
  // Ré-ouvrir la fiche après le refresh (refreshAll reconstruit les fiches)
  const card = document.getElementById('inc-' + id);
  if (card && !card.classList.contains('expanded')) {
    card.classList.add('expanded');
    const btn = card.querySelector('.inc-toggle-btn');
    if (btn) btn.textContent = '▼';
  }
}

function togglePreset(btn) {
  const label=btn.dataset.label;
  if(btn.classList.contains('active')){btn.classList.remove('active');jalonsList=jalonsList.filter(j=>j!==label);}
  else{btn.classList.add('active');jalonsList.push(label);}
  renderJalonTags();
}

function addCustomJalon() {
  const val=document.getElementById('jalon-custom').value.trim();
  if(!val||jalonsList.includes(val)) return;
  jalonsList.push(val); document.getElementById('jalon-custom').value='';
  renderJalonTags();
}

function removeJalon(label) {
  jalonsList=jalonsList.filter(j=>j!==label);
  document.querySelectorAll(`[data-label="${label}"]`).forEach(b=>b.classList.remove('active'));
  renderJalonTags();
}

function renderJalonTags() {
  document.getElementById('jalon-tags').innerHTML=jalonsList.map(j=>
    `<div class="jalon-tag">${j}<span class="jtag-rm" onclick="removeJalon('${j.replace(/'/g,"\\'")}')">✕</span></div>`
  ).join('');
}

// ── CRUD ─────────────────────────────────────────────
async function submitIncident() {
  const fait=document.getElementById('fait').value.trim();
  const siteId=document.getElementById('site_id').value;
  if(!fait){toast('FAIT obligatoire','err');return;}
  if(!siteId){toast('Sélectionner un site','err');return;}

  let estimated_resolution=null;
  const h=parseFloat(document.getElementById('resolution-hours').value);
  if(h) estimated_resolution=new Date(Date.now()+h*3600000).toISOString();

  // Si une UF est en pending (sélectionnée mais pas encore ajoutée avec +), l'ajouter automatiquement
  const _hidden = document.getElementById('unite_fonctionnelle');
  if (_hidden.dataset.pendingCode && !_ufSelected.find(u => u.code === _hidden.dataset.pendingCode)) {
    _ufSelected.push({code: _hidden.dataset.pendingCode, libelle: _hidden.dataset.pendingLibelle || _hidden.dataset.pendingCode});
    _ufRenderTags();
  }

  const payload={
    declarant_nom: document.getElementById('declarant_nom').value||'Anonyme',
    directeur_crise: document.getElementById('directeur_crise').value,
    site_id: siteId,
    unite_fonctionnelle: document.getElementById('unite_fonctionnelle').value,
    type_crise: selectedCrise, urgency: selectedUrgency, fait,
    analyse: document.getElementById('analyse').value,
    moyens_engages: document.getElementById('moyens_engages').value,
    intervenant_nom: document.getElementById('intervenant_nom').value,
    intervenant_contact: document.getElementById('intervenant_contact').value,
    impact_fonctionnel: document.getElementById('impact_fonctionnel')?.checked || false,
    estimated_resolution, jalons_labels:[...jalonsList]
  };

  try {
    const res=await apiFetch('/api/v1/sitrep/post',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(payload)});
    if(!res.ok) throw new Error(await res.text());
    const newInc=await res.json();

    const files=document.getElementById('attachments-input').files;
    for(const f of files){
      const fd=new FormData(); fd.append('file',f);
      await apiFetch(`/api/v1/attachments/${newInc.id}/upload`,{method:'POST',body:fd});
    }

    ['fait','analyse','moyens_engages','intervenant_nom','intervenant_contact'].forEach(id=>document.getElementById(id).value='');
    document.getElementById('resolution-hours').value='';
    document.getElementById('attachments-input').value='';
    var _impF = document.getElementById('impact_fonctionnel'); if (_impF) _impF.checked = false;
    jalonsList=[]; renderJalonTags();
    document.querySelectorAll('.jalon-preset-btn').forEach(b=>b.classList.remove('active'));
    clearUF(); // reset multi-UF
    toast(`Incident diffusé${files.length?' + '+files.length+' PJ':''} ✓`,'ok');
    await refreshAll();
  } catch(e){toast('Erreur: '+e.message,'err');}
}

async function resoudreEtArchiver(id, e) {
  if (e) e.stopPropagation();
  const inc = allIncidents.find(i => i.id === id);
  if (!inc) return;
  const nom = (inc.fait || '').substring(0, 60);
  if (!confirm('Résoudre et archiver cet incident ?\n\n"' + nom + '"\n\nIl disparaîtra de la vue principale.')) return;
  // Tenter RÉSOLU d'abord (enregistre resolved_at)
  const r1 = await apiFetch('/api/v1/sitrep/' + id + '/status', {
    method: 'PUT',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({status: 'RÉSOLU'})
  });
  // Dans tous les cas passer en ARCHIVÉ
  await apiFetch('/api/v1/sitrep/' + id + '/status', {
    method: 'PUT',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({status: 'ARCHIVÉ'})
  });
  toast('✓ Incident résolu et archivé', 'ok');
  await refreshAll();
}

async function updateStatus(id, status) {
  // Résolution directe via bouton dédié (plus via ce select)
  const tok = localStorage.getItem('scribe_token') || '';
  await apiFetch(`/api/v1/sitrep/${id}/status`, {
    method: 'PUT',
    headers: {'Content-Type':'application/json', 'Authorization':'Bearer '+tok},
    body: JSON.stringify({status})
  });
  if (status === 'RÉSOLU')  toast('✓ Incident résolu — horodatage enregistré', 'ok');
  if (status === 'ARCHIVÉ') toast('📦 Incident archivé', 'ok');
  await refreshAll();
}

async function archiverIncident(id, e) {
  if (e) e.stopPropagation();
  const inc = allIncidents.find(i => i.id === id);
  if (!inc) return;
  if (inc.status !== 'RÉSOLU') { toast("Résoudre l'incident avant de l'archiver", 'warn'); return; }
  if (!confirm('Archiver cet incident ? Il disparaîtra de la vue principale.')) return;
  await updateStatus(id, 'ARCHIVÉ');
}

async function deleteInc(id,e) {
  e.stopPropagation();
  if(!confirm('Supprimer ?')) return;
  await apiFetch(`/api/v1/sitrep/${id}`,{method:'DELETE'});
  toast('Supprimé','ok'); await refreshAll();
}

function uploadFor(id,e) {
  e.stopPropagation();
  const inp=document.createElement('input'); inp.type='file'; inp.multiple=true;
  inp.onchange=async()=>{
    for(const f of inp.files){const fd=new FormData();fd.append('file',f);await apiFetch(`/api/v1/attachments/${id}/upload`,{method:'POST',body:fd});}
    toast(`${inp.files.length} PJ ajoutée(s) ✓`,'ok');
    // Recharger PJ de cet incident immédiatement
    try { incAttachments[id] = await apiFetch(`/api/v1/attachments/${id}`).then(r=>r.json()); } catch(_) {}
    applyFilters();
  }; inp.click();
}

// ── ALBERT ───────────────────────────────────────────
async function _callAlbert(endpoint, payload, label) {
  try {
    const token = localStorage.getItem('scribe_token');
    const res = await fetch(endpoint, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'Authorization': token ? 'Bearer ' + token : ''
      },
      body: JSON.stringify(payload)
    });
    if (res.status === 404) {
      toast('Plugin Assistant IA non actif — activez-le dans Admin > Plugins et redémarrez l\'instance', 'err');
      return null;
    }
    if (!res.ok) { const e = await res.json(); throw new Error(e.detail || 'HTTP ' + res.status); }
    return await res.json();
  } catch(e) { toast('Assistant IA (' + label + '): ' + e.message, 'err'); return null; }
}

async function askAlbertForm() {
  const fait=document.getElementById('fait').value.trim();
  if(!fait){toast('Saisir un FAIT d\'abord','err');return;}
  toast('⏳ Assistant IA analyse...','ok');
  const data=await _callAlbert('/api/v1/albert/analyser',{fait,analyse:document.getElementById('analyse').value,type_crise:selectedCrise},'incident');
  if(data) showGlobalPanel(data.niveau_alerte,data.recommandation,data.source);
}

// v2195 — Wrapper sans paramètres fait/analyse dans le onclick (qui cassait
// le parsing HTML quand fait/analyse contenaient certains caractères).
// L'incident complet est retrouvé depuis allIncidents par ID.
async function askAlbertIncidentById(incId, e) {
  if (e) e.stopPropagation();
  var id = parseInt(incId, 10);
  if (isNaN(id)) { toast('ID incident invalide', 'err'); return; }
  var inc = (allIncidents || []).find(function(i) { return i.id === id; });
  if (!inc) { toast('Incident introuvable', 'err'); return; }
  return askAlbertIncident(id, encodeURIComponent(inc.fait || ''),
    encodeURIComponent(inc.analyse || ''), inc.type_crise || '', e || {stopPropagation:function(){}});
}
window.askAlbertIncidentById = askAlbertIncidentById;

// v2195 — Idem pour quickCreateTask
function quickCreateTaskById(incId, e) {
  if (e) e.stopPropagation();
  var id = parseInt(incId, 10);
  if (isNaN(id)) { toast('ID incident invalide', 'err'); return; }
  var inc = (allIncidents || []).find(function(i) { return i.id === id; });
  if (!inc) { toast('Incident introuvable', 'err'); return; }
  var faitShort = (inc.fait || '').substring(0, 60);
  return quickCreateTask(id, encodeURIComponent(faitShort), e || {stopPropagation:function(){}});
}
window.quickCreateTaskById = quickCreateTaskById;

async function askAlbertIncident(id,fE,aE,tc,e) {
  e.stopPropagation();
  toast('⏳ Assistant IA analyse cet incident...','ok');
  const inc = allIncidents.find(i => i.id === id);
  const data = await _callAlbert('/api/v1/albert/analyser',
    {fait:decodeURIComponent(fE), analyse:decodeURIComponent(aE), type_crise:tc},
    'incident');
  if(!data) return;
  // Sauvegarder l'avis dans la base (comportement historique)
  try {
    await apiFetch(`/api/v1/sitrep/${id}/albert-avis`,{
      method:'PUT', headers:{'Content-Type':'application/json'},
      body:JSON.stringify({avis:data.recommandation})
    });
  } catch(err) {}
  toast('Analyse SCRIBE reçue — voir modal','ok');
  // v2184 : ouvrir le modal d'avis incident avec bouton Convertir en actions
  showIncidentAlbertModal(id, inc, data.recommandation || '', data.source || '');
  await refreshAll();
}

// v2184 — Modal qui affiche le rapport Albert d'un incident et propose
// de le convertir en actions Kanban / brancardages pour cet incident.
function showIncidentAlbertModal(incId, inc, recommandation, source) {
  var modal = document.getElementById('inc-albert-modal');
  if (!modal) return;
  document.getElementById('iam-titre').textContent =
    '#' + incId + ' — ' + ((inc && inc.fait) || '').substring(0,80);
  document.getElementById('iam-meta').textContent =
    (inc && inc.type_crise || '?') + ' · urgence ' + (inc && inc.urgency || '?') +
    ' · ' + (inc && inc.site_id || '');
  document.getElementById('iam-body').textContent = recommandation +
    (source ? '\n\n[' + source + ']' : '');
  // Stocker l'incident courant pour le bouton Convertir
  modal.dataset.incidentId = String(incId);
  modal.dataset.recommandation = recommandation;
  modal.style.display = 'flex';
}
function closeIncidentAlbertModal() {
  var m = document.getElementById('inc-albert-modal');
  if (m) m.style.display = 'none';
}

async function askAlbertGlobal() {
  const btn=document.getElementById('btn-global-albert');
  const open=allIncidents.filter(i=>i.status!=='RÉSOLU');
  if(!open.length){toast('Aucun incident ouvert','err');return;}
  btn.classList.add('loading'); btn.textContent='⏳ Analyse...';
  toast(`⏳ Assistant IA analyse ${open.length} incident(s)...`,'ok');

  let decs=[];
  try{const dr=await apiFetch('/api/v1/cellule/decisions');const dl=await dr.json();decs=dl.map(d=>d.contenu);}catch(e){}
  allDecisions = decs.map ? allDecisions : [];

  const data=await _callAlbert('/api/v1/albert/situation-globale',{
    incidents:open.map(i=>({fait:i.fait,analyse:i.analyse||'',status:i.status,urgency:i.urgency,type_crise:i.type_crise,site_id:i.site_id})),
    decisions:decs
  },'global');

  btn.classList.remove('loading'); btn.textContent='🧠 ANALYSE IA';
  if(data) showGlobalPanel(data.niveau_global,data.analyse,data.source);
}

function showGlobalPanel(niveau,texte,source) {
  _iaConvGlobal = [];  // Reset conversation de suivi
  document.getElementById('global-albert-panel').classList.add('show');
  document.getElementById('btn-toggle-global').style.display='';
  const lv=document.getElementById('gap-level');
  const c=niveau==='CRITIQUE'||niveau==='CRISE'?'#f87171':niveau==='ALERTE'?'#fbbf24':'#4ade80';
  const bg=niveau==='CRITIQUE'||niveau==='CRISE'?'rgba(229,62,62,.2)':niveau==='ALERTE'?'rgba(217,119,6,.2)':'rgba(22,163,74,.2)';
  lv.textContent=niveau||'ANALYSE'; lv.style.color=c; lv.style.background=bg;
  document.getElementById('gap-body').textContent=(texte||'')+'\n\n['+source+']';
  document.getElementById('global-status-txt').textContent=`Analyse: ${new Date().toLocaleTimeString('fr-FR')}`;
}

function toggleGlobalPanel() {
  const p=document.getElementById('global-albert-panel'),b=document.getElementById('btn-toggle-global');
  const s=p.classList.contains('show');p.classList.toggle('show',!s);b.textContent=s?'▼ Voir':'▲ Réduire';
}
function closeGlobalPanel() {
  document.getElementById('global-albert-panel').classList.remove('show');
  document.getElementById('btn-toggle-global').textContent='▼ Voir';
}

// ── SÉLECTEURS ───────────────────────────────────────
function selectUrgency(btn) {
  document.querySelectorAll('#urgency-selector .sel-btn').forEach(b=>b.classList.remove('sel-active'));
  btn.classList.add('sel-active'); selectedUrgency=parseInt(btn.dataset.val);
}

function selectCrise(btn) {
  document.querySelectorAll('#crise-selector .sel-btn').forEach(b=>b.classList.remove('sel-active'));
  btn.classList.add('sel-active'); selectedCrise=btn.dataset.crise;
}

// ── CELLULE ──────────────────────────────────────────
async function logPresence(action) {
  const nom=document.getElementById('p-nom').value.trim();
  if(!nom){toast('Saisir un nom','err');return;}
  const role=document.getElementById('p-role').value.trim();
  await apiFetch('/api/v1/cellule/presences',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({nom,role,action})});
  document.getElementById('p-nom').value='';document.getElementById('p-role').value='';
  toast(`${action} — ${nom} ✓`,'ok'); loadPresences();
}

async function loadPresences() {
  try{
    const list=await(await apiFetch('/api/v1/cellule/presences')).json();
    const el=document.getElementById('presence-list');
    if(!list.length){el.innerHTML='<div class="empty-state">Aucune présence</div>';return;}
    el.innerHTML=list.map(p=>{
      const t=new Date(p.timestamp).toLocaleTimeString('fr-FR',{hour:'2-digit',minute:'2-digit'});
      return `<div class="presence-entry">
        <div class="presence-time">${t}</div>
        <div class="presence-info"><div class="presence-nom">${p.nom}</div>${p.role?`<div class="presence-role">${p.role}</div>`:''}</div>
        <div class="presence-badge ${p.action==='ENTRÉE'?'entree':'sortie'}">${p.action}</div>
      </div>`;
    }).join('');
  }catch(e){}
}

async function saveDecision() {
  const texte=document.getElementById('d-texte').value.trim();
  if(!texte){toast('Saisir une décision','err');return;}
  await apiFetch('/api/v1/cellule/decisions',{method:'POST',headers:{'Content-Type':'application/json'},
    body:JSON.stringify({contenu:texte,responsable:document.getElementById('d-responsable').value.trim(),base_reglementaire:document.getElementById('d-base').value})});
  document.getElementById('d-texte').value='';document.getElementById('d-responsable').value='';
  toast('Décision actée ✓','ok'); loadDecisions();
}

async function loadDecisions() {
  try{
    const list=await(await apiFetch('/api/v1/cellule/decisions')).json();
    allDecisions=list;
    const el=document.getElementById('decision-list');
    if(!list.length){el.innerHTML='<div class="empty-state">Aucune décision</div>';return;}
    el.innerHTML=list.map(d=>{
      const t=new Date(d.timestamp).toLocaleString('fr-FR',{day:'2-digit',month:'2-digit',hour:'2-digit',minute:'2-digit'});
      return `<div class="decision-entry">
        <div class="decision-time">${t}</div>
        ${d.responsable?`<div class="decision-responsable">▶ ${d.responsable}</div>`:''}
        <div class="decision-text">${d.contenu}</div>
        <span class="decision-base">${d.base_reglementaire||'Plan Blanc'}</span>
      </div>`;
    }).join('');
  }catch(e){}
}

// ── RELÈVE ───────────────────────────────────────────
async function sendConsigne() {
  const pour=document.getElementById('r-pour').value.trim(),texte=document.getElementById('r-texte').value.trim();
  if(!pour||!texte){toast('Remplir destinataire et consigne','err');return;}
  await apiFetch('/api/v1/releve/post',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({pour,texte})});
  document.getElementById('r-pour').value='';document.getElementById('r-texte').value='';
  toast('Consigne transmise ✓','ok'); loadConsignes();
}

async function loadConsignes() {
  try{
    const list=await(await apiFetch('/api/v1/releve/history')).json();
    const el=document.getElementById('consigne-list');
    if(!list.length){el.innerHTML='<div class="empty-state">Aucune consigne</div>';return;}
    el.innerHTML=list.map(c=>{
      const t=new Date(c.timestamp).toLocaleString('fr-FR',{day:'2-digit',month:'2-digit',hour:'2-digit',minute:'2-digit'});
      const ackTs = c.accuse_at ? new Date(c.accuse_at).toLocaleTimeString('fr-FR',{hour:'2-digit',minute:'2-digit'}) : '';
      const ackPar = c.accuse_par ? ` par ${c.accuse_par}` : '';
      const ack=c.accuse
        ?`<span class="badge-accuse ok">✓ REÇU${ackPar} à ${ackTs}</span>`
        :`<button class="btn-accuse" onclick="accuserReception(${c.id})">✓ ACCUSER RÉCEPTION</button>`;
      return `<div class="consigne-item">
        <div class="consigne-header"><span class="consigne-pour">→ ${c.pour}</span><span class="consigne-time">${t}</span></div>
        <div class="consigne-text">${c.texte}</div>${ack}
      </div>`;
    }).join('');
  }catch(e){}
}

async function accuserReception(id) {
  // Demander le prénom avant d'accuser réception
  const prenom = prompt("Votre prénom pour l'accusé de réception :");
  if (prenom === null) return; // annulé
  await apiFetch(`/api/v1/releve/${id}/accuser`, {
    method: 'PUT',
    headers: {'Content-Type':'application/json', 'Authorization':'Bearer '+(localStorage.getItem('scribe_token')||'')},
    body: JSON.stringify({prenom: prenom.trim() || 'Anonyme'})
  });
  toast('Réception accusée ✓','ok'); loadConsignes();
}

// ── ANNUAIRE ─────────────────────────────────────────
let _annMsgUsers = [];
let _fedStatus = null;  // statut fédération pour messagerie inter-GHT

async function loadFedStatus() {
  try {
    const r = await apiFetch('/api/v1/federation/status');
    if (r.ok) {
      _fedStatus = await r.json();
      // Le token est maintenant retourné directement par l'API
      // Fallback sur SCRIBE_CONFIG si l'API ne le retourne pas (ancienne version)
      if (_fedStatus && !_fedStatus.token && SCRIBE_CONFIG?.federation?.token) {
        _fedStatus.token = SCRIBE_CONFIG.federation.token;
      }
    }
  } catch(e) {}
}
let _annInterGHT = [];
let _heartbeatInterval = null;

// ── HEARTBEAT (présence en ligne) ─────────────────────────────────────────────
function startHeartbeat() {
  if (_heartbeatInterval) return;
  const ping = () => apiFetch('/api/v1/auth/heartbeat', {method:'POST', headers: authHeaders()}).catch(()=>{});
  ping();
  _heartbeatInterval = setInterval(ping, 30000);
}

function switchAnnuaire(mode, btn) {
  annuaireMode = mode;
  document.querySelectorAll('.ann-mode-btn').forEach(b => b.classList.remove('active'));
  if (btn) btn.classList.add('active');
  const classic = document.getElementById('ann-pane-classic');
  const msgPane = document.getElementById('ann-pane-messagerie');
  if (mode === 'messagerie') {
    if (classic) classic.style.display = 'none';
    if (msgPane) msgPane.style.display = 'flex';
    loadAnnuaireMessagerie();
  } else {
    if (classic) classic.style.display = '';
    if (msgPane) msgPane.style.display = 'none';
    document.getElementById('ann-search').value = '';
    renderAnnuaire();
  }
}

async function loadAnnuaireMessagerie() {
  const list = document.getElementById('ann-msg-list');
  const siteSel = document.getElementById('ann-msg-site-filter');
  if (!list) return;
  list.innerHTML = '<div style="font-family:var(--mono);font-size:9px;color:var(--muted);padding:12px">Chargement...</div>';

  // Charger contacts locaux + inter-GHT en parallèle
  const [rLocal, rGHT] = await Promise.allSettled([
    apiFetch('/api/v1/auth/annuaire-messagerie'),
    apiFetch('/api/v1/federation/annuaire-inter-ght'),
  ]);

  _annMsgUsers = rLocal.status === 'fulfilled' && rLocal.value.ok
    ? await rLocal.value.json() : [];
  
  // Charger l'annuaire agrégé depuis le collecteur si disponible
  let interGHT = rGHT.status === 'fulfilled' && rGHT.value.ok
    ? await rGHT.value.json() : [];
  
  // Tenter aussi l'annuaire direct du collecteur (plus complet)
  try {
    const fedStatus = await apiFetch('/api/v1/federation/status');
    if (fedStatus.ok) {
      const fed = await fedStatus.json();
      if (fed.ready && fed.collecteur_url) {
        const collBase = fed.collecteur_url.replace('/api/push', '');
        const rAnn = await fetch(collBase + '/api/annuaire').catch(()=>null);
        if (rAnn && rAnn.ok) {
          const annData = await rAnn.json();
          // Convertir en format _annInterGHT
          interGHT = annData.map(ght => ({
            ght: ght.sigle,
            ght_nom: ght.nom || ght.sigle,
            contacts: (ght.contacts || []).map(c => ({...c, online: 'unknown'})),
            niveau_global: 'NOMINAL',
            unavailable: ght.unavailable || false,
          }));
        }
      }
    }
  } catch(e) {}
  
  _annInterGHT = interGHT;

  // Peupler filtre site
  if (siteSel) {
    const sites = [...new Set(_annMsgUsers.map(u => u.site_tag).filter(Boolean))].sort();
    siteSel.innerHTML = '<option value="">Tous les sites</option>' +
      sites.map(s => `<option value="${s}">${s}</option>`).join('');
  }
  annMsgFilter();
}

function _onlineDot(status, label) {
  const colors = {
    online: '#4ade80',   // vert : actif maintenant
    today:  '#60a5fa',   // bleu : connecté aujourd'hui
    recent: '#f87171',   // rouge (legacy)
    never:  '#6b7280',   // gris : jamais connecté
    offline:'#6b7280',   // gris : déconnecté > 24h
    unknown:'#d1d5db'
  };
  const titles = {
    online: 'En ligne',
    today:  label || "Connecté aujourd'hui",
    recent: 'Connecté récemment',
    never:  'Jamais connecté',
    offline:'Hors ligne (> 24h)',
    unknown:'Statut inconnu (GHT distant)'
  };
  const c = colors[status] || '#6b7280';
  const t = titles[status] || '';
  return `<span title="${t}" style="display:inline-block;width:8px;height:8px;border-radius:50%;background:${c};flex-shrink:0"></span>`;
}

function annMsgFilter() {
  const search = (document.getElementById('ann-msg-search')?.value||'').toLowerCase();
  const site   = document.getElementById('ann-msg-site-filter')?.value||'';
  const list   = document.getElementById('ann-msg-list');
  if (!list) return;

  let filtered = _annMsgUsers;
  if (site)   filtered = filtered.filter(u => u.site_tag === site);
  if (search) filtered = filtered.filter(u =>
    (u.display_name||'').toLowerCase().includes(search) ||
    (u.username||'').toLowerCase().includes(search) ||
    (u.service||'').toLowerCase().includes(search) ||
    (u.site_tag||'').toLowerCase().includes(search)
  );

  let html = '';

  // ── Section GHT local ──
  if (filtered.length) {
    // Grouper par site
    const bySite = {};
    filtered.forEach(u => { const s = u.site_tag||'—'; if (!bySite[s]) bySite[s]=[]; bySite[s].push(u); });
    html += `<div style="font-family:var(--mono);font-size:8px;color:var(--blue);letter-spacing:1px;padding:4px 4px 2px;margin-bottom:2px;font-weight:700">📍 MON GHT</div>`;
    Object.entries(bySite).sort(([a],[b])=>a.localeCompare(b)).forEach(([site, users]) => {
      html += `<div style="margin-bottom:8px">
        <div style="font-family:var(--mono);font-size:8px;color:var(--muted2);letter-spacing:1px;padding:2px 4px;border-bottom:1px solid var(--border);margin-bottom:2px">${site.toUpperCase()}</div>`;
      users.forEach(u => {
        html += `<div style="display:flex;align-items:center;gap:7px;padding:5px 6px;border-radius:4px;cursor:pointer" onmouseover="this.style.background='var(--surface2)'" onmouseout="this.style.background='transparent'">
          ${_onlineDot(u.online, u.inactivity_label)}
          <div style="flex:1;min-width:0">
            <div style="font-family:var(--mono);font-size:10px;color:var(--text);white-space:nowrap;overflow:hidden;text-overflow:ellipsis">${u.display_name||u.username}</div>
            <div style="font-family:var(--mono);font-size:8px;color:var(--muted)">${u.service||u.username}${u.inactivity_label && u.online==='today' ? ` · <span style="color:#60a5fa">${u.inactivity_label}</span>` : u.online==='online' ? ` · <span style="color:#4ade80">En ligne</span>` : ''}</div>
          </div>
          <div style="display:flex;gap:3px;flex-shrink:0">
            <button onclick="msgOpenComposeDirect(${u.id})" title="Écrire un message" style="font-family:var(--mono);font-size:8px;padding:2px 7px;background:var(--blue);border:none;border-radius:3px;color:#fff;cursor:pointer">✉️</button>
            <button onclick="navigator.clipboard.writeText('${u.display_name||u.username}').then(()=>toast('✓ Copié','ok')).catch(()=>{})" title="Copier le nom" style="font-family:var(--mono);font-size:8px;padding:2px 6px;background:transparent;border:1px solid var(--border2);border-radius:3px;color:var(--muted);cursor:pointer">📋</button>
          </div>
        </div>`;
      });
      html += '</div>';
    });
  } else if (!search && !site) {
    html += '<div style="font-family:var(--mono);font-size:9px;color:var(--muted);padding:8px">Aucun correspondant local</div>';
  } else {
    html += '<div style="font-family:var(--mono);font-size:9px;color:var(--muted);padding:8px">Aucun résultat</div>';
  }

  // ── Section Inter-GHT ──
  if (_annInterGHT.length > 0 && !site) {
    html += `<div style="font-family:var(--mono);font-size:8px;color:var(--cyan,#67e8f9);letter-spacing:1px;padding:8px 4px 2px;margin-top:4px;font-weight:700;border-top:1px solid var(--border)">🌐 AUTRES GHT (SUPERVISION)</div>`;
    _annInterGHT.forEach(ght => {
      const niveauColor = ght.niveau_global === 'CRISE' ? '#f87171' : ght.niveau_global === 'ALERTE' ? '#fb923c' : '#4ade80';
      html += `<div style="margin-bottom:8px">
        <div style="font-family:var(--mono);font-size:8px;letter-spacing:1px;padding:2px 4px;border-bottom:1px solid var(--border);margin-bottom:2px;display:flex;align-items:center;gap:6px">
          <span style="width:7px;height:7px;border-radius:50%;background:${niveauColor};display:inline-block"></span>
          <span style="color:var(--muted2)">${ght.ght}</span>
          <span style="color:var(--muted);font-size:7px">${ght.ght_nom||''}</span>
        </div>`;
      if (ght.unavailable) {
        html += `<div style="font-family:var(--mono);font-size:8px;color:var(--muted);padding:4px 6px;opacity:0.7">⚠ Instance non joignable</div>`;
      } else if (!(ght.contacts||[]).length) {
        html += `<div style="font-family:var(--mono);font-size:8px;color:var(--muted);padding:4px 6px;opacity:0.7">Annuaire non disponible</div>`;
      }
      // Filtrer par recherche
      let filteredContacts = (ght.contacts||[]);
      if (search) filteredContacts = filteredContacts.filter(c =>
        (c.display_name||'').toLowerCase().includes(search) ||
        (c.service||'').toLowerCase().includes(search)
      );
      filteredContacts.slice(0, 20).forEach(c => {
        html += `<div style="display:flex;align-items:center;gap:7px;padding:4px 6px;opacity:0.85">
          <span title="Statut inconnu (GHT distant)" style="display:inline-block;width:8px;height:8px;border-radius:50%;background:#6b7280;border:1px dashed #9ca3af;flex-shrink:0"></span>
          <div style="flex:1;min-width:0">
            <div style="font-family:var(--mono);font-size:10px;color:var(--text)">${c.display_name||c.username||'—'}</div>
            <div style="font-family:var(--mono);font-size:8px;color:var(--muted)">${c.service||c.role||'—'}</div>
          </div>
        </div>`;
      });
      if (filteredContacts.length > 20) {
        html += `<div style="font-family:var(--mono);font-size:7px;color:var(--muted);padding:2px 6px">… et ${filteredContacts.length - 20} autres</div>`;
      }
      html += '</div>';
    });
  }

  list.innerHTML = html || '<div style="font-family:var(--mono);font-size:9px;color:var(--muted);padding:8px">Aucun correspondant</div>';
}

async function msgOpenComposeDirect(userId, displayName) {
  // Naviguer vers l'onglet messagerie d'abord
  const msgBtn = document.getElementById('tab-btn-messagerie');
  if (msgBtn) {
    openTab('tab-messagerie', msgBtn);
  }
  await msgOpenCompose();
  // Pré-sélectionner le destinataire
  const sel = document.getElementById('msg-compose-dest');
  if (sel) {
    sel.value = String(userId);
    // Si pas trouvé (filtre site actif), charger tous
    if (!sel.value || sel.value !== String(userId)) {
      await loadAnnuaireMessagerie();
      await msgOpenCompose();
      const sel2 = document.getElementById('msg-compose-dest');
      if (sel2) sel2.value = String(userId);
    }
  }
  // Fermer l'annuaire et afficher la fenêtre compose
  document.getElementById('msg-modal-compose').style.display = 'flex';
}

function renderAnnuaire(filter='') {
  const data = annuaireMode==='secours' ? ANNUAIRE_SECOURS : ANNUAIRE_NORMAL;
  const q = filter.toLowerCase();
  const filtered = q ? data.filter(e =>
    e.service.toLowerCase().includes(q) ||
    (e.local||'').toLowerCase().includes(q) ||
    e.tel.includes(q)
  ) : data;

  const el = document.getElementById('annuaire-list');
  if (!filtered.length) { el.innerHTML='<div class="empty-state">Aucun résultat</div>'; return; }

  // Grouper par première lettre du service
  const grouped = {};
  filtered.forEach(e => {
    const key = e.service[0].toUpperCase();
    if (!grouped[key]) grouped[key]=[]; grouped[key].push(e);
  });

  const badge = annuaireMode==='secours'
    ? '<span class="ann-secours-badge">🚨 SECOURS</span>'
    : '<span class="ann-normal-badge">📗 NOMINALE</span>';

  el.innerHTML = Object.keys(grouped).sort().map(letter => `
    <div class="ann-group">
      <div class="ann-group-header">${letter}</div>
      ${grouped[letter].map(e => {
        const initials = e.service.split(/[\s-\/]+/).filter(w=>w.length>2).slice(0,2).map(w=>w[0]).join('');
        const noteHtml = e.note ? `<div style="font-family:var(--mono);font-size:9px;color:var(--muted);margin-top:2px">${e.note}</div>` : '';
        return `<div class="ann-entry">
          <div class="ann-avatar">${initials||e.service[0]}</div>
          <div class="ann-info">
            <div class="ann-name">${e.service}</div>
            <div class="ann-service">${e.local||''}</div>
            ${noteHtml}
          </div>
          <div class="ann-phones">
            <div class="ann-phone">${e.tel}</div>
            ${badge}
          </div>
        </div>`;
      }).join('')}
    </div>
  `).join('');
}

function filterAnnuaire() {
  renderAnnuaire(document.getElementById('ann-search').value);
}

// ── TOAST ────────────────────────────────────────────
let toastTimer;
function toast(msg,type='ok') {
  const el=document.getElementById('toast');
  el.textContent=msg;el.className=`show ${type}`;
  clearTimeout(toastTimer);toastTimer=setTimeout(()=>el.className='',3500);
}

/* ═══════════════════ SCRIBE v5 — NEW JS ══════════════════ */

// ── AUTH STATE ────────────────────────────────────────────
let currentUser = null;
let authToken = null;
let notifInterval = null;

// ── LOGIN ─────────────────────────────────────────────────
async function doLogin() {
  const username = document.getElementById('login-user').value.trim();
  const password = document.getElementById('login-pass').value;
  const errEl = document.getElementById('login-err');
  errEl.classList.remove('show');
  try {
    const r = await fetch('/api/v1/auth/login', {
      method:'POST', headers:{'Content-Type':'application/json'},
      body: JSON.stringify({username, password})
    });
    if (!r.ok) {
      const msg = r.status === 401 ? 'Identifiants incorrects' : 'Erreur serveur ' + r.status;
      errEl.textContent = msg;
      errEl.classList.add('show');
      document.getElementById('login-pass').value = '';
      document.getElementById('login-pass').focus();
      return;
    }
    const data = await r.json();

    // v2315 — Si le compte a MFA activé, le backend renvoie
    // {require_mfa: true, mfa_token: ...} au lieu du JWT final.
    // On ouvre un prompt pour le code TOTP puis on rappelle /mfa/verify.
    if (data && data.require_mfa && data.mfa_token) {
      mfaPromptForCode(data.mfa_token, data.username || username);
      return;
    }

    authToken = data.token;
    currentUser = data.user;
    localStorage.setItem('scribe_token', authToken);
    localStorage.setItem('scribe_user', JSON.stringify(currentUser));
    applyUserState();
    startHeartbeat();
    await initAfterLogin();
    window.__scribe_auth_ready = true;
    window.dispatchEvent(new CustomEvent('scribe-auth-ready'));
    document.getElementById('login-overlay').classList.add('hidden');
    // Forcer changement de mot de passe si flag activé
    if (currentUser.must_change_password) {
      setTimeout(() => openForcedPasswordChange(), 400);
    }
  } catch(e) {
    errEl.textContent = 'Erreur réseau — serveur inaccessible';
    errEl.classList.add('show');
  }
}

// v2315 — Prompt MFA en phase 2 : user+password déjà validés, on
// demande le code TOTP (ou code de backup). En cas de succès, le JWT
// de session est délivré et on continue comme un login normal.
function mfaPromptForCode(mfaToken, username) {
  let modal = document.getElementById('mfa-login-modal');
  if (modal) modal.remove();
  modal = document.createElement('div');
  modal.id = 'mfa-login-modal';
  modal.style.cssText = 'position:fixed;inset:0;background:rgba(0,0,0,.75);z-index:11000;display:flex;align-items:center;justify-content:center;padding:20px;font-family:var(--mono),monospace';
  modal.innerHTML = `
    <div style="background:var(--bg,#1a1a1a);border:1px solid var(--border,#333);border-radius:10px;padding:26px;max-width:400px;width:100%;color:var(--text,#e5e5e5)">
      <h3 style="margin:0 0 8px;font-size:13px;letter-spacing:1.5px">🔐 Vérification à double facteur</h3>
      <p style="font-size:10px;color:var(--muted,#94a3b8);line-height:1.6;margin:0 0 16px">
        Compte <strong>${username}</strong> · Saisis le code à 6 chiffres affiché dans
        ton application d'authentification, ou un code de backup.
      </p>
      <input type="text" id="mfa-login-code" placeholder="000000"
        autocomplete="one-time-code" inputmode="numeric"
        style="width:100%;padding:12px 14px;background:var(--surface,#222);border:1px solid var(--border,#333);border-radius:4px;color:var(--text,#e5e5e5);font-family:var(--mono);font-size:20px;text-align:center;letter-spacing:4px;margin-bottom:10px">
      <div id="mfa-login-err" style="font-size:10px;color:#f87171;min-height:14px;margin-bottom:10px"></div>
      <div style="display:flex;gap:8px;justify-content:flex-end">
        <button onclick="mfaLoginCancel()" style="font-family:var(--mono);font-size:10px;padding:9px 14px;background:transparent;border:1px solid var(--border2,#555);border-radius:4px;color:var(--muted,#94a3b8);cursor:pointer">Annuler</button>
        <button onclick="mfaLoginSubmit()" id="mfa-login-submit" style="font-family:var(--mono);font-size:10px;padding:9px 18px;background:rgba(99,102,241,.15);border:1px solid #6366f1;border-radius:4px;color:#818cf8;cursor:pointer;font-weight:700">Valider</button>
      </div>
    </div>
  `;
  document.body.appendChild(modal);
  // Stocker le token pour l'utiliser dans mfaLoginSubmit
  window._pendingMfaToken = mfaToken;
  setTimeout(() => {
    const input = document.getElementById('mfa-login-code');
    if (input) {
      input.focus();
      // Submit automatique quand 6 chiffres sont saisis
      input.addEventListener('input', () => {
        const v = input.value.replace(/\s/g, '');
        if (v.length === 6 && /^\d+$/.test(v)) {
          mfaLoginSubmit();
        }
      });
      input.addEventListener('keydown', (e) => {
        if (e.key === 'Enter') mfaLoginSubmit();
      });
    }
  }, 50);
}

function mfaLoginCancel() {
  const m = document.getElementById('mfa-login-modal');
  if (m) m.remove();
  window._pendingMfaToken = null;
  // Redonner le focus au champ mot de passe
  const pass = document.getElementById('login-pass');
  if (pass) { pass.value = ''; pass.focus(); }
}

async function mfaLoginSubmit() {
  const code = (document.getElementById('mfa-login-code').value || '').trim();
  const err = document.getElementById('mfa-login-err');
  const submitBtn = document.getElementById('mfa-login-submit');
  err.textContent = '';
  if (!code) { err.textContent = 'Code requis'; return; }
  if (!window._pendingMfaToken) { err.textContent = 'Session expirée, recommence le login'; return; }
  if (submitBtn) { submitBtn.disabled = true; submitBtn.textContent = '⏳ …'; }
  try {
    const r = await fetch('/api/v1/mfa/verify', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({mfa_token: window._pendingMfaToken, code: code})
    });
    if (!r.ok) {
      const e = await r.json().catch(()=>({detail: 'HTTP ' + r.status}));
      err.textContent = e.detail || 'Code incorrect';
      if (submitBtn) { submitBtn.disabled = false; submitBtn.textContent = 'Valider'; }
      // Reset + refocus
      const input = document.getElementById('mfa-login-code');
      if (input) { input.value = ''; input.focus(); }
      return;
    }
    const data = await r.json();
    // Tear down modal + continue login normalement
    const m = document.getElementById('mfa-login-modal');
    if (m) m.remove();
    window._pendingMfaToken = null;
    authToken = data.token;
    currentUser = data.user;
    localStorage.setItem('scribe_token', authToken);
    localStorage.setItem('scribe_user', JSON.stringify(currentUser));
    applyUserState();
    startHeartbeat();
    await initAfterLogin();
    window.__scribe_auth_ready = true;
    window.dispatchEvent(new CustomEvent('scribe-auth-ready'));
    document.getElementById('login-overlay').classList.add('hidden');
    if (data.used_backup_code) {
      setTimeout(() => {
        toast('⚠ Code de backup utilisé — pense à régénérer ta liste', 'warn');
      }, 800);
    }
  } catch(e) {
    err.textContent = 'Erreur réseau : ' + e.message;
    if (submitBtn) { submitBtn.disabled = false; submitBtn.textContent = 'Valider'; }
  }
}

// ── Archiver crise (sans reset) ────────────────────────────────────────
// v2307-hotfix — Archivage enrichi avec option "générer un scénario
// rejouable". Plutôt qu'un confirm() basique, un petit modal maison
// permet de cocher la génération de scenario.json et de saisir un
// titre. Flow : archive ZIP classique (CSV incidents/décisions/...)
// + scenario.json s'il a été demandé.
async function archiverCrise() {
  // Construire et afficher un modal
  const existing = document.getElementById('archive-modal');
  if (existing) existing.remove();

  const modal = document.createElement('div');
  modal.id = 'archive-modal';
  modal.style.cssText = 'position:fixed;inset:0;background:rgba(0,0,0,.6);z-index:10000;display:flex;align-items:center;justify-content:center;font-family:var(--mono),monospace';
  modal.innerHTML = `
    <div style="background:var(--bg,#1a1a1a);border:1px solid var(--border,#333);border-radius:8px;padding:24px;max-width:520px;width:90%;color:var(--text,#e5e5e5);font-size:11px">
      <h3 style="margin:0 0 16px;font-size:13px;letter-spacing:1px">📦 Archiver la crise</h3>
      <p style="color:var(--muted,#94a3b8);line-height:1.6;margin:0 0 14px">
        Un fichier ZIP sera créé contenant les incidents, décisions, kanban,
        relève, communiqués. Le tableau de bord ne sera <strong>pas</strong> réinitialisé.
      </p>
      <div style="padding:12px;background:var(--surface,#222);border:1px solid var(--border,#333);border-radius:4px;margin-bottom:14px">
        <label style="display:flex;align-items:flex-start;gap:10px;cursor:pointer">
          <input type="checkbox" id="arch-opt-scenario" style="margin-top:2px">
          <div>
            <div style="color:var(--text,#e5e5e5);font-weight:700;margin-bottom:4px">
              🎬 Générer aussi un scénario rejouable
            </div>
            <div style="color:var(--muted,#94a3b8);line-height:1.5;font-size:10px">
              Ajoute un fichier <code>scenario.json</code> au ZIP, reconstituant
              le déroulé de la crise. Utilisable pour rejouer la crise en
              exercice et valider les mesures de remédiation mises en place.
            </div>
          </div>
        </label>
        <div id="arch-opt-scenario-fields" style="display:none;margin-top:10px;padding-top:10px;border-top:1px solid var(--border,#333)">
          <label style="display:block;color:var(--muted,#94a3b8);font-size:9px;letter-spacing:1px;margin-bottom:4px">TITRE DU SCÉNARIO (optionnel)</label>
          <input type="text" id="arch-scenario-titre"
                 placeholder="ex: REX Ransomware 2026-04 — rejouage annuel"
                 style="width:100%;padding:6px 10px;background:var(--bg,#1a1a1a);border:1px solid var(--border,#333);border-radius:3px;color:var(--text,#e5e5e5);font-family:var(--mono);font-size:10px;margin-bottom:10px">
          <label style="display:flex;align-items:center;gap:8px;color:var(--muted,#94a3b8);font-size:10px;cursor:pointer">
            <input type="checkbox" id="arch-scenario-anon" checked>
            Anonymiser (masquer noms, tél, email, IPP, NIR — <strong>recommandé</strong> pour partage)
          </label>
        </div>
      </div>
      <div style="display:flex;gap:10px;justify-content:flex-end">
        <button id="arch-cancel"
                style="font-family:var(--mono);font-size:10px;padding:7px 16px;background:transparent;border:1px solid var(--border2,#555);border-radius:4px;color:var(--muted,#94a3b8);cursor:pointer">
          Annuler
        </button>
        <button id="arch-confirm"
                style="font-family:var(--mono);font-size:10px;padding:7px 18px;background:rgba(99,102,241,.15);border:1px solid #6366f1;border-radius:4px;color:#818cf8;cursor:pointer;font-weight:700">
          📦 Archiver
        </button>
      </div>
    </div>
  `;
  document.body.appendChild(modal);

  // Toggle fields scenario
  const cbScenario = document.getElementById('arch-opt-scenario');
  cbScenario.addEventListener('change', () => {
    document.getElementById('arch-opt-scenario-fields').style.display = cbScenario.checked ? 'block' : 'none';
  });

  // Handlers
  return new Promise((resolve) => {
    document.getElementById('arch-cancel').addEventListener('click', () => {
      modal.remove(); resolve(false);
    });
    document.getElementById('arch-confirm').addEventListener('click', async () => {
      const genScenario = cbScenario.checked;
      const anon = document.getElementById('arch-scenario-anon').checked;
      const titre = (document.getElementById('arch-scenario-titre').value || '').trim();
      modal.remove();
      toast("Archivage en cours...", "info");
      try {
        const params = new URLSearchParams();
        if (genScenario) params.set('generer_scenario', 'true');
        if (genScenario) params.set('anonymiser', anon ? 'true' : 'false');
        if (genScenario && titre) params.set('titre_scenario', titre);
        const url = '/api/v1/rapport/archiver-crise' + (params.toString() ? '?' + params.toString() : '');
        const r = await apiFetch(url, { method: "POST" });
        if (!r.ok) { toast("Erreur archivage : " + r.status, "err"); resolve(false); return; }
        const d = await r.json();
        toast(d.scenario_inclus ? "Archive créée + scénario rejouable inclus" : "Archive créée", "ok");
        if (d.archive) {
          const nomFichier = d.archive.split('/').pop();
          const lien = document.createElement('a');
          lien.href = '/api/v1/rapport/telecharger-archive?nom=' + encodeURIComponent(nomFichier);
          lien.download = nomFichier;
          document.body.appendChild(lien);
          lien.click();
          document.body.removeChild(lien);
        }
        resolve(true);
      } catch(e) {
        toast("Erreur : " + e.message, "err");
        resolve(false);
      }
    });
  });
}

// ── Reset tableau de bord (sans archiver) ──────────────────────────────
async function resetTableauDeBord() {
  const ok1 = confirm(
    "REMETTRE À ZÉRO\n\n" +
    "Cette action va effacer :\n" +
    "  Incidents, décisions, kanban, relève, communiqués\n\n" +
    "⚠️ Cette action est irréversible.\n" +
    "Pensez à archiver d'abord si ce n'est pas fait.\n\n" +
    "Confirmer la remise à zéro ?"
  );
  if (!ok1) return;
  const ok2 = confirm("Êtes-vous certain ? Toutes les données seront perdues.");
  if (!ok2) return;
  const token = localStorage.getItem("scribe_token") || "";
  try {
    const r = await apiFetch("/api/v1/rapport/reset-tableau-de-bord", {
      method: "POST",
      headers: { "Authorization": "Bearer " + token }
    });
    if (!r.ok) { toast("Erreur reset : " + r.status, "err"); return; }
    toast("Tableau de bord remis à zéro !", "ok");
    setTimeout(() => location.reload(), 1200);
  } catch(e) {
    toast("Erreur : " + e.message, "err");
  }
}

// ── Nouvelle crise (archive + reset en séquence) ────────────────────────
async function confirmNouvelleCrise() {
  // Etape 1 : confirmation
  const ok1 = confirm(
    "NOUVELLE CRISE\n\n" +
    "Cette action va archiver la crise en cours :\n" +
    "  Incidents, decisions, kanban, releve, communiques\n\n" +
    "Les sites, UF, annuaire et configuration seront conserves.\n\n" +
    "Etes-vous sur de vouloir archiver la crise en cours ?"
  );
  if (!ok1) return;

  toast("Archivage en cours...", "info");
  const token = localStorage.getItem("scribe_token") || "";

  try {
    const r = await apiFetch("/api/v1/rapport/nouvelle-crise", {
      method: "POST",
      headers: { "Authorization": "Bearer " + token }
    });
    if (!r.ok) {
      const err = await r.json().catch(() => ({}));
      toast("Erreur archivage : " + (err.detail || r.status), "err");
      return;
    }
    const d = await r.json();

    // Etape 2 : confirmation reset
    const archive = d.archive || "archives/";
    const ok2 = confirm(
      "Archive creee avec succes !\n\n" +
      "Fichier : " + archive + "\n\n" +
      "Voulez-vous remettre le tableau de bord a zero maintenant ?"
    );
    if (ok2) {
      toast("Tableau de bord reinitialise !", "ok");
      setTimeout(() => location.reload(), 1200);
    } else {
      toast("Archive creee. Le tableau de bord n'a pas ete reinitialise.", "warn");
    }
  } catch(e) {
    toast("Erreur : " + e.message, "err");
  }
}

function applyUserState() {
  if (!currentUser) return;
  const nameEl = document.getElementById('current-user-name');
  const dotEl  = document.getElementById('role-dot');
  if (nameEl) nameEl.textContent = currentUser.display_name || currentUser.username;
  if (dotEl)  { dotEl.className = 'role-dot' + (currentUser.role === 'admin' ? ' admin' : ''); }
  // S'assurer que le chip utilisateur est visible
  const chip = document.getElementById('user-chip');
  if (chip) {
    chip.style.display = 'flex';
    chip.title = currentUser.role === 'admin' ? 'Panneau admin' : 'Mon compte';
  }
  // Bouton Admin visible uniquement pour les admins
  const adminBtn = document.getElementById('user-menu-admin');
  if (adminBtn) adminBtn.style.display = currentUser.role === 'admin' ? 'block' : 'none';
  const hdrAdminBtn = document.getElementById('hdr-admin-btn');
  if (hdrAdminBtn) hdrAdminBtn.style.display = currentUser.role === 'admin' ? 'inline-flex' : 'none';
  // Start polling notifications
  if (notifInterval) clearInterval(notifInterval);
  loadNotifications();
  notifInterval = setInterval(loadNotifications, 15000);
  // Polling badge inter-GHT (messages supervision + demandes)
  pollIGHTBadge();
  setInterval(pollIGHTBadge, 20000);
}

function authHeaders() {
  return authToken ? {'Authorization': 'Bearer ' + authToken, 'Content-Type': 'application/json'} : {'Content-Type': 'application/json'};
}

// Fetch avec détection automatique de session expirée
async function apiFetch(url, opts = {}) {
  // Toujours inclure Authorization — merger avec les headers fournis
  const base = authToken ? {'Authorization': 'Bearer ' + authToken} : {};
  opts.headers = Object.assign({}, base, opts.headers || {});
  const r = await fetch(url, opts);
  if (r.status === 401) {
    // Token invalide/expiré ou absent → forcer re-login
    const wasConnected = !!authToken;
    authToken = null; currentUser = null;
    localStorage.removeItem('scribe_token');
    localStorage.removeItem('scribe_user');
    if (_heartbeatInterval) { clearInterval(_heartbeatInterval); _heartbeatInterval = null; }
    if (notifInterval)      { clearInterval(notifInterval);      notifInterval = null; }
    const overlay = document.getElementById('login-overlay');
    if (overlay) { overlay.classList.remove('hidden'); overlay.style.display = 'flex'; }
    if (wasConnected) toast('⚠ Session expirée — reconnexion requise', 'warn');
  }
  return r;
}

// On load: restore session avec vérification serveur
window.addEventListener('load', async () => {
  // Auto-login via ?autotoken= dans l'URL (utilisé par l'iframe de supervision exercice)
  const _urlParams = new URLSearchParams(window.location.search);
  const _autoToken = _urlParams.get('autotoken');
  if (_autoToken) {
    // Purger immédiatement tout token précédent pour éviter que les plugins
    // (chat, exercice) partent avec un JWT périmé pendant qu'on valide le nouveau.
    try {
      localStorage.removeItem('scribe_token');
      localStorage.removeItem('scribe_user');
    } catch(e) {}
    try {
      const _r = await fetch('/api/v1/auth/me', {
        headers: {'Authorization': 'Bearer ' + _autoToken}
      });
      if (_r.ok) {
        authToken = _autoToken;
        currentUser = await _r.json();
        localStorage.setItem('scribe_token', _autoToken);
        localStorage.setItem('scribe_user', JSON.stringify(currentUser));
        // v2312-hotfix — Cacher l'overlay de login IMMÉDIATEMENT avant
        // initAfterLogin() qui peut prendre plusieurs secondes. Sinon
        // l'utilisateur voit encore l'écran de login même si le JWT a
        // déjà été accepté côté data → impression "SSO ne marche pas".
        const _ovl = document.getElementById('login-overlay');
        if (_ovl) _ovl.classList.add('hidden');
        applyUserState();
        startHeartbeat();
        await initAfterLogin();
        // Signaler aux plugins (chat, exercice…) que l'auth est prête
        window.__scribe_auth_ready = true;
        window.dispatchEvent(new CustomEvent('scribe-auth-ready'));
        // Supprimer le token de l'URL sans recharger
        const _clean = window.location.pathname;
        window.history.replaceState({}, '', _clean);
        return;
      } else {
        // v2312-hotfix — Diagnostic si l'autologin échoue, pour aider au
        // debug. Avant on ignorait silencieusement et fallback login manuel.
        console.warn('[SCRIBE autologin] Token refusé par /api/v1/auth/me: HTTP ' + _r.status);
      }
    } catch(e) {
      console.warn('[SCRIBE autologin] Erreur réseau validation token:', e);
      /* ignore, fall through to normal login */
    }
  }
  const tok = localStorage.getItem('scribe_token');
  const usr = localStorage.getItem('scribe_user');
  if (tok && usr) {
    authToken = tok;
    // Tenter de vérifier le token — avec retry en cas d'erreur réseau
    let verified = false;
    let isNetworkError = false;
    for (let attempt = 0; attempt < 3; attempt++) {
      try {
        const r = await fetch('/api/v1/auth/me', {
          headers: {'Authorization': 'Bearer ' + tok},
          signal: AbortSignal.timeout(5000)
        });
        if (r.ok) {
          currentUser = await r.json();
          localStorage.setItem('scribe_user', JSON.stringify(currentUser));
          verified = true;
          break;
        } else if (r.status === 401) {
          // Token vraiment invalide → pas de retry
          break;
        }
        // Autre erreur HTTP (503, 500) → retry
        isNetworkError = true;
      } catch(e) {
        // Erreur réseau ou timeout → retry
        isNetworkError = true;
        if (attempt < 2) await new Promise(res => setTimeout(res, 1500));
      }
    }
    if (verified) {
      applyUserState();
      startHeartbeat();
      await initAfterLogin();
      window.__scribe_auth_ready = true;
      window.dispatchEvent(new CustomEvent('scribe-auth-ready'));
      document.getElementById('login-overlay').classList.add('hidden');
      return;
    }
    if (isNetworkError) {
      // Serveur inaccessible : utiliser le cache localStorage et continuer
      try {
        currentUser = JSON.parse(usr);
        authToken = tok;
        applyUserState();
        startHeartbeat();
        await initAfterLogin();
        document.getElementById('login-overlay').classList.add('hidden');
        // Restaurer l'onglet actif avant le refresh
        const lastTab = localStorage.getItem('scribe_last_tab');
        const lastPlugin = localStorage.getItem('scribe_last_plugin');
        if (lastPlugin) {
          setTimeout(() => {
            const btn = document.getElementById('dyn-tab-btn-' + lastPlugin) ||
                        document.getElementById('tab-btn-' + lastPlugin);
            if (btn) btn.click();
          }, 500);
        } else if (lastTab) {
          setTimeout(() => {
            const btn = document.querySelector('[onclick*="' + lastTab + '"]');
            if (btn) btn.click();
          }, 500);
        }
        return;
      } catch(e2) {}
    }
    // Token vraiment invalide → nettoyer et afficher login
    localStorage.removeItem('scribe_token');
    localStorage.removeItem('scribe_user');
    authToken = null; currentUser = null;
  }
  // Pas de session valide → mire de connexion
  document.getElementById('login-overlay').classList.remove('hidden');
});

function loadIaBadge() {
  // Ne charger que si le plugin albert est actif (évite le 404 en console)
  apiFetch('/api/v1/plugins/active').then(r=>r.json()).then(plugins => {
    const albertActive = plugins.some(p => p.id === 'albert');
    if (!albertActive) return;
    apiFetch('/api/v1/albert/config').then(r=>r.json()).then(cfg => {
      const badge = document.getElementById('ia-badge');
      if (!badge) return;
      const icons = {albert:'🇫🇷',openai:'🤖',anthropic:'🟤',gemini:'🔷',mistral:'🌪️',ollama:'🏠',openai_compat:'⚙️'};
      badge.textContent = icons[cfg.provider]||'🧠' + ' ' + (cfg.provider||'').toUpperCase();
      badge.title = cfg.display_name || cfg.provider;
      badge.style.display = 'inline-block';
    }).catch(()=>{});
  }).catch(()=>{});
}

// ── ADMIN PANEL ───────────────────────────────────────────
function toggleUserMenu() {
  const menu = document.getElementById('user-menu');
  if (!menu) return;
  const isOpen = menu.style.display !== 'none';
  menu.style.display = isOpen ? 'none' : 'block';
  if (!isOpen && currentUser) {
    const info = document.getElementById('user-menu-info');
    if (info) info.textContent = (currentUser.display_name || currentUser.username) + ' · ' + (currentUser.role || '');
    const adminBtn = document.getElementById('user-menu-admin');
    if (adminBtn) adminBtn.style.display = currentUser.role === 'admin' ? 'block' : 'none';
    const hdrAdminBtn2 = document.getElementById('hdr-admin-btn');
    if (hdrAdminBtn2) hdrAdminBtn2.style.display = currentUser.role === 'admin' ? 'inline-flex' : 'none';
  }
}

// Fermer le menu si clic en dehors
document.addEventListener('click', function(e) {
  const chip = document.getElementById('user-chip');
  const menu = document.getElementById('user-menu');
  if (menu && chip && !chip.contains(e.target) && !menu.contains(e.target)) {
    menu.style.display = 'none';
  }
});

function doLogout() {
  authToken = null;
  currentUser = null;
  _appInitDone = false;
  if (_heartbeatInterval) { clearInterval(_heartbeatInterval); _heartbeatInterval = null; }
  if (notifInterval)      { clearInterval(notifInterval);      notifInterval = null; }
  localStorage.removeItem('scribe_token');
  localStorage.removeItem('scribe_user');
  // Cacher l'interface
  const hdr = document.getElementById('main-header');
  const nav = document.getElementById('main-nav');
  const app = document.getElementById('app-content');
  if (hdr) hdr.style.display = 'none';
  if (nav) nav.style.display = 'none';
  if (app) app.style.display = 'none';
  // Fermer menus ouverts
  const uMenu = document.getElementById('user-menu');
  if (uMenu) uMenu.style.display = 'none';
  // Afficher la mire de connexion
  const overlay = document.getElementById('login-overlay');
  if (overlay) { overlay.classList.remove('hidden'); overlay.style.display = 'flex'; }
  // Reset UI navbar
  const nameEl = document.getElementById('current-user-name');
  if (nameEl) nameEl.textContent = '...';
  const dotEl = document.getElementById('role-dot');
  if (dotEl) dotEl.className = 'role-dot';
  toast('Déconnexion effectuée', 'ok');
}

function openChangePassword() {
  // Réutiliser le modal forced-pw pour le changement volontaire aussi
  const modal = document.getElementById('modal-forced-pw');
  if (modal) {
    // Adapter le titre pour changement volontaire
    const title = modal.querySelector('[id="forced-pw-title"]');
    if (title) title.textContent = 'Changer le mot de passe';
    // Masquer le message d'avertissement obligatoire
    const warn = document.getElementById('forced-pw-warn');
    if (warn) warn.style.display = 'none';
    modal.style.display = 'flex';
    const inp = document.getElementById('forced-pw-new');
    if (inp) inp.focus();
  } else {
    if (currentUser?.role === 'admin') showAdminPanel();
    else toast("Changement de MDP via l'administrateur", "warn");
  }
}

function showAdminPanel() {
  if (!currentUser) return;
  if (currentUser.role !== 'admin') { toast('Accès réservé à l\'administrateur','err'); return; }
  document.getElementById('admin-panel').classList.add('open');
  adminShowSection('users', document.getElementById('admin-nav-users'));
}
function closeAdminPanel() {
  document.getElementById('admin-panel').classList.remove('open');
}
// v2307-hotfix — Raccourci Échap pour fermer le panel admin rapidement.
// Comportement attendu par les utilisateurs (cohérent avec la plupart
// des modals web).
document.addEventListener('keydown', (e) => {
  if (e.key === 'Escape') {
    const panel = document.getElementById('admin-panel');
    if (panel && panel.classList.contains('open')) {
      closeAdminPanel();
    }
  }
});
function adminShowSection(section, btn) {
  ['users','plugins','notifications','content','apis','network','lang','mfa','fed'].forEach(s => {
    const el = document.getElementById('admin-section-' + s);
    if (el) el.style.display = 'none';
  });
  document.querySelectorAll('.admin-sidebar-btn').forEach(b => b.classList.remove('active'));
  const target = document.getElementById('admin-section-' + section);
  if (target) target.style.display = 'block';
  if (btn) btn.classList.add('active');
  if (section === 'users')   { loadAdminUsers(); loadSetPwUsers(); }
  if (section === 'plugins') { loadAdminPlugins(); }
  if (section === 'apis')    { loadAdminIA(); loadAdminRouting(); }
  if (section === 'network') { loadAdminNetwork(); }
  if (section === 'lang')    { loadAdminLang(); }
  if (section === 'mfa')     { loadMfaSection(); }
  if (section === 'fed')     { loadFedStatusPanel(); loadFedConfig(); }
  if (section === 'content') { loadScenarioLibrary(); }
  if (section === 'notifications') {
    // v2305 — Lazy-load de l'iframe notifications pour ne charger la page
    // qu'au premier affichage de la section (économie mémoire + éviter
    // rechargement à chaque bascule de section).
    const iframe = document.getElementById('admin-notifs-iframe');
    if (iframe && (!iframe.src || iframe.src === 'about:blank')) {
      iframe.src = '/api/v1/notifications/ui';
    }
  }
}

// v2315 — Section MFA. Affiche l'état MFA de l'utilisateur courant +
// la liste MFA des autres utilisateurs (admin uniquement).
async function loadMfaSection() {
  // 1. Bloc "mon MFA"
  const statusBox = document.getElementById('mfa-self-status');
  const actionsBox = document.getElementById('mfa-self-actions');
  if (!statusBox || !actionsBox) return;
  try {
    const r = await apiFetch('/api/v1/mfa/status');
    if (!r.ok) throw new Error('HTTP ' + r.status);
    const d = await r.json();
    let badge = d.enabled
      ? '<span style="color:#34d399;font-weight:700">✓ MFA activé</span>'
      : (d.setup_pending
        ? '<span style="color:#fbbf24;font-weight:700">⚠ Setup en cours — code de confirmation attendu</span>'
        : '<span style="color:var(--muted);font-weight:700">○ MFA non activé</span>');
    statusBox.innerHTML = badge +
      (d.enabled ? ' · <span style="color:var(--muted)">' + d.backup_codes_remaining +
        ' code(s) de backup disponible(s)</span>' : '');
    // Actions
    actionsBox.innerHTML = '';
    if (!d.enabled && !d.setup_pending) {
      const b = document.createElement('button');
      b.textContent = '🔐 Activer l\'authentification double facteur';
      b.style.cssText = 'font-family:var(--mono);font-size:10px;padding:8px 16px;background:rgba(99,102,241,.15);border:1px solid #6366f1;border-radius:4px;color:#818cf8;cursor:pointer;font-weight:700';
      b.onclick = mfaStartSetup;
      actionsBox.appendChild(b);
    }
    if (d.setup_pending) {
      const b1 = document.createElement('button');
      b1.textContent = '↻ Reprendre le setup';
      b1.style.cssText = 'font-family:var(--mono);font-size:10px;padding:8px 16px;background:rgba(251,191,36,.15);border:1px solid #fbbf24;border-radius:4px;color:#fbbf24;cursor:pointer;font-weight:700';
      b1.onclick = mfaStartSetup;
      actionsBox.appendChild(b1);
    }
    if (d.enabled) {
      const b1 = document.createElement('button');
      b1.textContent = '🔄 Régénérer codes de backup';
      b1.style.cssText = 'font-family:var(--mono);font-size:10px;padding:8px 16px;background:transparent;border:1px solid var(--border2);border-radius:4px;color:var(--text);cursor:pointer';
      b1.onclick = mfaRegenerateBackup;
      actionsBox.appendChild(b1);
      const b2 = document.createElement('button');
      b2.textContent = '⊖ Désactiver MFA';
      b2.style.cssText = 'font-family:var(--mono);font-size:10px;padding:8px 16px;background:rgba(239,68,68,.1);border:1px solid #ef4444;border-radius:4px;color:#f87171;cursor:pointer';
      b2.onclick = mfaDisable;
      actionsBox.appendChild(b2);
    }
  } catch(e) {
    statusBox.innerHTML = '<span style="color:#f87171">Erreur chargement : ' + e.message + '</span>';
  }

  // 2. Bloc admin (MFA users) — uniquement si admin
  if (currentUser && currentUser.role === 'admin') {
    const block = document.getElementById('mfa-admin-block');
    if (block) {
      block.style.display = 'block';
      loadMfaUsersList();
    }
  }
}

async function loadMfaUsersList() {
  const list = document.getElementById('mfa-users-list');
  if (!list) return;
  try {
    const r = await apiFetch('/api/v1/auth/users');
    if (!r.ok) throw new Error('HTTP ' + r.status);
    const users = await r.json();
    if (!users.length) { list.innerHTML = '<div style="color:var(--muted)">Aucun utilisateur</div>'; return; }
    list.innerHTML = '<table style="width:100%;border-collapse:collapse">' +
      '<thead><tr style="text-align:left;font-family:var(--mono);font-size:9px;color:var(--muted);letter-spacing:1px">' +
      '<th style="padding:6px 4px">UTILISATEUR</th><th>RÔLE</th><th>MFA</th><th></th></tr></thead><tbody>' +
      users.map(u => {
        const mfaBadge = u.mfa_enabled
          ? '<span style="color:#34d399">✓ Activé</span>'
          : '<span style="color:var(--muted)">○ Non activé</span>';
        const resetBtn = u.mfa_enabled
          ? `<button onclick="mfaAdminReset(${u.id},'${(u.username||'').replace(/'/g,"")}')" style="font-family:var(--mono);font-size:9px;padding:3px 8px;background:rgba(239,68,68,.1);border:1px solid #ef4444;border-radius:3px;color:#f87171;cursor:pointer">↻ Réinitialiser</button>`
          : '';
        return '<tr style="border-top:1px solid var(--border)">' +
          '<td style="padding:6px 4px">' + (u.display_name || u.username) + ' <span style="color:var(--muted)">(' + u.username + ')</span></td>' +
          '<td>' + (u.role || '—') + '</td>' +
          '<td>' + mfaBadge + '</td>' +
          '<td style="text-align:right">' + resetBtn + '</td>' +
          '</tr>';
      }).join('') +
      '</tbody></table>';
  } catch(e) {
    list.innerHTML = '<span style="color:#f87171">Erreur : ' + e.message + '</span>';
  }
}

async function mfaStartSetup() {
  try {
    const r = await apiFetch('/api/v1/mfa/setup', { method: 'POST' });
    if (!r.ok) {
      const e = await r.json().catch(()=>({detail:'HTTP '+r.status}));
      toast('Erreur : ' + (e.detail || 'setup impossible'), 'err');
      return;
    }
    const d = await r.json();
    mfaShowSetupModal(d);
  } catch(e) {
    toast('Erreur réseau : ' + e.message, 'err');
  }
}

function mfaShowSetupModal(setupData) {
  // Créer un modal dédié
  let m = document.getElementById('mfa-setup-modal');
  if (m) m.remove();
  m = document.createElement('div');
  m.id = 'mfa-setup-modal';
  m.style.cssText = 'position:fixed;inset:0;background:rgba(0,0,0,.65);z-index:10000;display:flex;align-items:center;justify-content:center;padding:20px';
  m.innerHTML = `
    <div style="background:var(--bg,#1a1a1a);border:1px solid var(--border,#333);border-radius:10px;padding:24px;max-width:480px;width:100%;max-height:90vh;overflow-y:auto;color:var(--text,#e5e5e5);font-family:var(--mono)">
      <h3 style="margin:0 0 14px;font-size:13px;letter-spacing:1.5px">🔐 Configuration MFA</h3>
      <p style="font-size:10px;color:var(--muted,#94a3b8);line-height:1.7;margin:0 0 14px">
        <strong>1.</strong> Scanne ce QR code avec ton app d'authentification<br>
        (Google Authenticator, Aegis, 2FAS, Microsoft Authenticator…)
      </p>
      <div style="text-align:center;background:#fff;padding:14px;border-radius:8px;margin-bottom:14px">
        <img src="${setupData.qr_data_url}" style="max-width:200px;display:inline-block" alt="QR code MFA">
      </div>
      <details style="margin-bottom:14px;font-size:10px;color:var(--muted,#94a3b8)">
        <summary style="cursor:pointer">Ou saisir la clé manuellement</summary>
        <div style="margin-top:8px;padding:8px;background:rgba(0,0,0,.1);border-radius:4px;font-family:monospace;word-break:break-all;user-select:all;font-size:11px">${setupData.secret}</div>
      </details>
      <p style="font-size:10px;color:var(--muted,#94a3b8);margin:0 0 8px">
        <strong>2.</strong> Saisis le code à 6 chiffres affiché dans l'app :
      </p>
      <input type="text" id="mfa-setup-code" placeholder="000000" maxlength="6" autocomplete="one-time-code" inputmode="numeric" pattern="[0-9]{6}" style="width:100%;padding:10px 12px;background:var(--surface,#222);border:1px solid var(--border,#333);border-radius:4px;color:var(--text,#e5e5e5);font-family:var(--mono);font-size:18px;text-align:center;letter-spacing:4px;margin-bottom:8px">
      <div id="mfa-setup-err" style="font-size:10px;color:#f87171;min-height:14px;margin-bottom:8px"></div>
      <div style="display:flex;gap:8px;justify-content:flex-end">
        <button onclick="document.getElementById('mfa-setup-modal').remove()" style="font-family:var(--mono);font-size:10px;padding:8px 14px;background:transparent;border:1px solid var(--border2,#555);border-radius:4px;color:var(--muted,#94a3b8);cursor:pointer">Annuler</button>
        <button onclick="mfaConfirmSetup()" style="font-family:var(--mono);font-size:10px;padding:8px 18px;background:rgba(99,102,241,.15);border:1px solid #6366f1;border-radius:4px;color:#818cf8;cursor:pointer;font-weight:700">✓ Valider</button>
      </div>
    </div>
  `;
  document.body.appendChild(m);
  setTimeout(() => { document.getElementById('mfa-setup-code')?.focus(); }, 100);
}

async function mfaConfirmSetup() {
  const code = document.getElementById('mfa-setup-code').value.trim();
  const err = document.getElementById('mfa-setup-err');
  if (!code || code.length !== 6) {
    err.textContent = 'Code à 6 chiffres requis';
    return;
  }
  try {
    const r = await apiFetch('/api/v1/mfa/verify-setup', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({code: code}),
    });
    if (!r.ok) {
      const e = await r.json().catch(()=>({detail:'HTTP '+r.status}));
      err.textContent = e.detail || 'Code incorrect';
      return;
    }
    const d = await r.json();
    document.getElementById('mfa-setup-modal').remove();
    mfaShowBackupCodesModal(d.backup_codes, 'Activation MFA réussie !');
    loadMfaSection();
  } catch(e) {
    err.textContent = 'Erreur réseau : ' + e.message;
  }
}

function mfaShowBackupCodesModal(codes, title) {
  let m = document.getElementById('mfa-codes-modal');
  if (m) m.remove();
  m = document.createElement('div');
  m.id = 'mfa-codes-modal';
  m.style.cssText = 'position:fixed;inset:0;background:rgba(0,0,0,.75);z-index:10001;display:flex;align-items:center;justify-content:center;padding:20px';
  const codesText = (codes || []).join('\n');
  m.innerHTML = `
    <div style="background:var(--bg,#1a1a1a);border:1px solid #fbbf24;border-radius:10px;padding:24px;max-width:460px;width:100%;color:var(--text,#e5e5e5);font-family:var(--mono)">
      <h3 style="margin:0 0 12px;font-size:13px;letter-spacing:1.5px;color:#fbbf24">⚠ ${title || 'Codes de backup'}</h3>
      <p style="font-size:10px;color:var(--muted,#94a3b8);line-height:1.7;margin:0 0 14px">
        Garde ces codes <strong>dans un endroit sûr</strong> (gestionnaire de mots de passe,
        coffre, papier). Ils te permettent de te reconnecter si tu perds ton téléphone.
        <strong>Chaque code n'est utilisable qu'une seule fois.</strong> Ils ne seront
        <strong>plus jamais affichés</strong> — copie-les maintenant.
      </p>
      <div style="background:rgba(0,0,0,.15);padding:14px;border-radius:6px;margin-bottom:14px;font-size:14px;line-height:2;letter-spacing:2px;user-select:all;white-space:pre">${(codes||[]).join('\n')}</div>
      <div style="display:flex;gap:8px;justify-content:flex-end">
        <button onclick="mfaDownloadBackupCodes()" data-codes='${JSON.stringify(codes)}' id="mfa-dl-btn" style="font-family:var(--mono);font-size:10px;padding:8px 14px;background:transparent;border:1px solid var(--border2,#555);border-radius:4px;color:var(--text,#e5e5e5);cursor:pointer">💾 Télécharger .txt</button>
        <button onclick="document.getElementById('mfa-codes-modal').remove()" style="font-family:var(--mono);font-size:10px;padding:8px 18px;background:rgba(99,102,241,.15);border:1px solid #6366f1;border-radius:4px;color:#818cf8;cursor:pointer;font-weight:700">J'ai noté, continuer</button>
      </div>
    </div>
  `;
  document.body.appendChild(m);
}

function mfaDownloadBackupCodes() {
  const btn = document.getElementById('mfa-dl-btn');
  if (!btn) return;
  try {
    const codes = JSON.parse(btn.getAttribute('data-codes') || '[]');
    const content = 'SCRIBE — Codes de backup MFA\n' +
      'Compte : ' + (currentUser?.username || '?') + '\n' +
      'Date  : ' + new Date().toISOString() + '\n' +
      '\n' +
      codes.join('\n') + '\n' +
      '\n' +
      'Chaque code est utilisable UNE SEULE FOIS.\n' +
      'Garde ce fichier en lieu sûr.\n';
    const blob = new Blob([content], {type: 'text/plain'});
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = 'scribe-mfa-backup-' + (currentUser?.username || 'codes') + '.txt';
    a.click();
    URL.revokeObjectURL(url);
  } catch(e) { toast('Erreur : ' + e.message, 'err'); }
}

async function mfaRegenerateBackup() {
  const code = prompt('Entrez un code TOTP actuel pour confirmer la régénération :');
  if (!code) return;
  try {
    const r = await apiFetch('/api/v1/mfa/regenerate-backup-codes', {
      method: 'POST',
      headers: {'Content-Type':'application/json'},
      body: JSON.stringify({code: code.trim()}),
    });
    if (!r.ok) {
      const e = await r.json().catch(()=>({detail:'HTTP '+r.status}));
      toast('Erreur : ' + (e.detail||'échec'), 'err');
      return;
    }
    const d = await r.json();
    mfaShowBackupCodesModal(d.backup_codes, 'Nouveaux codes de backup');
    loadMfaSection();
  } catch(e) { toast('Erreur : ' + e.message, 'err'); }
}

async function mfaDisable() {
  const pwd = prompt('Confirmer avec ton mot de passe (pour désactiver le MFA) :');
  if (!pwd) return;
  try {
    const r = await apiFetch('/api/v1/mfa/disable', {
      method: 'POST',
      headers: {'Content-Type':'application/json'},
      body: JSON.stringify({password: pwd}),
    });
    if (!r.ok) {
      const e = await r.json().catch(()=>({detail:'HTTP '+r.status}));
      toast('Erreur : ' + (e.detail||'échec'), 'err');
      return;
    }
    toast('MFA désactivé', 'ok');
    loadMfaSection();
  } catch(e) { toast('Erreur : ' + e.message, 'err'); }
}

async function mfaAdminReset(userId, username) {
  if (!confirm('Réinitialiser le MFA de ' + username + ' ?\n\nL\'utilisateur devra refaire la configuration complète (nouveau QR + nouveau téléphone).')) return;
  try {
    // On utilise disable côté admin via route admin dédiée (à créer ci-dessous)
    const r = await apiFetch('/api/v1/auth/users/' + userId + '/mfa-reset', { method: 'POST' });
    if (!r.ok) {
      const e = await r.json().catch(()=>({detail:'HTTP '+r.status}));
      toast('Erreur : ' + (e.detail||'échec'), 'err');
      return;
    }
    toast('MFA de ' + username + ' réinitialisé', 'ok');
    loadMfaUsersList();
  } catch(e) { toast('Erreur : ' + e.message, 'err'); }
}

// v2307 — Sélecteur de langue admin
async function loadAdminLang() {
  try {
    const r = await apiFetch('/api/v1/admin/lang/current');
    if (!r.ok) throw new Error('HTTP ' + r.status);
    const d = await r.json();
    const sel = document.getElementById('lang-select');
    if (!sel) return;
    sel.innerHTML = '';
    (d.available || []).forEach(l => {
      const opt = document.createElement('option');
      opt.value = l.code;
      opt.textContent = `${l.flag || ''} ${l.name} (${l.code})`.trim();
      if (l.code === d.current) opt.selected = true;
      sel.appendChild(opt);
    });
  } catch(e) {
    const res = document.getElementById('lang-apply-result');
    if (res) { res.style.color = '#f87171'; res.textContent = 'Erreur chargement : ' + e.message; }
  }
}

async function applyAdminLang() {
  const sel = document.getElementById('lang-select');
  const res = document.getElementById('lang-apply-result');
  if (!sel || !sel.value) return;
  res.style.color = 'var(--muted)';
  res.textContent = 'Application en cours…';
  try {
    const r = await apiFetch('/api/v1/admin/lang/set', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({code: sel.value}),
    });
    if (!r.ok) throw new Error('HTTP ' + r.status);
    res.style.color = '#34d399';
    res.innerHTML = '✓ Langue changée. Rechargez la page (F5) pour voir l\'interface dans la nouvelle langue.';
    // Re-fetch des traductions et application immédiate (sans F5) pour
    // l'admin qui vient de faire le changement — les autres users auront
    // la nouvelle langue à leur prochain F5.
    try {
      LANG_CODE = sel.value;
      const r2 = await apiFetch(`/api/v1/i18n/${sel.value}`);
      if (r2.ok) {
        LANG = await r2.json();
        document.documentElement.setAttribute('lang', sel.value);
        applyI18nDOM();
      }
    } catch(e) {}
  } catch(e) {
    res.style.color = '#f87171';
    res.textContent = 'Erreur : ' + e.message;
  }
}

// v2.3.92 (v2306) — Génération de scénario depuis une crise passée.
// Trois fonctions : preview (aperçu quantitatif), generate (génère +
// affiche stats), download (génère + déclenche téléchargement).

/**
 * Échappe le HTML pour affichage sécurisé. Local à cette section pour
 * éviter de dépendre d'une éventuelle fonction globale non définie.
 */
function _scenEsc(s) {
  if (s == null) return '';
  return String(s)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;');
}

/**
 * Construit le body POST commun à preview/generate/download depuis les
 * champs du formulaire. Tolère les champs vides (omet les clés non
 * renseignées côté API Pydantic).
 */
function _scenBuildBody() {
  const titre = (document.getElementById('scen-titre').value || '').trim();
  if (!titre || titre.length < 3) {
    throw new Error("Titre requis (3 caractères minimum)");
  }
  const body = {
    titre,
    description: (document.getElementById('scen-description').value || '').trim(),
    cible_sigle: (document.getElementById('scen-cible').value || 'CHAG').trim(),
    anonymize: document.getElementById('scen-anonymize').checked,
    include_incidents: document.getElementById('scen-inc-incidents').checked,
    include_messages:  document.getElementById('scen-inc-messages').checked,
    include_transferts: document.getElementById('scen-inc-transferts').checked,
    type_crise: document.getElementById('scen-type').value,
    complexite: document.getElementById('scen-complexite').value,
  };
  const since = document.getElementById('scen-since').value;
  const until = document.getElementById('scen-until').value;
  // datetime-local donne du "YYYY-MM-DDTHH:mm" (sans timezone). On ajoute
  // le suffixe Z en faisant l'hypothèse que l'utilisateur raisonne en UTC.
  // Pour un usage plus rigoureux on pourrait faire une conversion locale.
  if (since) body.since = since + ":00";
  if (until) body.until = until + ":00";
  return body;
}

async function scenPreview() {
  const out = document.getElementById('scen-result');
  out.style.color = 'var(--muted)';
  out.textContent = 'Interrogation de la base…';
  try {
    const body = _scenBuildBody();
    const params = new URLSearchParams();
    if (body.since) params.set('since', body.since);
    if (body.until) params.set('until', body.until);
    const url = '/api/v1/admin/scenario/crisis-preview' + (params.toString() ? '?' + params.toString() : '');
    const r = await apiFetch(url);
    if (!r.ok) throw new Error(`HTTP ${r.status}`);
    const d = await r.json();
    const c = d.counts || {};
    out.style.color = '#94a3b8';
    out.innerHTML =
      `<strong>Aperçu</strong> — ` +
      `<span style="color:#60a5fa">${c.incidents||0}</span> incidents · ` +
      `<span style="color:#60a5fa">${c.messages||0}</span> messages · ` +
      `<span style="color:#60a5fa">${c.transferts||0}</span> transferts · ` +
      `<span style="color:#94a3b8">${c.decisions||0}</span> décisions observées` +
      (d.first_event ? `<br/>Premier événement : ${d.first_event}` : '') +
      (d.last_event  ? `<br/>Dernier événement : ${d.last_event}` : '');
  } catch(e) {
    out.style.color = '#f87171';
    out.textContent = 'Erreur : ' + (e.message || e);
  }
}

async function scenGenerate() {
  const out = document.getElementById('scen-result');
  out.style.color = 'var(--muted)';
  out.textContent = 'Génération en cours…';
  try {
    const body = _scenBuildBody();
    const r = await apiFetch('/api/v1/admin/scenario/export', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify(body),
    });
    if (!r.ok) {
      const err = await r.text();
      throw new Error(`HTTP ${r.status} — ${err.slice(0,200)}`);
    }
    const d = await r.json();
    out.style.color = '#34d399';
    const scen = d.scenario || {};
    const meta = scen.meta || {};
    out.innerHTML =
      `<strong>✓ Scénario généré</strong><br/>` +
      `Stimuli : <span style="color:#60a5fa">${d.stimuli_count}</span> · ` +
      `Durée estimée : <span style="color:#60a5fa">${meta.duree_min||0} min</span> · ` +
      `Anonymisé : ${d.anonymized ? 'oui' : 'non'}<br/>` +
      `Objectifs pédagogiques proposés :` +
      `<ul style="margin:6px 0 0 16px;padding:0">` +
      (meta.objectifs_pedagogiques||[]).map(o => `<li>${_scenEsc(o)}</li>`).join('') +
      `</ul>` +
      `<em style="color:var(--muted)">Cliquez sur "⬇ Télécharger JSON" pour obtenir le fichier injectable.</em>`;
  } catch(e) {
    out.style.color = '#f87171';
    out.textContent = 'Erreur : ' + (e.message || e);
  }
}

async function scenDownload() {
  const out = document.getElementById('scen-result');
  out.style.color = 'var(--muted)';
  out.textContent = 'Préparation du téléchargement…';
  try {
    const body = _scenBuildBody();
    const r = await apiFetch('/api/v1/admin/scenario/export?download=1', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify(body),
    });
    if (!r.ok) {
      const err = await r.text();
      throw new Error(`HTTP ${r.status} — ${err.slice(0,200)}`);
    }
    const blob = await r.blob();
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    // Nom dérivé du titre
    const safeTitre = body.titre.replace(/[^a-zA-Z0-9_-]/g,'_').slice(0,60);
    a.download = `scenario_${safeTitre}.json`;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    setTimeout(() => URL.revokeObjectURL(url), 1000);
    out.style.color = '#34d399';
    out.textContent = '✓ Fichier téléchargé. Dépose-le dans scenarios/ pour le rendre disponible en exercice.';
  } catch(e) {
    out.style.color = '#f87171';
    out.textContent = 'Erreur : ' + (e.message || e);
  }
}

/**
 * Liste les scénarios déjà présents dans scenarios/.
 * On réutilise la route existante si elle existe, sinon affichage générique.
 */
async function loadScenarioLibrary() {
  const box = document.getElementById('scen-lib-list');
  if (!box) return;
  box.textContent = 'Chargement…';
  try {
    // Essai : route existante du collecteur_exercice / ou listing direct
    const r = await apiFetch('/api/v1/admin/scenario/library', {method:'GET'});
    if (r.ok) {
      const d = await r.json();
      if (d && d.scenarios && d.scenarios.length) {
        box.innerHTML = d.scenarios.map(s =>
          `<div style="padding:6px 0;border-bottom:1px solid var(--border)">
             <strong>${_scenEsc(s.titre || s.id || '?')}</strong>
             <span style="color:var(--muted);margin-left:8px">${s.nb_stimuli||0} stimuli · ${_scenEsc(s.type_crise||'')} · ${_scenEsc(s.complexite||'')}</span>
           </div>`).join('');
        return;
      }
    }
    box.innerHTML = '<em>Liste non disponible via l\'API. Vérifie le dossier <code>scenarios/</code> sur le serveur.</em>';
  } catch(e) {
    box.innerHTML = '<em style="color:#f87171">Erreur chargement bibliothèque.</em>';
  }
}
async function adminFedPause() {
  const res = document.getElementById('fed-sync-result');
  try {
    const r = await apiFetch('/api/v1/federation/sync/pause', {method:'POST'});
    const d = await r.json();
    if (res) { res.style.color = '#fbbf24'; res.textContent = '⏸ ' + (d.message||'Synchronisation suspendue'); }
  } catch(e) { if(res) res.textContent = 'Erreur réseau'; }
}

async function adminFedResume() {
  const res = document.getElementById('fed-sync-result');
  try {
    const r = await apiFetch('/api/v1/federation/sync/resume', {method:'POST'});
    const d = await r.json();
    if (res) { res.style.color = '#4ade80'; res.textContent = '▶ ' + (d.message||'Synchronisation reprise'); }
    loadFedConfig();
  } catch(e) { if(res) res.textContent = 'Erreur réseau'; }
}

async function adminFedReload() {
  const res = document.getElementById('fed-sync-result');
  try {
    const r = await apiFetch('/api/v1/federation/reload', {method:'POST'});
    const d = await r.json();
    if (res) { res.style.color = '#60a5fa'; res.textContent = '⚡ ' + (d.message||'Rechargée'); }
    loadFedConfig();
  } catch(e) { if(res) res.textContent = 'Erreur réseau'; }
}

// Collecteurs multiples — liste dynamique
let _fedCollectors = [];  // [{url, token, intervalle}]

function adminAddCollectorRow(url, token, intervalle) {
  const list = document.getElementById('fed-collectors-list');
  if (!list) return;
  const idx = _fedCollectors.length;
  _fedCollectors.push({url: url||'', token: token||'', intervalle: intervalle||30});
  const row = document.createElement('div');
  row.id = 'fed-coll-row-' + idx;
  row.style.cssText = 'display:grid;grid-template-columns:1fr 1fr auto auto;gap:8px;align-items:center';
  row.innerHTML =
    '<input type="text" placeholder="http://collecteur:9000/api/push" value="' + (url||'') + '"' +
    '  style="font-family:var(--mono);font-size:10px;padding:5px 8px;background:var(--surface2);border:1px solid var(--border2);border-radius:4px;color:var(--text)"' +
    '  oninput="_fedCollectors[' + idx + '].url=this.value">' +
    '<input type="text" placeholder="token (min 16 car.)" value="' + (token||'') + '"' +
    '  style="font-family:var(--mono);font-size:10px;padding:5px 8px;background:var(--surface2);border:1px solid var(--border2);border-radius:4px;color:var(--text)"' +
    '  oninput="_fedCollectors[' + idx + '].token=this.value">' +
    '<input type="number" value="' + (intervalle||30) + '" min="10" max="300"' +
    '  style="width:60px;font-family:var(--mono);font-size:10px;padding:5px 6px;background:var(--surface2);border:1px solid var(--border2);border-radius:4px;color:var(--text)"' +
    '  oninput="_fedCollectors[' + idx + '].intervalle=parseInt(this.value)||30">' +
    '<button onclick="adminRemoveCollectorRow(' + idx + ')" style="font-family:var(--mono);font-size:9px;padding:4px 8px;background:rgba(239,68,68,.1);border:1px solid #ef4444;border-radius:4px;color:#f87171;cursor:pointer">✕</button>';
  list.appendChild(row);
}

function adminRemoveCollectorRow(idx) {
  const row = document.getElementById('fed-coll-row-' + idx);
  if (row) row.remove();
  _fedCollectors[idx] = null;
}

async function loadFedConfig() {
  const box = document.getElementById('fed-current-config');
  try {
    const r2 = await apiFetch('/api/v1/federation/status');
    const fedCfg = r2.ok ? await r2.json() : {};
    const url   = fedCfg.collecteur_url || '(non configuré)';
    const inter = fedCfg.intervalle_s || fedCfg.intervalle || 30;
    const paused = fedCfg.sync_paused || false;
    if (box) box.innerHTML =
      '<div><span style="color:var(--muted);font-size:9px">URL COLLECTEUR</span><div style="margin-top:2px">' + url + '</div></div>' +
      '<div style="margin-top:6px"><span style="color:var(--muted);font-size:9px">INTERVALLE</span><div style="margin-top:2px">' + inter + 's</div></div>' +
      '<div style="margin-top:6px"><span style="color:var(--muted);font-size:9px">ÉTAT</span><div style="margin-top:2px;color:' + (paused ? '#fbbf24' : '#4ade80') + '">' + (paused ? '⏸ Suspendue' : '▶ Active') + '</div></div>';
    // Pré-remplir la liste multi-collecteurs
    const list = document.getElementById('fed-collectors-list');
    if (list && url !== '(non configuré)') {
      list.innerHTML = '';
      _fedCollectors = [];
      adminAddCollectorRow(url, '', inter);
    }
  } catch(e) { if(box) box.innerHTML = '<span style="color:var(--muted)">Non disponible</span>'; }
}

async function adminSaveFedConfig() {
  const res = document.getElementById('fed-save-result');
  // Prendre le premier collecteur valide de la liste
  const valid = (_fedCollectors || []).filter(c => c && c.url && c.url.trim());
  if (!valid.length) { if(res) { res.style.color='#fbbf24'; res.textContent='⚠ Ajouter au moins un collecteur'; } return; }
  const first = valid[0];
  const url   = first.url.trim();
  const token = (first.token||'').trim();
  const inter = first.intervalle || 30;
  if (token && token.length < 16) { if(res) { res.style.color='#fbbf24'; res.textContent='⚠ Token min 16 caractères'; } return; }
  try {
    const r = await apiFetch('/api/v1/admin/config/federation', {
      method: 'POST',
      headers: {'Content-Type':'application/json'},
      body: JSON.stringify({collecteur_url: url, token: token||null, intervalle_secondes: parseInt(inter)})
    });
    if (r.ok) {
      if(res) { res.style.color='#4ade80'; res.textContent='✓ Configuration sauvegardée et rechargée'; }
      loadFedConfig();
      setTimeout(() => { if(res) res.textContent=''; }, 5000);
    } else {
      const d = await r.json().catch(()=>({}));
      if(res) { res.style.color='#f87171'; res.textContent='✗ ' + (d.detail||'Erreur'); }
    }
  } catch(e) { if(res) { res.style.color='#f87171'; res.textContent='Erreur réseau'; } }
}

async function loadAdminNetwork() {
  const box = document.getElementById('admin-network-info');
  if (!box) return;
  try {
    const r = await apiFetch('/api/v1/admin/config/network');
    if (!r.ok) return;
    const d = await r.json();
    box.innerHTML = '<div style="font-family:var(--mono);font-size:10px;display:flex;flex-direction:column;gap:8px">' +
      '<div><span style="color:var(--muted);font-size:9px">URL DE BASE</span><div style="margin-top:2px">' + (d.base_url||'—') + '</div></div>' +
      '<div><span style="color:var(--muted);font-size:9px">PORT</span><div style="margin-top:2px">' + (d.port||'—') + '</div></div>' +
      '<div><span style="color:var(--muted);font-size:9px">COLLECTEUR</span><div style="margin-top:2px">port ' + (d.collector_port||'—') + '</div></div>' +
      '<div style="margin-top:8px;color:var(--muted);font-size:9px">Modifier via SCRIBE_BASE_URL / SCRIBE_PORT</div></div>';
  } catch(e) {}
}
async function loadSetPwUsers() {
  const sel = document.getElementById('setpw-user-select');
  if (!sel) return;
  try {
    const r = await apiFetch('/api/v1/auth/users');
    if (!r.ok) return;
    const users = await r.json();
    sel.innerHTML = '<option value="">— Sélectionner un compte —</option>' +
      users.map(u => '<option value="' + u.id + '">' + (u.display_name||u.username) + ' (' + u.role + ')</option>').join('');
  } catch(e) {}
}
function selectUserForPw(uid, name) {
  document.getElementById('setpw-user-id').value = uid;
  document.getElementById('setpw-selected-name').textContent = name;
  document.getElementById('setpw-new').value = '';
  document.getElementById('setpw-confirm').value = '';
  document.getElementById('setpw-match').textContent = '';
  document.getElementById('setpw-btn').disabled = true;
  document.getElementById('setpw-btn').style.opacity = '.5';
  // Révéler la section (elle est display:none par défaut)
  const sec = document.getElementById('admin-setpw-section');
  if (sec) {
    sec.style.display = 'block';
    setTimeout(() => sec.scrollIntoView({behavior:'smooth', block:'start'}), 50);
  }
  // Focaliser le champ mot de passe
  setTimeout(() => document.getElementById('setpw-new')?.focus(), 150);
}
function adminCheckPw() {
  const pw  = document.getElementById('setpw-new')?.value || '';
  const pw2 = document.getElementById('setpw-confirm')?.value || '';
  const match = document.getElementById('setpw-match');
  const btn   = document.getElementById('setpw-btn');
  if (!pw) { match.textContent=''; btn.disabled=true; btn.style.opacity='.5'; return; }
  if (pw.length < 6) { match.textContent='⚠ Minimum 6 caractères'; match.style.color='#fbbf24'; btn.disabled=true; btn.style.opacity='.5'; return; }
  if (pw !== pw2) { match.textContent='✗ Les mots de passe ne correspondent pas'; match.style.color='#f87171'; btn.disabled=true; btn.style.opacity='.5'; return; }
  match.textContent='✓ Mots de passe identiques'; match.style.color='#4ade80';
  btn.disabled=false; btn.style.opacity='1';
}
async function adminSetPassword() {
  const uid  = document.getElementById('setpw-user-id')?.value;
  const name = document.getElementById('setpw-selected-name')?.textContent;
  const pw   = document.getElementById('setpw-new')?.value;
  const pw2  = document.getElementById('setpw-confirm')?.value;
  const res  = document.getElementById('setpw-result');
  if (!uid || uid === '') { if(res) { res.style.color='#fbbf24'; res.textContent='⚠ Sélectionner un compte'; } return; }
  if (!pw || pw.length < 6) { if(res) { res.style.color='#fbbf24'; res.textContent='⚠ Min 6 caractères'; } return; }
  if (pw !== pw2) { if(res) { res.style.color='#f87171'; res.textContent='✗ Mots de passe différents'; } return; }
  try {
    const r = await apiFetch('/api/v1/auth/users/' + uid, {
      method:'PUT', headers:{...authHeaders(), 'Content-Type':'application/json'},
      body: JSON.stringify({password: pw})
    });
    if (r.ok) {
      if(res) { res.style.color='#4ade80'; res.textContent='✓ Mot de passe de ' + name + ' mis à jour'; }
      document.getElementById('setpw-new').value='';
      document.getElementById('setpw-confirm').value='';
      document.getElementById('setpw-match').textContent='';
      document.getElementById('setpw-btn').disabled=true;
      document.getElementById('setpw-btn').style.opacity='.5';
      document.getElementById('setpw-user-id').value='';
      document.getElementById('setpw-selected-name').textContent='— cliquer sur un compte —';
      setTimeout(() => { if(res) res.textContent=''; }, 4000);
    } else { if(res) { res.style.color='#f87171'; res.textContent='✗ Erreur serveur'; } }
  } catch(e) { if(res) { res.style.color='#f87171'; res.textContent='Erreur réseau'; } }
}

async function loadAdminUsers() {
  try {
    const r = await apiFetch('/api/v1/auth/users', {headers: authHeaders()});
    const users = await r.json();
    const el = document.getElementById('admin-user-list');
    if (!users.length) { el.innerHTML = '<div class="empty-state">Aucun compte</div>'; return; }
    el.innerHTML = users.map(u => `
      <div class="user-row" style="cursor:pointer"
           onmouseover="this.style.background='var(--surface2)'" onmouseout="this.style.background=''">
        <input type="checkbox" class="user-select-cb" data-uid="${u.id}" onclick="event.stopPropagation();adminUpdateSelectCount()"
               style="width:14px;height:14px;cursor:pointer;flex-shrink:0">
        <span class="user-row-name">${u.display_name}</span>
        <span class="user-row-meta">@${u.username}</span>
        <span class="role-${u.role}">${u.role}</span>
        ${u.perimetre ? `<span style="font-family:var(--mono);font-size:9px;color:var(--muted)">${u.perimetre}</span>` : ''}
        <span style="font-family:var(--mono);font-size:9px;color:${u.active?'#4ade80':'#f87171'}">${u.active?'Actif':'Inactif'}</span>
        <button class="kc-btn" title="Modifier le mot de passe" onclick="event.stopPropagation();selectUserForPw(${u.id},'${(u.display_name||u.username).replace(/'/g,'')}')">🔑</button>
        ${u.role !== 'admin' ? `<button class="kc-btn" style="margin-left:2px" onclick="event.stopPropagation();toggleUserActive(${u.id},${u.active})">${u.active?'Désactiver':'Activer'}</button>
        <button class="kc-btn" style="color:#f87171" onclick="event.stopPropagation();deleteUser(${u.id})">✕</button>` : ''}
      </div>`).join('');
  } catch(e) { console.error(e); }
}

function adminSelectAllUsers() {
  const cbs = document.querySelectorAll('.user-select-cb');
  const allChecked = [...cbs].every(cb => cb.checked);
  cbs.forEach(cb => cb.checked = !allChecked);
  adminUpdateSelectCount();
}
function adminUpdateSelectCount() {
  const n = document.querySelectorAll('.user-select-cb:checked').length;
  const el = document.getElementById('admin-select-count');
  if (el) el.textContent = n > 0 ? n + ' sélectionné(s)' : '';
}
async function adminDeleteSelected() {
  const cbs = [...document.querySelectorAll('.user-select-cb:checked')];
  if (!cbs.length) { toast('Sélectionner au moins un compte', 'warn'); return; }
  const uids = cbs.map(cb => cb.getAttribute('data-uid'));
  if (!confirm('Supprimer ' + uids.length + ' compte(s) ? Cette action est irréversible.')) return;
  let ok = 0, fail = 0;
  for (const uid of uids) {
    try {
      const r = await apiFetch('/api/v1/auth/users/' + uid, {method:'DELETE'});
      if (r.ok) ok++; else fail++;
    } catch(e) { fail++; }
  }
  toast('✓ ' + ok + ' supprimé(s)' + (fail ? ' · ' + fail + ' erreur(s)' : ''), ok > 0 ? 'ok' : 'err');
  loadAdminUsers();
}

async function createUser() {
  const body = {
    username:     document.getElementById('nu-username').value.trim(),
    display_name: document.getElementById('nu-display').value.trim(),
    password:     document.getElementById('nu-pass').value,
    role:         document.getElementById('nu-role').value,
    perimetre:    document.getElementById('nu-perimetre').value.trim() || null
  };
  if (!body.username || !body.display_name || !body.password) { toast('Tous les champs obligatoires','err'); return; }
  try {
    const r = await apiFetch('/api/v1/auth/users', { method:'POST', headers: authHeaders(), body: JSON.stringify(body) });
    if (!r.ok) { const d=await r.json(); toast(d.detail||'Erreur','err'); return; }
    toast('Compte créé : @'+body.username);
    ['nu-username','nu-display','nu-pass','nu-perimetre'].forEach(id => document.getElementById(id).value='');
    loadAdminUsers();
  } catch(e) { toast('Erreur réseau','err'); }
}

async function toggleUserActive(uid, active) {
  await apiFetch(`/api/v1/auth/users/${uid}`, { method:'PUT', headers: authHeaders(), body: JSON.stringify({active: !active}) });
  loadAdminUsers();
}

async function deleteUser(uid) {
  if (!confirm('Supprimer cet utilisateur ?')) return;
  await apiFetch(`/api/v1/auth/users/${uid}`, { method:'DELETE', headers: authHeaders() });
  loadAdminUsers();
}

// ── NOTIFICATIONS INBOX ───────────────────────────────────
function toggleNotifPanel() {
  document.getElementById('notif-panel').classList.toggle('open');
  if (document.getElementById('notif-panel').classList.contains('open')) loadNotifications();
}

async function pollIGHTBadge() {
  // Mettre à jour le badge inter-GHT même sans ouvrir l'onglet
  if (!_fedStatus) { try { await loadFedStatus(); } catch(e) {} }
  let total = 0;
  // Compter les demandes non traitées
  try {
    const r = await apiFetch('/api/v1/interght/demandes');
    if (r.ok) {
      const local = await r.json();
      // + demandes distantes si collecteur dispo
      if (_fedStatus?.ready && _fedStatus?.collecteur_url) {
        const collBase = _fedStatus.collecteur_url.replace('/api/push','');
        const rc = await fetch(collBase + '/api/demandes', {
          headers:{'Authorization':'Bearer '+(_fedStatus.token||'')}
        });
        if (rc.ok) {
          const allRemote = await rc.json();
          const monSigle = (SCRIBE_CONFIG?.etablissement?.sigle||'').toUpperCase();
          const remoteDems = allRemote.filter(d =>
            d.ght_emetteur !== monSigle &&
            (!d.ght_destinataire || d.ght_destinataire === monSigle || d.ght_destinataire === '')
          );
          total += remoteDems.filter(d => d.statut !== 'traite').length;
        }
      }
      // Messages non lus
      if (_fedStatus?.ready && _fedStatus?.collecteur_url) {
        const collBase = _fedStatus.collecteur_url.replace('/api/push','');
        const rm = await fetch(collBase + '/api/messages', {
          headers:{'Authorization':'Bearer '+(_fedStatus.token||'')}
        });
        if (rm.ok) {
          const msgs = await rm.json();
          const all = [...(msgs.received||[]), ...(msgs.sent||[])];
          // Compter les messages reçus des 24 dernières heures non encore vus
          const since = Date.now() - 24*3600*1000;
          total += all.filter(m => (parseUTC(m.created_at)||new Date(0)) > since && !(m.sent_by_me)).length;
        }
      }
    }
  } catch(e) {}
  const badge = document.getElementById('ight-badge');
  if (badge) {
    badge.textContent = total > 0 ? String(total) : '';
    badge.style.display = total > 0 ? 'inline' : 'none';
  }
}

async function loadNotifications() {
  if (!authToken) return;
  try {
    const r = await apiFetch('/api/v1/auth/notifications', {headers: authHeaders()});
    if (!r.ok) return;
    const notifs = await r.json();
    const unread = notifs.filter(n => !n.lu).length;
    const badge = document.getElementById('notif-badge');
    const countTxt = document.getElementById('notif-count-txt');
    if (badge) { badge.textContent = unread; badge.className = 'notif-badge' + (unread > 0 ? ' show' : ''); }
    if (countTxt) countTxt.textContent = unread > 0 ? `Inbox (${unread})` : 'Inbox';
    const list = document.getElementById('notif-list');
    if (!list) return;
    if (!notifs.length) { list.innerHTML = '<div class="empty-state">Aucune notification</div>'; return; }
    list.innerHTML = notifs.map(n => `
      <div class="np-item ${n.lu ? '' : 'unread'}" onclick="readNotif(${n.id}, ${n.incident_id})">
        <div class="np-item-titre">${n.titre}</div>
        <div class="np-item-msg">${n.message}</div>
        <div class="np-item-time">${n.timestamp ? new Date(n.timestamp).toLocaleString('fr-FR') : ''}</div>
      </div>`).join('');
    document.getElementById('np-count-info').textContent = `${notifs.length} notification(s) — ${unread} non lue(s)`;
  } catch(e) {}
}

async function readNotif(id, incidentId) {
  await apiFetch(`/api/v1/auth/notifications/${id}/read`, {method:'PUT', headers: authHeaders()});
  loadNotifications();
  if (incidentId) {
    // Navigate to veille and highlight incident
    const btn = document.querySelector('.tab-btn');
    openTab('tab-veille', btn);
    setTimeout(() => { const el = document.getElementById(`inc-${incidentId}`); if(el) { el.scrollIntoView({behavior:'smooth'}); el.classList.add('expanded'); } }, 300);
  }
}

async function markAllRead() {
  if (!authToken) return;
  await apiFetch('/api/v1/auth/notifications/read-all', {method:'PUT', headers: authHeaders()});
  loadNotifications();
}

// ── MAP RESIZE ────────────────────────────────────────────
(function() {
  const handle = document.getElementById('map-resize-handle');
  const mapEl  = document.getElementById('map');
  if (!handle || !mapEl) return;
  let dragging = false, startY = 0, startH = 0;
  handle.addEventListener('mousedown', e => {
    dragging = true; startY = e.clientY; startH = mapEl.offsetHeight;
    document.body.style.cursor = 'ns-resize'; e.preventDefault();
  });
  document.addEventListener('mousemove', e => {
    if (!dragging) return;
    const newH = Math.max(80, Math.min(700, startH + e.clientY - startY));
    mapEl.style.height = newH + 'px';
    if (map) map.invalidateSize();
  });
  document.addEventListener('mouseup', () => {
    if (dragging) { dragging = false; document.body.style.cursor = ''; }
  });
})();

// Auto-zoom map on highest incident sites
function autoZoomMap(bySite) {
  // Ne pas faire d'autoZoom automatique - évite les boucles NaN avec flyTo
  // L'utilisateur peut zoomer manuellement
}

// ── NOTIFICATION MESSAGERIE (incident + kanban) ─────────────────────────────
let _notifyAllUsers = [];
let _notifyContext  = '';

async function openNotifyModal(contextLabel, prefillMsg) {
  // Charger les users
  try {
    const r = await apiFetch('/api/v1/auth/users', {headers: authHeaders()});
    if (r.ok) {
      const all = await r.json();
      const me = currentUser?.id;
      _notifyAllUsers = all.filter(u => u.active);
    }
  } catch(e) { _notifyAllUsers = []; }

  // Peupler le filtre site
  const siteSel = document.getElementById('notify-site');
  if (siteSel) {
    const sites = new Set(['— Tous les sites —']);
    // Sites de l'instance courante
    allSites.forEach(s => sites.add(s.nom));
    // Tags extraits des usernames
    _notifyAllUsers.forEach(u => {
      const m = u.username.match(/_demo_(.+)$/);
      if (m) sites.add(m[1]);
      const dn = (u.display_name||'').match(/— (.{3,30})$/);
      if (dn) sites.add(dn[1]);
    });
    siteSel.innerHTML = '<option value="">— Tous les sites —</option>' +
      [...sites].filter(s=>s!=='— Tous les sites —').sort()
        .map(s=>`<option value="${s}">${s}</option>`).join('');
  }

  notifyFilterUsers();

  // Contexte et message pré-rempli
  const ctxEl = document.getElementById('notify-context');
  if (ctxEl) ctxEl.textContent = contextLabel || '';
  const msgEl = document.getElementById('notify-msg');
  if (msgEl) msgEl.value = prefillMsg || '';

  document.getElementById('notify-modal').style.display = 'flex';
}

function notifyFilterUsers() {
  const site = document.getElementById('notify-site')?.value || '';
  const sel = document.getElementById('notify-dest');
  if (!sel) return;
  let filtered = _notifyAllUsers;
  if (site) {
    const tag = site.toLowerCase().replace(/[^a-z0-9]/g, '').substring(0, 12);
    filtered = _notifyAllUsers.filter(u =>
      u.username.toLowerCase().includes(tag) ||
      (u.display_name||'').toLowerCase().includes(site.toLowerCase().substring(0,10))
    );
  }
  sel.innerHTML = filtered.length
    ? filtered.map(u => `<option value="${u.id}">${u.display_name||u.username}</option>`).join('')
    : '<option value="">Aucun correspondant</option>';
}

function closeNotifyModal() {
  document.getElementById('notify-modal').style.display = 'none';
}

async function notifySend() {
  const destId = parseInt(document.getElementById('notify-dest')?.value);
  const msg    = document.getElementById('notify-msg')?.value?.trim();
  const ctx    = document.getElementById('notify-context')?.textContent || 'Notification';
  if (!destId || isNaN(destId)) { toast('Sélectionnez un destinataire', 'warn'); return; }
  if (!msg) { toast('Message vide', 'warn'); return; }
  try {
    const r = await apiFetch('/api/v1/messagerie', {
      method: 'POST', headers: authHeaders(),
      body: JSON.stringify({destinataire_id: destId, sujet: ctx, contenu: msg})
    });
    if (r.ok) { toast('✉️ Notification envoyée', 'ok'); closeNotifyModal(); }
    else toast('Erreur envoi', 'err');
  } catch(e) { toast('Erreur réseau', 'err'); }
}


// ── KANBAN ────────────────────────────────────────────────
let allTasks = [];
let draggedTaskId = null;
let editingTaskId = null;

async function loadTasks() {
  try {
    const r = await apiFetch('/api/v1/tasks/');
    allTasks = await r.json();
    renderKanban();
    // v2200 — Mettre à jour badge kanban (compte tâches non terminées)
    try {
      const ouvertes = (allTasks || []).filter(t => t && t.colonne !== 'TERMINÉ').length;
      const badge = document.getElementById('kanban-badge');
      if (badge) {
        badge.textContent = ouvertes;
        badge.style.display = ouvertes ? 'inline' : 'none';
      }
    } catch(e) {}
  } catch(e) {}
}

function renderKanban() {
  const cols = ['BACKLOG','EN_COURS','EN_ATTENTE','TERMINÉ'];
  const PRIO_LABEL = {4:'CRITIQUE',3:'HAUTE',2:'NORMALE',1:'BASSE'};
  cols.forEach(col => {
    const tasks = allTasks.filter(t => t.colonne === col);
    const cnt = document.getElementById('cnt-' + col);
    if (cnt) cnt.textContent = tasks.length;
    const el = document.getElementById('col-' + col);
    if (!el) return;
    el.innerHTML = tasks.map(t => {
      const dueTxt = t.due_at ? new Date(t.due_at).toLocaleString('fr-FR',{month:'2-digit',day:'2-digit',hour:'2-digit',minute:'2-digit'}) : '';
      const overdue = t.due_at && new Date(t.due_at) < new Date() && col !== 'TERMINÉ';
      return `
      <div class="kanban-card p${t.priorite}" id="kcard-${t.id}"
        draggable="true" ondragstart="onDragStart(event,${t.id})" ondragend="onDragEnd(event)">
        <div class="kc-actions">
          <button class="kc-btn" onclick="openTaskModal(${t.id})">✏️</button>
          <button class="kc-btn" style="color:#f87171" onclick="deleteTask(${t.id})">✕</button>
        </div>
        <div class="kc-title">${t.titre}</div>
        <div class="kc-meta">
          <span class="kc-prio kc-p${t.priorite}">${PRIO_LABEL[t.priorite]||t.priorite}</span>
          ${t.assignee ? `<span class="kc-assignee">👤 ${t.assignee}</span>` : ''}
          ${dueTxt ? `<span class="kc-due" style="color:${overdue?'#f87171':'var(--muted)'}">⏱ ${dueTxt}</span>` : ''}
        </div>
        ${t.incident_id ? `<div class="kc-inc-link">#${t.incident_id}</div>` : ''}
        ${t.description ? `<div style="font-family:var(--mono);font-size:9px;color:var(--muted);margin-top:4px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap">${t.description}</div>` : ''}
      </div>`;
    }).join('');
  });
}

function onDragStart(e, id) {
  draggedTaskId = id;
  setTimeout(() => { const el = document.getElementById('kcard-' + id); if(el) el.classList.add('dragging'); }, 0);
  e.dataTransfer.effectAllowed = 'move';
}
function onDragEnd(e) {
  document.querySelectorAll('.kanban-card').forEach(c => c.classList.remove('dragging'));
  document.querySelectorAll('.kanban-cards').forEach(c => c.classList.remove('drag-over'));
}
function onDragOver(e, col) {
  e.preventDefault(); e.dataTransfer.dropEffect = 'move';
  document.getElementById('col-' + col).classList.add('drag-over');
}
function onDragLeave(e) {
  e.currentTarget.classList.remove('drag-over');
}
async function onDrop(e, col) {
  e.preventDefault();
  document.getElementById('col-' + col).classList.remove('drag-over');
  if (draggedTaskId === null) return;
  try {
    await apiFetch(`/api/v1/tasks/${draggedTaskId}/move`, {
      method:'PUT', headers:{'Content-Type':'application/json'},
      body: JSON.stringify({colonne: col})
    });
    await loadTasks();
  } catch(err) { toast('Erreur déplacement','err'); }
  draggedTaskId = null;
}

function openTaskModal(taskId = null, defaultCol = 'BACKLOG') {
  editingTaskId = taskId;
  const titleEl = document.getElementById('task-modal-title');
  if (taskId) {
    const t = allTasks.find(x => x.id === taskId);
    if (t) {
      titleEl.textContent = 'Modifier la tâche';
      document.getElementById('tm-titre').value = t.titre;
      document.getElementById('tm-assignee').value = t.assignee || '';
      document.getElementById('tm-priorite').value = t.priorite;
      document.getElementById('tm-colonne').value = t.colonne;
      document.getElementById('tm-incident').value = t.incident_id || '';
      document.getElementById('tm-desc').value = t.description || '';
      document.getElementById('tm-due').value = t.due_at ? new Date(t.due_at).toISOString().slice(0,16) : '';
    }
  } else {
    titleEl.textContent = 'Nouvelle tâche';
    document.getElementById('tm-titre').value = '';
    document.getElementById('tm-assignee').value = '';
    document.getElementById('tm-priorite').value = 2;
    document.getElementById('tm-colonne').value = defaultCol;
    document.getElementById('tm-incident').value = '';
    document.getElementById('tm-desc').value = '';
    document.getElementById('tm-due').value = '';
  }
  document.getElementById('task-modal').classList.add('open');
  setTimeout(() => document.getElementById('tm-titre').focus(), 50);
}

function closeTaskModal() { document.getElementById('task-modal').classList.remove('open'); }

async function saveTask() {
  const titre = document.getElementById('tm-titre').value.trim();
  if (!titre) { toast('Le titre est obligatoire','err'); return; }
  const body = {
    titre,
    assignee:    document.getElementById('tm-assignee').value.trim() || null,
    priorite:    parseInt(document.getElementById('tm-priorite').value),
    colonne:     document.getElementById('tm-colonne').value,
    incident_id: parseInt(document.getElementById('tm-incident').value) || null,
    description: document.getElementById('tm-desc').value.trim() || null,
    due_at:      document.getElementById('tm-due').value || null,
  };
  try {
    if (editingTaskId) {
      await apiFetch(`/api/v1/tasks/${editingTaskId}`, {method:'PUT', headers:{'Content-Type':'application/json'}, body:JSON.stringify(body)});
    } else {
      await apiFetch('/api/v1/tasks/', {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify(body)});
    }
    closeTaskModal();
    await loadTasks();
    toast(editingTaskId ? 'Tâche mise à jour' : 'Tâche créée');
  } catch(e) { toast('Erreur sauvegarde','err'); }
}

async function deleteTask(id) {
  if (!confirm('Supprimer cette tâche ?')) return;
  await apiFetch(`/api/v1/tasks/${id}`, {method:'DELETE'});
  await loadTasks();
  toast('Tâche supprimée');
}

// ── REX ───────────────────────────────────────────────────
function openRexModal() {
  ['rex-titre','rex-pos','rex-amelio','rex-actions','rex-lecons','rex-redacteur',
   'rex-mttd-h','rex-mttd-m','rex-mttr-h','rex-mttr-m'].forEach(id => {
    const el = document.getElementById(id); if(el) el.value='';
  });
  ['rex-poles','rex-decisions','rex-jt','rex-jd'].forEach(id => {
    const el = document.getElementById(id); if(el) el.value='0';
  });
  document.getElementById('rex-modal').classList.add('open');
}
function closeRexModal() { document.getElementById('rex-modal').classList.remove('open'); }

async function saveRex() {
  const titre = document.getElementById('rex-titre').value.trim();
  if (!titre) { toast('Titre obligatoire','err'); return; }
  const parseLines = id => document.getElementById(id).value.split('\n').map(s=>s.trim()).filter(Boolean);
  // Convertir h+min en minutes totales
  const _hm = (hId, mId) => {
    const h = parseInt(document.getElementById(hId)?.value)||0;
    const m = parseInt(document.getElementById(mId)?.value)||0;
    const total = h*60+m;
    return total > 0 ? total : null;
  };
  const mttd = _hm('rex-mttd-h','rex-mttd-m');
  const mttr = _hm('rex-mttr-h','rex-mttr-m');
  const body = {
    titre,
    type_crise:      document.getElementById('rex-type').value,
    duree_minutes:   mttr,   // durée totale = MTTR
    mttd_minutes:    mttd,
    mttr_minutes:    mttr,
    nb_poles:        parseInt(document.getElementById('rex-poles').value)||0,
    nb_decisions:    parseInt(document.getElementById('rex-decisions').value)||0,
    nb_jalons_total: parseInt(document.getElementById('rex-jt').value)||0,
    nb_jalons_done:  parseInt(document.getElementById('rex-jd').value)||0,
    points_positifs: parseLines('rex-pos'),
    points_amelio:   parseLines('rex-amelio'),
    actions_futures: parseLines('rex-actions'),
    lecons:          document.getElementById('rex-lecons').value.trim(),
    redacteur:       document.getElementById('rex-redacteur').value.trim(),
  };
  try {
    const r = await apiFetch('/api/v1/rapport/rex', {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify(body)});
    if (!r.ok) throw new Error();
    closeRexModal();
    await loadRex();
    toast('Fiche REX enregistrée');
  } catch(e) { toast('Erreur sauvegarde REX','err'); }
}

async function loadRex() {
  try {
    const [rexRes, statsRes] = await Promise.all([
      apiFetch('/api/v1/rapport/rex'),
      apiFetch('/api/v1/rapport/rex-stats')
    ]);
    const rexList  = await rexRes.json();
    const stats    = await statsRes.json();
    // KPIs
    const _min = m => m ? (m>=60 ? `${Math.floor(m/60)}h${(m%60).toString().padStart(2,'0')}` : m+'min') : '—';
    document.getElementById('rex-total').textContent     = stats.total || '0';
    document.getElementById('rex-mttr').textContent      = _min(stats.avg_mttr_min);
    document.getElementById('rex-mttd').textContent      = _min(stats.avg_mttd_min);
    document.getElementById('rex-jalons-pct').textContent = stats.avg_jalons_pct != null ? stats.avg_jalons_pct + '%' : '—';
    // Bar chart by type
    const typeEl = document.getElementById('rex-by-type');
    const typeColors = {CYBER:'#60a5fa',SANITAIRE:'#4ade80',MIXTE:'#fbbf24'};
    const byType = stats.by_type || {};
    const maxV = Math.max(...Object.values(byType), 1);
    typeEl.innerHTML = Object.entries(byType).map(([k,v]) =>
      `<div class="rex-bar-row">
        <span class="rex-bar-label">${k}</span>
        <div class="rex-bar"><div class="rex-bar-fill" style="width:${v/maxV*100}%;background:${typeColors[k]||'#60a5fa'}"></div></div>
        <span class="rex-bar-val">${v}</span>
      </div>`).join('') || '<div style="color:var(--muted);font-family:var(--mono);font-size:10px">Aucune donnée</div>';
    // REX list
    const listEl = document.getElementById('rex-list');
    if (!rexList.length) { listEl.innerHTML='<div class="empty-state">Aucune fiche REX</div>'; return; }
    listEl.innerHTML = rexList.map(r => {
      const pos = _parseList(r.points_positifs);
      const amelio = _parseList(r.points_amelio);
      const actions = _parseList(r.actions_futures);
      const typeColor = {CYBER:'#60a5fa',SANITAIRE:'#4ade80',MIXTE:'#fbbf24'}[r.type_crise]||'var(--muted)';
      return `
      <div class="rex-entry-card">
        <div class="rex-entry-header">
          <span class="rex-entry-titre">${r.titre}</span>
          <span class="rex-entry-type" style="color:${typeColor};border:1px solid ${typeColor};background:${typeColor}22">${r.type_crise||'?'}</span>
          <span class="rex-entry-date">${r.created_at ? new Date(r.created_at).toLocaleDateString('fr-FR') : ''}</span>
          <button class="kc-btn" style="color:#f87171" onclick="deleteRex(${r.id})">✕</button>
        </div>
        <div class="rex-entry-metrics">
          ${r.duree_minutes ? `<div class="rex-metric"><div class="rex-metric-val">${_min(r.duree_minutes)}</div><div class="rex-metric-label">Durée</div></div>` : ''}
          ${r.mttr_minutes  ? `<div class="rex-metric"><div class="rex-metric-val" style="color:#fbbf24">${_min(r.mttr_minutes)}</div><div class="rex-metric-label">MTTR</div></div>` : ''}
          ${r.mttd_minutes  ? `<div class="rex-metric"><div class="rex-metric-val" style="color:#f87171">${_min(r.mttd_minutes)}</div><div class="rex-metric-label">MTTD</div></div>` : ''}
          ${r.nb_poles ? `<div class="rex-metric"><div class="rex-metric-val">${r.nb_poles}</div><div class="rex-metric-label">Pôles</div></div>` : ''}
          ${r.nb_jalons_total ? `<div class="rex-metric"><div class="rex-metric-val" style="color:#4ade80">${r.nb_jalons_done}/${r.nb_jalons_total}</div><div class="rex-metric-label">Jalons</div></div>` : ''}
        </div>
        ${pos.length   ? `<div class="rex-section"><div class="rex-section-title">✅ Points positifs</div>${pos.map(p=>`<span class="rex-tag pos">${p}</span>`).join('')}</div>` : ''}
        ${amelio.length? `<div class="rex-section"><div class="rex-section-title">⚠️ À améliorer</div>${amelio.map(p=>`<span class="rex-tag amelio">${p}</span>`).join('')}</div>` : ''}
        ${actions.length?`<div class="rex-section"><div class="rex-section-title">🎯 Actions</div>${actions.map(p=>`<span class="rex-tag action">${p}</span>`).join('')}</div>` : ''}
        ${r.lecons ? `<div class="rex-section"><div class="rex-section-title">📖 Leçons</div><div style="font-size:12px;color:var(--muted2);margin-top:3px">${r.lecons}</div></div>` : ''}
        ${r.incident_id ? `<div style="margin-top:7px"><a class="btn-export" href="/api/v1/rapport/rapport/${r.incident_id}" download>📄 Rapport DOCX incident #${r.incident_id}</a></div>` : ''}
        ${r.redacteur ? `<div style="font-family:var(--mono);font-size:9px;color:var(--muted);margin-top:5px">Rédacteur : ${r.redacteur}</div>` : ''}
      </div>`;
    }).join('');
  } catch(e) { console.error(e); }
}

function _parseList(val) {
  if (!val) return [];
  try { const p = JSON.parse(val); return Array.isArray(p) ? p : []; } catch { return []; }
}

async function deleteRex(id) {
  if (!confirm('Supprimer cette fiche REX ?')) return;
  await apiFetch(`/api/v1/rapport/rex/${id}`, {method:'DELETE'});
  await loadRex();
  toast('REX supprimé');
}

async function genRexFromIncident() {
  const selVal = document.getElementById('rex-inc-id').value;
  const id = parseInt(selVal);
  if (!id) { toast('Sélectionner un incident','err'); return; }
  try {
    const r = await apiFetch(`/api/v1/sitrep/history`);
    const all = await r.json();
    const inc = all.find(i => i.id === id);
    if (!inc) { toast('Incident #' + id + ' non trouvé','err'); return; }
    const ts = new Date(inc.timestamp);
    const resolved = inc.resolved_at ? new Date(inc.resolved_at) : null;
    const dureeMin = resolved ? Math.round((resolved - ts) / 60000) : null;
    const jalons = inc.jalons ? (() => { try { return JSON.parse(inc.jalons); } catch { return []; } })() : [];
    // Pré-remplir le modal REX
    document.getElementById('rex-titre').value = `Incident #${id} — ${inc.fait.substring(0,60)}`;
    document.getElementById('rex-type').value = inc.type_crise || 'CYBER';
    // Pré-remplir durée en h/min
    if (dureeMin) {
      document.getElementById('rex-mttr-h').value = Math.floor(dureeMin/60);
      document.getElementById('rex-mttr-m').value = dureeMin % 60;
    }
    document.getElementById('rex-jt').value = jalons.length;
    document.getElementById('rex-jd').value = jalons.filter(j=>j.done).length;
    // Show rapport download link
    const dlBtn = document.getElementById('dl-rapport-btn');
    if (dlBtn) { dlBtn.href = `/api/v1/rapport/rapport/${id}`; dlBtn.style.display = 'inline-flex'; }
    openRexModal();
    toast('Données pré-remplies depuis l\'incident #' + id);
  } catch(e) { toast('Erreur chargement incident','err'); }
}

// ══════════════════════════════════════════════════════════
// TRANSFERTS MODULE
// ══════════════════════════════════════════════════════════
let trData = [];
let trIncoming = []; // Transferts entrants depuis le collecteur
let _trDropZonesReady = false;
const TR_STATUTS = ['EN_PREPARATION','EN_COURS','ARRIVE','ANNULE'];
const TR_COLORS  = {EN_PREPARATION:'#fbbf24',EN_COURS:'#60a5fa',ARRIVE:'#4ade80',ANNULE:'#6b7280'};

async function loadTransferts() {
  try {
    const r = await apiFetch('/api/v1/transferts');
    if (!r.ok) return;
    trData = await r.json();
    await loadTransfertsEntrants();
    _trDropZonesReady = false; // forcer réinit drop zones
    trRender();
    trUpdateBadge();
  } catch(e) {}
}

const _trArrivesConfirmes = new Set();
const _trSortantsConfirmes = new Set();
let _trArrivesLocaux = []; // transferts entrants confirmés ARRIVE — affichés localement // IDs de nos transferts sortants confirmés ARRIVE

async function checkTransfertsSortants() {
  // Vérifier si nos transferts EN_COURS sortants ont été confirmés ARRIVE
  if (!_fedStatus?.ready || !_fedStatus?.collecteur_url) return;
  const collBase = _fedStatus.collecteur_url.replace('/api/push','');
  const token = _fedStatus.token || '';
  // Transferts locaux EN_COURS vers un GHT externe
  const monSigle = (SCRIBE_CONFIG?.etablissement?.sigle||'').toUpperCase();
  const monNom = (SCRIBE_CONFIG?.etablissement?.nom||'').toUpperCase();
  const sortants = trData.filter(t =>
    t.statut === 'EN_COURS' &&
    t.etablissement_destination &&
    t.etablissement_destination.toUpperCase() !== monSigle &&
    t.etablissement_destination.toUpperCase() !== monNom
  );
  for (const t of sortants) {
    if (_trSortantsConfirmes.has(t.id)) continue;
    try {
      const r = await fetch(`${collBase}/api/transfert-statut/${t.id}`, {
        headers: {'Authorization': 'Bearer ' + token}
      });
      if (r.ok) {
        const d = await r.json();
        if (d.statut === 'ARRIVE' || (!d.found && d.statut === 'ARRIVE')) {
          _trSortantsConfirmes.add(t.id);
          // Mettre à jour statut local
          const tok = localStorage.getItem('scribe_token')||'';
          await apiFetch(`/api/v1/transferts/${t.id}/statut`, {
            method: 'PATCH',
            headers: {'Content-Type':'application/json','Authorization':'Bearer '+tok},
            body: JSON.stringify({statut: 'ARRIVE'})
          });
          toast(`✅ Transfert confirmé arrivé par le destinataire`, 'ok');
        }
      }
    } catch(e) {}
  }
}

async function loadTransfertsEntrants() {
  trIncoming = [];
  if (!_fedStatus) await loadFedStatus();
  if (!_fedStatus?.ready || !_fedStatus?.collecteur_url) return;
  try {
    const collBase = _fedStatus.collecteur_url.replace('/api/push','');
    const r = await fetch(collBase + '/api/transferts-en-cours', {
      headers: {'Authorization': 'Bearer ' + (_fedStatus.token || '')}
    });
    if (r.ok) {
      const data = await r.json();
      // Filtrer les déjà confirmés (évite réapparition)
      const filtree = data.filter(t => !_trArrivesConfirmes.has(`${t.id_local}_${t.ght_emetteur}`));
      // Nettoyer les confirmés locaux de plus de 2h
      const cutoff = new Date(Date.now() - 2*3600*1000).toISOString();
      _trArrivesLocaux = _trArrivesLocaux.filter(t => t._confirmed_at > cutoff);
      // Fusionner : données collecteur + confirmés locaux (pour colonne ARRIVE)
      trIncoming = [...filtree];
      _trArrivesLocaux.forEach(t => {
        if (!trIncoming.find(x => x.id_local == t.id_local && x.ght_emetteur == t.ght_emetteur))
          trIncoming.push(t);
      });
    }
  } catch(e) {}
}

function trInitDropZones() {
  if (_trDropZonesReady) return;
  let allFound = true;
  TR_STATUTS.forEach(s => {
    const colEl = document.getElementById('tr-col-' + s);
    if (!colEl) { allFound = false; return; }
    colEl.addEventListener('dragover',  e => { e.preventDefault(); e.dataTransfer.dropEffect = 'move'; colEl.classList.add('drag-over'); });
    colEl.addEventListener('dragleave', e => { if (!colEl.contains(e.relatedTarget)) colEl.classList.remove('drag-over'); });
    colEl.addEventListener('drop', async e => {
      e.preventDefault(); colEl.classList.remove('drag-over');
      const draggedId = parseInt(e.dataTransfer.getData('text/plain'));
      if (draggedId && !isNaN(draggedId)) await trChangeStatut(draggedId, s);
    });
  });
  if (allFound) _trDropZonesReady = true;
}

function trRender() {
  trInitDropZones();
  const fStatut = document.getElementById('tr-filter-statut')?.value || '';
  const fSite   = document.getElementById('tr-filter-site')?.value   || '';
  const filtered = trData.filter(t =>
    (!fStatut || t.statut === fStatut) &&
    (!fSite   || t.etablissement_origine === fSite || t.etablissement_destination === fSite)
  );
  const siteSel = document.getElementById('tr-filter-site');
  if (siteSel && siteSel.options.length <= 1) {
    const sites = [...new Set(trData.flatMap(t=>[t.etablissement_origine,t.etablissement_destination]).filter(Boolean))];
    sites.forEach(s => { const o=document.createElement('option'); o.value=s; o.textContent=s; siteSel.appendChild(o); });
  }
  TR_STATUTS.forEach(s => {
    const col = document.getElementById('tr-list-'+s);
    const cpt = document.getElementById('tr-n-'+s);
    if (!col) return;
    const items = filtered.filter(t => t.statut === s);
    // Transferts entrants : EN_PREPARATION/EN_COURS → colonne EN_PREPARATION, ARRIVE → colonne ARRIVE
    const incomingForCol = s === 'EN_PREPARATION'
      ? trIncoming.filter(t => t.statut === 'EN_PREPARATION' || t.statut === 'EN_COURS')
      : s === 'ARRIVE'
      ? trIncoming.filter(t => t.statut === 'ARRIVE')
      : [];
    const totalCol = items.length + incomingForCol.length;
    if (cpt) cpt.textContent = totalCol ? `(${totalCol})` : '';
    let html = '';
    if (s === 'EN_PREPARATION' && incomingForCol.length > 0) {
      html += `<div style="font-family:var(--mono);font-size:8px;color:#a5b4fc;letter-spacing:1px;padding:4px 6px;background:rgba(99,102,241,.08);border-bottom:1px solid var(--border);margin-bottom:4px">📡 EN ATTENTE D'ACCUEIL (${incomingForCol.length})</div>`;
      html += incomingForCol.map(t => trCardHtml(t, true)).join('');
    }
    if (s === 'ARRIVE' && incomingForCol.length > 0) {
      html += `<div style="font-family:var(--mono);font-size:8px;color:#4ade80;letter-spacing:1px;padding:4px 6px;background:rgba(74,222,128,.08);border-bottom:1px solid var(--border);margin-bottom:4px">✅ ARRIVÉS (${incomingForCol.length})</div>`;
      html += incomingForCol.map(t => trCardHtml(t, true)).join('');
    }
    html += items.map(t => trCardHtml(t, false)).join('') ||
      (totalCol === 0 ? `<div style="font-family:var(--mono);font-size:9px;color:var(--muted);padding:10px;text-align:center">Aucun transfert</div>` : '');
    col.innerHTML = html;
    col.querySelectorAll('.tr-card-local').forEach(card => {
      card.draggable = true;
      card.ondragstart = e => { e.dataTransfer.setData('text/plain', card.dataset.id); e.dataTransfer.effectAllowed='move'; card.classList.add('dragging'); };
      card.ondragend = () => card.classList.remove('dragging');
    });
  });
  const total = filtered.length + trIncoming.length;
  const cpt = document.getElementById('tr-count');
  if (cpt) cpt.textContent = `${total} transfert${total>1?'s':''}`;
}

function trCardHtml(t, isIncoming) {
  const initiales = ((t.nom||'?')[0] + (t.prenom||'?')[0]).toUpperCase();
  const heure = t.horodatage_creation ? parseUTC(t.horodatage_creation)?.toLocaleTimeString('fr-FR',{hour:'2-digit',minute:'2-digit'})||'' : '';
  const date  = t.horodatage_creation ? parseUTC(t.horodatage_creation)?.toLocaleDateString('fr-FR',{day:'2-digit',month:'2-digit'}) : '';
  const col = TR_COLORS[t.statut] || 'var(--muted)';
  let etaHtml = '';
  if (t.eta) {
    const etaDate = parseUTC(t.eta) || new Date(0); const now = new Date(); const diffMs = etaDate - now;
    const etaStr = etaDate.toLocaleTimeString('fr-FR',{hour:'2-digit',minute:'2-digit'});
    if (t.statut === 'EN_COURS' && diffMs > 0) {
      const diffMin = Math.round(diffMs/60000); const h=Math.floor(diffMin/60),m=diffMin%60;
      etaHtml = `<div style="font-family:var(--mono);font-size:9px;color:#fbbf24;margin-top:3px">⏱ ETA ${etaStr} — dans ${h>0?h+'h'+String(m).padStart(2,'0'):m+' min'}</div>`;
    } else if (t.statut === 'EN_COURS') {
      etaHtml = `<div style="font-family:var(--mono);font-size:9px;color:#f87171;margin-top:3px">⚠ ETA ${etaStr} — en retard</div>`;
    } else {
      etaHtml = `<div style="font-family:var(--mono);font-size:8px;color:var(--muted);margin-top:2px">🕐 ETA : ${etaStr}</div>`;
    }
  }
  return `<div class="tr-card ${isIncoming?'':'tr-card-local'}" data-id="${t.id}" onclick="${isIncoming?'':('trOpenEdit('+t.id+')')}" style="${isIncoming?'opacity:.9;border-left:3px solid #6366f1':''}">
    <div style="display:flex;align-items:center;gap:7px">
      <div style="width:26px;height:26px;border-radius:50%;background:${col}22;border:1px solid ${col}55;display:flex;align-items:center;justify-content:center;font-size:10px;font-weight:700;color:${col};flex-shrink:0">${isIncoming?'📡':initiales}</div>
      <div style="flex:1;min-width:0">
        <div class="tr-card-patient">${isIncoming?(t.unite_origine||'—')+' → '+(t.unite_destination||'—'):(t.nom||'—')+' '+(t.prenom||'')}</div>
        ${isIncoming?`<span style="font-family:var(--mono);font-size:7px;padding:1px 5px;background:rgba(99,102,241,.2);border:1px solid #6366f1;border-radius:10px;color:#a5b4fc">📡 ${t.ght_emetteur||t.etablissement_origine}</span>`:''}
      </div>
    </div>
    <div class="tr-card-route">
      <span style="color:var(--muted2)">${t.etablissement_origine||'?'}</span>
      <span style="color:${col}">→</span>
      <span style="color:var(--text)">${t.site_destination||t.etablissement_destination||'?'}</span>
    </div>
    <div style="font-family:var(--mono);font-size:9px;color:var(--muted2);margin-top:2px">${t.unite_origine||''} → ${t.unite_destination||''}</div>
    ${etaHtml}
    ${t.commentaire?`<div style="font-family:var(--mono);font-size:8px;color:var(--muted);margin-top:3px;font-style:italic">${t.commentaire.substring(0,60)}${t.commentaire.length>60?'…':''}</div>`:''}
    <div class="tr-card-time">${date} ${heure}${isIncoming?'':' · '+(t.redacteur||'')}</div>
    ${isIncoming ? `<div style="margin-top:6px;display:flex;gap:5px">
      ${t.statut==='EN_COURS' ? `<button onclick="event.stopPropagation();trConfirmerArrivee('${t.id_local}','${t.ght_emetteur}')" style="font-family:var(--mono);font-size:8px;padding:3px 10px;background:rgba(74,222,128,.15);border:1px solid #4ade80;border-radius:3px;color:#4ade80;cursor:pointer;flex:1">✅ Confirmer arrivée</button>` : ''}
      ${t.statut==='EN_PREPARATION' ? `<span style="font-family:var(--mono);font-size:8px;color:var(--muted);padding:3px 0">En attente de départ…</span>` : ''}
    </div>` : `<div style="margin-top:6px">
      ${(t.statut==='ARRIVE'||t.statut==='ANNULE') ? `<button onclick="event.stopPropagation();trArchiver(${t.id})" style="font-family:var(--mono);font-size:8px;padding:3px 10px;background:rgba(107,114,128,.15);border:1px solid #6b7280;border-radius:3px;color:#9ca3af;cursor:pointer">🗑 Effacer</button>` : ''}
    </div>`}
  </div>`;
}

function trUpdateBadge() {
  const actifs = trData.filter(t => t.statut === 'EN_COURS' || t.statut === 'EN_PREPARATION').length;
  const entrants = trIncoming.length;
  const total = actifs + entrants;
  const badge = document.getElementById('transfert-badge');
  if (badge) {
    badge.textContent = total;
    badge.style.display = total ? 'inline' : 'none';
    badge.style.background = entrants > 0 ? '#6366f1' : '#f97316';
  }
}

// Polling transferts entrants toutes les 60s
setInterval(async () => {
  if (!authToken) return;
  await checkTransfertsSortants();
  const prevIds = new Set(trIncoming.map(t => `${t.id_local}_${t.ght_emetteur}_${t.statut}`));
  await loadTransfertsEntrants();
  // Nouveaux entrants (EN_PREPARATION ou EN_COURS)
  const nouveaux = trIncoming.filter(t =>
    (t.statut === 'EN_PREPARATION' || t.statut === 'EN_COURS') &&
    !prevIds.has(`${t.id_local}_${t.ght_emetteur}_${t.statut}`)
  );
  if (nouveaux.length) {
    toast(`📡 ${nouveaux.length} nouveau${nouveaux.length>1?'x':''} transfert${nouveaux.length>1?'s':''} entrant${nouveaux.length>1?'s':''}`, 'warn');
  }
  // Transferts passés à ARRIVE
  const arrives = trIncoming.filter(t =>
    t.statut === 'ARRIVE' &&
    !prevIds.has(`${t.id_local}_${t.ght_emetteur}_ARRIVE`)
  );
  if (arrives.length) {
    arrives.forEach(t => toast(`✅ Transfert arrivé : ${t.unite_origine||''} depuis ${t.ght_emetteur||t.etablissement_origine}`, 'ok'));
  }
  if (nouveaux.length || arrives.length) { trRender(); trUpdateBadge(); }
}, 60000);

// Données collecteur pour les sites inter-GHT
let _trAllSites = [];

async function trLoadAllSites() {
  _trAllSites = []; // reset avant reconstruction
  const local = allSites.map(s => ({nom: s.nom, etab: SCRIBE_CONFIG?.etablissement?.sigle || 'local', local: true}));
  let remote = [];
  try {
    const r = await apiFetch('/api/v1/federation/status');
    if (r.ok) {
      const fed = await r.json();
      if (fed.ready) {
        const r2 = await apiFetch('/api/v1/federation/collecteur-sites').catch(()=>null);
        if (r2 && r2.ok) {
          const cs = await r2.json();
          remote = cs.map(s => ({nom: s.nom, etab: s.sigle, local: false}));
        }
      }
    }
  } catch(e) {}
  // Dédoublonner les sites distants (même nom sous même établissement)
  const seen = new Set();
  const deduped = [...local, ...remote].filter(s => {
    const key = s.etab + '|||' + s.nom;
    if (seen.has(key)) return false;
    seen.add(key);
    return true;
  });
  _trAllSites = deduped;
}

async function trPopulateSites() {
  await trLoadAllSites();
  const origSel = document.getElementById('tr-etab-orig');
  const destSel = document.getElementById('tr-etab-dest');
  if (!origSel || !destSel) return;
  const monSigle = (SCRIBE_CONFIG?.etablissement?.sigle||'').toUpperCase();
  const etabs = {};
  // Sites distants (autres GHT)
  const nomsDistants = new Set(_trAllSites.filter(s => !s.local && s.etab.toUpperCase() !== monSigle).map(s => s.nom));
  // Locaux : regrouper sous le sigle local, exclure ceux qui existent déjà dans un GHT distant
  _trAllSites.forEach(s => {
    if (s.local || s.etab.toUpperCase() === monSigle) {
      if (nomsDistants.has(s.nom)) return; // Déjà dans un GHT distant — ne pas dupliquer
      if (!etabs[monSigle]) etabs[monSigle]=[];
      if (!etabs[monSigle].includes(s.nom)) etabs[monSigle].push(s.nom);
    } else {
      if (!etabs[s.etab]) etabs[s.etab]=[];
      if (!etabs[s.etab].includes(s.nom)) etabs[s.etab].push(s.nom);
    }
  });
  // Select ORIGINE : uniquement les sites locaux (on ne peut pas émettre depuis un autre établissement)
  const makeOptsOrig = () => '<option value="">— Site d\'origine (local) —</option>' +
    (etabs[monSigle] || []).map(s =>
      `<option value="${monSigle}|||${s}">${s}</option>`
    ).join('') +
    // Sites distants grisés et non sélectionnables pour rappel visuel
    Object.entries(etabs).filter(([etab]) => etab !== monSigle).map(([etab, sites]) =>
      `<optgroup label="— ${etab} (autre établissement)" disabled style="color:var(--muted);opacity:.4">${
        sites.map(s=>`<option value="" disabled style="color:var(--muted)">${s}</option>`).join('')
      }</optgroup>`
    ).join('');

  // Select DESTINATION : tous les établissements
  const makeOptsDest = () => '<option value="">— Sélectionner —</option>' +
    Object.entries(etabs).map(([etab, sites]) =>
      `<optgroup label="${etab}">${sites.map(s=>`<option value="${etab}|||${s}">${s}</option>`).join('')}</optgroup>`
    ).join('');

  origSel.innerHTML = makeOptsOrig();
  destSel.innerHTML = makeOptsDest();
  const mainSite = allSites[0];
  const sigle = SCRIBE_CONFIG?.etablissement?.sigle || '';
  if (mainSite && sigle) { const val=`${sigle}|||${mainSite.nom}`; origSel.value=val; trLoadUfOrig(); }
}

async function trLoadUfOrig() {
  const val = document.getElementById('tr-etab-orig')?.value || '';
  const [etab, site] = val.split('|||');
  const sel = document.getElementById('tr-uf-orig');
  if (!sel) return;
  try {
    const r = await apiFetch('/api/v1/cartographie/ufs?site=' + encodeURIComponent(site||''));
    const ufs = r.ok ? await r.json() : [];
    sel.innerHTML = ufs.length ? ufs.map(u=>`<option value="${u.libelle}">${u.libelle}</option>`).join('') :
      allUFList.map(u=>`<option value="${u.libelle}">${u.libelle}</option>`).join('') || '<option value="">— Saisir —</option>';
  } catch(e) { sel.innerHTML = allUFList.map(u=>`<option value="${u.libelle}">${u.libelle}</option>`).join('') || '<option>—</option>'; }
}

async function trLoadUfDest() {
  const val = document.getElementById('tr-etab-dest')?.value || '';
  const [etab, site] = val.includes('|||') ? val.split('|||') : [val, val];
  const sel = document.getElementById('tr-uf-dest');
  const manualDiv = document.getElementById('tr-uf-dest-manual-wrap');
  if (!sel) return;
  // Site distant → saisie libre
  const monSigle = (SCRIBE_CONFIG?.etablissement?.sigle || '').toUpperCase();
  const estLocal = !etab || etab.toUpperCase() === monSigle || allSites.some(s => s.nom === site);
  if (!estLocal) {
    sel.style.display = 'none';
    if (manualDiv) { manualDiv.style.display=''; const inp=document.getElementById('tr-uf-dest-manual'); if(inp){inp.placeholder=`Service (${etab||'GHT distant'})…`;inp.value='';} }
    return;
  }
  try {
    const r = await apiFetch('/api/v1/cartographie/ufs?site=' + encodeURIComponent(site||''));
    const ufs = r.ok ? await r.json() : [];
    if (ufs.length) { sel.style.display=''; if(manualDiv) manualDiv.style.display='none'; sel.innerHTML=ufs.map(u=>`<option value="${u.libelle}">${u.libelle}</option>`).join(''); }
    else { sel.style.display='none'; if(manualDiv) manualDiv.style.display=''; }
  } catch(e) { sel.style.display='none'; if(manualDiv) manualDiv.style.display=''; }
}

function trOpenForm() {
  document.getElementById('tr-edit-id').value = '';
  document.getElementById('tr-modal-title').textContent = '🚑 Nouveau transfert';
  const metaEl = document.getElementById('tr-modal-meta'); if(metaEl) metaEl.textContent='';
  ['tr-nom','tr-prenom','tr-njf','tr-ipp','tr-ddn','tr-comment','tr-eta'].forEach(id => { const el=document.getElementById(id); if(el) el.value=''; });
  const redEl = document.getElementById('tr-redacteur');
  if (redEl) redEl.value = currentUser?.display_name || currentUser?.username || '';
  trPopulateSites();
  const _trModal = document.getElementById('tr-modal');
  _trModal.style.display = 'flex';
  // Scroll au top pour que le formulaire commence depuis le début
  setTimeout(() => {
    const _trContent = _trModal.querySelector('[style*="overflow-y:auto"]');
    if (_trContent) _trContent.scrollTop = 0;
    _trModal.scrollTop = 0;
  }, 50);
}

async function trOpenEdit(id) {
  const t = trData.find(x => x.id === id);
  if (!t) return;
  document.getElementById('tr-edit-id').value = t.id;
  document.getElementById('tr-modal-title').textContent = '✏️ Modifier transfert';
  const metaEl = document.getElementById('tr-modal-meta');
  if (metaEl && t.horodatage_creation) {
    const dt = parseUTC(t.horodatage_creation) || new Date();
    const dateStr = dt.toLocaleString('fr-FR',{day:'2-digit',month:'2-digit',hour:'2-digit',minute:'2-digit'});
    const col = {EN_PREPARATION:'#fbbf24',EN_COURS:'#60a5fa',ARRIVE:'#4ade80',ANNULE:'#6b7280'};
    metaEl.innerHTML = `<span style="color:var(--muted)">Créé le ${dateStr}</span> · <span style="color:${col[t.statut]||'#9ca3af'}">${t.statut.replace('_',' ')}</span>`;
  }
  const simpleFields = {
    'tr-nom':t.nom,'tr-prenom':t.prenom,'tr-njf':t.nom_jeune_fille,
    'tr-ipp':t.ipp,'tr-ddn':t.date_naissance,
    'tr-redacteur':currentUser?(currentUser.display_name||currentUser.username):(t.redacteur||''),
    'tr-comment':t.commentaire,'tr-eta':t.eta?t.eta.substring(0,16):''
  };
  Object.entries(simpleFields).forEach(([id,val])=>{const el=document.getElementById(id);if(el)el.value=val||'';});
  await trPopulateSitesForEdit(t);
  document.getElementById('tr-modal').style.display = 'flex';
}

async function trPopulateSitesForEdit(t) {
  await trLoadAllSites();
  const origSel = document.getElementById('tr-etab-orig');
  const destSel = document.getElementById('tr-etab-dest');
  if (!origSel || !destSel) return;
  const etabs = {};
  _trAllSites.forEach(s => { if(!etabs[s.etab]) etabs[s.etab]=[]; etabs[s.etab].push(s.nom); });
  const addIfMissing = (sigle,nom) => { if(sigle&&nom){if(!etabs[sigle])etabs[sigle]=[];if(!etabs[sigle].includes(nom))etabs[sigle].push(nom);} };
  addIfMissing(t.etablissement_origine,t.etablissement_origine);
  addIfMissing(t.etablissement_destination,t.etablissement_destination);
  const makeOpts = () => '<option value="">— Sélectionner —</option>' +
    Object.entries(etabs).map(([etab,sites])=>`<optgroup label="${etab}">${sites.map(s=>`<option value="${etab}|||${s}">${s}</option>`).join('')}</optgroup>`).join('');
  origSel.innerHTML = makeOpts(); destSel.innerHTML = makeOpts();
  const findOpt=(sel,etab,nom)=>{const exact=`${etab}|||${nom}`;if([...sel.options].some(o=>o.value===exact)){sel.value=exact;return;}const byNom=[...sel.options].find(o=>o.value.endsWith('|||'+nom));if(byNom){sel.value=byNom.value;return;}const opt=document.createElement('option');opt.value=`${etab}|||${nom}`;opt.textContent=nom;sel.appendChild(opt);sel.value=opt.value;};
  findOpt(origSel,t.etablissement_origine,t.etablissement_origine);
  // Destination : chercher dans sites distants si sigle GHT externe
  const _destStored = t.etablissement_destination || '';
  const _siteStored = t.site_destination || '';
  // Chercher d'abord par site_destination (nom exact du site), puis par sigle GHT
  const _destBySite = _siteStored
    ? _trAllSites.find(s => !s.local && s.nom.toUpperCase() === _siteStored.toUpperCase())
    : null;
  const _destByNom  = _trAllSites.find(s => !s.local && s.nom.toUpperCase() === _destStored.toUpperCase());
  const _destByEtab = _trAllSites.find(s => !s.local && s.etab.toUpperCase() === _destStored.toUpperCase());
  const _destRemote = _destBySite || _destByNom || _destByEtab;
  if (_destRemote) {
    findOpt(destSel, _destRemote.etab, _destRemote.nom);
  } else {
    findOpt(destSel, _destStored, _siteStored || _destStored);
  }
  const ufOrigSel=document.getElementById('tr-uf-orig');
  if(ufOrigSel){if(![...ufOrigSel.options].some(o=>o.value===t.unite_origine)){const o=document.createElement('option');o.value=t.unite_origine;o.textContent=t.unite_origine;ufOrigSel.appendChild(o);}ufOrigSel.value=t.unite_origine||'';}
  const ufDestSel=document.getElementById('tr-uf-dest');
  if(ufDestSel){if(![...ufDestSel.options].some(o=>o.value===t.unite_destination)){const o=document.createElement('option');o.value=t.unite_destination;o.textContent=t.unite_destination;ufDestSel.appendChild(o);}ufDestSel.value=t.unite_destination||'';ufDestSel.style.display='';const mw=document.getElementById('tr-uf-dest-manual-wrap');if(mw)mw.style.display='none';}
}

async function trSave() {
  const tok = localStorage.getItem('scribe_token') || '';
  const nom=document.getElementById('tr-nom').value.trim();
  const prenom=document.getElementById('tr-prenom').value.trim();
  const origVal=document.getElementById('tr-etab-orig').value||'';
  const [etabO,siteO]=origVal.includes('|||')?origVal.split('|||'):[origVal,origVal];
  const destVal=document.getElementById('tr-etab-dest').value||'';
  const [etabD,siteD]=destVal.includes('|||')?destVal.split('|||'):[destVal,destVal];
  const ufO=document.getElementById('tr-uf-orig')?.value?.trim()||siteO;
  const ufDestManualWrap=document.getElementById('tr-uf-dest-manual-wrap');
  const ufDestManual=document.getElementById('tr-uf-dest-manual')?.value?.trim();
  const ufD=(ufDestManualWrap&&ufDestManualWrap.style.display!=='none'&&ufDestManual)?ufDestManual:(document.getElementById('tr-uf-dest')?.value?.trim()||siteD);
  const etabOClean=etabO.trim(); const etabDClean=etabD.trim();
  const redc=document.getElementById('tr-redacteur').value.trim();
  const etaVal=document.getElementById('tr-eta')?.value||null;
  if (!nom||!prenom||!ufO||!etabOClean||!ufD||!etabDClean||!redc) { toast('Champs obligatoires manquants (*)','warn'); return; }
  const editId=document.getElementById('tr-edit-id').value;
  // Résoudre le vrai nom de site destination (siteD peut être le sigle GHT si le select n'avait pas de |||)
  let siteDResolved = siteD;
  if (!siteD || siteD === etabDClean) {
    // Chercher dans _trAllSites le premier site de cet établissement
    const siteEntry = _trAllSites.find(s => s.etab.toUpperCase() === etabDClean.toUpperCase() && !s.local);
    if (siteEntry) siteDResolved = siteEntry.nom;
  }
  const payload={nom,prenom,
    nom_jeune_fille:document.getElementById('tr-njf').value.trim()||null,
    ipp:document.getElementById('tr-ipp').value.trim()||null,
    date_naissance:document.getElementById('tr-ddn').value||null,
    unite_origine:ufO,etablissement_origine:etabOClean,
    unite_destination:ufD,etablissement_destination:etabDClean,site_destination:siteDResolved||etabDClean,
    redacteur:redc,commentaire:document.getElementById('tr-comment').value.trim()||null,
    statut:'EN_PREPARATION',eta:etaVal||null};
  const url=editId?`/api/v1/transferts/${editId}`:'/api/v1/transferts';
  const method=editId?'PUT':'POST';
  const r=await fetch(url,{method,headers:{'Content-Type':'application/json','Authorization':'Bearer '+tok},body:JSON.stringify(payload)});
  if (r.ok) {
    const saved=await r.json();
    document.getElementById('tr-modal').style.display='none';
    toast(editId?'✓ Transfert mis à jour':'✓ Transfert créé','ok');
    await loadTransferts();
    await trPushCollecteur(saved);
  } else { const d=await r.json().catch(()=>({})); toast('Erreur : '+(d.detail||r.status),'err'); }
}

async function trPushCollecteur(t) {
  const monSigle=(SCRIBE_CONFIG?.etablissement?.sigle||_fedStatus?.etablissement||'').toUpperCase();
  const _destNom = (t.etablissement_destination||'').toUpperCase();
  const _destEntry = _trAllSites.find(s => s.nom.toUpperCase()===_destNom || s.etab.toUpperCase()===_destNom);
  const destSigle = _destEntry ? _destEntry.etab.toUpperCase() : _destNom;
  if (!monSigle||destSigle===monSigle) return;
  if (!_fedStatus) await loadFedStatus();
  if (!_fedStatus?.ready||!_fedStatus?.collecteur_url) return;
  const collBase=_fedStatus.collecteur_url.replace('/api/push','');
  const token=_fedStatus.token||'';
  if (!token) return;
  try {
    await fetch(collBase+'/api/push-transfert',{method:'POST',
      headers:{'Authorization':'Bearer '+token,'Content-Type':'application/json'},
      body:JSON.stringify({id_local:t.id,ght_emetteur_nom:SCRIBE_CONFIG?.etablissement?.nom||monSigle,
        ght_destinataire:destSigle,unite_origine:t.unite_origine,etablissement_origine:t.etablissement_origine,
        unite_destination:t.unite_destination,etablissement_destination:t.etablissement_destination,site_destination:t.site_destination||t.etablissement_destination,
        statut:t.statut,eta:t.eta,horodatage_depart:t.horodatage_depart,commentaire:t.commentaire})});
  } catch(e) {}
}

async function trArchiver(id) {
  if (!confirm('Effacer ce transfert de la liste ?')) return;
  const r = await apiFetch(`/api/v1/transferts/${id}`, {method:'DELETE', headers:authHeaders()});
  if (r && r.ok) { toast('Transfert effacé','ok'); await loadTransferts(); }
  else toast('Erreur suppression','err');
}

async function trChangeStatut(id, newStatut) {
  const tok = localStorage.getItem('scribe_token') || '';
  const r = await apiFetch(`/api/v1/transferts/${id}/statut`, {
    method:'PATCH', headers:{'Content-Type':'application/json','Authorization':'Bearer '+tok},
    body: JSON.stringify({statut: newStatut})
  });
  if (r.ok) {
    await loadTransferts();
    toast(`→ ${newStatut.replace('_',' ')}`, 'ok');
    const t = trData.find(x => x.id === id);
    if (t) await trPushCollecteur({...t, statut: newStatut});
  }
}

async function trConfirmerArrivee(idLocal, ghtEmetteur) {
  // Notifier le collecteur que le transfert est ARRIVÉ
  if (!_fedStatus) await loadFedStatus();
  if (!_fedStatus?.ready || !_fedStatus?.collecteur_url) {
    toast('Collecteur non disponible', 'warn'); return;
  }
  const collBase = _fedStatus.collecteur_url.replace('/api/push','');
  const token = _fedStatus.token || '';
  if (!token) { toast('Token fédération manquant', 'warn'); return; }
  try {
    // Mettre à jour le statut du transfert dans le collecteur
    await fetch(collBase + '/api/push-transfert', {
      method: 'POST',
      headers: {'Authorization': 'Bearer ' + token, 'Content-Type': 'application/json'},
      body: JSON.stringify({
        id_local: idLocal,
        ght_emetteur_nom: ghtEmetteur,
        ght_destinataire: (SCRIBE_CONFIG?.etablissement?.sigle || '').toUpperCase(),
        statut: 'ARRIVE',
        etablissement_origine: ghtEmetteur,
        etablissement_destination: SCRIBE_CONFIG?.etablissement?.sigle || '',
        unite_origine: '', unite_destination: '',
      })
    });
    toast('✅ Arrivée confirmée — notifié au collecteur', 'ok');
    // Retirer de la liste entrante localement
    _trArrivesConfirmes.add(`${idLocal}_${ghtEmetteur.toUpperCase()}`);
    // Garder une copie locale pour affichage dans colonne ARRIVE
    const tConfirme = trIncoming.find(t => t.id_local == idLocal && (t.ght_emetteur||'').toUpperCase() === ghtEmetteur.toUpperCase());
    if (tConfirme) {
      _trArrivesLocaux.push({...tConfirme, statut:'ARRIVE', _confirmed_at: new Date().toISOString()});
    }
    trIncoming = trIncoming.filter(t => !(t.id_local == idLocal && (t.ght_emetteur||'').toUpperCase() === ghtEmetteur.toUpperCase()));
    trRender(); trUpdateBadge();
  } catch(e) {
    toast('Erreur lors de la confirmation', 'err');
  }
}



// ── FEDERATION STATUS (panel admin) ─────────────────────────────────────────
// ── ADMIN : config IA et routing ────────────────────────────────────────────

async function loadAdminIA() {
  const box = document.getElementById('admin-ia-info');
  if (!box) return;
  try {
    const r = await apiFetch('/api/v1/admin/config/ia');
    if (!r.ok) { box.innerHTML = '<span style="color:#f87171">Non disponible</span>'; return; }
    const d = await r.json();
    const hdsColor = d.hds ? '#4ade80' : '#f87171';
    const hdsLabel = d.hds ? '✓ Conforme HDS' : '⚠ Non certifié HDS';
    const localLabel = d.local ? ' · Local (zéro donnée externe)' : '';
    box.innerHTML =
      '<div style="display:flex;flex-direction:column;gap:6px">' +
        '<div><span style="color:var(--muted);font-family:var(--mono);font-size:9px">FOURNISSEUR</span>' +
          '<div style="font-weight:700;margin-top:2px">' + d.label + '</div></div>' +
        '<div><span style="color:var(--muted);font-family:var(--mono);font-size:9px">MODELE</span>' +
          '<div style="font-family:var(--mono);font-size:10px;margin-top:2px">' + (d.model || '(défaut)') + '</div></div>' +
        '<div><span style="color:' + hdsColor + '">' + hdsLabel + '</span>' +
          '<span style="color:var(--muted);font-size:10px">' + localLabel + '</span></div>' +
        (d.has_key ? '<div style="color:#4ade80;font-size:10px">✓ Clé API configurée</div>' :
                     '<div style="color:#fbbf24;font-size:10px">⚠ Aucune clé API — configurer SCRIBE_IA_KEY</div>') +
        '<div style="font-family:var(--mono);font-size:9px;color:var(--muted);margin-top:4px">' +
          'Modifier via variable d&#39;env SCRIBE_IA_PROVIDER / SCRIBE_IA_KEY / SCRIBE_IA_MODEL</div>' +
      '</div>';
  } catch(e) { box.innerHTML = '<span style="color:var(--muted);font-size:10px">Plugin IA inactif</span>'; }
  // Charger la liste des fournisseurs disponibles
  try {
    const r2 = await apiFetch('/api/v1/admin/config/ia');
    if (!r2 || !r2.ok) return;
    const d2 = await r2.json();
    const provBox = document.getElementById('admin-ia-providers');
    if (!provBox || !d2.all_providers) return;
    provBox.innerHTML = d2.all_providers.map(p => {
      const isActive = p.id === d2.provider;
      const hdsLabel = p.hds ? '<span style="color:#4ade80">✓ HDS</span>' : '<span style="color:#fbbf24">⚠ Non-HDS</span>';
      return '<div style="display:flex;align-items:center;gap:10px;padding:10px 12px;margin-bottom:6px;background:var(--surface' + (isActive?'':' 2') + ');border:' + (isActive?'2px solid #003189':'1px solid var(--border2)') + ';border-radius:6px;cursor:pointer" onclick="adminShowIaConfig(&quot;' + p.id + '&quot;,&quot;' + p.label.replace(/'/g,'') + '&quot;)">' +
        '<div style="flex:1">' +
          '<div style="font-family:var(--mono);font-size:10px;font-weight:700">' + p.label + (isActive ? ' <span style="color:#4ade80;font-weight:400">← actif</span>' : '') + '</div>' +
          '<div style="font-family:var(--mono);font-size:9px;margin-top:2px">' + hdsLabel + (p.local ? ' · <span style="color:var(--muted)">Local</span>' : '') + '</div>' +
        '</div>' +
        '<span style="font-family:var(--mono);font-size:9px;color:var(--muted)">⚙ Configurer</span>' +
      '</div>';
    }).join('') +
    '<div id="ia-config-panel" style="display:none;margin-top:14px;padding:14px;background:var(--surface2);border:1px solid var(--border2);border-radius:6px"></div>';
  } catch(e) {}
}

function adminShowIaConfig(providerId, providerLabel) {
  const panel = document.getElementById('ia-config-panel');
  if (!panel) return;
  panel.style.display = 'block';
  panel.scrollIntoView({behavior:'smooth', block:'nearest'});
  panel.innerHTML =
    '<div style="font-family:var(--mono);font-size:11px;font-weight:700;margin-bottom:10px">⚙ Configurer : ' + providerLabel + '</div>' +
    '<p style="font-family:var(--mono);font-size:10px;color:var(--muted);margin-bottom:10px">' +
      'Pour activer ce fournisseur, définir les variables d\'environnement suivantes avant de démarrer SCRIBE :' +
    '</p>' +
    '<div style="background:var(--surface3);border-radius:4px;padding:10px;font-family:var(--mono);font-size:10px;line-height:2">' +
      '<div>export <strong>SCRIBE_IA_PROVIDER</strong>=' + providerId + '</div>' +
      '<div>export <strong>SCRIBE_IA_KEY</strong>=<em>votre-clé-api</em></div>' +
      '<div>export <strong>SCRIBE_IA_MODEL</strong>=<em>nom-du-modèle (optionnel)</em></div>' +
    '</div>' +
    '<div id="ia-config-key-section" style="margin-top:12px">' +
      '<label style="font-family:var(--mono);font-size:9px;color:var(--muted);letter-spacing:1px;display:block;margin-bottom:4px">CLÉ API (sauvegardée en variable d\'env temporaire)</label>' +
      '<div style="display:flex;gap:8px">' +
        '<input type="password" id="ia-config-key-input" placeholder="sk-... ou clé API" style="flex:1;font-family:var(--mono);font-size:10px;padding:6px 8px;background:var(--surface2);border:1px solid var(--border2);border-radius:4px;color:var(--text)">' +
        '<button onclick="adminSaveIaKey(&quot;' + providerId + '&quot;)" style="font-family:var(--mono);font-size:10px;padding:6px 14px;background:#003189;color:#fff;border:none;border-radius:4px;cursor:pointer">Tester</button>' +
      '</div>' +
      '<div id="ia-config-result" style="font-family:var(--mono);font-size:10px;margin-top:6px"></div>' +
    '</div>';
}

async function adminSaveIaKey(providerId) {
  const key = document.getElementById('ia-config-key-input')?.value?.trim();
  const res = document.getElementById('ia-config-result');
  if (!key) { if(res) { res.style.color='#fbbf24'; res.textContent='⚠ Saisir une clé API'; } return; }
  if(res) { res.style.color='var(--muted)'; res.textContent='⏳ Test de connexion…'; }
  try {
    const r = await apiFetch('/api/v1/admin/config/ia/test', {
      method: 'POST',
      headers: {'Content-Type':'application/json'},
      body: JSON.stringify({provider: providerId, api_key: key})
    });
    const d = await r.json();
    if (d.ok) {
      if(res) { res.style.color='#4ade80'; res.textContent='✓ Connexion OK — ' + (d.message||''); }
    } else {
      if(res) { res.style.color='#f87171'; res.textContent='✗ ' + (d.detail||d.message||'Erreur'); }
    }
  } catch(e) { if(res) { res.style.color='#f87171'; res.textContent='Erreur réseau : ' + e.message; } }
}

async function loadAdminRouting() {
  const box = document.getElementById('admin-routing-info');
  if (!box) return;
  try {
    const r = await apiFetch('/api/v1/admin/config/routing');
    if (!r.ok) { box.innerHTML = '<span style="color:#f87171">Erreur</span>'; return; }
    const d = await r.json();
    box.innerHTML =
      '<div style="display:flex;flex-direction:column;gap:6px">' +
        '<div><span style="color:var(--muted);font-family:var(--mono);font-size:9px">MOTEUR ACTIF</span>' +
          '<div style="font-weight:700;margin-top:2px">' + d.engine + '</div></div>' +
        '<div style="font-family:var(--mono);font-size:9px;word-break:break-all">' + d.url + '</div>' +
        '<div style="font-size:10px;color:var(--muted)">Timeout : ' + d.timeout + 's' +
          (d.has_key ? ' · Clé API configurée' : '') + '</div>' +
        '<div style="font-family:var(--mono);font-size:9px;color:var(--muted);margin-top:4px">' +
          'Modifier via SCRIBE_ROUTING_ENGINE / SCRIBE_OSRM_URL</div>' +
      '</div>';
  } catch(e) { box.innerHTML = '<span style="color:var(--muted);font-size:10px">Non disponible</span>'; }
}

// ── ADMIN : gestion des plugins ─────────────────────────────────────────────

async function adminUploadPlugin() {
  const file = document.getElementById('plugin-upload-file')?.files[0];
  const res  = document.getElementById('plugin-upload-result');
  if (!file) { if(res) { res.style.color='#fbbf24'; res.textContent='⚠ Sélectionner un fichier ZIP'; } return; }
  if (!file.name.endsWith('.zip')) { if(res) { res.style.color='#f87171'; res.textContent='✗ Format ZIP requis'; } return; }
  if(res) { res.style.color='var(--muted)'; res.textContent='⬆ Upload en cours…'; }
  const formData = new FormData();
  formData.append('file', file);
  try {
    const token = localStorage.getItem('scribe_token') || '';
    const r = await fetch('/api/v1/admin/plugins/upload', {
      method: 'POST',
      headers: {'Authorization': 'Bearer ' + token},
      body: formData
    });
    if (r.ok) {
      const d = await r.json();
      if(res) { res.style.color='#4ade80'; res.textContent='✓ Plugin ' + (d.plugin_id||file.name) + ' installé — redémarrage requis'; }
      setTimeout(loadAdminPlugins, 800);
    } else {
      const d = await r.json().catch(()=>({}));
      if(res) { res.style.color='#f87171'; res.textContent='✗ ' + (d.detail||'Erreur upload'); }
    }
  } catch(e) { if(res) { res.style.color='#f87171'; res.textContent='Erreur réseau : ' + e.message; } }
}

async function deletePlugin(pluginId) {
  if (!confirm('Désactiver et supprimer le plugin "' + pluginId + '" ?')) return;
  try {
    const r = await apiFetch('/api/v1/admin/plugins/' + pluginId, {method:'DELETE'});
    if (r.ok) { toast('Plugin supprimé', 'ok'); loadAdminPlugins(); }
    else { const d = await r.json().catch(()=>({})); toast('Erreur : ' + (d.detail||r.status), 'err'); }
  } catch(e) { toast('Erreur réseau', 'err'); }
}

async function loadAdminPlugins() {
  const box = document.getElementById('admin-plugins-list');
  if (!box) return;
  box.innerHTML = '<div style="color:var(--muted);font-size:11px">Chargement...</div>';
  try {
    const r = await apiFetch('/api/v1/admin/plugins');
    if (!r.ok) { box.innerHTML = '<div style="color:#f87171">Erreur chargement plugins</div>'; return; }
    const plugins = await r.json();
    if (!plugins.length) { box.innerHTML = '<div style="color:var(--muted);font-size:11px">Aucun plugin configuré</div>'; return; }
    box.innerHTML = plugins.map(p => {
      const stateColor = p.loaded ? '#4ade80' : (p.enabled ? '#fbbf24' : 'var(--muted)');
      const stateLabel = p.loaded ? 'actif' : (p.enabled ? 'activé — redémarrage requis' : 'désactivé — redémarrage requis');
      const legacyBadge = p.legacy ? '<span style="font-size:9px;color:var(--muted);margin-left:6px">[legacy]</span>' : '';
      const trackBg = p.enabled ? '#003189' : 'var(--border2)';
      const thumbLeft = p.enabled ? '18px' : '2px';
      const checked = p.enabled ? 'checked' : '';
      return '<div style="display:flex;align-items:center;gap:10px;padding:8px 10px;background:var(--surface2);border-radius:6px;border:1px solid var(--border2)">' +
        '<span style="font-size:14px">' + (p.icon || '🔌') + '</span>' +
        '<div style="flex:1">' +
          '<div style="font-family:var(--mono);font-size:10px;font-weight:700">' + p.id + legacyBadge + '</div>' +
          '<div style="font-size:10px;color:' + stateColor + '">' + stateLabel + '</div>' +
        '</div>' +
        '<div style="position:relative;width:36px;height:20px;cursor:pointer" data-plugin-id="' + p.id + '" data-enabled="' + p.enabled + '" onclick="pluginToggleClick(this)">' +
          '<div id="plug-track-' + p.id + '" style="position:absolute;inset:0;border-radius:10px;background:' + trackBg + ';transition:background .2s"></div>' +
          '<div id="plug-thumb-' + p.id + '" style="position:absolute;top:2px;left:' + thumbLeft + ';width:16px;height:16px;border-radius:50%;background:#fff;transition:left .2s"></div>' +
        '</div>' +
      '</div>';
    }).join('');
  } catch(e) {
    box.innerHTML = '<div style="color:#f87171;font-size:11px">Erreur : ' + e.message + '</div>';
  }
}

function pluginToggleClick(el) {
  const pluginId = el.dataset.pluginId;
  const currentEnabled = el.dataset.enabled === 'true';
  const newEnabled = !currentEnabled;
  togglePlugin(pluginId, newEnabled);
}

async function togglePlugin(pluginId, enabled) {
  const track = document.getElementById('plug-track-' + pluginId);
  const thumb = document.getElementById('plug-thumb-' + pluginId);
  if (track) track.style.background = enabled ? '#003189' : 'var(--border2)';
  if (thumb) thumb.style.left = enabled ? '18px' : '2px';
  try {
    const token = localStorage.getItem('scribe_token');
    if (!token) { toast('Session expirée — veuillez vous reconnecter', 'err'); return; }
    const r = await fetch('/api/v1/admin/plugins/' + pluginId + '/toggle', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'Authorization': 'Bearer ' + token
      },
      body: JSON.stringify({enabled})
    });
    if (r.status === 401 || r.status === 403) {
      toast('Accès refusé — rôle admin requis ou session expirée', 'err');
      // Rétablir l'état visuel
      if (track) track.style.background = enabled ? 'var(--border2)' : '#003189';
      if (thumb) thumb.style.left = enabled ? '2px' : '18px';
      return;
    }
    if (!r.ok) { toast('Erreur toggle plugin (' + r.status + ')', 'err'); return; }
    const data = await r.json();
    toast((enabled ? '🧩 Activé' : '🔌 Désactivé') + ' — ' + pluginId +
      (data.restart_required ? ' · Redémarrage requis pour prendre effet' : ''), 'ok');
    setTimeout(loadAdminPlugins, 600);
  } catch(e) {
    toast('Erreur réseau : ' + e.message, 'err');
  }
}

async function loadFedStatusPanel() {
  const box = document.getElementById('fed-status-box');
  if (!box) return;
  box.innerHTML = '<span style="color:var(--muted)">Chargement...</span>';
  try {
    const tok = localStorage.getItem('scribe_token') || '';
    const r = await apiFetch('/api/v1/federation/status', {headers:{'Authorization':'Bearer '+tok}});
    const d = await r.json();
    const ok = d.ready;
    const col = ok ? 'var(--green)' : d.enabled ? '#f97316' : 'var(--muted)';
    box.innerHTML = `
      <div style="display:flex;align-items:center;gap:8px;margin-bottom:8px">
        <span style="width:8px;height:8px;border-radius:50%;background:${col};display:inline-block"></span>
        <span style="font-weight:700;color:${col}">${ok ? '✓ ACTIVE' : d.enabled ? '⚠ ACTIVÉE MAIS NON PRÊTE' : '— DÉSACTIVÉE'}</span>
      </div>
      <div><span style="color:var(--muted)">Collecteur :</span> ${d.collecteur_url || '—'}</div>
      <div><span style="color:var(--muted)">Token :</span> ${d.token_preview || '—'}</div>
      <div><span style="color:var(--muted)">Établissement :</span> ${d.etablissement || '—'}</div>
      <div><span style="color:var(--muted)">Intervalle :</span> ${d.intervalle_s || '—'}s</div>
      ${!ok && d.enabled ? '<div style="margin-top:6px;color:#f97316">⚠ Vérifier que config.js est généré et que le collecteur est démarré</div>' : ''}
      ${ok ? '<div style="margin-top:6px;color:var(--muted)">ℹ Aller sur le collecteur → ⏳ EN ATTENTE → cliquer ✓ ACCEPTER</div>' : ''}`;
  } catch(e) {
    box.innerHTML = `<span style="color:var(--red)">✗ Erreur : ${e.message}</span>`;
  }
}

// ── SUIVI IA (champs de question) ───────────────────────────────────────────
let _iaConvGlobal  = [];
let _iaConvSoins   = [];
let _iaConvAnalyse = [];

async function askAlbertFollowUp(zone) {
  const fieldId  = zone === 'global' ? 'gap-question' : zone === 'soins' ? 'soins-albert-question' : 'analyse-question';
  const bodyId   = zone === 'global' ? 'gap-body' : zone === 'soins' ? 'soins-albert-body' : 'analyse-live-result';
  const conv     = zone === 'global' ? _iaConvGlobal : zone === 'soins' ? _iaConvSoins : _iaConvAnalyse;

  const q = document.getElementById(fieldId)?.value?.trim();
  if (!q) return;
  document.getElementById(fieldId).value = '';

  const box = document.getElementById(bodyId);
  if (!box) return;
  const prev = box.textContent || '';
  box.textContent = prev + '\n\n❓ ' + q + '\n⏳ Réponse en cours...';
  box.scrollTop = box.scrollHeight;

  conv.push({role: 'user', content: q});

  try {
    const r = await apiFetch('/api/v1/albert/ask', {
      method: 'POST',
      headers: authHeaders(),
      body: JSON.stringify({question: q, contexte: prev.substring(0, 800)})
    });
    if (r.ok) {
      const d = await r.json();
      const text = d.reponse || d.response || d.content || '';
      conv.push({role: 'assistant', content: text});
      box.textContent = prev + '\n\n❓ ' + q + '\n\n💬 ' + text;
    } else {
      box.textContent = prev + '\n\n❓ ' + q + '\n\n⚠ Erreur IA (' + r.status + ')';
    }
  } catch(e) {
    box.textContent = prev + '\n\n❓ ' + q + '\n\n⚠ Erreur réseau';
  }
  box.scrollTop = box.scrollHeight;
}

// ── ANALYSE LIVE (main courante complète) ───────────────────────────────────
async function loadAnalyseLive() {
  const box = document.getElementById('analyse-live-result');
  if (!box) return;
  box.style.display = 'block';
  const followupDiv = document.getElementById('analyse-live-followup');
  if (followupDiv) followupDiv.style.display = 'flex';
  _iaConvAnalyse = [];
  box.textContent = '⏳ Chargement de la main courante...';

  let logs = [], incidents = [], messages = [], transferts = [];
  try {
    const r = await apiFetch('/api/v1/main-courante/logs?limit=500', {headers: authHeaders()});
    if (r.ok) logs = await r.json();
  } catch(e) {}
  try {
    const [rI, rM, rT] = await Promise.all([
      apiFetch('/api/v1/sitrep/history?limit=50', {headers: authHeaders()}),
      apiFetch('/api/v1/messagerie?limit=50', {headers: authHeaders()}),
      apiFetch('/api/v1/transferts', {headers: authHeaders()}),
    ]);
    if (rI.ok) incidents = await rI.json();
    if (rM.ok) { const d = await rM.json(); messages = d.messages || d || []; }
    if (rT.ok) transferts = await rT.json();
  } catch(e) {}

  if (!logs.length && !incidents.length) {
    box.textContent = 'ℹ Aucun événement enregistré dans cette session.';
    return;
  }

  // Analyse locale immédiate (pas d'appel IA externe)
  const critiques = incidents.filter(i => i.urgency >= 3 && i.status !== 'RÉSOLU');
  const resolus   = incidents.filter(i => i.status === 'RÉSOLU');
  const enCours   = transferts.filter(t => t.statut === 'EN_COURS');

  const lines = [
    '📊 ANALYSE DE SESSION — SCRIBE v2.3.65',
    '',
    '📋 RÉSUMÉ',
    '  • ' + incidents.length + ' incident(s) déclaré(s) dont ' + critiques.length + ' critique(s) non résolus',
    '  • ' + resolus.length + ' incident(s) résolu(s)',
    '  • ' + transferts.length + ' transfert(s) patient dont ' + enCours.length + ' en cours',
    '  • ' + messages.length + ' message(s) échangé(s)',
    '  • ' + logs.length + ' événement(s) loggués en main courante',
    '',
    '⏱ DERNIERS ÉVÉNEMENTS (main courante)',
  ];
  logs.slice(0, 15).forEach(l => {
    const ts = l.timestamp ? l.timestamp.substring(11,16) : '?';
    lines.push('  [' + ts + '] ' + l.categorie + ' | ' + l.action + ' — ' + (l.detail||'').substring(0,70));
  });
  if (critiques.length > 0) {
    lines.push('');
    lines.push('⚠️ INCIDENTS CRITIQUES NON RÉSOLUS');
    critiques.forEach(i => lines.push('  • [' + i.urgency + '★] ' + (i.site_id||'') + ' | ' + (i.fait||'').substring(0,80)));
  } else {
    lines.push('');
    lines.push('✓ Aucun incident critique non résolu');
  }
  if (enCours.length > 0) {
    lines.push('');
    lines.push('🚑 TRANSFERTS EN COURS');
    enCours.forEach(t => lines.push('  • ' + t.unite_origine + ' → ' + t.unite_destination + ' (' + t.etablissement_destination + ')'));
  }

  box.textContent = lines.join('\n');

  // Demander à Albert si disponible
  try {
    const r2 = await apiFetch('/api/v1/albert/ask', {
      method: 'POST', headers: authHeaders(),
      body: JSON.stringify({
        question: 'Analyse cette session de crise et donne une synthèse opérationnelle : '
          + incidents.length + ' incidents, ' + critiques.length + ' critiques non résolus, '
          + transferts.length + ' transferts, ' + messages.length + ' messages. '
          + 'Points positifs, axes d amélioration, 3 recommandations.'
      })
    });
    if (r2.ok) {
      const d2 = await r2.json();
      const aiText = d2.reponse || d2.response || d2.content || '';
      if (aiText) {
        lines.push('');
        lines.push('🤖 ANALYSE ALBERT AI');
        lines.push(aiText);
        box.textContent = lines.join('\n');
      }
    }
  } catch(e) {}
}

// Patch openTab to load kanban/rex
const _origOpenTab = openTab;
openTab = function(id, btn) {
  _origOpenTab(id, btn);
  if (id === 'tab-kanban') loadTasks();
  if (id === 'tab-rex')    loadRex();
  if (id === 'tab-communique') loadCommData();
};

// updateMap sans auto-zoom (évite la boucle flyTo NaN)
const _origUpdateMap = updateMap;
updateMap = function(bySite) {
  _origUpdateMap(bySite);
};


/* ═══════════════════ SCRIBE v2.3.65 ══════════════════ */

// ── THEME SWITCH ─────────────────────────────────────────────────────
function toggleTheme() {
  const isLight = document.body.classList.toggle('light');
  const btn = document.getElementById('theme-toggle-btn');
  if (btn) btn.textContent = isLight ? '🌙' : '☀️';
  localStorage.setItem('scribe_theme', isLight ? 'light' : 'dark');
}

// Restaurer le thème au démarrage — clair par défaut
(function() {
  const saved = localStorage.getItem('scribe_theme');
  // Si explicitement 'dark', appliquer dark. Sinon light.
  if (saved !== 'dark') {
    document.body.classList.add('light');
    document.addEventListener('DOMContentLoaded', () => {
      const btn = document.getElementById('theme-toggle-btn');
      if (btn) btn.textContent = '🌙';
    });
  } else {
    // S'assurer que dark est actif (pas de classe 'light')
    document.body.classList.remove('light');
  }
})();

// ── KANBAN : charger incidents dans le select tm-incident ─────────────
async function populateIncidentSelect() {
  try {
    const incidents = await apiFetch('/api/v1/sitrep/history').then(r=>r.json());
    const sel = document.getElementById('tm-incident');
    if (!sel) return;
    // Garder la valeur actuelle
    const current = sel.value;
    sel.innerHTML = '<option value="">— Aucun —</option>';
    // Trier : ouverts d'abord, puis par urgence desc
    const open = incidents.filter(i => i.status !== 'RÉSOLU').sort((a,b) => b.urgency - a.urgency);
    const closed = incidents.filter(i => i.status === 'RÉSOLU');
    if (open.length) {
      const grp = document.createElement('optgroup');
      grp.label = '🔴 Incidents ouverts';
      open.forEach(i => {
        const opt = document.createElement('option');
        opt.value = i.id;
        opt.textContent = `#${i.id} — U${i.urgency} ${i.site_id} : ${i.fait.substring(0,45)}${i.fait.length>45?'…':''}`;
        grp.appendChild(opt);
      });
      sel.appendChild(grp);
    }
    if (closed.length) {
      const grp = document.createElement('optgroup');
      grp.label = '✓ Résolus';
      closed.slice(0,10).forEach(i => {
        const opt = document.createElement('option');
        opt.value = i.id;
        opt.textContent = `#${i.id} — ${i.site_id} : ${i.fait.substring(0,40)}…`;
        grp.appendChild(opt);
      });
      sel.appendChild(grp);
    }
    if (current) sel.value = current;
  } catch(e) {}
}

// ── REX : peupler le select incident ─────────────────────────────────
async function populateRexIncidentSelect() {
  try {
    const incidents = await apiFetch('/api/v1/sitrep/history').then(r=>r.json());
    const sel = document.getElementById('rex-inc-id');
    if (!sel) return;
    const current = sel.value;
    sel.innerHTML = '<option value="">— Sélectionner un incident —</option>';
    const open   = incidents.filter(i => i.status !== 'RÉSOLU').sort((a,b) => b.urgency - a.urgency);
    const closed = incidents.filter(i => i.status === 'RÉSOLU');
    if (open.length) {
      const grp = document.createElement('optgroup');
      grp.label = '🔴 Incidents ouverts';
      open.forEach(i => {
        const opt = document.createElement('option');
        opt.value = i.id;
        const ts = (parseUTC(i.timestamp)||new Date(0)).toLocaleDateString('fr-FR',{day:'2-digit',month:'2-digit'});
        opt.textContent = `#${i.id} — U${i.urgency} ${i.site_id} [${ts}] : ${i.fait.substring(0,50)}${i.fait.length>50?'…':''}`;
        grp.appendChild(opt);
      });
      sel.appendChild(grp);
    }
    if (closed.length) {
      const grp = document.createElement('optgroup');
      grp.label = '✓ Résolus';
      closed.forEach(i => {
        const opt = document.createElement('option');
        opt.value = i.id;
        const ts = (parseUTC(i.timestamp)||new Date(0)).toLocaleDateString('fr-FR',{day:'2-digit',month:'2-digit'});
        opt.textContent = `#${i.id} — ${i.site_id} [${ts}] : ${i.fait.substring(0,45)}${i.fait.length>45?'…':''}`;
        grp.appendChild(opt);
      });
      sel.appendChild(grp);
    }
    if (current) sel.value = current;
  } catch(e) {}
}

// Patch openTaskModal pour peupler le select
const _origOpenTaskModal = openTaskModal;
openTaskModal = function(taskId, defaultCol) {
  _origOpenTaskModal(taskId, defaultCol);
  populateIncidentSelect().then(() => {
    // Restaurer la valeur si édition
    if (taskId) {
      const t = allTasks.find(x => x.id === taskId);
      if (t && t.incident_id) {
        const sel = document.getElementById('tm-incident');
        if (sel) sel.value = t.incident_id;
      }
    }
  });
};

// Patch saveTask pour lire la valeur select (déjà string/number, OK)

// ── QUICK ACTIONS depuis les cards ───────────────────────────────────
function quickCreateTask(incidentId, encodedFait, e) {
  e.stopPropagation();
  // Ouvrir kanban + modal pré-rempli
  const kanbBtn = document.querySelector('[onclick*="tab-kanban"]');
  if (kanbBtn) openTab('tab-kanban', kanbBtn);
  setTimeout(() => {
    openTaskModal(null, 'BACKLOG');
    setTimeout(() => {
      const titre = document.getElementById('tm-titre');
      const inc   = document.getElementById('tm-incident');
      if (titre) titre.value = decodeURIComponent(encodedFait);
      if (inc)   { inc.value = incidentId; }
    }, 300);
  }, 100);
}

function quickRex(incidentId, e) {
  e.stopPropagation();
  const rexBtn = document.querySelector('[onclick*="tab-rex"]');
  if (rexBtn) openTab('tab-rex', rexBtn);
  setTimeout(async () => {
    await populateRexIncidentSelect();
    document.getElementById('rex-inc-id').value = incidentId;
    genRexFromIncident();
  }, 150);
}

// ══════════════════════════════════════════════════════════════
//  COMMUNIQUÉ — Page de statut publique
// ══════════════════════════════════════════════════════════════

let commData = null;   // état courant chargé depuis l'API

const NIVEAUX_LABELS = {
  OPERATIONNEL:   '✓ Système opérationnel',
  PERTURBE:       '⚠ Système perturbé',
  INCIDENT_MAJEUR:'✕ Incident majeur en cours',
  MAINTENANCE:    '↻ Maintenance en cours',
};
const SVC_STATES = ['OK','PERTURBE','HS','MAINTENANCE'];
const SVC_STATE_LABELS = {OK:'OK',PERTURBE:'Perturbé',HS:'Hors service',MAINTENANCE:'Maintenance'};
const NIVEAU_COLORS = {
  OPERATIONNEL:   {bg:'#052e16',color:'#4ade80',border:'#16a34a',dot:'#4ade80'},
  PERTURBE:       {bg:'#422006',color:'#fbbf24',border:'#b45309',dot:'#fbbf24'},
  INCIDENT_MAJEUR:{bg:'#450a0a',color:'#f87171',border:'#dc2626',dot:'#f87171'},
  MAINTENANCE:    {bg:'#0c2340',color:'#60a5fa',border:'#1d4ed8',dot:'#60a5fa'},
};

async function loadCommData() {
  try {
    const token = localStorage.getItem('scribe_token') || '';
    // Peupler le select avec les sites — fetch frais si nécessaire
    const sel = document.getElementById('comm-etab-select');
    if (sel) {
      const etab  = (typeof SCRIBE_CONFIG !== 'undefined' && SCRIBE_CONFIG.etablissement) || {};
      const nom   = etab.nom || 'Établissement';
      const sigle = etab.sigle || '';
      // Charger les sites si pas encore disponibles
      if (!allSites || allSites.length === 0) {
        try {
          const token = localStorage.getItem('scribe_token') || '';
          const r = await apiFetch('/api/v1/cartographie/sites', {headers:{'Authorization':'Bearer '+token}});
          if (r.ok) allSites = await r.json();
        } catch(e) {}
      }
      let opts = `<option value="global">${nom}${sigle?' — '+sigle:''} (tous les sites)</option>`;
      if (allSites && allSites.length > 0) {
        allSites.forEach(s => {
          opts += `<option value="${s.id || s.nom}">${s.nom}</option>`;
        });
      }
      sel.innerHTML = opts;
      const info = document.getElementById('comm-etab-info');
      if (info) info.textContent = allSites && allSites.length > 1
        ? `${allSites.length} sites disponibles`
        : '→ Couvre tous les sites';
    }

    const siteId  = (commSelectedSite && commSelectedSite !== 'global') ? commSelectedSite : '0';
    const siteObj = allSites && allSites.find(s => String(s.id) === String(siteId));
    const siteNom = siteObj ? encodeURIComponent(siteObj.nom) : '';
    const r = await apiFetch(`/api/v1/status/current?site_id=${siteId}&site_nom=${siteNom}`, {
      headers: { 'Authorization': 'Bearer ' + (localStorage.getItem('scribe_token') || '') }
    });
    if (!r.ok) return;
    commData = await r.json();
    renderCommEditor();
    renderCommPreview();
  } catch(e) { console.warn('Status page:', e); }
}

let commSelectedSite = 'global';  // site sélectionné dans le menu

function onCommEtabChange(val) {
  commSelectedSite = val;
  const info = document.getElementById('comm-etab-info');

  const titleEl = document.getElementById('comm-site-context');
  if (val === 'global') {
    if (info) info.textContent = allSites && allSites.length > 1
      ? `${allSites.length} sites disponibles — communiqué global`
      : '→ Couvre tous les sites';
    if (titleEl) titleEl.style.display = 'none';
  } else {
    const site = allSites && allSites.find(s => String(s.id || s.nom) === String(val));
    const siteNom = site ? site.nom : val;
    if (info) info.textContent = `📍 ${siteNom}`;
    if (titleEl) {
      titleEl.textContent = `📍 Communiqué pour : ${siteNom} — les modifications sont propres à ce site`;
      titleEl.style.cssText = 'font-family:var(--mono);font-size:9px;color:var(--cyan);padding:6px 16px;background:rgba(0,207,255,.06);border-bottom:1px solid var(--border);display:block;flex-shrink:0';
    }
  }
  // Recharger les données (même communiqué, contexte visuel différent)
  loadCommData();
}

function renderCommEditor() {
  if (!commData) return;

  // Niveau
  document.querySelectorAll('.niveau-btn').forEach(b => {
    const n = b.getAttribute('onclick').match(/'([A-Z_]+)'/)?.[1];
    b.className = 'niveau-btn' + (n === commData.niveau_global ? ' active-' + n : '');
  });

  // Message
  const msgEl = document.getElementById('comm-message');
  if (msgEl) msgEl.value = commData.message_public || '';

  // Services SI
  renderSvcList('comm-si-list', commData.services_si || [], 'si');
  // PEC
  renderSvcList('comm-pec-list', commData.prise_en_charge || [], 'pec');
  // FAQ
  renderFaqList(commData.faq || []);
  // Chronologie
  renderChronList(commData.chronologie || []);
  // Publish state
  updatePublishBar(commData.published);
}

function renderSvcList(containerId, svcs, prefix) {
  const c = document.getElementById(containerId);
  if (!c) return;
  c.innerHTML = svcs.map((s, i) => `
    <div class="svc-toggle-row">
      <span class="svc-toggle-label">${s.label}</span>
      ${SVC_STATES.map(st => `
        <button class="svc-state-btn ${s.statut===st?'s-'+st:''}"
          onclick="setSvcState('${prefix}',${i},'${st}')">${SVC_STATE_LABELS[st]}</button>
      `).join('')}
    </div>`).join('');
}

function renderFaqList(faq) {
  const c = document.getElementById('comm-faq-list');
  if (!c) return;
  c.innerHTML = faq.map((f, i) => `
    <div class="faq-row">
      <div class="faq-q-label">
        <input type="checkbox" class="faq-toggle" ${f.visible?'checked':''}
          onchange="setFaqVisible(${i}, this.checked)">
        <span>${f.question}</span>
      </div>
      ${f.visible ? `<textarea class="faq-reponse" rows="2"
        placeholder="Réponse officielle..."
        onblur="setFaqReponse(${i}, this.value)">${f.reponse||''}</textarea>` : ''}
    </div>`).join('');
}

function renderChronList(chrons) {
  const c = document.getElementById('comm-chron-list');
  if (!c) return;
  if (!chrons.length) { c.innerHTML = '<div style="font-family:var(--mono);font-size:10px;color:var(--muted);padding:4px 0">Aucune entrée</div>'; return; }
  c.innerHTML = chrons.map(ch => {
    const ts = ch.ts ? new Date(ch.ts).toLocaleTimeString('fr-FR',{hour:'2-digit',minute:'2-digit'}) : '';
    return `<div class="chron-list-item">
      <span class="chron-ts">${ts}</span>
      <span class="chron-texte">${ch.texte}</span>
      <button onclick="delChronEntry(${ch.id})"
        style="font-size:9px;padding:1px 5px;background:transparent;border:1px solid var(--border2);color:var(--muted);border-radius:2px;cursor:pointer">✕</button>
    </div>`;
  }).join('');
}

function renderCommPreview() {
  const c = document.getElementById('comm-preview');
  if (!c || !commData) return;
  const lvl   = commData.niveau_global || 'OPERATIONNEL';
  const col   = NIVEAU_COLORS[lvl] || NIVEAU_COLORS.OPERATIONNEL;
  const svcs  = commData.services_si || [];
  const pec   = commData.prise_en_charge || [];
  const faq   = (commData.faq||[]).filter(f=>f.visible&&f.reponse);
  const chrons= commData.chronologie || [];
  const etab  = (typeof SCRIBE_CONFIG !== 'undefined') ? SCRIBE_CONFIG.etablissement : {};

  const svcRows = (list) => list.map(s => {
    const C = {OK:'#4ade80',PERTURBE:'#fbbf24',HS:'#f87171',MAINTENANCE:'#60a5fa'}[s.statut]||'#64748b';
    return `<div class="preview-svc-row">
      <div class="preview-svc-dot" style="background:${C}"></div>
      <span style="flex:1;font-size:12px">${s.label}</span>
      <span class="preview-svc-badge" style="background:${C}22;color:${C};border:1px solid ${C}44">${SVC_STATE_LABELS[s.statut]||s.statut}</span>
    </div>`;
  }).join('');

  c.innerHTML = `
    <div class="preview-hdr">
      <div class="preview-title">${etab.nom||'Établissement de santé'}</div>
      <div class="preview-sub">État du système d'information — Point de situation</div>
    </div>
    <div class="preview-banner" style="background:${col.bg}22;border-color:${col.border}44">
      <div class="preview-banner-dot" style="background:${col.dot}"></div>
      <div>
        <div class="preview-banner-level" style="color:${col.color}">${NIVEAUX_LABELS[lvl]||lvl}</div>
        ${commData.message_public?`<div class="preview-banner-msg">${commData.message_public}</div>`:''}
      </div>
    </div>
    <div style="display:grid;grid-template-columns:1fr 1fr;gap:8px;margin-bottom:8px">
      <div class="preview-card">
        <div class="preview-card-hdr">Système d'information</div>
        ${svcRows(svcs)}
      </div>
      <div class="preview-card">
        <div class="preview-card-hdr">Prise en charge patients</div>
        ${svcRows(pec)}
      </div>
    </div>
    ${faq.length?`<div class="preview-card">
      <div class="preview-card-hdr">Questions fréquentes</div>
      ${faq.map(f=>`<div style="padding:8px 12px;border-bottom:1px solid var(--border)">
        <div style="font-size:11px;font-weight:600;margin-bottom:3px">${f.question}</div>
        <div style="font-size:11px;color:var(--muted)">${f.reponse}</div>
      </div>`).join('')}
    </div>`:''}
    ${chrons.length?`<div class="preview-card">
      <div class="preview-card-hdr">Chronologie</div>
      ${chrons.map(ch=>`<div style="padding:7px 12px;border-bottom:1px solid var(--border);font-size:11px">
        <span style="color:var(--muted);font-family:var(--mono);font-size:10px;margin-right:8px">${ch.ts?new Date(ch.ts).toLocaleTimeString('fr-FR',{hour:'2-digit',minute:'2-digit'}):''}</span>
        ${ch.texte}
      </div>`).join('')}
    </div>`:''}
    <div class="qr-box">
      <div class="qr-placeholder" id="comm-qr-holder"><!-- QR généré dynamiquement --></div>
      <a href="${window.location.origin}/status" target="_blank" rel="noopener" class="qr-url" style="display:block;text-decoration:underline;color:inherit;cursor:pointer">${window.location.origin}/status ↗</a>
    </div>
  `;
  // v2.3.88 — Générer le QR code et lier vers /status dans une nouvelle fenêtre
  // Taille augmentée (180px) pour scan facile depuis un smartphone à distance
  try {
    const holder = document.getElementById('comm-qr-holder');
    if (holder && window.QRCode) {
      holder.innerHTML = '';
      new QRCode(holder, {
        text: window.location.origin + '/status',
        width: 180, height: 180,
        colorDark: '#000000', colorLight: '#ffffff',
        correctLevel: QRCode.CorrectLevel.M,
      });
    } else if (holder) {
      holder.textContent = 'QR';
    }
  } catch(e) { console.warn('QR generation failed:', e); }
}

function updatePublishBar(published) {
  const dot = document.getElementById('comm-pub-dot');
  const lbl = document.getElementById('comm-pub-label');
  const btn = document.getElementById('comm-pub-btn');
  if (!dot || !lbl || !btn) return;
  if (published) {
    dot.className = 'published-dot on';
    lbl.textContent = 'Publié — accessible sur /status';
    btn.textContent = 'Dépublier';
    btn.className   = 'btn-publish on';
  } else {
    dot.className = 'published-dot off';
    lbl.textContent = 'Non publié — /status non disponible';
    btn.textContent = 'Publier';
    btn.className   = 'btn-publish off';
  }
}

// ── Actions ──────────────────────────────────────────────────────────

function setNiveau(niveau, btn) {
  if (!commData) return;
  commData.niveau_global = niveau;
  document.querySelectorAll('.niveau-btn').forEach(b => {
    const n = b.getAttribute('onclick').match(/'([A-Z_]+)'/)?.[1];
    b.className = 'niveau-btn' + (n === niveau ? ' active-' + n : '');
  });
  renderCommPreview();
  saveStatus();
}

function setSvcState(prefix, idx, statut) {
  if (!commData) return;
  const arr = prefix === 'si' ? commData.services_si : commData.prise_en_charge;
  if (arr && arr[idx]) arr[idx].statut = statut;
  renderSvcList(prefix === 'si' ? 'comm-si-list' : 'comm-pec-list', arr, prefix);
  renderCommPreview();
  saveStatus();
}

function setFaqVisible(idx, visible) {
  if (!commData || !commData.faq) return;
  commData.faq[idx].visible = visible;
  renderFaqList(commData.faq);
  renderCommPreview();
  saveStatus();
}

function setFaqReponse(idx, reponse) {
  if (!commData || !commData.faq) return;
  commData.faq[idx].reponse = reponse;
  renderCommPreview();
  saveStatus();
}

async function addChronEntry() {
  const ta = document.getElementById('comm-chron-new');
  if (!ta || !ta.value.trim()) return;
  const token = localStorage.getItem('scribe_token') || '';
  try {
    await apiFetch('/api/v1/status/chronologie', {
      method: 'POST',
      headers: { 'Content-Type':'application/json','Authorization':'Bearer '+token },
      body: JSON.stringify({ texte: ta.value.trim() })
    });
    ta.value = '';
    await loadCommData();
  } catch(e) { toast('Erreur: ' + e.message, 'err'); }
}

async function delChronEntry(id) {
  const token = localStorage.getItem('scribe_token') || '';
  try {
    await apiFetch('/api/v1/status/chronologie/' + id, {
      method:'DELETE', headers:{'Authorization':'Bearer '+token}
    });
    await loadCommData();
  } catch(e) { toast('Erreur: ' + e.message, 'err'); }
}

async function togglePublish() {
  if (!commData) return;
  commData.published = !commData.published;
  updatePublishBar(commData.published);
  // Sauvegarder IMMÉDIATEMENT sans debounce
  await saveStatusNow();
  toast(commData.published ? '✓ Point de situation publié sur /status' : 'Dépublié', commData.published ? 'ok' : 'warn');
}

// Sauvegarde immédiate (sans timer) utilisée par togglePublish
async function saveStatusNow() {
  if (!commData) return;
  const token = localStorage.getItem('scribe_token') || '';
  try {
    const msgEl = document.getElementById('comm-message');
    if (msgEl) commData.message_public = msgEl.value;
    const siteIdSave  = (commSelectedSite && commSelectedSite !== 'global') ? commSelectedSite : '0';
    const siteObjSave = allSites && allSites.find(s => String(s.id) === String(siteIdSave));
    const siteNomSave = siteObjSave ? encodeURIComponent(siteObjSave.nom) : '';
    const resp = await apiFetch(`/api/v1/status/update?site_id=${siteIdSave}&site_nom=${siteNomSave}`, {
      method:'PUT',
      headers:{'Content-Type':'application/json','Authorization':'Bearer '+token},
      body: JSON.stringify({
        niveau_global:   commData.niveau_global,
        message_public:  commData.message_public,
        services_si:     commData.services_si,
        prise_en_charge: commData.prise_en_charge,
        faq:             commData.faq,
        published:       commData.published,
      })
    });
    if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
    renderCommPreview();
  } catch(e) { console.warn('saveStatusNow:', e); toast('Erreur sauvegarde: ' + e.message, 'err'); }
}

let _saveTimer = null;
async function saveStatus() {
  clearTimeout(_saveTimer);
  _saveTimer = setTimeout(async () => {
    if (!commData) return;
    const token = localStorage.getItem('scribe_token') || '';
    try {
      const msgEl = document.getElementById('comm-message');
      if (msgEl) commData.message_public = msgEl.value;
      const siteIdSave  = (commSelectedSite && commSelectedSite !== 'global') ? commSelectedSite : '0';
      const siteObjSave = allSites && allSites.find(s => String(s.id) === String(siteIdSave));
      const siteNomSave = siteObjSave ? encodeURIComponent(siteObjSave.nom) : '';
      await apiFetch(`/api/v1/status/update?site_id=${siteIdSave}&site_nom=${siteNomSave}`, {
        method:'PUT',
        headers:{'Content-Type':'application/json','Authorization':'Bearer '+token},
        body: JSON.stringify({
          niveau_global:   commData.niveau_global,
          message_public:  commData.message_public,
          services_si:     commData.services_si,
          prise_en_charge: commData.prise_en_charge,
          faq:             commData.faq,
          published:       commData.published,
        })
      });
      renderCommPreview();
    } catch(e) { console.warn('saveStatus:', e); }
  }, 800);
}


// ── Afficher l'icone thème correctement après login ───────────────────
const _origApplyUserState = applyUserState;
applyUserState = function() {
  _origApplyUserState();
  const isLight = document.body.classList.contains('light');
  const btn = document.getElementById('theme-toggle-btn');
  if (btn) btn.textContent = isLight ? '🌙' : '☀️';
};

/* ════════════════════════════════════════════════════════════ */

/* JSZip 3.10.1 embarqué — fonctionne hors-ligne */
/*!

JSZip v3.10.1 - A JavaScript class for generating and reading zip files
<http://stuartk.com/jszip>

(c) 2009-2016 Stuart Knightley <stuart [at] stuartk.com>
Dual licenced under the MIT license or GPLv3. See https://raw.github.com/Stuk/jszip/main/LICENSE.markdown.

JSZip uses the library pako released under the MIT license :
https://github.com/nodeca/pako/blob/main/LICENSE
*/

!function(e){if("object"==typeof exports&&"undefined"!=typeof module)module.exports=e();else if("function"==typeof define&&define.amd)define([],e);else{("undefined"!=typeof window?window:"undefined"!=typeof global?global:"undefined"!=typeof self?self:this).JSZip=e()}}(function(){return function s(a,o,h){function u(r,e){if(!o[r]){if(!a[r]){var t="function"==typeof require&&require;if(!e&&t)return t(r,!0);if(l)return l(r,!0);var n=new Error("Cannot find module '"+r+"'");throw n.code="MODULE_NOT_FOUND",n}var i=o[r]={exports:{}};a[r][0].call(i.exports,function(e){var t=a[r][1][e];return u(t||e)},i,i.exports,s,a,o,h)}return o[r].exports}for(var l="function"==typeof require&&require,e=0;e<h.length;e++)u(h[e]);return u}({1:[function(e,t,r){"use strict";var d=e("./utils"),c=e("./support"),p="ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/=";r.encode=function(e){for(var t,r,n,i,s,a,o,h=[],u=0,l=e.length,f=l,c="string"!==d.getTypeOf(e);u<e.length;)f=l-u,n=c?(t=e[u++],r=u<l?e[u++]:0,u<l?e[u++]:0):(t=e.charCodeAt(u++),r=u<l?e.charCodeAt(u++):0,u<l?e.charCodeAt(u++):0),i=t>>2,s=(3&t)<<4|r>>4,a=1<f?(15&r)<<2|n>>6:64,o=2<f?63&n:64,h.push(p.charAt(i)+p.charAt(s)+p.charAt(a)+p.charAt(o));return h.join("")},r.decode=function(e){var t,r,n,i,s,a,o=0,h=0,u="data:";if(e.substr(0,u.length)===u)throw new Error("Invalid base64 input, it looks like a data url.");var l,f=3*(e=e.replace(/[^A-Za-z0-9+/=]/g,"")).length/4;if(e.charAt(e.length-1)===p.charAt(64)&&f--,e.charAt(e.length-2)===p.charAt(64)&&f--,f%1!=0)throw new Error("Invalid base64 input, bad content length.");for(l=c.uint8array?new Uint8Array(0|f):new Array(0|f);o<e.length;)t=p.indexOf(e.charAt(o++))<<2|(i=p.indexOf(e.charAt(o++)))>>4,r=(15&i)<<4|(s=p.indexOf(e.charAt(o++)))>>2,n=(3&s)<<6|(a=p.indexOf(e.charAt(o++))),l[h++]=t,64!==s&&(l[h++]=r),64!==a&&(l[h++]=n);return l}},{"./support":30,"./utils":32}],2:[function(e,t,r){"use strict";var n=e("./external"),i=e("./stream/DataWorker"),s=e("./stream/Crc32Probe"),a=e("./stream/DataLengthProbe");function o(e,t,r,n,i){this.compressedSize=e,this.uncompressedSize=t,this.crc32=r,this.compression=n,this.compressedContent=i}o.prototype={getContentWorker:function(){var e=new i(n.Promise.resolve(this.compressedContent)).pipe(this.compression.uncompressWorker()).pipe(new a("data_length")),t=this;return e.on("end",function(){if(this.streamInfo.data_length!==t.uncompressedSize)throw new Error("Bug : uncompressed data size mismatch")}),e},getCompressedWorker:function(){return new i(n.Promise.resolve(this.compressedContent)).withStreamInfo("compressedSize",this.compressedSize).withStreamInfo("uncompressedSize",this.uncompressedSize).withStreamInfo("crc32",this.crc32).withStreamInfo("compression",this.compression)}},o.createWorkerFrom=function(e,t,r){return e.pipe(new s).pipe(new a("uncompressedSize")).pipe(t.compressWorker(r)).pipe(new a("compressedSize")).withStreamInfo("compression",t)},t.exports=o},{"./external":6,"./stream/Crc32Probe":25,"./stream/DataLengthProbe":26,"./stream/DataWorker":27}],3:[function(e,t,r){"use strict";var n=e("./stream/GenericWorker");r.STORE={magic:"\0\0",compressWorker:function(){return new n("STORE compression")},uncompressWorker:function(){return new n("STORE decompression")}},r.DEFLATE=e("./flate")},{"./flate":7,"./stream/GenericWorker":28}],4:[function(e,t,r){"use strict";var n=e("./utils");var o=function(){for(var e,t=[],r=0;r<256;r++){e=r;for(var n=0;n<8;n++)e=1&e?3988292384^e>>>1:e>>>1;t[r]=e}return t}();t.exports=function(e,t){return void 0!==e&&e.length?"string"!==n.getTypeOf(e)?function(e,t,r,n){var i=o,s=n+r;e^=-1;for(var a=n;a<s;a++)e=e>>>8^i[255&(e^t[a])];return-1^e}(0|t,e,e.length,0):function(e,t,r,n){var i=o,s=n+r;e^=-1;for(var a=n;a<s;a++)e=e>>>8^i[255&(e^t.charCodeAt(a))];return-1^e}(0|t,e,e.length,0):0}},{"./utils":32}],5:[function(e,t,r){"use strict";r.base64=!1,r.binary=!1,r.dir=!1,r.createFolders=!0,r.date=null,r.compression=null,r.compressionOptions=null,r.comment=null,r.unixPermissions=null,r.dosPermissions=null},{}],6:[function(e,t,r){"use strict";var n=null;n="undefined"!=typeof Promise?Promise:e("lie"),t.exports={Promise:n}},{lie:37}],7:[function(e,t,r){"use strict";var n="undefined"!=typeof Uint8Array&&"undefined"!=typeof Uint16Array&&"undefined"!=typeof Uint32Array,i=e("pako"),s=e("./utils"),a=e("./stream/GenericWorker"),o=n?"uint8array":"array";function h(e,t){a.call(this,"FlateWorker/"+e),this._pako=null,this._pakoAction=e,this._pakoOptions=t,this.meta={}}r.magic="\b\0",s.inherits(h,a),h.prototype.processChunk=function(e){this.meta=e.meta,null===this._pako&&this._createPako(),this._pako.push(s.transformTo(o,e.data),!1)},h.prototype.flush=function(){a.prototype.flush.call(this),null===this._pako&&this._createPako(),this._pako.push([],!0)},h.prototype.cleanUp=function(){a.prototype.cleanUp.call(this),this._pako=null},h.prototype._createPako=function(){this._pako=new i[this._pakoAction]({raw:!0,level:this._pakoOptions.level||-1});var t=this;this._pako.onData=function(e){t.push({data:e,meta:t.meta})}},r.compressWorker=function(e){return new h("Deflate",e)},r.uncompressWorker=function(){return new h("Inflate",{})}},{"./stream/GenericWorker":28,"./utils":32,pako:38}],8:[function(e,t,r){"use strict";function A(e,t){var r,n="";for(r=0;r<t;r++)n+=String.fromCharCode(255&e),e>>>=8;return n}function n(e,t,r,n,i,s){var a,o,h=e.file,u=e.compression,l=s!==O.utf8encode,f=I.transformTo("string",s(h.name)),c=I.transformTo("string",O.utf8encode(h.name)),d=h.comment,p=I.transformTo("string",s(d)),m=I.transformTo("string",O.utf8encode(d)),_=c.length!==h.name.length,g=m.length!==d.length,b="",v="",y="",w=h.dir,k=h.date,x={crc32:0,compressedSize:0,uncompressedSize:0};t&&!r||(x.crc32=e.crc32,x.compressedSize=e.compressedSize,x.uncompressedSize=e.uncompressedSize);var S=0;t&&(S|=8),l||!_&&!g||(S|=2048);var z=0,C=0;w&&(z|=16),"UNIX"===i?(C=798,z|=function(e,t){var r=e;return e||(r=t?16893:33204),(65535&r)<<16}(h.unixPermissions,w)):(C=20,z|=function(e){return 63&(e||0)}(h.dosPermissions)),a=k.getUTCHours(),a<<=6,a|=k.getUTCMinutes(),a<<=5,a|=k.getUTCSeconds()/2,o=k.getUTCFullYear()-1980,o<<=4,o|=k.getUTCMonth()+1,o<<=5,o|=k.getUTCDate(),_&&(v=A(1,1)+A(B(f),4)+c,b+="up"+A(v.length,2)+v),g&&(y=A(1,1)+A(B(p),4)+m,b+="uc"+A(y.length,2)+y);var E="";return E+="\n\0",E+=A(S,2),E+=u.magic,E+=A(a,2),E+=A(o,2),E+=A(x.crc32,4),E+=A(x.compressedSize,4),E+=A(x.uncompressedSize,4),E+=A(f.length,2),E+=A(b.length,2),{fileRecord:R.LOCAL_FILE_HEADER+E+f+b,dirRecord:R.CENTRAL_FILE_HEADER+A(C,2)+E+A(p.length,2)+"\0\0\0\0"+A(z,4)+A(n,4)+f+b+p}}var I=e("../utils"),i=e("../stream/GenericWorker"),O=e("../utf8"),B=e("../crc32"),R=e("../signature");function s(e,t,r,n){i.call(this,"ZipFileWorker"),this.bytesWritten=0,this.zipComment=t,this.zipPlatform=r,this.encodeFileName=n,this.streamFiles=e,this.accumulate=!1,this.contentBuffer=[],this.dirRecords=[],this.currentSourceOffset=0,this.entriesCount=0,this.currentFile=null,this._sources=[]}I.inherits(s,i),s.prototype.push=function(e){var t=e.meta.percent||0,r=this.entriesCount,n=this._sources.length;this.accumulate?this.contentBuffer.push(e):(this.bytesWritten+=e.data.length,i.prototype.push.call(this,{data:e.data,meta:{currentFile:this.currentFile,percent:r?(t+100*(r-n-1))/r:100}}))},s.prototype.openedSource=function(e){this.currentSourceOffset=this.bytesWritten,this.currentFile=e.file.name;var t=this.streamFiles&&!e.file.dir;if(t){var r=n(e,t,!1,this.currentSourceOffset,this.zipPlatform,this.encodeFileName);this.push({data:r.fileRecord,meta:{percent:0}})}else this.accumulate=!0},s.prototype.closedSource=function(e){this.accumulate=!1;var t=this.streamFiles&&!e.file.dir,r=n(e,t,!0,this.currentSourceOffset,this.zipPlatform,this.encodeFileName);if(this.dirRecords.push(r.dirRecord),t)this.push({data:function(e){return R.DATA_DESCRIPTOR+A(e.crc32,4)+A(e.compressedSize,4)+A(e.uncompressedSize,4)}(e),meta:{percent:100}});else for(this.push({data:r.fileRecord,meta:{percent:0}});this.contentBuffer.length;)this.push(this.contentBuffer.shift());this.currentFile=null},s.prototype.flush=function(){for(var e=this.bytesWritten,t=0;t<this.dirRecords.length;t++)this.push({data:this.dirRecords[t],meta:{percent:100}});var r=this.bytesWritten-e,n=function(e,t,r,n,i){var s=I.transformTo("string",i(n));return R.CENTRAL_DIRECTORY_END+"\0\0\0\0"+A(e,2)+A(e,2)+A(t,4)+A(r,4)+A(s.length,2)+s}(this.dirRecords.length,r,e,this.zipComment,this.encodeFileName);this.push({data:n,meta:{percent:100}})},s.prototype.prepareNextSource=function(){this.previous=this._sources.shift(),this.openedSource(this.previous.streamInfo),this.isPaused?this.previous.pause():this.previous.resume()},s.prototype.registerPrevious=function(e){this._sources.push(e);var t=this;return e.on("data",function(e){t.processChunk(e)}),e.on("end",function(){t.closedSource(t.previous.streamInfo),t._sources.length?t.prepareNextSource():t.end()}),e.on("error",function(e){t.error(e)}),this},s.prototype.resume=function(){return!!i.prototype.resume.call(this)&&(!this.previous&&this._sources.length?(this.prepareNextSource(),!0):this.previous||this._sources.length||this.generatedError?void 0:(this.end(),!0))},s.prototype.error=function(e){var t=this._sources;if(!i.prototype.error.call(this,e))return!1;for(var r=0;r<t.length;r++)try{t[r].error(e)}catch(e){}return!0},s.prototype.lock=function(){i.prototype.lock.call(this);for(var e=this._sources,t=0;t<e.length;t++)e[t].lock()},t.exports=s},{"../crc32":4,"../signature":23,"../stream/GenericWorker":28,"../utf8":31,"../utils":32}],9:[function(e,t,r){"use strict";var u=e("../compressions"),n=e("./ZipFileWorker");r.generateWorker=function(e,a,t){var o=new n(a.streamFiles,t,a.platform,a.encodeFileName),h=0;try{e.forEach(function(e,t){h++;var r=function(e,t){var r=e||t,n=u[r];if(!n)throw new Error(r+" is not a valid compression method !");return n}(t.options.compression,a.compression),n=t.options.compressionOptions||a.compressionOptions||{},i=t.dir,s=t.date;t._compressWorker(r,n).withStreamInfo("file",{name:e,dir:i,date:s,comment:t.comment||"",unixPermissions:t.unixPermissions,dosPermissions:t.dosPermissions}).pipe(o)}),o.entriesCount=h}catch(e){o.error(e)}return o}},{"../compressions":3,"./ZipFileWorker":8}],10:[function(e,t,r){"use strict";function n(){if(!(this instanceof n))return new n;if(arguments.length)throw new Error("The constructor with parameters has been removed in JSZip 3.0, please check the upgrade guide.");this.files=Object.create(null),this.comment=null,this.root="",this.clone=function(){var e=new n;for(var t in this)"function"!=typeof this[t]&&(e[t]=this[t]);return e}}(n.prototype=e("./object")).loadAsync=e("./load"),n.support=e("./support"),n.defaults=e("./defaults"),n.version="3.10.1",n.loadAsync=function(e,t){return(new n).loadAsync(e,t)},n.external=e("./external"),t.exports=n},{"./defaults":5,"./external":6,"./load":11,"./object":15,"./support":30}],11:[function(e,t,r){"use strict";var u=e("./utils"),i=e("./external"),n=e("./utf8"),s=e("./zipEntries"),a=e("./stream/Crc32Probe"),l=e("./nodejsUtils");function f(n){return new i.Promise(function(e,t){var r=n.decompressed.getContentWorker().pipe(new a);r.on("error",function(e){t(e)}).on("end",function(){r.streamInfo.crc32!==n.decompressed.crc32?t(new Error("Corrupted zip : CRC32 mismatch")):e()}).resume()})}t.exports=function(e,o){var h=this;return o=u.extend(o||{},{base64:!1,checkCRC32:!1,optimizedBinaryString:!1,createFolders:!1,decodeFileName:n.utf8decode}),l.isNode&&l.isStream(e)?i.Promise.reject(new Error("JSZip can't accept a stream when loading a zip file.")):u.prepareContent("the loaded zip file",e,!0,o.optimizedBinaryString,o.base64).then(function(e){var t=new s(o);return t.load(e),t}).then(function(e){var t=[i.Promise.resolve(e)],r=e.files;if(o.checkCRC32)for(var n=0;n<r.length;n++)t.push(f(r[n]));return i.Promise.all(t)}).then(function(e){for(var t=e.shift(),r=t.files,n=0;n<r.length;n++){var i=r[n],s=i.fileNameStr,a=u.resolve(i.fileNameStr);h.file(a,i.decompressed,{binary:!0,optimizedBinaryString:!0,date:i.date,dir:i.dir,comment:i.fileCommentStr.length?i.fileCommentStr:null,unixPermissions:i.unixPermissions,dosPermissions:i.dosPermissions,createFolders:o.createFolders}),i.dir||(h.file(a).unsafeOriginalName=s)}return t.zipComment.length&&(h.comment=t.zipComment),h})}},{"./external":6,"./nodejsUtils":14,"./stream/Crc32Probe":25,"./utf8":31,"./utils":32,"./zipEntries":33}],12:[function(e,t,r){"use strict";var n=e("../utils"),i=e("../stream/GenericWorker");function s(e,t){i.call(this,"Nodejs stream input adapter for "+e),this._upstreamEnded=!1,this._bindStream(t)}n.inherits(s,i),s.prototype._bindStream=function(e){var t=this;(this._stream=e).pause(),e.on("data",function(e){t.push({data:e,meta:{percent:0}})}).on("error",function(e){t.isPaused?this.generatedError=e:t.error(e)}).on("end",function(){t.isPaused?t._upstreamEnded=!0:t.end()})},s.prototype.pause=function(){return!!i.prototype.pause.call(this)&&(this._stream.pause(),!0)},s.prototype.resume=function(){return!!i.prototype.resume.call(this)&&(this._upstreamEnded?this.end():this._stream.resume(),!0)},t.exports=s},{"../stream/GenericWorker":28,"../utils":32}],13:[function(e,t,r){"use strict";var i=e("readable-stream").Readable;function n(e,t,r){i.call(this,t),this._helper=e;var n=this;e.on("data",function(e,t){n.push(e)||n._helper.pause(),r&&r(t)}).on("error",function(e){n.emit("error",e)}).on("end",function(){n.push(null)})}e("../utils").inherits(n,i),n.prototype._read=function(){this._helper.resume()},t.exports=n},{"../utils":32,"readable-stream":16}],14:[function(e,t,r){"use strict";t.exports={isNode:"undefined"!=typeof Buffer,newBufferFrom:function(e,t){if(Buffer.from&&Buffer.from!==Uint8Array.from)return Buffer.from(e,t);if("number"==typeof e)throw new Error('The "data" argument must not be a number');return new Buffer(e,t)},allocBuffer:function(e){if(Buffer.alloc)return Buffer.alloc(e);var t=new Buffer(e);return t.fill(0),t},isBuffer:function(e){return Buffer.isBuffer(e)},isStream:function(e){return e&&"function"==typeof e.on&&"function"==typeof e.pause&&"function"==typeof e.resume}}},{}],15:[function(e,t,r){"use strict";function s(e,t,r){var n,i=u.getTypeOf(t),s=u.extend(r||{},f);s.date=s.date||new Date,null!==s.compression&&(s.compression=s.compression.toUpperCase()),"string"==typeof s.unixPermissions&&(s.unixPermissions=parseInt(s.unixPermissions,8)),s.unixPermissions&&16384&s.unixPermissions&&(s.dir=!0),s.dosPermissions&&16&s.dosPermissions&&(s.dir=!0),s.dir&&(e=g(e)),s.createFolders&&(n=_(e))&&b.call(this,n,!0);var a="string"===i&&!1===s.binary&&!1===s.base64;r&&void 0!==r.binary||(s.binary=!a),(t instanceof c&&0===t.uncompressedSize||s.dir||!t||0===t.length)&&(s.base64=!1,s.binary=!0,t="",s.compression="STORE",i="string");var o=null;o=t instanceof c||t instanceof l?t:p.isNode&&p.isStream(t)?new m(e,t):u.prepareContent(e,t,s.binary,s.optimizedBinaryString,s.base64);var h=new d(e,o,s);this.files[e]=h}var i=e("./utf8"),u=e("./utils"),l=e("./stream/GenericWorker"),a=e("./stream/StreamHelper"),f=e("./defaults"),c=e("./compressedObject"),d=e("./zipObject"),o=e("./generate"),p=e("./nodejsUtils"),m=e("./nodejs/NodejsStreamInputAdapter"),_=function(e){"/"===e.slice(-1)&&(e=e.substring(0,e.length-1));var t=e.lastIndexOf("/");return 0<t?e.substring(0,t):""},g=function(e){return"/"!==e.slice(-1)&&(e+="/"),e},b=function(e,t){return t=void 0!==t?t:f.createFolders,e=g(e),this.files[e]||s.call(this,e,null,{dir:!0,createFolders:t}),this.files[e]};function h(e){return"[object RegExp]"===Object.prototype.toString.call(e)}var n={load:function(){throw new Error("This method has been removed in JSZip 3.0, please check the upgrade guide.")},forEach:function(e){var t,r,n;for(t in this.files)n=this.files[t],(r=t.slice(this.root.length,t.length))&&t.slice(0,this.root.length)===this.root&&e(r,n)},filter:function(r){var n=[];return this.forEach(function(e,t){r(e,t)&&n.push(t)}),n},file:function(e,t,r){if(1!==arguments.length)return e=this.root+e,s.call(this,e,t,r),this;if(h(e)){var n=e;return this.filter(function(e,t){return!t.dir&&n.test(e)})}var i=this.files[this.root+e];return i&&!i.dir?i:null},folder:function(r){if(!r)return this;if(h(r))return this.filter(function(e,t){return t.dir&&r.test(e)});var e=this.root+r,t=b.call(this,e),n=this.clone();return n.root=t.name,n},remove:function(r){r=this.root+r;var e=this.files[r];if(e||("/"!==r.slice(-1)&&(r+="/"),e=this.files[r]),e&&!e.dir)delete this.files[r];else for(var t=this.filter(function(e,t){return t.name.slice(0,r.length)===r}),n=0;n<t.length;n++)delete this.files[t[n].name];return this},generate:function(){throw new Error("This method has been removed in JSZip 3.0, please check the upgrade guide.")},generateInternalStream:function(e){var t,r={};try{if((r=u.extend(e||{},{streamFiles:!1,compression:"STORE",compressionOptions:null,type:"",platform:"DOS",comment:null,mimeType:"application/zip",encodeFileName:i.utf8encode})).type=r.type.toLowerCase(),r.compression=r.compression.toUpperCase(),"binarystring"===r.type&&(r.type="string"),!r.type)throw new Error("No output type specified.");u.checkSupport(r.type),"darwin"!==r.platform&&"freebsd"!==r.platform&&"linux"!==r.platform&&"sunos"!==r.platform||(r.platform="UNIX"),"win32"===r.platform&&(r.platform="DOS");var n=r.comment||this.comment||"";t=o.generateWorker(this,r,n)}catch(e){(t=new l("error")).error(e)}return new a(t,r.type||"string",r.mimeType)},generateAsync:function(e,t){return this.generateInternalStream(e).accumulate(t)},generateNodeStream:function(e,t){return(e=e||{}).type||(e.type="nodebuffer"),this.generateInternalStream(e).toNodejsStream(t)}};t.exports=n},{"./compressedObject":2,"./defaults":5,"./generate":9,"./nodejs/NodejsStreamInputAdapter":12,"./nodejsUtils":14,"./stream/GenericWorker":28,"./stream/StreamHelper":29,"./utf8":31,"./utils":32,"./zipObject":35}],16:[function(e,t,r){"use strict";t.exports=e("stream")},{stream:void 0}],17:[function(e,t,r){"use strict";var n=e("./DataReader");function i(e){n.call(this,e);for(var t=0;t<this.data.length;t++)e[t]=255&e[t]}e("../utils").inherits(i,n),i.prototype.byteAt=function(e){return this.data[this.zero+e]},i.prototype.lastIndexOfSignature=function(e){for(var t=e.charCodeAt(0),r=e.charCodeAt(1),n=e.charCodeAt(2),i=e.charCodeAt(3),s=this.length-4;0<=s;--s)if(this.data[s]===t&&this.data[s+1]===r&&this.data[s+2]===n&&this.data[s+3]===i)return s-this.zero;return-1},i.prototype.readAndCheckSignature=function(e){var t=e.charCodeAt(0),r=e.charCodeAt(1),n=e.charCodeAt(2),i=e.charCodeAt(3),s=this.readData(4);return t===s[0]&&r===s[1]&&n===s[2]&&i===s[3]},i.prototype.readData=function(e){if(this.checkOffset(e),0===e)return[];var t=this.data.slice(this.zero+this.index,this.zero+this.index+e);return this.index+=e,t},t.exports=i},{"../utils":32,"./DataReader":18}],18:[function(e,t,r){"use strict";var n=e("../utils");function i(e){this.data=e,this.length=e.length,this.index=0,this.zero=0}i.prototype={checkOffset:function(e){this.checkIndex(this.index+e)},checkIndex:function(e){if(this.length<this.zero+e||e<0)throw new Error("End of data reached (data length = "+this.length+", asked index = "+e+"). Corrupted zip ?")},setIndex:function(e){this.checkIndex(e),this.index=e},skip:function(e){this.setIndex(this.index+e)},byteAt:function(){},readInt:function(e){var t,r=0;for(this.checkOffset(e),t=this.index+e-1;t>=this.index;t--)r=(r<<8)+this.byteAt(t);return this.index+=e,r},readString:function(e){return n.transformTo("string",this.readData(e))},readData:function(){},lastIndexOfSignature:function(){},readAndCheckSignature:function(){},readDate:function(){var e=this.readInt(4);return new Date(Date.UTC(1980+(e>>25&127),(e>>21&15)-1,e>>16&31,e>>11&31,e>>5&63,(31&e)<<1))}},t.exports=i},{"../utils":32}],19:[function(e,t,r){"use strict";var n=e("./Uint8ArrayReader");function i(e){n.call(this,e)}e("../utils").inherits(i,n),i.prototype.readData=function(e){this.checkOffset(e);var t=this.data.slice(this.zero+this.index,this.zero+this.index+e);return this.index+=e,t},t.exports=i},{"../utils":32,"./Uint8ArrayReader":21}],20:[function(e,t,r){"use strict";var n=e("./DataReader");function i(e){n.call(this,e)}e("../utils").inherits(i,n),i.prototype.byteAt=function(e){return this.data.charCodeAt(this.zero+e)},i.prototype.lastIndexOfSignature=function(e){return this.data.lastIndexOf(e)-this.zero},i.prototype.readAndCheckSignature=function(e){return e===this.readData(4)},i.prototype.readData=function(e){this.checkOffset(e);var t=this.data.slice(this.zero+this.index,this.zero+this.index+e);return this.index+=e,t},t.exports=i},{"../utils":32,"./DataReader":18}],21:[function(e,t,r){"use strict";var n=e("./ArrayReader");function i(e){n.call(this,e)}e("../utils").inherits(i,n),i.prototype.readData=function(e){if(this.checkOffset(e),0===e)return new Uint8Array(0);var t=this.data.subarray(this.zero+this.index,this.zero+this.index+e);return this.index+=e,t},t.exports=i},{"../utils":32,"./ArrayReader":17}],22:[function(e,t,r){"use strict";var n=e("../utils"),i=e("../support"),s=e("./ArrayReader"),a=e("./StringReader"),o=e("./NodeBufferReader"),h=e("./Uint8ArrayReader");t.exports=function(e){var t=n.getTypeOf(e);return n.checkSupport(t),"string"!==t||i.uint8array?"nodebuffer"===t?new o(e):i.uint8array?new h(n.transformTo("uint8array",e)):new s(n.transformTo("array",e)):new a(e)}},{"../support":30,"../utils":32,"./ArrayReader":17,"./NodeBufferReader":19,"./StringReader":20,"./Uint8ArrayReader":21}],23:[function(e,t,r){"use strict";r.LOCAL_FILE_HEADER="PK",r.CENTRAL_FILE_HEADER="PK",r.CENTRAL_DIRECTORY_END="PK",r.ZIP64_CENTRAL_DIRECTORY_LOCATOR="PK",r.ZIP64_CENTRAL_DIRECTORY_END="PK",r.DATA_DESCRIPTOR="PK\b"},{}],24:[function(e,t,r){"use strict";var n=e("./GenericWorker"),i=e("../utils");function s(e){n.call(this,"ConvertWorker to "+e),this.destType=e}i.inherits(s,n),s.prototype.processChunk=function(e){this.push({data:i.transformTo(this.destType,e.data),meta:e.meta})},t.exports=s},{"../utils":32,"./GenericWorker":28}],25:[function(e,t,r){"use strict";var n=e("./GenericWorker"),i=e("../crc32");function s(){n.call(this,"Crc32Probe"),this.withStreamInfo("crc32",0)}e("../utils").inherits(s,n),s.prototype.processChunk=function(e){this.streamInfo.crc32=i(e.data,this.streamInfo.crc32||0),this.push(e)},t.exports=s},{"../crc32":4,"../utils":32,"./GenericWorker":28}],26:[function(e,t,r){"use strict";var n=e("../utils"),i=e("./GenericWorker");function s(e){i.call(this,"DataLengthProbe for "+e),this.propName=e,this.withStreamInfo(e,0)}n.inherits(s,i),s.prototype.processChunk=function(e){if(e){var t=this.streamInfo[this.propName]||0;this.streamInfo[this.propName]=t+e.data.length}i.prototype.processChunk.call(this,e)},t.exports=s},{"../utils":32,"./GenericWorker":28}],27:[function(e,t,r){"use strict";var n=e("../utils"),i=e("./GenericWorker");function s(e){i.call(this,"DataWorker");var t=this;this.dataIsReady=!1,this.index=0,this.max=0,this.data=null,this.type="",this._tickScheduled=!1,e.then(function(e){t.dataIsReady=!0,t.data=e,t.max=e&&e.length||0,t.type=n.getTypeOf(e),t.isPaused||t._tickAndRepeat()},function(e){t.error(e)})}n.inherits(s,i),s.prototype.cleanUp=function(){i.prototype.cleanUp.call(this),this.data=null},s.prototype.resume=function(){return!!i.prototype.resume.call(this)&&(!this._tickScheduled&&this.dataIsReady&&(this._tickScheduled=!0,n.delay(this._tickAndRepeat,[],this)),!0)},s.prototype._tickAndRepeat=function(){this._tickScheduled=!1,this.isPaused||this.isFinished||(this._tick(),this.isFinished||(n.delay(this._tickAndRepeat,[],this),this._tickScheduled=!0))},s.prototype._tick=function(){if(this.isPaused||this.isFinished)return!1;var e=null,t=Math.min(this.max,this.index+16384);if(this.index>=this.max)return this.end();switch(this.type){case"string":e=this.data.substring(this.index,t);break;case"uint8array":e=this.data.subarray(this.index,t);break;case"array":case"nodebuffer":e=this.data.slice(this.index,t)}return this.index=t,this.push({data:e,meta:{percent:this.max?this.index/this.max*100:0}})},t.exports=s},{"../utils":32,"./GenericWorker":28}],28:[function(e,t,r){"use strict";function n(e){this.name=e||"default",this.streamInfo={},this.generatedError=null,this.extraStreamInfo={},this.isPaused=!0,this.isFinished=!1,this.isLocked=!1,this._listeners={data:[],end:[],error:[]},this.previous=null}n.prototype={push:function(e){this.emit("data",e)},end:function(){if(this.isFinished)return!1;this.flush();try{this.emit("end"),this.cleanUp(),this.isFinished=!0}catch(e){this.emit("error",e)}return!0},error:function(e){return!this.isFinished&&(this.isPaused?this.generatedError=e:(this.isFinished=!0,this.emit("error",e),this.previous&&this.previous.error(e),this.cleanUp()),!0)},on:function(e,t){return this._listeners[e].push(t),this},cleanUp:function(){this.streamInfo=this.generatedError=this.extraStreamInfo=null,this._listeners=[]},emit:function(e,t){if(this._listeners[e])for(var r=0;r<this._listeners[e].length;r++)this._listeners[e][r].call(this,t)},pipe:function(e){return e.registerPrevious(this)},registerPrevious:function(e){if(this.isLocked)throw new Error("The stream '"+this+"' has already been used.");this.streamInfo=e.streamInfo,this.mergeStreamInfo(),this.previous=e;var t=this;return e.on("data",function(e){t.processChunk(e)}),e.on("end",function(){t.end()}),e.on("error",function(e){t.error(e)}),this},pause:function(){return!this.isPaused&&!this.isFinished&&(this.isPaused=!0,this.previous&&this.previous.pause(),!0)},resume:function(){if(!this.isPaused||this.isFinished)return!1;var e=this.isPaused=!1;return this.generatedError&&(this.error(this.generatedError),e=!0),this.previous&&this.previous.resume(),!e},flush:function(){},processChunk:function(e){this.push(e)},withStreamInfo:function(e,t){return this.extraStreamInfo[e]=t,this.mergeStreamInfo(),this},mergeStreamInfo:function(){for(var e in this.extraStreamInfo)Object.prototype.hasOwnProperty.call(this.extraStreamInfo,e)&&(this.streamInfo[e]=this.extraStreamInfo[e])},lock:function(){if(this.isLocked)throw new Error("The stream '"+this+"' has already been used.");this.isLocked=!0,this.previous&&this.previous.lock()},toString:function(){var e="Worker "+this.name;return this.previous?this.previous+" -> "+e:e}},t.exports=n},{}],29:[function(e,t,r){"use strict";var h=e("../utils"),i=e("./ConvertWorker"),s=e("./GenericWorker"),u=e("../base64"),n=e("../support"),a=e("../external"),o=null;if(n.nodestream)try{o=e("../nodejs/NodejsStreamOutputAdapter")}catch(e){}function l(e,o){return new a.Promise(function(t,r){var n=[],i=e._internalType,s=e._outputType,a=e._mimeType;e.on("data",function(e,t){n.push(e),o&&o(t)}).on("error",function(e){n=[],r(e)}).on("end",function(){try{var e=function(e,t,r){switch(e){case"blob":return h.newBlob(h.transformTo("arraybuffer",t),r);case"base64":return u.encode(t);default:return h.transformTo(e,t)}}(s,function(e,t){var r,n=0,i=null,s=0;for(r=0;r<t.length;r++)s+=t[r].length;switch(e){case"string":return t.join("");case"array":return Array.prototype.concat.apply([],t);case"uint8array":for(i=new Uint8Array(s),r=0;r<t.length;r++)i.set(t[r],n),n+=t[r].length;return i;case"nodebuffer":return Buffer.concat(t);default:throw new Error("concat : unsupported type '"+e+"'")}}(i,n),a);t(e)}catch(e){r(e)}n=[]}).resume()})}function f(e,t,r){var n=t;switch(t){case"blob":case"arraybuffer":n="uint8array";break;case"base64":n="string"}try{this._internalType=n,this._outputType=t,this._mimeType=r,h.checkSupport(n),this._worker=e.pipe(new i(n)),e.lock()}catch(e){this._worker=new s("error"),this._worker.error(e)}}f.prototype={accumulate:function(e){return l(this,e)},on:function(e,t){var r=this;return"data"===e?this._worker.on(e,function(e){t.call(r,e.data,e.meta)}):this._worker.on(e,function(){h.delay(t,arguments,r)}),this},resume:function(){return h.delay(this._worker.resume,[],this._worker),this},pause:function(){return this._worker.pause(),this},toNodejsStream:function(e){if(h.checkSupport("nodestream"),"nodebuffer"!==this._outputType)throw new Error(this._outputType+" is not supported by this method");return new o(this,{objectMode:"nodebuffer"!==this._outputType},e)}},t.exports=f},{"../base64":1,"../external":6,"../nodejs/NodejsStreamOutputAdapter":13,"../support":30,"../utils":32,"./ConvertWorker":24,"./GenericWorker":28}],30:[function(e,t,r){"use strict";if(r.base64=!0,r.array=!0,r.string=!0,r.arraybuffer="undefined"!=typeof ArrayBuffer&&"undefined"!=typeof Uint8Array,r.nodebuffer="undefined"!=typeof Buffer,r.uint8array="undefined"!=typeof Uint8Array,"undefined"==typeof ArrayBuffer)r.blob=!1;else{var n=new ArrayBuffer(0);try{r.blob=0===new Blob([n],{type:"application/zip"}).size}catch(e){try{var i=new(self.BlobBuilder||self.WebKitBlobBuilder||self.MozBlobBuilder||self.MSBlobBuilder);i.append(n),r.blob=0===i.getBlob("application/zip").size}catch(e){r.blob=!1}}}try{r.nodestream=!!e("readable-stream").Readable}catch(e){r.nodestream=!1}},{"readable-stream":16}],31:[function(e,t,s){"use strict";for(var o=e("./utils"),h=e("./support"),r=e("./nodejsUtils"),n=e("./stream/GenericWorker"),u=new Array(256),i=0;i<256;i++)u[i]=252<=i?6:248<=i?5:240<=i?4:224<=i?3:192<=i?2:1;u[254]=u[254]=1;function a(){n.call(this,"utf-8 decode"),this.leftOver=null}function l(){n.call(this,"utf-8 encode")}s.utf8encode=function(e){return h.nodebuffer?r.newBufferFrom(e,"utf-8"):function(e){var t,r,n,i,s,a=e.length,o=0;for(i=0;i<a;i++)55296==(64512&(r=e.charCodeAt(i)))&&i+1<a&&56320==(64512&(n=e.charCodeAt(i+1)))&&(r=65536+(r-55296<<10)+(n-56320),i++),o+=r<128?1:r<2048?2:r<65536?3:4;for(t=h.uint8array?new Uint8Array(o):new Array(o),i=s=0;s<o;i++)55296==(64512&(r=e.charCodeAt(i)))&&i+1<a&&56320==(64512&(n=e.charCodeAt(i+1)))&&(r=65536+(r-55296<<10)+(n-56320),i++),r<128?t[s++]=r:(r<2048?t[s++]=192|r>>>6:(r<65536?t[s++]=224|r>>>12:(t[s++]=240|r>>>18,t[s++]=128|r>>>12&63),t[s++]=128|r>>>6&63),t[s++]=128|63&r);return t}(e)},s.utf8decode=function(e){return h.nodebuffer?o.transformTo("nodebuffer",e).toString("utf-8"):function(e){var t,r,n,i,s=e.length,a=new Array(2*s);for(t=r=0;t<s;)if((n=e[t++])<128)a[r++]=n;else if(4<(i=u[n]))a[r++]=65533,t+=i-1;else{for(n&=2===i?31:3===i?15:7;1<i&&t<s;)n=n<<6|63&e[t++],i--;1<i?a[r++]=65533:n<65536?a[r++]=n:(n-=65536,a[r++]=55296|n>>10&1023,a[r++]=56320|1023&n)}return a.length!==r&&(a.subarray?a=a.subarray(0,r):a.length=r),o.applyFromCharCode(a)}(e=o.transformTo(h.uint8array?"uint8array":"array",e))},o.inherits(a,n),a.prototype.processChunk=function(e){var t=o.transformTo(h.uint8array?"uint8array":"array",e.data);if(this.leftOver&&this.leftOver.length){if(h.uint8array){var r=t;(t=new Uint8Array(r.length+this.leftOver.length)).set(this.leftOver,0),t.set(r,this.leftOver.length)}else t=this.leftOver.concat(t);this.leftOver=null}var n=function(e,t){var r;for((t=t||e.length)>e.length&&(t=e.length),r=t-1;0<=r&&128==(192&e[r]);)r--;return r<0?t:0===r?t:r+u[e[r]]>t?r:t}(t),i=t;n!==t.length&&(h.uint8array?(i=t.subarray(0,n),this.leftOver=t.subarray(n,t.length)):(i=t.slice(0,n),this.leftOver=t.slice(n,t.length))),this.push({data:s.utf8decode(i),meta:e.meta})},a.prototype.flush=function(){this.leftOver&&this.leftOver.length&&(this.push({data:s.utf8decode(this.leftOver),meta:{}}),this.leftOver=null)},s.Utf8DecodeWorker=a,o.inherits(l,n),l.prototype.processChunk=function(e){this.push({data:s.utf8encode(e.data),meta:e.meta})},s.Utf8EncodeWorker=l},{"./nodejsUtils":14,"./stream/GenericWorker":28,"./support":30,"./utils":32}],32:[function(e,t,a){"use strict";var o=e("./support"),h=e("./base64"),r=e("./nodejsUtils"),u=e("./external");function n(e){return e}function l(e,t){for(var r=0;r<e.length;++r)t[r]=255&e.charCodeAt(r);return t}e("setimmediate"),a.newBlob=function(t,r){a.checkSupport("blob");try{return new Blob([t],{type:r})}catch(e){try{var n=new(self.BlobBuilder||self.WebKitBlobBuilder||self.MozBlobBuilder||self.MSBlobBuilder);return n.append(t),n.getBlob(r)}catch(e){throw new Error("Bug : can't construct the Blob.")}}};var i={stringifyByChunk:function(e,t,r){var n=[],i=0,s=e.length;if(s<=r)return String.fromCharCode.apply(null,e);for(;i<s;)"array"===t||"nodebuffer"===t?n.push(String.fromCharCode.apply(null,e.slice(i,Math.min(i+r,s)))):n.push(String.fromCharCode.apply(null,e.subarray(i,Math.min(i+r,s)))),i+=r;return n.join("")},stringifyByChar:function(e){for(var t="",r=0;r<e.length;r++)t+=String.fromCharCode(e[r]);return t},applyCanBeUsed:{uint8array:function(){try{return o.uint8array&&1===String.fromCharCode.apply(null,new Uint8Array(1)).length}catch(e){return!1}}(),nodebuffer:function(){try{return o.nodebuffer&&1===String.fromCharCode.apply(null,r.allocBuffer(1)).length}catch(e){return!1}}()}};function s(e){var t=65536,r=a.getTypeOf(e),n=!0;if("uint8array"===r?n=i.applyCanBeUsed.uint8array:"nodebuffer"===r&&(n=i.applyCanBeUsed.nodebuffer),n)for(;1<t;)try{return i.stringifyByChunk(e,r,t)}catch(e){t=Math.floor(t/2)}return i.stringifyByChar(e)}function f(e,t){for(var r=0;r<e.length;r++)t[r]=e[r];return t}a.applyFromCharCode=s;var c={};c.string={string:n,array:function(e){return l(e,new Array(e.length))},arraybuffer:function(e){return c.string.uint8array(e).buffer},uint8array:function(e){return l(e,new Uint8Array(e.length))},nodebuffer:function(e){return l(e,r.allocBuffer(e.length))}},c.array={string:s,array:n,arraybuffer:function(e){return new Uint8Array(e).buffer},uint8array:function(e){return new Uint8Array(e)},nodebuffer:function(e){return r.newBufferFrom(e)}},c.arraybuffer={string:function(e){return s(new Uint8Array(e))},array:function(e){return f(new Uint8Array(e),new Array(e.byteLength))},arraybuffer:n,uint8array:function(e){return new Uint8Array(e)},nodebuffer:function(e){return r.newBufferFrom(new Uint8Array(e))}},c.uint8array={string:s,array:function(e){return f(e,new Array(e.length))},arraybuffer:function(e){return e.buffer},uint8array:n,nodebuffer:function(e){return r.newBufferFrom(e)}},c.nodebuffer={string:s,array:function(e){return f(e,new Array(e.length))},arraybuffer:function(e){return c.nodebuffer.uint8array(e).buffer},uint8array:function(e){return f(e,new Uint8Array(e.length))},nodebuffer:n},a.transformTo=function(e,t){if(t=t||"",!e)return t;a.checkSupport(e);var r=a.getTypeOf(t);return c[r][e](t)},a.resolve=function(e){for(var t=e.split("/"),r=[],n=0;n<t.length;n++){var i=t[n];"."===i||""===i&&0!==n&&n!==t.length-1||(".."===i?r.pop():r.push(i))}return r.join("/")},a.getTypeOf=function(e){return"string"==typeof e?"string":"[object Array]"===Object.prototype.toString.call(e)?"array":o.nodebuffer&&r.isBuffer(e)?"nodebuffer":o.uint8array&&e instanceof Uint8Array?"uint8array":o.arraybuffer&&e instanceof ArrayBuffer?"arraybuffer":void 0},a.checkSupport=function(e){if(!o[e.toLowerCase()])throw new Error(e+" is not supported by this platform")},a.MAX_VALUE_16BITS=65535,a.MAX_VALUE_32BITS=-1,a.pretty=function(e){var t,r,n="";for(r=0;r<(e||"").length;r++)n+="\\x"+((t=e.charCodeAt(r))<16?"0":"")+t.toString(16).toUpperCase();return n},a.delay=function(e,t,r){setImmediate(function(){e.apply(r||null,t||[])})},a.inherits=function(e,t){function r(){}r.prototype=t.prototype,e.prototype=new r},a.extend=function(){var e,t,r={};for(e=0;e<arguments.length;e++)for(t in arguments[e])Object.prototype.hasOwnProperty.call(arguments[e],t)&&void 0===r[t]&&(r[t]=arguments[e][t]);return r},a.prepareContent=function(r,e,n,i,s){return u.Promise.resolve(e).then(function(n){return o.blob&&(n instanceof Blob||-1!==["[object File]","[object Blob]"].indexOf(Object.prototype.toString.call(n)))&&"undefined"!=typeof FileReader?new u.Promise(function(t,r){var e=new FileReader;e.onload=function(e){t(e.target.result)},e.onerror=function(e){r(e.target.error)},e.readAsArrayBuffer(n)}):n}).then(function(e){var t=a.getTypeOf(e);return t?("arraybuffer"===t?e=a.transformTo("uint8array",e):"string"===t&&(s?e=h.decode(e):n&&!0!==i&&(e=function(e){return l(e,o.uint8array?new Uint8Array(e.length):new Array(e.length))}(e))),e):u.Promise.reject(new Error("Can't read the data of '"+r+"'. Is it in a supported JavaScript type (String, Blob, ArrayBuffer, etc) ?"))})}},{"./base64":1,"./external":6,"./nodejsUtils":14,"./support":30,setimmediate:54}],33:[function(e,t,r){"use strict";var n=e("./reader/readerFor"),i=e("./utils"),s=e("./signature"),a=e("./zipEntry"),o=e("./support");function h(e){this.files=[],this.loadOptions=e}h.prototype={checkSignature:function(e){if(!this.reader.readAndCheckSignature(e)){this.reader.index-=4;var t=this.reader.readString(4);throw new Error("Corrupted zip or bug: unexpected signature ("+i.pretty(t)+", expected "+i.pretty(e)+")")}},isSignature:function(e,t){var r=this.reader.index;this.reader.setIndex(e);var n=this.reader.readString(4)===t;return this.reader.setIndex(r),n},readBlockEndOfCentral:function(){this.diskNumber=this.reader.readInt(2),this.diskWithCentralDirStart=this.reader.readInt(2),this.centralDirRecordsOnThisDisk=this.reader.readInt(2),this.centralDirRecords=this.reader.readInt(2),this.centralDirSize=this.reader.readInt(4),this.centralDirOffset=this.reader.readInt(4),this.zipCommentLength=this.reader.readInt(2);var e=this.reader.readData(this.zipCommentLength),t=o.uint8array?"uint8array":"array",r=i.transformTo(t,e);this.zipComment=this.loadOptions.decodeFileName(r)},readBlockZip64EndOfCentral:function(){this.zip64EndOfCentralSize=this.reader.readInt(8),this.reader.skip(4),this.diskNumber=this.reader.readInt(4),this.diskWithCentralDirStart=this.reader.readInt(4),this.centralDirRecordsOnThisDisk=this.reader.readInt(8),this.centralDirRecords=this.reader.readInt(8),this.centralDirSize=this.reader.readInt(8),this.centralDirOffset=this.reader.readInt(8),this.zip64ExtensibleData={};for(var e,t,r,n=this.zip64EndOfCentralSize-44;0<n;)e=this.reader.readInt(2),t=this.reader.readInt(4),r=this.reader.readData(t),this.zip64ExtensibleData[e]={id:e,length:t,value:r}},readBlockZip64EndOfCentralLocator:function(){if(this.diskWithZip64CentralDirStart=this.reader.readInt(4),this.relativeOffsetEndOfZip64CentralDir=this.reader.readInt(8),this.disksCount=this.reader.readInt(4),1<this.disksCount)throw new Error("Multi-volumes zip are not supported")},readLocalFiles:function(){var e,t;for(e=0;e<this.files.length;e++)t=this.files[e],this.reader.setIndex(t.localHeaderOffset),this.checkSignature(s.LOCAL_FILE_HEADER),t.readLocalPart(this.reader),t.handleUTF8(),t.processAttributes()},readCentralDir:function(){var e;for(this.reader.setIndex(this.centralDirOffset);this.reader.readAndCheckSignature(s.CENTRAL_FILE_HEADER);)(e=new a({zip64:this.zip64},this.loadOptions)).readCentralPart(this.reader),this.files.push(e);if(this.centralDirRecords!==this.files.length&&0!==this.centralDirRecords&&0===this.files.length)throw new Error("Corrupted zip or bug: expected "+this.centralDirRecords+" records in central dir, got "+this.files.length)},readEndOfCentral:function(){var e=this.reader.lastIndexOfSignature(s.CENTRAL_DIRECTORY_END);if(e<0)throw!this.isSignature(0,s.LOCAL_FILE_HEADER)?new Error("Can't find end of central directory : is this a zip file ? If it is, see https://stuk.github.io/jszip/documentation/howto/read_zip.html"):new Error("Corrupted zip: can't find end of central directory");this.reader.setIndex(e);var t=e;if(this.checkSignature(s.CENTRAL_DIRECTORY_END),this.readBlockEndOfCentral(),this.diskNumber===i.MAX_VALUE_16BITS||this.diskWithCentralDirStart===i.MAX_VALUE_16BITS||this.centralDirRecordsOnThisDisk===i.MAX_VALUE_16BITS||this.centralDirRecords===i.MAX_VALUE_16BITS||this.centralDirSize===i.MAX_VALUE_32BITS||this.centralDirOffset===i.MAX_VALUE_32BITS){if(this.zip64=!0,(e=this.reader.lastIndexOfSignature(s.ZIP64_CENTRAL_DIRECTORY_LOCATOR))<0)throw new Error("Corrupted zip: can't find the ZIP64 end of central directory locator");if(this.reader.setIndex(e),this.checkSignature(s.ZIP64_CENTRAL_DIRECTORY_LOCATOR),this.readBlockZip64EndOfCentralLocator(),!this.isSignature(this.relativeOffsetEndOfZip64CentralDir,s.ZIP64_CENTRAL_DIRECTORY_END)&&(this.relativeOffsetEndOfZip64CentralDir=this.reader.lastIndexOfSignature(s.ZIP64_CENTRAL_DIRECTORY_END),this.relativeOffsetEndOfZip64CentralDir<0))throw new Error("Corrupted zip: can't find the ZIP64 end of central directory");this.reader.setIndex(this.relativeOffsetEndOfZip64CentralDir),this.checkSignature(s.ZIP64_CENTRAL_DIRECTORY_END),this.readBlockZip64EndOfCentral()}var r=this.centralDirOffset+this.centralDirSize;this.zip64&&(r+=20,r+=12+this.zip64EndOfCentralSize);var n=t-r;if(0<n)this.isSignature(t,s.CENTRAL_FILE_HEADER)||(this.reader.zero=n);else if(n<0)throw new Error("Corrupted zip: missing "+Math.abs(n)+" bytes.")},prepareReader:function(e){this.reader=n(e)},load:function(e){this.prepareReader(e),this.readEndOfCentral(),this.readCentralDir(),this.readLocalFiles()}},t.exports=h},{"./reader/readerFor":22,"./signature":23,"./support":30,"./utils":32,"./zipEntry":34}],34:[function(e,t,r){"use strict";var n=e("./reader/readerFor"),s=e("./utils"),i=e("./compressedObject"),a=e("./crc32"),o=e("./utf8"),h=e("./compressions"),u=e("./support");function l(e,t){this.options=e,this.loadOptions=t}l.prototype={isEncrypted:function(){return 1==(1&this.bitFlag)},useUTF8:function(){return 2048==(2048&this.bitFlag)},readLocalPart:function(e){var t,r;if(e.skip(22),this.fileNameLength=e.readInt(2),r=e.readInt(2),this.fileName=e.readData(this.fileNameLength),e.skip(r),-1===this.compressedSize||-1===this.uncompressedSize)throw new Error("Bug or corrupted zip : didn't get enough information from the central directory (compressedSize === -1 || uncompressedSize === -1)");if(null===(t=function(e){for(var t in h)if(Object.prototype.hasOwnProperty.call(h,t)&&h[t].magic===e)return h[t];return null}(this.compressionMethod)))throw new Error("Corrupted zip : compression "+s.pretty(this.compressionMethod)+" unknown (inner file : "+s.transformTo("string",this.fileName)+")");this.decompressed=new i(this.compressedSize,this.uncompressedSize,this.crc32,t,e.readData(this.compressedSize))},readCentralPart:function(e){this.versionMadeBy=e.readInt(2),e.skip(2),this.bitFlag=e.readInt(2),this.compressionMethod=e.readString(2),this.date=e.readDate(),this.crc32=e.readInt(4),this.compressedSize=e.readInt(4),this.uncompressedSize=e.readInt(4);var t=e.readInt(2);if(this.extraFieldsLength=e.readInt(2),this.fileCommentLength=e.readInt(2),this.diskNumberStart=e.readInt(2),this.internalFileAttributes=e.readInt(2),this.externalFileAttributes=e.readInt(4),this.localHeaderOffset=e.readInt(4),this.isEncrypted())throw new Error("Encrypted zip are not supported");e.skip(t),this.readExtraFields(e),this.parseZIP64ExtraField(e),this.fileComment=e.readData(this.fileCommentLength)},processAttributes:function(){this.unixPermissions=null,this.dosPermissions=null;var e=this.versionMadeBy>>8;this.dir=!!(16&this.externalFileAttributes),0==e&&(this.dosPermissions=63&this.externalFileAttributes),3==e&&(this.unixPermissions=this.externalFileAttributes>>16&65535),this.dir||"/"!==this.fileNameStr.slice(-1)||(this.dir=!0)},parseZIP64ExtraField:function(){if(this.extraFields[1]){var e=n(this.extraFields[1].value);this.uncompressedSize===s.MAX_VALUE_32BITS&&(this.uncompressedSize=e.readInt(8)),this.compressedSize===s.MAX_VALUE_32BITS&&(this.compressedSize=e.readInt(8)),this.localHeaderOffset===s.MAX_VALUE_32BITS&&(this.localHeaderOffset=e.readInt(8)),this.diskNumberStart===s.MAX_VALUE_32BITS&&(this.diskNumberStart=e.readInt(4))}},readExtraFields:function(e){var t,r,n,i=e.index+this.extraFieldsLength;for(this.extraFields||(this.extraFields={});e.index+4<i;)t=e.readInt(2),r=e.readInt(2),n=e.readData(r),this.extraFields[t]={id:t,length:r,value:n};e.setIndex(i)},handleUTF8:function(){var e=u.uint8array?"uint8array":"array";if(this.useUTF8())this.fileNameStr=o.utf8decode(this.fileName),this.fileCommentStr=o.utf8decode(this.fileComment);else{var t=this.findExtraFieldUnicodePath();if(null!==t)this.fileNameStr=t;else{var r=s.transformTo(e,this.fileName);this.fileNameStr=this.loadOptions.decodeFileName(r)}var n=this.findExtraFieldUnicodeComment();if(null!==n)this.fileCommentStr=n;else{var i=s.transformTo(e,this.fileComment);this.fileCommentStr=this.loadOptions.decodeFileName(i)}}},findExtraFieldUnicodePath:function(){var e=this.extraFields[28789];if(e){var t=n(e.value);return 1!==t.readInt(1)?null:a(this.fileName)!==t.readInt(4)?null:o.utf8decode(t.readData(e.length-5))}return null},findExtraFieldUnicodeComment:function(){var e=this.extraFields[25461];if(e){var t=n(e.value);return 1!==t.readInt(1)?null:a(this.fileComment)!==t.readInt(4)?null:o.utf8decode(t.readData(e.length-5))}return null}},t.exports=l},{"./compressedObject":2,"./compressions":3,"./crc32":4,"./reader/readerFor":22,"./support":30,"./utf8":31,"./utils":32}],35:[function(e,t,r){"use strict";function n(e,t,r){this.name=e,this.dir=r.dir,this.date=r.date,this.comment=r.comment,this.unixPermissions=r.unixPermissions,this.dosPermissions=r.dosPermissions,this._data=t,this._dataBinary=r.binary,this.options={compression:r.compression,compressionOptions:r.compressionOptions}}var s=e("./stream/StreamHelper"),i=e("./stream/DataWorker"),a=e("./utf8"),o=e("./compressedObject"),h=e("./stream/GenericWorker");n.prototype={internalStream:function(e){var t=null,r="string";try{if(!e)throw new Error("No output type specified.");var n="string"===(r=e.toLowerCase())||"text"===r;"binarystring"!==r&&"text"!==r||(r="string"),t=this._decompressWorker();var i=!this._dataBinary;i&&!n&&(t=t.pipe(new a.Utf8EncodeWorker)),!i&&n&&(t=t.pipe(new a.Utf8DecodeWorker))}catch(e){(t=new h("error")).error(e)}return new s(t,r,"")},async:function(e,t){return this.internalStream(e).accumulate(t)},nodeStream:function(e,t){return this.internalStream(e||"nodebuffer").toNodejsStream(t)},_compressWorker:function(e,t){if(this._data instanceof o&&this._data.compression.magic===e.magic)return this._data.getCompressedWorker();var r=this._decompressWorker();return this._dataBinary||(r=r.pipe(new a.Utf8EncodeWorker)),o.createWorkerFrom(r,e,t)},_decompressWorker:function(){return this._data instanceof o?this._data.getContentWorker():this._data instanceof h?this._data:new i(this._data)}};for(var u=["asText","asBinary","asNodeBuffer","asUint8Array","asArrayBuffer"],l=function(){throw new Error("This method has been removed in JSZip 3.0, please check the upgrade guide.")},f=0;f<u.length;f++)n.prototype[u[f]]=l;t.exports=n},{"./compressedObject":2,"./stream/DataWorker":27,"./stream/GenericWorker":28,"./stream/StreamHelper":29,"./utf8":31}],36:[function(e,l,t){(function(t){"use strict";var r,n,e=t.MutationObserver||t.WebKitMutationObserver;if(e){var i=0,s=new e(u),a=t.document.createTextNode("");s.observe(a,{characterData:!0}),r=function(){a.data=i=++i%2}}else if(t.setImmediate||void 0===t.MessageChannel)r="document"in t&&"onreadystatechange"in t.document.createElement("script")?function(){var e=t.document.createElement("script");e.onreadystatechange=function(){u(),e.onreadystatechange=null,e.parentNode.removeChild(e),e=null},t.document.documentElement.appendChild(e)}:function(){setTimeout(u,0)};else{var o=new t.MessageChannel;o.port1.onmessage=u,r=function(){o.port2.postMessage(0)}}var h=[];function u(){var e,t;n=!0;for(var r=h.length;r;){for(t=h,h=[],e=-1;++e<r;)t[e]();r=h.length}n=!1}l.exports=function(e){1!==h.push(e)||n||r()}}).call(this,"undefined"!=typeof global?global:"undefined"!=typeof self?self:"undefined"!=typeof window?window:{})},{}],37:[function(e,t,r){"use strict";var i=e("immediate");function u(){}var l={},s=["REJECTED"],a=["FULFILLED"],n=["PENDING"];function o(e){if("function"!=typeof e)throw new TypeError("resolver must be a function");this.state=n,this.queue=[],this.outcome=void 0,e!==u&&d(this,e)}function h(e,t,r){this.promise=e,"function"==typeof t&&(this.onFulfilled=t,this.callFulfilled=this.otherCallFulfilled),"function"==typeof r&&(this.onRejected=r,this.callRejected=this.otherCallRejected)}function f(t,r,n){i(function(){var e;try{e=r(n)}catch(e){return l.reject(t,e)}e===t?l.reject(t,new TypeError("Cannot resolve promise with itself")):l.resolve(t,e)})}function c(e){var t=e&&e.then;if(e&&("object"==typeof e||"function"==typeof e)&&"function"==typeof t)return function(){t.apply(e,arguments)}}function d(t,e){var r=!1;function n(e){r||(r=!0,l.reject(t,e))}function i(e){r||(r=!0,l.resolve(t,e))}var s=p(function(){e(i,n)});"error"===s.status&&n(s.value)}function p(e,t){var r={};try{r.value=e(t),r.status="success"}catch(e){r.status="error",r.value=e}return r}(t.exports=o).prototype.finally=function(t){if("function"!=typeof t)return this;var r=this.constructor;return this.then(function(e){return r.resolve(t()).then(function(){return e})},function(e){return r.resolve(t()).then(function(){throw e})})},o.prototype.catch=function(e){return this.then(null,e)},o.prototype.then=function(e,t){if("function"!=typeof e&&this.state===a||"function"!=typeof t&&this.state===s)return this;var r=new this.constructor(u);this.state!==n?f(r,this.state===a?e:t,this.outcome):this.queue.push(new h(r,e,t));return r},h.prototype.callFulfilled=function(e){l.resolve(this.promise,e)},h.prototype.otherCallFulfilled=function(e){f(this.promise,this.onFulfilled,e)},h.prototype.callRejected=function(e){l.reject(this.promise,e)},h.prototype.otherCallRejected=function(e){f(this.promise,this.onRejected,e)},l.resolve=function(e,t){var r=p(c,t);if("error"===r.status)return l.reject(e,r.value);var n=r.value;if(n)d(e,n);else{e.state=a,e.outcome=t;for(var i=-1,s=e.queue.length;++i<s;)e.queue[i].callFulfilled(t)}return e},l.reject=function(e,t){e.state=s,e.outcome=t;for(var r=-1,n=e.queue.length;++r<n;)e.queue[r].callRejected(t);return e},o.resolve=function(e){if(e instanceof this)return e;return l.resolve(new this(u),e)},o.reject=function(e){var t=new this(u);return l.reject(t,e)},o.all=function(e){var r=this;if("[object Array]"!==Object.prototype.toString.call(e))return this.reject(new TypeError("must be an array"));var n=e.length,i=!1;if(!n)return this.resolve([]);var s=new Array(n),a=0,t=-1,o=new this(u);for(;++t<n;)h(e[t],t);return o;function h(e,t){r.resolve(e).then(function(e){s[t]=e,++a!==n||i||(i=!0,l.resolve(o,s))},function(e){i||(i=!0,l.reject(o,e))})}},o.race=function(e){var t=this;if("[object Array]"!==Object.prototype.toString.call(e))return this.reject(new TypeError("must be an array"));var r=e.length,n=!1;if(!r)return this.resolve([]);var i=-1,s=new this(u);for(;++i<r;)a=e[i],t.resolve(a).then(function(e){n||(n=!0,l.resolve(s,e))},function(e){n||(n=!0,l.reject(s,e))});var a;return s}},{immediate:36}],38:[function(e,t,r){"use strict";var n={};(0,e("./lib/utils/common").assign)(n,e("./lib/deflate"),e("./lib/inflate"),e("./lib/zlib/constants")),t.exports=n},{"./lib/deflate":39,"./lib/inflate":40,"./lib/utils/common":41,"./lib/zlib/constants":44}],39:[function(e,t,r){"use strict";var a=e("./zlib/deflate"),o=e("./utils/common"),h=e("./utils/strings"),i=e("./zlib/messages"),s=e("./zlib/zstream"),u=Object.prototype.toString,l=0,f=-1,c=0,d=8;function p(e){if(!(this instanceof p))return new p(e);this.options=o.assign({level:f,method:d,chunkSize:16384,windowBits:15,memLevel:8,strategy:c,to:""},e||{});var t=this.options;t.raw&&0<t.windowBits?t.windowBits=-t.windowBits:t.gzip&&0<t.windowBits&&t.windowBits<16&&(t.windowBits+=16),this.err=0,this.msg="",this.ended=!1,this.chunks=[],this.strm=new s,this.strm.avail_out=0;var r=a.deflateInit2(this.strm,t.level,t.method,t.windowBits,t.memLevel,t.strategy);if(r!==l)throw new Error(i[r]);if(t.header&&a.deflateSetHeader(this.strm,t.header),t.dictionary){var n;if(n="string"==typeof t.dictionary?h.string2buf(t.dictionary):"[object ArrayBuffer]"===u.call(t.dictionary)?new Uint8Array(t.dictionary):t.dictionary,(r=a.deflateSetDictionary(this.strm,n))!==l)throw new Error(i[r]);this._dict_set=!0}}function n(e,t){var r=new p(t);if(r.push(e,!0),r.err)throw r.msg||i[r.err];return r.result}p.prototype.push=function(e,t){var r,n,i=this.strm,s=this.options.chunkSize;if(this.ended)return!1;n=t===~~t?t:!0===t?4:0,"string"==typeof e?i.input=h.string2buf(e):"[object ArrayBuffer]"===u.call(e)?i.input=new Uint8Array(e):i.input=e,i.next_in=0,i.avail_in=i.input.length;do{if(0===i.avail_out&&(i.output=new o.Buf8(s),i.next_out=0,i.avail_out=s),1!==(r=a.deflate(i,n))&&r!==l)return this.onEnd(r),!(this.ended=!0);0!==i.avail_out&&(0!==i.avail_in||4!==n&&2!==n)||("string"===this.options.to?this.onData(h.buf2binstring(o.shrinkBuf(i.output,i.next_out))):this.onData(o.shrinkBuf(i.output,i.next_out)))}while((0<i.avail_in||0===i.avail_out)&&1!==r);return 4===n?(r=a.deflateEnd(this.strm),this.onEnd(r),this.ended=!0,r===l):2!==n||(this.onEnd(l),!(i.avail_out=0))},p.prototype.onData=function(e){this.chunks.push(e)},p.prototype.onEnd=function(e){e===l&&("string"===this.options.to?this.result=this.chunks.join(""):this.result=o.flattenChunks(this.chunks)),this.chunks=[],this.err=e,this.msg=this.strm.msg},r.Deflate=p,r.deflate=n,r.deflateRaw=function(e,t){return(t=t||{}).raw=!0,n(e,t)},r.gzip=function(e,t){return(t=t||{}).gzip=!0,n(e,t)}},{"./utils/common":41,"./utils/strings":42,"./zlib/deflate":46,"./zlib/messages":51,"./zlib/zstream":53}],40:[function(e,t,r){"use strict";var c=e("./zlib/inflate"),d=e("./utils/common"),p=e("./utils/strings"),m=e("./zlib/constants"),n=e("./zlib/messages"),i=e("./zlib/zstream"),s=e("./zlib/gzheader"),_=Object.prototype.toString;function a(e){if(!(this instanceof a))return new a(e);this.options=d.assign({chunkSize:16384,windowBits:0,to:""},e||{});var t=this.options;t.raw&&0<=t.windowBits&&t.windowBits<16&&(t.windowBits=-t.windowBits,0===t.windowBits&&(t.windowBits=-15)),!(0<=t.windowBits&&t.windowBits<16)||e&&e.windowBits||(t.windowBits+=32),15<t.windowBits&&t.windowBits<48&&0==(15&t.windowBits)&&(t.windowBits|=15),this.err=0,this.msg="",this.ended=!1,this.chunks=[],this.strm=new i,this.strm.avail_out=0;var r=c.inflateInit2(this.strm,t.windowBits);if(r!==m.Z_OK)throw new Error(n[r]);this.header=new s,c.inflateGetHeader(this.strm,this.header)}function o(e,t){var r=new a(t);if(r.push(e,!0),r.err)throw r.msg||n[r.err];return r.result}a.prototype.push=function(e,t){var r,n,i,s,a,o,h=this.strm,u=this.options.chunkSize,l=this.options.dictionary,f=!1;if(this.ended)return!1;n=t===~~t?t:!0===t?m.Z_FINISH:m.Z_NO_FLUSH,"string"==typeof e?h.input=p.binstring2buf(e):"[object ArrayBuffer]"===_.call(e)?h.input=new Uint8Array(e):h.input=e,h.next_in=0,h.avail_in=h.input.length;do{if(0===h.avail_out&&(h.output=new d.Buf8(u),h.next_out=0,h.avail_out=u),(r=c.inflate(h,m.Z_NO_FLUSH))===m.Z_NEED_DICT&&l&&(o="string"==typeof l?p.string2buf(l):"[object ArrayBuffer]"===_.call(l)?new Uint8Array(l):l,r=c.inflateSetDictionary(this.strm,o)),r===m.Z_BUF_ERROR&&!0===f&&(r=m.Z_OK,f=!1),r!==m.Z_STREAM_END&&r!==m.Z_OK)return this.onEnd(r),!(this.ended=!0);h.next_out&&(0!==h.avail_out&&r!==m.Z_STREAM_END&&(0!==h.avail_in||n!==m.Z_FINISH&&n!==m.Z_SYNC_FLUSH)||("string"===this.options.to?(i=p.utf8border(h.output,h.next_out),s=h.next_out-i,a=p.buf2string(h.output,i),h.next_out=s,h.avail_out=u-s,s&&d.arraySet(h.output,h.output,i,s,0),this.onData(a)):this.onData(d.shrinkBuf(h.output,h.next_out)))),0===h.avail_in&&0===h.avail_out&&(f=!0)}while((0<h.avail_in||0===h.avail_out)&&r!==m.Z_STREAM_END);return r===m.Z_STREAM_END&&(n=m.Z_FINISH),n===m.Z_FINISH?(r=c.inflateEnd(this.strm),this.onEnd(r),this.ended=!0,r===m.Z_OK):n!==m.Z_SYNC_FLUSH||(this.onEnd(m.Z_OK),!(h.avail_out=0))},a.prototype.onData=function(e){this.chunks.push(e)},a.prototype.onEnd=function(e){e===m.Z_OK&&("string"===this.options.to?this.result=this.chunks.join(""):this.result=d.flattenChunks(this.chunks)),this.chunks=[],this.err=e,this.msg=this.strm.msg},r.Inflate=a,r.inflate=o,r.inflateRaw=function(e,t){return(t=t||{}).raw=!0,o(e,t)},r.ungzip=o},{"./utils/common":41,"./utils/strings":42,"./zlib/constants":44,"./zlib/gzheader":47,"./zlib/inflate":49,"./zlib/messages":51,"./zlib/zstream":53}],41:[function(e,t,r){"use strict";var n="undefined"!=typeof Uint8Array&&"undefined"!=typeof Uint16Array&&"undefined"!=typeof Int32Array;r.assign=function(e){for(var t=Array.prototype.slice.call(arguments,1);t.length;){var r=t.shift();if(r){if("object"!=typeof r)throw new TypeError(r+"must be non-object");for(var n in r)r.hasOwnProperty(n)&&(e[n]=r[n])}}return e},r.shrinkBuf=function(e,t){return e.length===t?e:e.subarray?e.subarray(0,t):(e.length=t,e)};var i={arraySet:function(e,t,r,n,i){if(t.subarray&&e.subarray)e.set(t.subarray(r,r+n),i);else for(var s=0;s<n;s++)e[i+s]=t[r+s]},flattenChunks:function(e){var t,r,n,i,s,a;for(t=n=0,r=e.length;t<r;t++)n+=e[t].length;for(a=new Uint8Array(n),t=i=0,r=e.length;t<r;t++)s=e[t],a.set(s,i),i+=s.length;return a}},s={arraySet:function(e,t,r,n,i){for(var s=0;s<n;s++)e[i+s]=t[r+s]},flattenChunks:function(e){return[].concat.apply([],e)}};r.setTyped=function(e){e?(r.Buf8=Uint8Array,r.Buf16=Uint16Array,r.Buf32=Int32Array,r.assign(r,i)):(r.Buf8=Array,r.Buf16=Array,r.Buf32=Array,r.assign(r,s))},r.setTyped(n)},{}],42:[function(e,t,r){"use strict";var h=e("./common"),i=!0,s=!0;try{String.fromCharCode.apply(null,[0])}catch(e){i=!1}try{String.fromCharCode.apply(null,new Uint8Array(1))}catch(e){s=!1}for(var u=new h.Buf8(256),n=0;n<256;n++)u[n]=252<=n?6:248<=n?5:240<=n?4:224<=n?3:192<=n?2:1;function l(e,t){if(t<65537&&(e.subarray&&s||!e.subarray&&i))return String.fromCharCode.apply(null,h.shrinkBuf(e,t));for(var r="",n=0;n<t;n++)r+=String.fromCharCode(e[n]);return r}u[254]=u[254]=1,r.string2buf=function(e){var t,r,n,i,s,a=e.length,o=0;for(i=0;i<a;i++)55296==(64512&(r=e.charCodeAt(i)))&&i+1<a&&56320==(64512&(n=e.charCodeAt(i+1)))&&(r=65536+(r-55296<<10)+(n-56320),i++),o+=r<128?1:r<2048?2:r<65536?3:4;for(t=new h.Buf8(o),i=s=0;s<o;i++)55296==(64512&(r=e.charCodeAt(i)))&&i+1<a&&56320==(64512&(n=e.charCodeAt(i+1)))&&(r=65536+(r-55296<<10)+(n-56320),i++),r<128?t[s++]=r:(r<2048?t[s++]=192|r>>>6:(r<65536?t[s++]=224|r>>>12:(t[s++]=240|r>>>18,t[s++]=128|r>>>12&63),t[s++]=128|r>>>6&63),t[s++]=128|63&r);return t},r.buf2binstring=function(e){return l(e,e.length)},r.binstring2buf=function(e){for(var t=new h.Buf8(e.length),r=0,n=t.length;r<n;r++)t[r]=e.charCodeAt(r);return t},r.buf2string=function(e,t){var r,n,i,s,a=t||e.length,o=new Array(2*a);for(r=n=0;r<a;)if((i=e[r++])<128)o[n++]=i;else if(4<(s=u[i]))o[n++]=65533,r+=s-1;else{for(i&=2===s?31:3===s?15:7;1<s&&r<a;)i=i<<6|63&e[r++],s--;1<s?o[n++]=65533:i<65536?o[n++]=i:(i-=65536,o[n++]=55296|i>>10&1023,o[n++]=56320|1023&i)}return l(o,n)},r.utf8border=function(e,t){var r;for((t=t||e.length)>e.length&&(t=e.length),r=t-1;0<=r&&128==(192&e[r]);)r--;return r<0?t:0===r?t:r+u[e[r]]>t?r:t}},{"./common":41}],43:[function(e,t,r){"use strict";t.exports=function(e,t,r,n){for(var i=65535&e|0,s=e>>>16&65535|0,a=0;0!==r;){for(r-=a=2e3<r?2e3:r;s=s+(i=i+t[n++]|0)|0,--a;);i%=65521,s%=65521}return i|s<<16|0}},{}],44:[function(e,t,r){"use strict";t.exports={Z_NO_FLUSH:0,Z_PARTIAL_FLUSH:1,Z_SYNC_FLUSH:2,Z_FULL_FLUSH:3,Z_FINISH:4,Z_BLOCK:5,Z_TREES:6,Z_OK:0,Z_STREAM_END:1,Z_NEED_DICT:2,Z_ERRNO:-1,Z_STREAM_ERROR:-2,Z_DATA_ERROR:-3,Z_BUF_ERROR:-5,Z_NO_COMPRESSION:0,Z_BEST_SPEED:1,Z_BEST_COMPRESSION:9,Z_DEFAULT_COMPRESSION:-1,Z_FILTERED:1,Z_HUFFMAN_ONLY:2,Z_RLE:3,Z_FIXED:4,Z_DEFAULT_STRATEGY:0,Z_BINARY:0,Z_TEXT:1,Z_UNKNOWN:2,Z_DEFLATED:8}},{}],45:[function(e,t,r){"use strict";var o=function(){for(var e,t=[],r=0;r<256;r++){e=r;for(var n=0;n<8;n++)e=1&e?3988292384^e>>>1:e>>>1;t[r]=e}return t}();t.exports=function(e,t,r,n){var i=o,s=n+r;e^=-1;for(var a=n;a<s;a++)e=e>>>8^i[255&(e^t[a])];return-1^e}},{}],46:[function(e,t,r){"use strict";var h,c=e("../utils/common"),u=e("./trees"),d=e("./adler32"),p=e("./crc32"),n=e("./messages"),l=0,f=4,m=0,_=-2,g=-1,b=4,i=2,v=8,y=9,s=286,a=30,o=19,w=2*s+1,k=15,x=3,S=258,z=S+x+1,C=42,E=113,A=1,I=2,O=3,B=4;function R(e,t){return e.msg=n[t],t}function T(e){return(e<<1)-(4<e?9:0)}function D(e){for(var t=e.length;0<=--t;)e[t]=0}function F(e){var t=e.state,r=t.pending;r>e.avail_out&&(r=e.avail_out),0!==r&&(c.arraySet(e.output,t.pending_buf,t.pending_out,r,e.next_out),e.next_out+=r,t.pending_out+=r,e.total_out+=r,e.avail_out-=r,t.pending-=r,0===t.pending&&(t.pending_out=0))}function N(e,t){u._tr_flush_block(e,0<=e.block_start?e.block_start:-1,e.strstart-e.block_start,t),e.block_start=e.strstart,F(e.strm)}function U(e,t){e.pending_buf[e.pending++]=t}function P(e,t){e.pending_buf[e.pending++]=t>>>8&255,e.pending_buf[e.pending++]=255&t}function L(e,t){var r,n,i=e.max_chain_length,s=e.strstart,a=e.prev_length,o=e.nice_match,h=e.strstart>e.w_size-z?e.strstart-(e.w_size-z):0,u=e.window,l=e.w_mask,f=e.prev,c=e.strstart+S,d=u[s+a-1],p=u[s+a];e.prev_length>=e.good_match&&(i>>=2),o>e.lookahead&&(o=e.lookahead);do{if(u[(r=t)+a]===p&&u[r+a-1]===d&&u[r]===u[s]&&u[++r]===u[s+1]){s+=2,r++;do{}while(u[++s]===u[++r]&&u[++s]===u[++r]&&u[++s]===u[++r]&&u[++s]===u[++r]&&u[++s]===u[++r]&&u[++s]===u[++r]&&u[++s]===u[++r]&&u[++s]===u[++r]&&s<c);if(n=S-(c-s),s=c-S,a<n){if(e.match_start=t,o<=(a=n))break;d=u[s+a-1],p=u[s+a]}}}while((t=f[t&l])>h&&0!=--i);return a<=e.lookahead?a:e.lookahead}function j(e){var t,r,n,i,s,a,o,h,u,l,f=e.w_size;do{if(i=e.window_size-e.lookahead-e.strstart,e.strstart>=f+(f-z)){for(c.arraySet(e.window,e.window,f,f,0),e.match_start-=f,e.strstart-=f,e.block_start-=f,t=r=e.hash_size;n=e.head[--t],e.head[t]=f<=n?n-f:0,--r;);for(t=r=f;n=e.prev[--t],e.prev[t]=f<=n?n-f:0,--r;);i+=f}if(0===e.strm.avail_in)break;if(a=e.strm,o=e.window,h=e.strstart+e.lookahead,u=i,l=void 0,l=a.avail_in,u<l&&(l=u),r=0===l?0:(a.avail_in-=l,c.arraySet(o,a.input,a.next_in,l,h),1===a.state.wrap?a.adler=d(a.adler,o,l,h):2===a.state.wrap&&(a.adler=p(a.adler,o,l,h)),a.next_in+=l,a.total_in+=l,l),e.lookahead+=r,e.lookahead+e.insert>=x)for(s=e.strstart-e.insert,e.ins_h=e.window[s],e.ins_h=(e.ins_h<<e.hash_shift^e.window[s+1])&e.hash_mask;e.insert&&(e.ins_h=(e.ins_h<<e.hash_shift^e.window[s+x-1])&e.hash_mask,e.prev[s&e.w_mask]=e.head[e.ins_h],e.head[e.ins_h]=s,s++,e.insert--,!(e.lookahead+e.insert<x)););}while(e.lookahead<z&&0!==e.strm.avail_in)}function Z(e,t){for(var r,n;;){if(e.lookahead<z){if(j(e),e.lookahead<z&&t===l)return A;if(0===e.lookahead)break}if(r=0,e.lookahead>=x&&(e.ins_h=(e.ins_h<<e.hash_shift^e.window[e.strstart+x-1])&e.hash_mask,r=e.prev[e.strstart&e.w_mask]=e.head[e.ins_h],e.head[e.ins_h]=e.strstart),0!==r&&e.strstart-r<=e.w_size-z&&(e.match_length=L(e,r)),e.match_length>=x)if(n=u._tr_tally(e,e.strstart-e.match_start,e.match_length-x),e.lookahead-=e.match_length,e.match_length<=e.max_lazy_match&&e.lookahead>=x){for(e.match_length--;e.strstart++,e.ins_h=(e.ins_h<<e.hash_shift^e.window[e.strstart+x-1])&e.hash_mask,r=e.prev[e.strstart&e.w_mask]=e.head[e.ins_h],e.head[e.ins_h]=e.strstart,0!=--e.match_length;);e.strstart++}else e.strstart+=e.match_length,e.match_length=0,e.ins_h=e.window[e.strstart],e.ins_h=(e.ins_h<<e.hash_shift^e.window[e.strstart+1])&e.hash_mask;else n=u._tr_tally(e,0,e.window[e.strstart]),e.lookahead--,e.strstart++;if(n&&(N(e,!1),0===e.strm.avail_out))return A}return e.insert=e.strstart<x-1?e.strstart:x-1,t===f?(N(e,!0),0===e.strm.avail_out?O:B):e.last_lit&&(N(e,!1),0===e.strm.avail_out)?A:I}function W(e,t){for(var r,n,i;;){if(e.lookahead<z){if(j(e),e.lookahead<z&&t===l)return A;if(0===e.lookahead)break}if(r=0,e.lookahead>=x&&(e.ins_h=(e.ins_h<<e.hash_shift^e.window[e.strstart+x-1])&e.hash_mask,r=e.prev[e.strstart&e.w_mask]=e.head[e.ins_h],e.head[e.ins_h]=e.strstart),e.prev_length=e.match_length,e.prev_match=e.match_start,e.match_length=x-1,0!==r&&e.prev_length<e.max_lazy_match&&e.strstart-r<=e.w_size-z&&(e.match_length=L(e,r),e.match_length<=5&&(1===e.strategy||e.match_length===x&&4096<e.strstart-e.match_start)&&(e.match_length=x-1)),e.prev_length>=x&&e.match_length<=e.prev_length){for(i=e.strstart+e.lookahead-x,n=u._tr_tally(e,e.strstart-1-e.prev_match,e.prev_length-x),e.lookahead-=e.prev_length-1,e.prev_length-=2;++e.strstart<=i&&(e.ins_h=(e.ins_h<<e.hash_shift^e.window[e.strstart+x-1])&e.hash_mask,r=e.prev[e.strstart&e.w_mask]=e.head[e.ins_h],e.head[e.ins_h]=e.strstart),0!=--e.prev_length;);if(e.match_available=0,e.match_length=x-1,e.strstart++,n&&(N(e,!1),0===e.strm.avail_out))return A}else if(e.match_available){if((n=u._tr_tally(e,0,e.window[e.strstart-1]))&&N(e,!1),e.strstart++,e.lookahead--,0===e.strm.avail_out)return A}else e.match_available=1,e.strstart++,e.lookahead--}return e.match_available&&(n=u._tr_tally(e,0,e.window[e.strstart-1]),e.match_available=0),e.insert=e.strstart<x-1?e.strstart:x-1,t===f?(N(e,!0),0===e.strm.avail_out?O:B):e.last_lit&&(N(e,!1),0===e.strm.avail_out)?A:I}function M(e,t,r,n,i){this.good_length=e,this.max_lazy=t,this.nice_length=r,this.max_chain=n,this.func=i}function H(){this.strm=null,this.status=0,this.pending_buf=null,this.pending_buf_size=0,this.pending_out=0,this.pending=0,this.wrap=0,this.gzhead=null,this.gzindex=0,this.method=v,this.last_flush=-1,this.w_size=0,this.w_bits=0,this.w_mask=0,this.window=null,this.window_size=0,this.prev=null,this.head=null,this.ins_h=0,this.hash_size=0,this.hash_bits=0,this.hash_mask=0,this.hash_shift=0,this.block_start=0,this.match_length=0,this.prev_match=0,this.match_available=0,this.strstart=0,this.match_start=0,this.lookahead=0,this.prev_length=0,this.max_chain_length=0,this.max_lazy_match=0,this.level=0,this.strategy=0,this.good_match=0,this.nice_match=0,this.dyn_ltree=new c.Buf16(2*w),this.dyn_dtree=new c.Buf16(2*(2*a+1)),this.bl_tree=new c.Buf16(2*(2*o+1)),D(this.dyn_ltree),D(this.dyn_dtree),D(this.bl_tree),this.l_desc=null,this.d_desc=null,this.bl_desc=null,this.bl_count=new c.Buf16(k+1),this.heap=new c.Buf16(2*s+1),D(this.heap),this.heap_len=0,this.heap_max=0,this.depth=new c.Buf16(2*s+1),D(this.depth),this.l_buf=0,this.lit_bufsize=0,this.last_lit=0,this.d_buf=0,this.opt_len=0,this.static_len=0,this.matches=0,this.insert=0,this.bi_buf=0,this.bi_valid=0}function G(e){var t;return e&&e.state?(e.total_in=e.total_out=0,e.data_type=i,(t=e.state).pending=0,t.pending_out=0,t.wrap<0&&(t.wrap=-t.wrap),t.status=t.wrap?C:E,e.adler=2===t.wrap?0:1,t.last_flush=l,u._tr_init(t),m):R(e,_)}function K(e){var t=G(e);return t===m&&function(e){e.window_size=2*e.w_size,D(e.head),e.max_lazy_match=h[e.level].max_lazy,e.good_match=h[e.level].good_length,e.nice_match=h[e.level].nice_length,e.max_chain_length=h[e.level].max_chain,e.strstart=0,e.block_start=0,e.lookahead=0,e.insert=0,e.match_length=e.prev_length=x-1,e.match_available=0,e.ins_h=0}(e.state),t}function Y(e,t,r,n,i,s){if(!e)return _;var a=1;if(t===g&&(t=6),n<0?(a=0,n=-n):15<n&&(a=2,n-=16),i<1||y<i||r!==v||n<8||15<n||t<0||9<t||s<0||b<s)return R(e,_);8===n&&(n=9);var o=new H;return(e.state=o).strm=e,o.wrap=a,o.gzhead=null,o.w_bits=n,o.w_size=1<<o.w_bits,o.w_mask=o.w_size-1,o.hash_bits=i+7,o.hash_size=1<<o.hash_bits,o.hash_mask=o.hash_size-1,o.hash_shift=~~((o.hash_bits+x-1)/x),o.window=new c.Buf8(2*o.w_size),o.head=new c.Buf16(o.hash_size),o.prev=new c.Buf16(o.w_size),o.lit_bufsize=1<<i+6,o.pending_buf_size=4*o.lit_bufsize,o.pending_buf=new c.Buf8(o.pending_buf_size),o.d_buf=1*o.lit_bufsize,o.l_buf=3*o.lit_bufsize,o.level=t,o.strategy=s,o.method=r,K(e)}h=[new M(0,0,0,0,function(e,t){var r=65535;for(r>e.pending_buf_size-5&&(r=e.pending_buf_size-5);;){if(e.lookahead<=1){if(j(e),0===e.lookahead&&t===l)return A;if(0===e.lookahead)break}e.strstart+=e.lookahead,e.lookahead=0;var n=e.block_start+r;if((0===e.strstart||e.strstart>=n)&&(e.lookahead=e.strstart-n,e.strstart=n,N(e,!1),0===e.strm.avail_out))return A;if(e.strstart-e.block_start>=e.w_size-z&&(N(e,!1),0===e.strm.avail_out))return A}return e.insert=0,t===f?(N(e,!0),0===e.strm.avail_out?O:B):(e.strstart>e.block_start&&(N(e,!1),e.strm.avail_out),A)}),new M(4,4,8,4,Z),new M(4,5,16,8,Z),new M(4,6,32,32,Z),new M(4,4,16,16,W),new M(8,16,32,32,W),new M(8,16,128,128,W),new M(8,32,128,256,W),new M(32,128,258,1024,W),new M(32,258,258,4096,W)],r.deflateInit=function(e,t){return Y(e,t,v,15,8,0)},r.deflateInit2=Y,r.deflateReset=K,r.deflateResetKeep=G,r.deflateSetHeader=function(e,t){return e&&e.state?2!==e.state.wrap?_:(e.state.gzhead=t,m):_},r.deflate=function(e,t){var r,n,i,s;if(!e||!e.state||5<t||t<0)return e?R(e,_):_;if(n=e.state,!e.output||!e.input&&0!==e.avail_in||666===n.status&&t!==f)return R(e,0===e.avail_out?-5:_);if(n.strm=e,r=n.last_flush,n.last_flush=t,n.status===C)if(2===n.wrap)e.adler=0,U(n,31),U(n,139),U(n,8),n.gzhead?(U(n,(n.gzhead.text?1:0)+(n.gzhead.hcrc?2:0)+(n.gzhead.extra?4:0)+(n.gzhead.name?8:0)+(n.gzhead.comment?16:0)),U(n,255&n.gzhead.time),U(n,n.gzhead.time>>8&255),U(n,n.gzhead.time>>16&255),U(n,n.gzhead.time>>24&255),U(n,9===n.level?2:2<=n.strategy||n.level<2?4:0),U(n,255&n.gzhead.os),n.gzhead.extra&&n.gzhead.extra.length&&(U(n,255&n.gzhead.extra.length),U(n,n.gzhead.extra.length>>8&255)),n.gzhead.hcrc&&(e.adler=p(e.adler,n.pending_buf,n.pending,0)),n.gzindex=0,n.status=69):(U(n,0),U(n,0),U(n,0),U(n,0),U(n,0),U(n,9===n.level?2:2<=n.strategy||n.level<2?4:0),U(n,3),n.status=E);else{var a=v+(n.w_bits-8<<4)<<8;a|=(2<=n.strategy||n.level<2?0:n.level<6?1:6===n.level?2:3)<<6,0!==n.strstart&&(a|=32),a+=31-a%31,n.status=E,P(n,a),0!==n.strstart&&(P(n,e.adler>>>16),P(n,65535&e.adler)),e.adler=1}if(69===n.status)if(n.gzhead.extra){for(i=n.pending;n.gzindex<(65535&n.gzhead.extra.length)&&(n.pending!==n.pending_buf_size||(n.gzhead.hcrc&&n.pending>i&&(e.adler=p(e.adler,n.pending_buf,n.pending-i,i)),F(e),i=n.pending,n.pending!==n.pending_buf_size));)U(n,255&n.gzhead.extra[n.gzindex]),n.gzindex++;n.gzhead.hcrc&&n.pending>i&&(e.adler=p(e.adler,n.pending_buf,n.pending-i,i)),n.gzindex===n.gzhead.extra.length&&(n.gzindex=0,n.status=73)}else n.status=73;if(73===n.status)if(n.gzhead.name){i=n.pending;do{if(n.pending===n.pending_buf_size&&(n.gzhead.hcrc&&n.pending>i&&(e.adler=p(e.adler,n.pending_buf,n.pending-i,i)),F(e),i=n.pending,n.pending===n.pending_buf_size)){s=1;break}s=n.gzindex<n.gzhead.name.length?255&n.gzhead.name.charCodeAt(n.gzindex++):0,U(n,s)}while(0!==s);n.gzhead.hcrc&&n.pending>i&&(e.adler=p(e.adler,n.pending_buf,n.pending-i,i)),0===s&&(n.gzindex=0,n.status=91)}else n.status=91;if(91===n.status)if(n.gzhead.comment){i=n.pending;do{if(n.pending===n.pending_buf_size&&(n.gzhead.hcrc&&n.pending>i&&(e.adler=p(e.adler,n.pending_buf,n.pending-i,i)),F(e),i=n.pending,n.pending===n.pending_buf_size)){s=1;break}s=n.gzindex<n.gzhead.comment.length?255&n.gzhead.comment.charCodeAt(n.gzindex++):0,U(n,s)}while(0!==s);n.gzhead.hcrc&&n.pending>i&&(e.adler=p(e.adler,n.pending_buf,n.pending-i,i)),0===s&&(n.status=103)}else n.status=103;if(103===n.status&&(n.gzhead.hcrc?(n.pending+2>n.pending_buf_size&&F(e),n.pending+2<=n.pending_buf_size&&(U(n,255&e.adler),U(n,e.adler>>8&255),e.adler=0,n.status=E)):n.status=E),0!==n.pending){if(F(e),0===e.avail_out)return n.last_flush=-1,m}else if(0===e.avail_in&&T(t)<=T(r)&&t!==f)return R(e,-5);if(666===n.status&&0!==e.avail_in)return R(e,-5);if(0!==e.avail_in||0!==n.lookahead||t!==l&&666!==n.status){var o=2===n.strategy?function(e,t){for(var r;;){if(0===e.lookahead&&(j(e),0===e.lookahead)){if(t===l)return A;break}if(e.match_length=0,r=u._tr_tally(e,0,e.window[e.strstart]),e.lookahead--,e.strstart++,r&&(N(e,!1),0===e.strm.avail_out))return A}return e.insert=0,t===f?(N(e,!0),0===e.strm.avail_out?O:B):e.last_lit&&(N(e,!1),0===e.strm.avail_out)?A:I}(n,t):3===n.strategy?function(e,t){for(var r,n,i,s,a=e.window;;){if(e.lookahead<=S){if(j(e),e.lookahead<=S&&t===l)return A;if(0===e.lookahead)break}if(e.match_length=0,e.lookahead>=x&&0<e.strstart&&(n=a[i=e.strstart-1])===a[++i]&&n===a[++i]&&n===a[++i]){s=e.strstart+S;do{}while(n===a[++i]&&n===a[++i]&&n===a[++i]&&n===a[++i]&&n===a[++i]&&n===a[++i]&&n===a[++i]&&n===a[++i]&&i<s);e.match_length=S-(s-i),e.match_length>e.lookahead&&(e.match_length=e.lookahead)}if(e.match_length>=x?(r=u._tr_tally(e,1,e.match_length-x),e.lookahead-=e.match_length,e.strstart+=e.match_length,e.match_length=0):(r=u._tr_tally(e,0,e.window[e.strstart]),e.lookahead--,e.strstart++),r&&(N(e,!1),0===e.strm.avail_out))return A}return e.insert=0,t===f?(N(e,!0),0===e.strm.avail_out?O:B):e.last_lit&&(N(e,!1),0===e.strm.avail_out)?A:I}(n,t):h[n.level].func(n,t);if(o!==O&&o!==B||(n.status=666),o===A||o===O)return 0===e.avail_out&&(n.last_flush=-1),m;if(o===I&&(1===t?u._tr_align(n):5!==t&&(u._tr_stored_block(n,0,0,!1),3===t&&(D(n.head),0===n.lookahead&&(n.strstart=0,n.block_start=0,n.insert=0))),F(e),0===e.avail_out))return n.last_flush=-1,m}return t!==f?m:n.wrap<=0?1:(2===n.wrap?(U(n,255&e.adler),U(n,e.adler>>8&255),U(n,e.adler>>16&255),U(n,e.adler>>24&255),U(n,255&e.total_in),U(n,e.total_in>>8&255),U(n,e.total_in>>16&255),U(n,e.total_in>>24&255)):(P(n,e.adler>>>16),P(n,65535&e.adler)),F(e),0<n.wrap&&(n.wrap=-n.wrap),0!==n.pending?m:1)},r.deflateEnd=function(e){var t;return e&&e.state?(t=e.state.status)!==C&&69!==t&&73!==t&&91!==t&&103!==t&&t!==E&&666!==t?R(e,_):(e.state=null,t===E?R(e,-3):m):_},r.deflateSetDictionary=function(e,t){var r,n,i,s,a,o,h,u,l=t.length;if(!e||!e.state)return _;if(2===(s=(r=e.state).wrap)||1===s&&r.status!==C||r.lookahead)return _;for(1===s&&(e.adler=d(e.adler,t,l,0)),r.wrap=0,l>=r.w_size&&(0===s&&(D(r.head),r.strstart=0,r.block_start=0,r.insert=0),u=new c.Buf8(r.w_size),c.arraySet(u,t,l-r.w_size,r.w_size,0),t=u,l=r.w_size),a=e.avail_in,o=e.next_in,h=e.input,e.avail_in=l,e.next_in=0,e.input=t,j(r);r.lookahead>=x;){for(n=r.strstart,i=r.lookahead-(x-1);r.ins_h=(r.ins_h<<r.hash_shift^r.window[n+x-1])&r.hash_mask,r.prev[n&r.w_mask]=r.head[r.ins_h],r.head[r.ins_h]=n,n++,--i;);r.strstart=n,r.lookahead=x-1,j(r)}return r.strstart+=r.lookahead,r.block_start=r.strstart,r.insert=r.lookahead,r.lookahead=0,r.match_length=r.prev_length=x-1,r.match_available=0,e.next_in=o,e.input=h,e.avail_in=a,r.wrap=s,m},r.deflateInfo="pako deflate (from Nodeca project)"},{"../utils/common":41,"./adler32":43,"./crc32":45,"./messages":51,"./trees":52}],47:[function(e,t,r){"use strict";t.exports=function(){this.text=0,this.time=0,this.xflags=0,this.os=0,this.extra=null,this.extra_len=0,this.name="",this.comment="",this.hcrc=0,this.done=!1}},{}],48:[function(e,t,r){"use strict";t.exports=function(e,t){var r,n,i,s,a,o,h,u,l,f,c,d,p,m,_,g,b,v,y,w,k,x,S,z,C;r=e.state,n=e.next_in,z=e.input,i=n+(e.avail_in-5),s=e.next_out,C=e.output,a=s-(t-e.avail_out),o=s+(e.avail_out-257),h=r.dmax,u=r.wsize,l=r.whave,f=r.wnext,c=r.window,d=r.hold,p=r.bits,m=r.lencode,_=r.distcode,g=(1<<r.lenbits)-1,b=(1<<r.distbits)-1;e:do{p<15&&(d+=z[n++]<<p,p+=8,d+=z[n++]<<p,p+=8),v=m[d&g];t:for(;;){if(d>>>=y=v>>>24,p-=y,0===(y=v>>>16&255))C[s++]=65535&v;else{if(!(16&y)){if(0==(64&y)){v=m[(65535&v)+(d&(1<<y)-1)];continue t}if(32&y){r.mode=12;break e}e.msg="invalid literal/length code",r.mode=30;break e}w=65535&v,(y&=15)&&(p<y&&(d+=z[n++]<<p,p+=8),w+=d&(1<<y)-1,d>>>=y,p-=y),p<15&&(d+=z[n++]<<p,p+=8,d+=z[n++]<<p,p+=8),v=_[d&b];r:for(;;){if(d>>>=y=v>>>24,p-=y,!(16&(y=v>>>16&255))){if(0==(64&y)){v=_[(65535&v)+(d&(1<<y)-1)];continue r}e.msg="invalid distance code",r.mode=30;break e}if(k=65535&v,p<(y&=15)&&(d+=z[n++]<<p,(p+=8)<y&&(d+=z[n++]<<p,p+=8)),h<(k+=d&(1<<y)-1)){e.msg="invalid distance too far back",r.mode=30;break e}if(d>>>=y,p-=y,(y=s-a)<k){if(l<(y=k-y)&&r.sane){e.msg="invalid distance too far back",r.mode=30;break e}if(S=c,(x=0)===f){if(x+=u-y,y<w){for(w-=y;C[s++]=c[x++],--y;);x=s-k,S=C}}else if(f<y){if(x+=u+f-y,(y-=f)<w){for(w-=y;C[s++]=c[x++],--y;);if(x=0,f<w){for(w-=y=f;C[s++]=c[x++],--y;);x=s-k,S=C}}}else if(x+=f-y,y<w){for(w-=y;C[s++]=c[x++],--y;);x=s-k,S=C}for(;2<w;)C[s++]=S[x++],C[s++]=S[x++],C[s++]=S[x++],w-=3;w&&(C[s++]=S[x++],1<w&&(C[s++]=S[x++]))}else{for(x=s-k;C[s++]=C[x++],C[s++]=C[x++],C[s++]=C[x++],2<(w-=3););w&&(C[s++]=C[x++],1<w&&(C[s++]=C[x++]))}break}}break}}while(n<i&&s<o);n-=w=p>>3,d&=(1<<(p-=w<<3))-1,e.next_in=n,e.next_out=s,e.avail_in=n<i?i-n+5:5-(n-i),e.avail_out=s<o?o-s+257:257-(s-o),r.hold=d,r.bits=p}},{}],49:[function(e,t,r){"use strict";var I=e("../utils/common"),O=e("./adler32"),B=e("./crc32"),R=e("./inffast"),T=e("./inftrees"),D=1,F=2,N=0,U=-2,P=1,n=852,i=592;function L(e){return(e>>>24&255)+(e>>>8&65280)+((65280&e)<<8)+((255&e)<<24)}function s(){this.mode=0,this.last=!1,this.wrap=0,this.havedict=!1,this.flags=0,this.dmax=0,this.check=0,this.total=0,this.head=null,this.wbits=0,this.wsize=0,this.whave=0,this.wnext=0,this.window=null,this.hold=0,this.bits=0,this.length=0,this.offset=0,this.extra=0,this.lencode=null,this.distcode=null,this.lenbits=0,this.distbits=0,this.ncode=0,this.nlen=0,this.ndist=0,this.have=0,this.next=null,this.lens=new I.Buf16(320),this.work=new I.Buf16(288),this.lendyn=null,this.distdyn=null,this.sane=0,this.back=0,this.was=0}function a(e){var t;return e&&e.state?(t=e.state,e.total_in=e.total_out=t.total=0,e.msg="",t.wrap&&(e.adler=1&t.wrap),t.mode=P,t.last=0,t.havedict=0,t.dmax=32768,t.head=null,t.hold=0,t.bits=0,t.lencode=t.lendyn=new I.Buf32(n),t.distcode=t.distdyn=new I.Buf32(i),t.sane=1,t.back=-1,N):U}function o(e){var t;return e&&e.state?((t=e.state).wsize=0,t.whave=0,t.wnext=0,a(e)):U}function h(e,t){var r,n;return e&&e.state?(n=e.state,t<0?(r=0,t=-t):(r=1+(t>>4),t<48&&(t&=15)),t&&(t<8||15<t)?U:(null!==n.window&&n.wbits!==t&&(n.window=null),n.wrap=r,n.wbits=t,o(e))):U}function u(e,t){var r,n;return e?(n=new s,(e.state=n).window=null,(r=h(e,t))!==N&&(e.state=null),r):U}var l,f,c=!0;function j(e){if(c){var t;for(l=new I.Buf32(512),f=new I.Buf32(32),t=0;t<144;)e.lens[t++]=8;for(;t<256;)e.lens[t++]=9;for(;t<280;)e.lens[t++]=7;for(;t<288;)e.lens[t++]=8;for(T(D,e.lens,0,288,l,0,e.work,{bits:9}),t=0;t<32;)e.lens[t++]=5;T(F,e.lens,0,32,f,0,e.work,{bits:5}),c=!1}e.lencode=l,e.lenbits=9,e.distcode=f,e.distbits=5}function Z(e,t,r,n){var i,s=e.state;return null===s.window&&(s.wsize=1<<s.wbits,s.wnext=0,s.whave=0,s.window=new I.Buf8(s.wsize)),n>=s.wsize?(I.arraySet(s.window,t,r-s.wsize,s.wsize,0),s.wnext=0,s.whave=s.wsize):(n<(i=s.wsize-s.wnext)&&(i=n),I.arraySet(s.window,t,r-n,i,s.wnext),(n-=i)?(I.arraySet(s.window,t,r-n,n,0),s.wnext=n,s.whave=s.wsize):(s.wnext+=i,s.wnext===s.wsize&&(s.wnext=0),s.whave<s.wsize&&(s.whave+=i))),0}r.inflateReset=o,r.inflateReset2=h,r.inflateResetKeep=a,r.inflateInit=function(e){return u(e,15)},r.inflateInit2=u,r.inflate=function(e,t){var r,n,i,s,a,o,h,u,l,f,c,d,p,m,_,g,b,v,y,w,k,x,S,z,C=0,E=new I.Buf8(4),A=[16,17,18,0,8,7,9,6,10,5,11,4,12,3,13,2,14,1,15];if(!e||!e.state||!e.output||!e.input&&0!==e.avail_in)return U;12===(r=e.state).mode&&(r.mode=13),a=e.next_out,i=e.output,h=e.avail_out,s=e.next_in,n=e.input,o=e.avail_in,u=r.hold,l=r.bits,f=o,c=h,x=N;e:for(;;)switch(r.mode){case P:if(0===r.wrap){r.mode=13;break}for(;l<16;){if(0===o)break e;o--,u+=n[s++]<<l,l+=8}if(2&r.wrap&&35615===u){E[r.check=0]=255&u,E[1]=u>>>8&255,r.check=B(r.check,E,2,0),l=u=0,r.mode=2;break}if(r.flags=0,r.head&&(r.head.done=!1),!(1&r.wrap)||(((255&u)<<8)+(u>>8))%31){e.msg="incorrect header check",r.mode=30;break}if(8!=(15&u)){e.msg="unknown compression method",r.mode=30;break}if(l-=4,k=8+(15&(u>>>=4)),0===r.wbits)r.wbits=k;else if(k>r.wbits){e.msg="invalid window size",r.mode=30;break}r.dmax=1<<k,e.adler=r.check=1,r.mode=512&u?10:12,l=u=0;break;case 2:for(;l<16;){if(0===o)break e;o--,u+=n[s++]<<l,l+=8}if(r.flags=u,8!=(255&r.flags)){e.msg="unknown compression method",r.mode=30;break}if(57344&r.flags){e.msg="unknown header flags set",r.mode=30;break}r.head&&(r.head.text=u>>8&1),512&r.flags&&(E[0]=255&u,E[1]=u>>>8&255,r.check=B(r.check,E,2,0)),l=u=0,r.mode=3;case 3:for(;l<32;){if(0===o)break e;o--,u+=n[s++]<<l,l+=8}r.head&&(r.head.time=u),512&r.flags&&(E[0]=255&u,E[1]=u>>>8&255,E[2]=u>>>16&255,E[3]=u>>>24&255,r.check=B(r.check,E,4,0)),l=u=0,r.mode=4;case 4:for(;l<16;){if(0===o)break e;o--,u+=n[s++]<<l,l+=8}r.head&&(r.head.xflags=255&u,r.head.os=u>>8),512&r.flags&&(E[0]=255&u,E[1]=u>>>8&255,r.check=B(r.check,E,2,0)),l=u=0,r.mode=5;case 5:if(1024&r.flags){for(;l<16;){if(0===o)break e;o--,u+=n[s++]<<l,l+=8}r.length=u,r.head&&(r.head.extra_len=u),512&r.flags&&(E[0]=255&u,E[1]=u>>>8&255,r.check=B(r.check,E,2,0)),l=u=0}else r.head&&(r.head.extra=null);r.mode=6;case 6:if(1024&r.flags&&(o<(d=r.length)&&(d=o),d&&(r.head&&(k=r.head.extra_len-r.length,r.head.extra||(r.head.extra=new Array(r.head.extra_len)),I.arraySet(r.head.extra,n,s,d,k)),512&r.flags&&(r.check=B(r.check,n,d,s)),o-=d,s+=d,r.length-=d),r.length))break e;r.length=0,r.mode=7;case 7:if(2048&r.flags){if(0===o)break e;for(d=0;k=n[s+d++],r.head&&k&&r.length<65536&&(r.head.name+=String.fromCharCode(k)),k&&d<o;);if(512&r.flags&&(r.check=B(r.check,n,d,s)),o-=d,s+=d,k)break e}else r.head&&(r.head.name=null);r.length=0,r.mode=8;case 8:if(4096&r.flags){if(0===o)break e;for(d=0;k=n[s+d++],r.head&&k&&r.length<65536&&(r.head.comment+=String.fromCharCode(k)),k&&d<o;);if(512&r.flags&&(r.check=B(r.check,n,d,s)),o-=d,s+=d,k)break e}else r.head&&(r.head.comment=null);r.mode=9;case 9:if(512&r.flags){for(;l<16;){if(0===o)break e;o--,u+=n[s++]<<l,l+=8}if(u!==(65535&r.check)){e.msg="header crc mismatch",r.mode=30;break}l=u=0}r.head&&(r.head.hcrc=r.flags>>9&1,r.head.done=!0),e.adler=r.check=0,r.mode=12;break;case 10:for(;l<32;){if(0===o)break e;o--,u+=n[s++]<<l,l+=8}e.adler=r.check=L(u),l=u=0,r.mode=11;case 11:if(0===r.havedict)return e.next_out=a,e.avail_out=h,e.next_in=s,e.avail_in=o,r.hold=u,r.bits=l,2;e.adler=r.check=1,r.mode=12;case 12:if(5===t||6===t)break e;case 13:if(r.last){u>>>=7&l,l-=7&l,r.mode=27;break}for(;l<3;){if(0===o)break e;o--,u+=n[s++]<<l,l+=8}switch(r.last=1&u,l-=1,3&(u>>>=1)){case 0:r.mode=14;break;case 1:if(j(r),r.mode=20,6!==t)break;u>>>=2,l-=2;break e;case 2:r.mode=17;break;case 3:e.msg="invalid block type",r.mode=30}u>>>=2,l-=2;break;case 14:for(u>>>=7&l,l-=7&l;l<32;){if(0===o)break e;o--,u+=n[s++]<<l,l+=8}if((65535&u)!=(u>>>16^65535)){e.msg="invalid stored block lengths",r.mode=30;break}if(r.length=65535&u,l=u=0,r.mode=15,6===t)break e;case 15:r.mode=16;case 16:if(d=r.length){if(o<d&&(d=o),h<d&&(d=h),0===d)break e;I.arraySet(i,n,s,d,a),o-=d,s+=d,h-=d,a+=d,r.length-=d;break}r.mode=12;break;case 17:for(;l<14;){if(0===o)break e;o--,u+=n[s++]<<l,l+=8}if(r.nlen=257+(31&u),u>>>=5,l-=5,r.ndist=1+(31&u),u>>>=5,l-=5,r.ncode=4+(15&u),u>>>=4,l-=4,286<r.nlen||30<r.ndist){e.msg="too many length or distance symbols",r.mode=30;break}r.have=0,r.mode=18;case 18:for(;r.have<r.ncode;){for(;l<3;){if(0===o)break e;o--,u+=n[s++]<<l,l+=8}r.lens[A[r.have++]]=7&u,u>>>=3,l-=3}for(;r.have<19;)r.lens[A[r.have++]]=0;if(r.lencode=r.lendyn,r.lenbits=7,S={bits:r.lenbits},x=T(0,r.lens,0,19,r.lencode,0,r.work,S),r.lenbits=S.bits,x){e.msg="invalid code lengths set",r.mode=30;break}r.have=0,r.mode=19;case 19:for(;r.have<r.nlen+r.ndist;){for(;g=(C=r.lencode[u&(1<<r.lenbits)-1])>>>16&255,b=65535&C,!((_=C>>>24)<=l);){if(0===o)break e;o--,u+=n[s++]<<l,l+=8}if(b<16)u>>>=_,l-=_,r.lens[r.have++]=b;else{if(16===b){for(z=_+2;l<z;){if(0===o)break e;o--,u+=n[s++]<<l,l+=8}if(u>>>=_,l-=_,0===r.have){e.msg="invalid bit length repeat",r.mode=30;break}k=r.lens[r.have-1],d=3+(3&u),u>>>=2,l-=2}else if(17===b){for(z=_+3;l<z;){if(0===o)break e;o--,u+=n[s++]<<l,l+=8}l-=_,k=0,d=3+(7&(u>>>=_)),u>>>=3,l-=3}else{for(z=_+7;l<z;){if(0===o)break e;o--,u+=n[s++]<<l,l+=8}l-=_,k=0,d=11+(127&(u>>>=_)),u>>>=7,l-=7}if(r.have+d>r.nlen+r.ndist){e.msg="invalid bit length repeat",r.mode=30;break}for(;d--;)r.lens[r.have++]=k}}if(30===r.mode)break;if(0===r.lens[256]){e.msg="invalid code -- missing end-of-block",r.mode=30;break}if(r.lenbits=9,S={bits:r.lenbits},x=T(D,r.lens,0,r.nlen,r.lencode,0,r.work,S),r.lenbits=S.bits,x){e.msg="invalid literal/lengths set",r.mode=30;break}if(r.distbits=6,r.distcode=r.distdyn,S={bits:r.distbits},x=T(F,r.lens,r.nlen,r.ndist,r.distcode,0,r.work,S),r.distbits=S.bits,x){e.msg="invalid distances set",r.mode=30;break}if(r.mode=20,6===t)break e;case 20:r.mode=21;case 21:if(6<=o&&258<=h){e.next_out=a,e.avail_out=h,e.next_in=s,e.avail_in=o,r.hold=u,r.bits=l,R(e,c),a=e.next_out,i=e.output,h=e.avail_out,s=e.next_in,n=e.input,o=e.avail_in,u=r.hold,l=r.bits,12===r.mode&&(r.back=-1);break}for(r.back=0;g=(C=r.lencode[u&(1<<r.lenbits)-1])>>>16&255,b=65535&C,!((_=C>>>24)<=l);){if(0===o)break e;o--,u+=n[s++]<<l,l+=8}if(g&&0==(240&g)){for(v=_,y=g,w=b;g=(C=r.lencode[w+((u&(1<<v+y)-1)>>v)])>>>16&255,b=65535&C,!(v+(_=C>>>24)<=l);){if(0===o)break e;o--,u+=n[s++]<<l,l+=8}u>>>=v,l-=v,r.back+=v}if(u>>>=_,l-=_,r.back+=_,r.length=b,0===g){r.mode=26;break}if(32&g){r.back=-1,r.mode=12;break}if(64&g){e.msg="invalid literal/length code",r.mode=30;break}r.extra=15&g,r.mode=22;case 22:if(r.extra){for(z=r.extra;l<z;){if(0===o)break e;o--,u+=n[s++]<<l,l+=8}r.length+=u&(1<<r.extra)-1,u>>>=r.extra,l-=r.extra,r.back+=r.extra}r.was=r.length,r.mode=23;case 23:for(;g=(C=r.distcode[u&(1<<r.distbits)-1])>>>16&255,b=65535&C,!((_=C>>>24)<=l);){if(0===o)break e;o--,u+=n[s++]<<l,l+=8}if(0==(240&g)){for(v=_,y=g,w=b;g=(C=r.distcode[w+((u&(1<<v+y)-1)>>v)])>>>16&255,b=65535&C,!(v+(_=C>>>24)<=l);){if(0===o)break e;o--,u+=n[s++]<<l,l+=8}u>>>=v,l-=v,r.back+=v}if(u>>>=_,l-=_,r.back+=_,64&g){e.msg="invalid distance code",r.mode=30;break}r.offset=b,r.extra=15&g,r.mode=24;case 24:if(r.extra){for(z=r.extra;l<z;){if(0===o)break e;o--,u+=n[s++]<<l,l+=8}r.offset+=u&(1<<r.extra)-1,u>>>=r.extra,l-=r.extra,r.back+=r.extra}if(r.offset>r.dmax){e.msg="invalid distance too far back",r.mode=30;break}r.mode=25;case 25:if(0===h)break e;if(d=c-h,r.offset>d){if((d=r.offset-d)>r.whave&&r.sane){e.msg="invalid distance too far back",r.mode=30;break}p=d>r.wnext?(d-=r.wnext,r.wsize-d):r.wnext-d,d>r.length&&(d=r.length),m=r.window}else m=i,p=a-r.offset,d=r.length;for(h<d&&(d=h),h-=d,r.length-=d;i[a++]=m[p++],--d;);0===r.length&&(r.mode=21);break;case 26:if(0===h)break e;i[a++]=r.length,h--,r.mode=21;break;case 27:if(r.wrap){for(;l<32;){if(0===o)break e;o--,u|=n[s++]<<l,l+=8}if(c-=h,e.total_out+=c,r.total+=c,c&&(e.adler=r.check=r.flags?B(r.check,i,c,a-c):O(r.check,i,c,a-c)),c=h,(r.flags?u:L(u))!==r.check){e.msg="incorrect data check",r.mode=30;break}l=u=0}r.mode=28;case 28:if(r.wrap&&r.flags){for(;l<32;){if(0===o)break e;o--,u+=n[s++]<<l,l+=8}if(u!==(4294967295&r.total)){e.msg="incorrect length check",r.mode=30;break}l=u=0}r.mode=29;case 29:x=1;break e;case 30:x=-3;break e;case 31:return-4;case 32:default:return U}return e.next_out=a,e.avail_out=h,e.next_in=s,e.avail_in=o,r.hold=u,r.bits=l,(r.wsize||c!==e.avail_out&&r.mode<30&&(r.mode<27||4!==t))&&Z(e,e.output,e.next_out,c-e.avail_out)?(r.mode=31,-4):(f-=e.avail_in,c-=e.avail_out,e.total_in+=f,e.total_out+=c,r.total+=c,r.wrap&&c&&(e.adler=r.check=r.flags?B(r.check,i,c,e.next_out-c):O(r.check,i,c,e.next_out-c)),e.data_type=r.bits+(r.last?64:0)+(12===r.mode?128:0)+(20===r.mode||15===r.mode?256:0),(0==f&&0===c||4===t)&&x===N&&(x=-5),x)},r.inflateEnd=function(e){if(!e||!e.state)return U;var t=e.state;return t.window&&(t.window=null),e.state=null,N},r.inflateGetHeader=function(e,t){var r;return e&&e.state?0==(2&(r=e.state).wrap)?U:((r.head=t).done=!1,N):U},r.inflateSetDictionary=function(e,t){var r,n=t.length;return e&&e.state?0!==(r=e.state).wrap&&11!==r.mode?U:11===r.mode&&O(1,t,n,0)!==r.check?-3:Z(e,t,n,n)?(r.mode=31,-4):(r.havedict=1,N):U},r.inflateInfo="pako inflate (from Nodeca project)"},{"../utils/common":41,"./adler32":43,"./crc32":45,"./inffast":48,"./inftrees":50}],50:[function(e,t,r){"use strict";var D=e("../utils/common"),F=[3,4,5,6,7,8,9,10,11,13,15,17,19,23,27,31,35,43,51,59,67,83,99,115,131,163,195,227,258,0,0],N=[16,16,16,16,16,16,16,16,17,17,17,17,18,18,18,18,19,19,19,19,20,20,20,20,21,21,21,21,16,72,78],U=[1,2,3,4,5,7,9,13,17,25,33,49,65,97,129,193,257,385,513,769,1025,1537,2049,3073,4097,6145,8193,12289,16385,24577,0,0],P=[16,16,16,16,17,17,18,18,19,19,20,20,21,21,22,22,23,23,24,24,25,25,26,26,27,27,28,28,29,29,64,64];t.exports=function(e,t,r,n,i,s,a,o){var h,u,l,f,c,d,p,m,_,g=o.bits,b=0,v=0,y=0,w=0,k=0,x=0,S=0,z=0,C=0,E=0,A=null,I=0,O=new D.Buf16(16),B=new D.Buf16(16),R=null,T=0;for(b=0;b<=15;b++)O[b]=0;for(v=0;v<n;v++)O[t[r+v]]++;for(k=g,w=15;1<=w&&0===O[w];w--);if(w<k&&(k=w),0===w)return i[s++]=20971520,i[s++]=20971520,o.bits=1,0;for(y=1;y<w&&0===O[y];y++);for(k<y&&(k=y),b=z=1;b<=15;b++)if(z<<=1,(z-=O[b])<0)return-1;if(0<z&&(0===e||1!==w))return-1;for(B[1]=0,b=1;b<15;b++)B[b+1]=B[b]+O[b];for(v=0;v<n;v++)0!==t[r+v]&&(a[B[t[r+v]]++]=v);if(d=0===e?(A=R=a,19):1===e?(A=F,I-=257,R=N,T-=257,256):(A=U,R=P,-1),b=y,c=s,S=v=E=0,l=-1,f=(C=1<<(x=k))-1,1===e&&852<C||2===e&&592<C)return 1;for(;;){for(p=b-S,_=a[v]<d?(m=0,a[v]):a[v]>d?(m=R[T+a[v]],A[I+a[v]]):(m=96,0),h=1<<b-S,y=u=1<<x;i[c+(E>>S)+(u-=h)]=p<<24|m<<16|_|0,0!==u;);for(h=1<<b-1;E&h;)h>>=1;if(0!==h?(E&=h-1,E+=h):E=0,v++,0==--O[b]){if(b===w)break;b=t[r+a[v]]}if(k<b&&(E&f)!==l){for(0===S&&(S=k),c+=y,z=1<<(x=b-S);x+S<w&&!((z-=O[x+S])<=0);)x++,z<<=1;if(C+=1<<x,1===e&&852<C||2===e&&592<C)return 1;i[l=E&f]=k<<24|x<<16|c-s|0}}return 0!==E&&(i[c+E]=b-S<<24|64<<16|0),o.bits=k,0}},{"../utils/common":41}],51:[function(e,t,r){"use strict";t.exports={2:"need dictionary",1:"stream end",0:"","-1":"file error","-2":"stream error","-3":"data error","-4":"insufficient memory","-5":"buffer error","-6":"incompatible version"}},{}],52:[function(e,t,r){"use strict";var i=e("../utils/common"),o=0,h=1;function n(e){for(var t=e.length;0<=--t;)e[t]=0}var s=0,a=29,u=256,l=u+1+a,f=30,c=19,_=2*l+1,g=15,d=16,p=7,m=256,b=16,v=17,y=18,w=[0,0,0,0,0,0,0,0,1,1,1,1,2,2,2,2,3,3,3,3,4,4,4,4,5,5,5,5,0],k=[0,0,0,0,1,1,2,2,3,3,4,4,5,5,6,6,7,7,8,8,9,9,10,10,11,11,12,12,13,13],x=[0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,2,3,7],S=[16,17,18,0,8,7,9,6,10,5,11,4,12,3,13,2,14,1,15],z=new Array(2*(l+2));n(z);var C=new Array(2*f);n(C);var E=new Array(512);n(E);var A=new Array(256);n(A);var I=new Array(a);n(I);var O,B,R,T=new Array(f);function D(e,t,r,n,i){this.static_tree=e,this.extra_bits=t,this.extra_base=r,this.elems=n,this.max_length=i,this.has_stree=e&&e.length}function F(e,t){this.dyn_tree=e,this.max_code=0,this.stat_desc=t}function N(e){return e<256?E[e]:E[256+(e>>>7)]}function U(e,t){e.pending_buf[e.pending++]=255&t,e.pending_buf[e.pending++]=t>>>8&255}function P(e,t,r){e.bi_valid>d-r?(e.bi_buf|=t<<e.bi_valid&65535,U(e,e.bi_buf),e.bi_buf=t>>d-e.bi_valid,e.bi_valid+=r-d):(e.bi_buf|=t<<e.bi_valid&65535,e.bi_valid+=r)}function L(e,t,r){P(e,r[2*t],r[2*t+1])}function j(e,t){for(var r=0;r|=1&e,e>>>=1,r<<=1,0<--t;);return r>>>1}function Z(e,t,r){var n,i,s=new Array(g+1),a=0;for(n=1;n<=g;n++)s[n]=a=a+r[n-1]<<1;for(i=0;i<=t;i++){var o=e[2*i+1];0!==o&&(e[2*i]=j(s[o]++,o))}}function W(e){var t;for(t=0;t<l;t++)e.dyn_ltree[2*t]=0;for(t=0;t<f;t++)e.dyn_dtree[2*t]=0;for(t=0;t<c;t++)e.bl_tree[2*t]=0;e.dyn_ltree[2*m]=1,e.opt_len=e.static_len=0,e.last_lit=e.matches=0}function M(e){8<e.bi_valid?U(e,e.bi_buf):0<e.bi_valid&&(e.pending_buf[e.pending++]=e.bi_buf),e.bi_buf=0,e.bi_valid=0}function H(e,t,r,n){var i=2*t,s=2*r;return e[i]<e[s]||e[i]===e[s]&&n[t]<=n[r]}function G(e,t,r){for(var n=e.heap[r],i=r<<1;i<=e.heap_len&&(i<e.heap_len&&H(t,e.heap[i+1],e.heap[i],e.depth)&&i++,!H(t,n,e.heap[i],e.depth));)e.heap[r]=e.heap[i],r=i,i<<=1;e.heap[r]=n}function K(e,t,r){var n,i,s,a,o=0;if(0!==e.last_lit)for(;n=e.pending_buf[e.d_buf+2*o]<<8|e.pending_buf[e.d_buf+2*o+1],i=e.pending_buf[e.l_buf+o],o++,0===n?L(e,i,t):(L(e,(s=A[i])+u+1,t),0!==(a=w[s])&&P(e,i-=I[s],a),L(e,s=N(--n),r),0!==(a=k[s])&&P(e,n-=T[s],a)),o<e.last_lit;);L(e,m,t)}function Y(e,t){var r,n,i,s=t.dyn_tree,a=t.stat_desc.static_tree,o=t.stat_desc.has_stree,h=t.stat_desc.elems,u=-1;for(e.heap_len=0,e.heap_max=_,r=0;r<h;r++)0!==s[2*r]?(e.heap[++e.heap_len]=u=r,e.depth[r]=0):s[2*r+1]=0;for(;e.heap_len<2;)s[2*(i=e.heap[++e.heap_len]=u<2?++u:0)]=1,e.depth[i]=0,e.opt_len--,o&&(e.static_len-=a[2*i+1]);for(t.max_code=u,r=e.heap_len>>1;1<=r;r--)G(e,s,r);for(i=h;r=e.heap[1],e.heap[1]=e.heap[e.heap_len--],G(e,s,1),n=e.heap[1],e.heap[--e.heap_max]=r,e.heap[--e.heap_max]=n,s[2*i]=s[2*r]+s[2*n],e.depth[i]=(e.depth[r]>=e.depth[n]?e.depth[r]:e.depth[n])+1,s[2*r+1]=s[2*n+1]=i,e.heap[1]=i++,G(e,s,1),2<=e.heap_len;);e.heap[--e.heap_max]=e.heap[1],function(e,t){var r,n,i,s,a,o,h=t.dyn_tree,u=t.max_code,l=t.stat_desc.static_tree,f=t.stat_desc.has_stree,c=t.stat_desc.extra_bits,d=t.stat_desc.extra_base,p=t.stat_desc.max_length,m=0;for(s=0;s<=g;s++)e.bl_count[s]=0;for(h[2*e.heap[e.heap_max]+1]=0,r=e.heap_max+1;r<_;r++)p<(s=h[2*h[2*(n=e.heap[r])+1]+1]+1)&&(s=p,m++),h[2*n+1]=s,u<n||(e.bl_count[s]++,a=0,d<=n&&(a=c[n-d]),o=h[2*n],e.opt_len+=o*(s+a),f&&(e.static_len+=o*(l[2*n+1]+a)));if(0!==m){do{for(s=p-1;0===e.bl_count[s];)s--;e.bl_count[s]--,e.bl_count[s+1]+=2,e.bl_count[p]--,m-=2}while(0<m);for(s=p;0!==s;s--)for(n=e.bl_count[s];0!==n;)u<(i=e.heap[--r])||(h[2*i+1]!==s&&(e.opt_len+=(s-h[2*i+1])*h[2*i],h[2*i+1]=s),n--)}}(e,t),Z(s,u,e.bl_count)}function X(e,t,r){var n,i,s=-1,a=t[1],o=0,h=7,u=4;for(0===a&&(h=138,u=3),t[2*(r+1)+1]=65535,n=0;n<=r;n++)i=a,a=t[2*(n+1)+1],++o<h&&i===a||(o<u?e.bl_tree[2*i]+=o:0!==i?(i!==s&&e.bl_tree[2*i]++,e.bl_tree[2*b]++):o<=10?e.bl_tree[2*v]++:e.bl_tree[2*y]++,s=i,u=(o=0)===a?(h=138,3):i===a?(h=6,3):(h=7,4))}function V(e,t,r){var n,i,s=-1,a=t[1],o=0,h=7,u=4;for(0===a&&(h=138,u=3),n=0;n<=r;n++)if(i=a,a=t[2*(n+1)+1],!(++o<h&&i===a)){if(o<u)for(;L(e,i,e.bl_tree),0!=--o;);else 0!==i?(i!==s&&(L(e,i,e.bl_tree),o--),L(e,b,e.bl_tree),P(e,o-3,2)):o<=10?(L(e,v,e.bl_tree),P(e,o-3,3)):(L(e,y,e.bl_tree),P(e,o-11,7));s=i,u=(o=0)===a?(h=138,3):i===a?(h=6,3):(h=7,4)}}n(T);var q=!1;function J(e,t,r,n){P(e,(s<<1)+(n?1:0),3),function(e,t,r,n){M(e),n&&(U(e,r),U(e,~r)),i.arraySet(e.pending_buf,e.window,t,r,e.pending),e.pending+=r}(e,t,r,!0)}r._tr_init=function(e){q||(function(){var e,t,r,n,i,s=new Array(g+1);for(n=r=0;n<a-1;n++)for(I[n]=r,e=0;e<1<<w[n];e++)A[r++]=n;for(A[r-1]=n,n=i=0;n<16;n++)for(T[n]=i,e=0;e<1<<k[n];e++)E[i++]=n;for(i>>=7;n<f;n++)for(T[n]=i<<7,e=0;e<1<<k[n]-7;e++)E[256+i++]=n;for(t=0;t<=g;t++)s[t]=0;for(e=0;e<=143;)z[2*e+1]=8,e++,s[8]++;for(;e<=255;)z[2*e+1]=9,e++,s[9]++;for(;e<=279;)z[2*e+1]=7,e++,s[7]++;for(;e<=287;)z[2*e+1]=8,e++,s[8]++;for(Z(z,l+1,s),e=0;e<f;e++)C[2*e+1]=5,C[2*e]=j(e,5);O=new D(z,w,u+1,l,g),B=new D(C,k,0,f,g),R=new D(new Array(0),x,0,c,p)}(),q=!0),e.l_desc=new F(e.dyn_ltree,O),e.d_desc=new F(e.dyn_dtree,B),e.bl_desc=new F(e.bl_tree,R),e.bi_buf=0,e.bi_valid=0,W(e)},r._tr_stored_block=J,r._tr_flush_block=function(e,t,r,n){var i,s,a=0;0<e.level?(2===e.strm.data_type&&(e.strm.data_type=function(e){var t,r=4093624447;for(t=0;t<=31;t++,r>>>=1)if(1&r&&0!==e.dyn_ltree[2*t])return o;if(0!==e.dyn_ltree[18]||0!==e.dyn_ltree[20]||0!==e.dyn_ltree[26])return h;for(t=32;t<u;t++)if(0!==e.dyn_ltree[2*t])return h;return o}(e)),Y(e,e.l_desc),Y(e,e.d_desc),a=function(e){var t;for(X(e,e.dyn_ltree,e.l_desc.max_code),X(e,e.dyn_dtree,e.d_desc.max_code),Y(e,e.bl_desc),t=c-1;3<=t&&0===e.bl_tree[2*S[t]+1];t--);return e.opt_len+=3*(t+1)+5+5+4,t}(e),i=e.opt_len+3+7>>>3,(s=e.static_len+3+7>>>3)<=i&&(i=s)):i=s=r+5,r+4<=i&&-1!==t?J(e,t,r,n):4===e.strategy||s===i?(P(e,2+(n?1:0),3),K(e,z,C)):(P(e,4+(n?1:0),3),function(e,t,r,n){var i;for(P(e,t-257,5),P(e,r-1,5),P(e,n-4,4),i=0;i<n;i++)P(e,e.bl_tree[2*S[i]+1],3);V(e,e.dyn_ltree,t-1),V(e,e.dyn_dtree,r-1)}(e,e.l_desc.max_code+1,e.d_desc.max_code+1,a+1),K(e,e.dyn_ltree,e.dyn_dtree)),W(e),n&&M(e)},r._tr_tally=function(e,t,r){return e.pending_buf[e.d_buf+2*e.last_lit]=t>>>8&255,e.pending_buf[e.d_buf+2*e.last_lit+1]=255&t,e.pending_buf[e.l_buf+e.last_lit]=255&r,e.last_lit++,0===t?e.dyn_ltree[2*r]++:(e.matches++,t--,e.dyn_ltree[2*(A[r]+u+1)]++,e.dyn_dtree[2*N(t)]++),e.last_lit===e.lit_bufsize-1},r._tr_align=function(e){P(e,2,3),L(e,m,z),function(e){16===e.bi_valid?(U(e,e.bi_buf),e.bi_buf=0,e.bi_valid=0):8<=e.bi_valid&&(e.pending_buf[e.pending++]=255&e.bi_buf,e.bi_buf>>=8,e.bi_valid-=8)}(e)}},{"../utils/common":41}],53:[function(e,t,r){"use strict";t.exports=function(){this.input=null,this.next_in=0,this.avail_in=0,this.total_in=0,this.output=null,this.next_out=0,this.avail_out=0,this.total_out=0,this.msg="",this.state=null,this.data_type=2,this.adler=0}},{}],54:[function(e,t,r){(function(e){!function(r,n){"use strict";if(!r.setImmediate){var i,s,t,a,o=1,h={},u=!1,l=r.document,e=Object.getPrototypeOf&&Object.getPrototypeOf(r);e=e&&e.setTimeout?e:r,i="[object process]"==={}.toString.call(r.process)?function(e){process.nextTick(function(){c(e)})}:function(){if(r.postMessage&&!r.importScripts){var e=!0,t=r.onmessage;return r.onmessage=function(){e=!1},r.postMessage("","*"),r.onmessage=t,e}}()?(a="setImmediate$"+Math.random()+"$",r.addEventListener?r.addEventListener("message",d,!1):r.attachEvent("onmessage",d),function(e){r.postMessage(a+e,"*")}):r.MessageChannel?((t=new MessageChannel).port1.onmessage=function(e){c(e.data)},function(e){t.port2.postMessage(e)}):l&&"onreadystatechange"in l.createElement("script")?(s=l.documentElement,function(e){var t=l.createElement("script");t.onreadystatechange=function(){c(e),t.onreadystatechange=null,s.removeChild(t),t=null},s.appendChild(t)}):function(e){setTimeout(c,0,e)},e.setImmediate=function(e){"function"!=typeof e&&(e=new Function(""+e));for(var t=new Array(arguments.length-1),r=0;r<t.length;r++)t[r]=arguments[r+1];var n={callback:e,args:t};return h[o]=n,i(o),o++},e.clearImmediate=f}function f(e){delete h[e]}function c(e){if(u)setTimeout(c,0,e);else{var t=h[e];if(t){u=!0;try{!function(e){var t=e.callback,r=e.args;switch(r.length){case 0:t();break;case 1:t(r[0]);break;case 2:t(r[0],r[1]);break;case 3:t(r[0],r[1],r[2]);break;default:t.apply(n,r)}}(t)}finally{f(e),u=!1}}}}function d(e){e.source===r&&"string"==typeof e.data&&0===e.data.indexOf(a)&&c(+e.data.slice(a.length))}}("undefined"==typeof self?void 0===e?this:e:self)}).call(this,"undefined"!=typeof global?global:"undefined"!=typeof self?self:"undefined"!=typeof window?window:{})},{}]},{},[10])(10)});

/* ════════════════════════════════════════════════════════════ */

// ════ SCRIBE ANALYSE v1.2.0 ════════════════════════════════

let analyseDataA=null,analyseDataB=null,selectedEvent=null,analyseReady=false;
let activeFilters=new Set(["INCIDENT","DÉCISION","PRÉSENCE","KANBAN","RELÈVE","COMMUNIQUÉ","REX"]);
let analyseAnnotations={},albertAnalyseContext="";

const CAT_COLORS={
  "INCIDENT":"#ef4444","INCIDENT — JALON":"#f97316",
  "DÉCISION CELLULE":"#f59e0b","PRÉSENCE CELLULE":"#3d9eff",
  "KANBAN":"#a855f7","KANBAN — DÉPLACEMENT":"#7c3aed",
  "RELÈVE — CONSIGNE":"#6b7494","COMMUNIQUÉ PUBLIC":"#00e5a0","REX":"#22d3ee"
};

function handleDrop(e,side){
  e.preventDefault();
  document.getElementById("drop-"+side).classList.remove("az-drag-over");
  if(e.dataTransfer.files[0]) loadArchive(e.dataTransfer.files[0],side);
}

function clearArchive(side){
  if(side==="a"){analyseDataA=null;analyseReady=false;}
  else analyseDataB=null;
  document.getElementById("drop-"+side+"-loaded").style.display="none";
  document.getElementById("drop-"+side).classList.remove("az-loaded-state");
  document.getElementById("az-summary").style.display="none";
  document.getElementById("az-progress-bar").style.display="none";
  if(side==="a"){
    document.getElementById("analyse-metrics").style.display="none";
    document.getElementById("analyse-toolbar").style.display="none";
    document.getElementById("analyse-empty").style.display="";
    document.getElementById("btn-debrief-export").style.display="none";
    document.getElementById("frise-inner").innerHTML="";
    document.getElementById("adetail").innerHTML='<div class="adetail-empty">← Cliquez sur un événement pour voir son détail</div>';
    document.getElementById("achat").innerHTML="";
  }
}

async function loadArchive(file,side){
  function azLog(msg,color){
    var el=document.getElementById('az-log-content');
    if(el){var t=new Date().toLocaleTimeString('fr-FR',{hour:'2-digit',minute:'2-digit',second:'2-digit'});el.innerHTML+='<span style="color:'+(color||'#4ade80')+'">'+t+' '+msg+'</span><br>';el.scrollTop=el.scrollHeight;}
    console.log('[ANALYSE]',msg);
  }
  azLog('Chargement: '+file.name+' ('+Math.round(file.size/1024)+'Ko)');
  if(!file||!file.name.endsWith('.zip')){azLog('ERREUR: pas un .zip','#ef4444');toast('Fichier invalide','err');return;}
  if(!window.JSZip){azLog('ERREUR: JSZip indisponible','#ef4444');toast('JSZip manquant','err');return;}
  azLog('JSZip OK (version: '+JSZip.version+')');
  var pb=document.getElementById('az-progress-bar'),pf=document.getElementById('az-progress-fill'),pl=document.getElementById('az-progress-label');
  if(pb)pb.style.display='';document.getElementById('az-summary').style.display='none';
  if(pf)pf.style.width='5%';if(pl)pl.textContent='Lecture...';
  try{
    var zip=await JSZip.loadAsync(file);
    var fileList=[];zip.forEach(function(p){fileList.push(p);});
    azLog('ZIP OK, fichiers: '+fileList.join(', '));
    if(pf)pf.style.width='30%';if(pl)pl.textContent='Parsing CSV...';
    var events=[],stats={incidents:0,decisions:0,presences:0,releve:0,kanban:0,rex:0,communiques:0};
    var mainCSV=null;zip.forEach(function(path,f){if(path.endsWith('.csv')&&path.indexOf('main_courante')>=0)mainCSV=f;});
    if(mainCSV){
      azLog('main_courante.csv trouvé');
      var text=await mainCSV.async('string');
      azLog('CSV: '+text.length+' chars');
      var rows=parseCSV(text);azLog('Lignes parsées: '+rows.length);
      rows.slice(1).forEach(function(row,i){
        if(row.length<2||!row[0])return;
        var cat=row[1]||'';
        events.push({id:side+'_'+i,ts:parseTS(row[0]),tsStr:row[0],cat:cat,sousType:row[2]||'',acteur:row[3]||'',contenu:row[4]||'',detail:row[5]||'',side:side});
        if(cat.indexOf('INCIDENT')>=0&&cat.indexOf('JALON')<0)stats.incidents++;
        else if(cat.indexOf('DCISION')>=0||cat.indexOf('\u00e9cision')>=0||cat.indexOf('DÉCISION')>=0)stats.decisions++;
        else if(cat.indexOf('PRÉSENCE')>=0||cat.indexOf('SENCE')>=0)stats.presences++;
        else if(cat.indexOf('RELÈVE')>=0||cat.indexOf('REL')>=0)stats.releve++;
        else if(cat.indexOf('KANBAN')>=0)stats.kanban++;
        else if(cat.indexOf('REX')>=0)stats.rex++;
        else if(cat.indexOf('COMMUNIQUÉ')>=0||cat.indexOf('COMMUNIQU')>=0)stats.communiques++;
      });
    } else {
      azLog('Pas de main_courante, lecture fichiers individuels');
      var FM={incidents:{cat:'INCIDENT',sk:'incidents'},decisions:{cat:'DÉCISION CELLULE',sk:'decisions'},presences:{cat:'PRÉSENCE CELLULE',sk:'presences'},releve:{cat:'RELÈVE',sk:'releve'},kanban:{cat:'KANBAN',sk:'kanban'},rex:{cat:'REX',sk:'rex'},chronologie_publique:{cat:'COMMUNIQUÉ PUBLIC',sk:'communiques'}};
      for(var fn in FM){
        var fobj=zip.file(fn+'.csv');
        if(!fobj){azLog('  '+fn+'.csv: absent');continue;}
        var txt=await fobj.async('string');
        var rows2=parseCSV(txt);azLog('  '+fn+'.csv: '+rows2.length+' lignes');
        rows2.slice(1).forEach(function(r,i){if(!r[1])return;events.push({id:side+'_'+fn+'_'+i,ts:parseTS(r[1]),tsStr:r[1],cat:FM[fn].cat,sousType:r[2]||'',acteur:r[3]||'',contenu:r[4]||'',detail:r[5]||'',side:side});stats[FM[fn].sk]++;});
      }
    }
    events.sort(function(a,b){return(a.ts||0)-(b.ts||0);});
    azLog(events.length+' événements: inc='+stats.incidents+' dec='+stats.decisions+' pres='+stats.presences,'#60a5fa');
    if(pf)pf.style.width='95%';if(pl)pl.textContent=events.length+' événements';
    if(side==='a'){analyseDataA=events;try{analyseAnnotations.a=JSON.parse(localStorage.getItem('an_a')||'{}');}catch(e2){analyseAnnotations.a={};}}
    else{analyseDataB=events;try{analyseAnnotations.b=JSON.parse(localStorage.getItem('an_b')||'{}');}catch(e3){analyseAnnotations.b={};}}
    var lo=document.getElementById('drop-'+side+'-loaded'),nm=document.getElementById('drop-'+side+'-name');
    if(nm)nm.textContent=file.name;if(lo)lo.style.display='';
    var dz=document.getElementById('drop-'+side);if(dz)dz.classList.add('az-loaded-state');
    setTimeout(function(){if(pb)pb.style.display='none';showSummary(side,file.name,events,stats);azLog('Résumé affiché — cliquez Démarrer','#4ade80');},300);
  }catch(e){
    if(pb)pb.style.display='none';
    azLog('ERREUR FATALE: '+e.message,'#ef4444');
    toast('Erreur ZIP: '+e.message,'err');
    console.error(e);
  }
}

function showSummary(side,fname,events,stats){
  const sum=document.getElementById("az-summary"),
        ttl=document.getElementById("az-summary-title"),
        grid=document.getElementById("az-metrics-grid"),
        btn=document.getElementById("az-btn-start");
  const ok=events.length>0;
  ttl.textContent=ok?"✓ "+fname+" — "+events.length+" événements":"⚠ Archive vide";
  ttl.className="az-summary-title "+(ok?"ok":"warn");
  const chips=[
    {l:"Incidents",v:stats.incidents},{l:"Décisions",v:stats.decisions},
    {l:"Présences",v:stats.presences},{l:"Consignes",v:stats.releve},
    {l:"Kanban",v:stats.kanban},{l:"REX",v:stats.rex},{l:"Communiqués",v:stats.communiques}
  ];
  grid.innerHTML=chips.map(c=>`<div class="az-metric-chip ${c.v>0?"ok":"empty"}">${c.v>0?"✓":"—"} ${c.v} ${c.l}</div>`).join("");
  btn.style.display=ok?"":"none";
  sum.style.display="";
}

function startAnalyse(){
  if(!analyseDataA||!analyseDataA.length)return;
  analyseReady=true;
  document.getElementById("az-summary").style.display="none";
  document.getElementById("analyse-empty").style.display="none";
  document.getElementById("analyse-toolbar").style.display="";
  document.getElementById("analyse-metrics").style.display="";
  document.getElementById("btn-debrief-export").style.display="";
  buildAlbertContext();computeMetrics();renderFrise();
}

function parseCSV(text){
  var CR=13,LF=10,SEMI=59,QUOT=34;
  var lines=[],line=[],cur="",inQ=false;
  for(var i=0;i<text.length;i++){
    var code=text.charCodeAt(i);
    if(code===CR){if(text.charCodeAt(i+1)===LF)i++;lines.push(line);line=[];cur="";inQ=false;}
    else if(code===LF){lines.push(line);line=[];cur="";inQ=false;}
    else if(code===QUOT){inQ=!inQ;}
    else if(code===SEMI&&!inQ){line.push(cur);cur="";}
    else cur+=text[i];
  }
  line.push(cur);lines.push(line);
  return lines;
}

function parseTS(str){
  if(!str)return null;
  try{
    if(str.includes("/")){
      const[date,time]=(str||"").trim().split(" ");
      const[d,m,y]=(date||"").split("/");
      if(!y)return null;
      return new Date(y+"-"+m+"-"+d+"T"+(time||"00:00")+":00").getTime();
    }
    const t=new Date(str).getTime();
    return isNaN(t)?null:t;
  }catch(e){return null;}
}

function computeMetrics(){
  const data=analyseDataA||[];
  const inc=data.filter(e=>e.cat.includes("INCIDENT")&&!e.cat.includes("JALON"));
  const dec=data.filter(e=>e.cat.includes("DÉCISION"));
  const pre=data.filter(e=>e.cat.includes("PRÉSENCE"));
  const kan=data.filter(e=>e.cat==="KANBAN");
  const com=data.filter(e=>e.cat.includes("COMMUNIQUÉ"));
  const fmt=ms=>{if(!ms||ms<0)return"—";const m=Math.round(ms/60000);if(m<60)return m+"min";return Math.floor(m/60)+"h"+String(m%60).padStart(2,"0");};
  const fi=inc[0]?.ts,li=inc[inc.length-1]?.ts;
  setMet("duree",fmt(li&&fi?li-fi:null));
  setMet("incidents",inc.length,inc.length>5?"warn":"ok");
  const fp=pre.find(e=>e.sousType.includes("ENTREE")||e.acteur)?.ts;
  setMet("mtta",fmt(fp&&fi?fp-fi:null),fp&&fi&&fp-fi<3600000?"ok":"warn");
  const fc=com[0]?.ts;
  setMet("mttc",fmt(fc&&fi?fc-fi:null),fc&&fi&&fc-fi<7200000?"ok":"warn");
  setMet("decisions",dec.length,"neutral");
  const done=kan.filter(e=>e.sousType.includes("TERMINÉ")||e.detail.includes("TERMINÉ")).length;
  const pct=kan.length?Math.round(done/kan.length*100):null;
  setMet("kanban",pct!==null?pct+"%":"—",pct>=75?"ok":"warn");
  setMet("jalons",data.filter(e=>e.cat.includes("JALON")).length+" ✓","ok");
  setMet("participants",new Set(pre.map(e=>e.acteur).filter(Boolean)).size||"—","neutral");
}

function setMet(id,val,cls){
  const el=document.getElementById("mv-"+id);
  if(!el)return;
  el.textContent=val;
  el.className="amet-val "+(cls||"");
}

function renderFrise(){
  const container=document.getElementById("frise-inner");
  const allData=[...(analyseDataA||[]),...(analyseDataB||[])].filter(e=>[...activeFilters].some(f=>e.cat.startsWith(f.split(" ")[0])));
  if(!allData.length){container.innerHTML="";return;}
  const zoom=parseInt(document.getElementById("frise-zoom")?.value||1);
  const tMin=Math.min(...allData.map(e=>e.ts).filter(Boolean));
  const tMax=Math.max(...allData.map(e=>e.ts).filter(Boolean));
  const tSpan=tMax-tMin||1;
  const cW=Math.max(800,(document.getElementById("frise-container")?.clientWidth||900)-120)*zoom;
  const lanes={};
  allData.forEach(e=>{
    const k=e.cat.split(" ")[0];
    if(!lanes[k])lanes[k]={label:k,events:[],color:CAT_COLORS[e.cat]||"#6b7494"};
    lanes[k].events.push(e);
    lanes[k].color=CAT_COLORS[e.cat]||lanes[k].color;
  });
  let html=`<div style="position:relative;min-width:${cW+120}px">`;
  html+=`<div style="display:flex;padding:0 16px 0 106px;margin-bottom:4px">`;
  const nT=Math.min(8,zoom*4);
  for(let i=0;i<=nT;i++){
    const t=new Date(tMin+tSpan*i/nT);
    html+=`<div style="flex:1;font-family:var(--mono);font-size:8px;color:var(--muted);text-align:${i===nT?"right":"left"}">${t.toLocaleTimeString("fr-FR",{hour:"2-digit",minute:"2-digit"})}</div>`;
  }
  html+=`</div>`;
  Object.values(lanes).forEach(lane=>{
    html+=`<div class="frise-lane"><div class="frise-lane-lbl" style="color:${lane.color}">${lane.label}</div><div class="frise-lane-track" style="width:${cW}px;position:relative">`;
    lane.events.forEach(ev=>{
      if(!ev.ts)return;
      const pct=(ev.ts-tMin)/tSpan*100;
      const hasNote=analyseAnnotations.a?.[ev.id]||analyseAnnotations.b?.[ev.id];
      const sid=ev.side==="b"?"border:2px dashed #a855f7;background:#0a0d14":`background:${lane.color}`;
      const eid=ev.id.replace(/[^a-zA-Z0-9_]/g,'_');
      html+=`<div class="frise-event${hasNote?" annotated":""}" style="left:${pct}%;${sid}" title="${ev.tsStr} — ${(ev.contenu||"").substring(0,60)}" onclick="selectFriseEvent('${eid}')"></div>`;
    });
    html+=`</div></div>`;
  });
  html+=`</div>`;
  container.innerHTML=html;
}

function selectFriseEvent(id){
  const all=[...(analyseDataA||[]),...(analyseDataB||[])];
  const ev=all.find(e=>e.id.replace(/[^a-zA-Z0-9_]/g,'_')===id||e.id===id);
  if(!ev)return;
  selectedEvent=ev;
  const panel=document.getElementById("adetail");
  const color=CAT_COLORS[ev.cat]||"var(--muted)";
  const note=analyseAnnotations[ev.side]?.[ev.id]||"";
  const eid=ev.id.replace(/[^a-zA-Z0-9_]/g,'_');
  panel.innerHTML=`
    <div style="display:flex;align-items:center;gap:6px;margin-bottom:10px">
      <span class="compare-badge compare-${ev.side}">Archive ${ev.side.toUpperCase()}</span>
      <span style="font-family:var(--mono);font-size:9px;color:${color};font-weight:700">${ev.cat}</span>
    </div>
    <div class="adetail-title" style="color:${color}">${ev.contenu||"—"}</div>
    <div class="adetail-row"><span class="adetail-key">Horodatage</span><span>${ev.tsStr}</span></div>
    ${ev.sousType?`<div class="adetail-row"><span class="adetail-key">Sous-type</span><span>${ev.sousType}</span></div>`:""}
    ${ev.acteur?`<div class="adetail-row"><span class="adetail-key">Acteur</span><span>${ev.acteur}</span></div>`:""}
    ${ev.detail?`<div class="adetail-row"><span class="adetail-key">Détail</span><span style="color:var(--muted2)">${ev.detail}</span></div>`:""}
    <div class="adetail-note">
      <div style="font-family:var(--mono);font-size:9px;color:var(--muted);margin-bottom:4px">📝 ANNOTATION</div>
      <textarea id="annot-input" placeholder="Notez ce qui aurait pu être fait différemment..."
        onblur="saveAnnotation('${eid}','${ev.side}')">${note}</textarea>
      <button onclick="saveAnnotation('${eid}','${ev.side}')" style="margin-top:4px;font-family:var(--head);font-size:10px;padding:4px 10px;background:rgba(26,127,60,.15);color:#1a7f3c;border:1px solid rgba(26,127,60,.3);border-radius:4px;cursor:pointer">Sauvegarder</button>
    </div>`;
}

function saveAnnotation(evId,side){
  const val=document.getElementById("annot-input")?.value||"";
  if(!analyseAnnotations[side])analyseAnnotations[side]={};
  analyseAnnotations[side][evId]=val;
  const k=analyseAnnotations[side+"_key"];
  if(k)localStorage.setItem(k,JSON.stringify(analyseAnnotations[side]));
  renderFrise();
}

function toggleFilter(btn){
  const cat=btn.getAttribute("data-cat");
  if(activeFilters.has(cat)){activeFilters.delete(cat);btn.classList.remove("on");}
  else{activeFilters.add(cat);btn.classList.add("on");}
  renderFrise();
}

function toggleDebugLog(){
  var el=document.getElementById('az-debug-log');
  if(el)el.style.display=el.style.display==='none'?'':'none';
}

function resetAnalyse(){
  analyseDataA=null;analyseDataB=null;selectedEvent=null;albertAnalyseContext="";analyseReady=false;
  ["a","b"].forEach(s=>{
    const lo=document.getElementById("drop-"+s+"-loaded"),dz=document.getElementById("drop-"+s);
    if(lo)lo.style.display="none";
    if(dz)dz.classList.remove("az-loaded-state","az-drag-over");
  });
  document.getElementById("az-summary").style.display="none";
  document.getElementById("az-progress-bar").style.display="none";
  document.getElementById("analyse-empty").style.display="";
  document.getElementById("analyse-toolbar").style.display="none";
  document.getElementById("analyse-metrics").style.display="none";
  document.getElementById("btn-debrief-export").style.display="none";
  document.getElementById("frise-inner").innerHTML="";
  document.getElementById("adetail").innerHTML='<div class="adetail-empty">← Cliquez sur un événement pour voir son détail</div>';
  document.getElementById("achat").innerHTML="";
}

function buildAlbertContext(){
  const lines=(analyseDataA||[]).slice(0,120).map(e=>`[${e.tsStr}] ${e.cat} | ${e.acteur||""} | ${e.contenu||""}`);
  albertAnalyseContext="Main courante de la crise :\n\n"+lines.join("\n")+"\n\nQuestion :";
}

function askAlbertQuick(q){document.getElementById("achat-input").value=q;sendAlbertAnalyse();}

async function sendAlbertAnalyse(){
  const input=document.getElementById("achat-input");
  const question=input.value.trim();
  if(!question)return;
  if(!analyseDataA){toast("Chargez d'abord une archive","warn");return;}
  input.value="";
  const chat=document.getElementById("achat");
  chat.innerHTML+=`<div class="achat-msg user">${question}</div>`;
  const th=document.createElement("div");
  th.className="achat-msg ai";th.textContent="⏳ Analyse en cours...";
  chat.appendChild(th);chat.scrollTop=chat.scrollHeight;
  const tok=localStorage.getItem("scribe_token")||"";
  try{
    const r=await apiFetch("/api/v1/albert/analyse-crise",{
      method:"POST",headers:{"Content-Type":"application/json","Authorization":"Bearer "+tok},
      body:JSON.stringify({question:albertAnalyseContext+"\n\n"+question,mode:"analyse_crise"})
    });
    const d=await r.json();
    th.textContent=d.analyse||d.message||"Pas de réponse";
  }catch(e){th.textContent="Erreur : "+e.message;}
  chat.scrollTop=chat.scrollHeight;
}

async function albertAnalyseSynth(){
  const ann=Object.values(analyseAnnotations.a||{}).filter(Boolean);
  const q="Synthèse debriefing : 1) Points forts 2) Axes amélioration 3) Actions prioritaires."+(ann.length?" Annotations : "+ann.join(" | "):"");
  document.getElementById("achat-input").value=q;
  await sendAlbertAnalyse();
}

async function exportDebriefDocx(){
  if(!analyseDataA){toast("Aucune archive","warn");return;}
  toast("Génération rapport...","info");
  const met={incidents:(analyseDataA||[]).filter(e=>e.cat.includes("INCIDENT")).length,decisions:(analyseDataA||[]).filter(e=>e.cat.includes("DÉCISION")).length,presences:(analyseDataA||[]).filter(e=>e.cat.includes("PRÉSENCE")).length,kanban:(analyseDataA||[]).filter(e=>e.cat.includes("KANBAN")).length};
  const ann=analyseAnnotations.a||{};
  const evs=(analyseDataA||[]).slice(0,80).map(e=>({ts:e.tsStr,cat:e.cat,acteur:e.acteur,contenu:e.contenu,note:ann[e.id]||""}));
  const tok=localStorage.getItem("scribe_token")||"";
  const r=await apiFetch("/api/v1/rapport/debrief-docx",{method:"POST",headers:{"Content-Type":"application/json","Authorization":"Bearer "+tok},body:JSON.stringify({metrics:met,events:evs,annotations:ann})});
  if(!r.ok){toast("Erreur rapport","err");return;}
  const blob=await r.blob();
  const url=URL.createObjectURL(blob);
  const a=document.createElement("a");a.href=url;a.download="debrief_crise.docx";a.click();
  URL.revokeObjectURL(url);toast("Rapport téléchargé !","ok");
}

/* ════════════════════════════════════════════════════════════ */

// ════ SCRIBE CAPACITÉ v1.3.0 ═══════════════════════════════════════════

let capData = [];          // référentiel complet
let capCurrentSite = 'all';
let capCurrentRef = null;  // référentiel en cours d'édition dans le popup
let capSyntheseMode = false;

const CAP_STATUT_LABELS = {
  normal:'Normal', tension:'Tension', critique:'Critique',
  ferme:'Fermé', inconnu:'Non déclaré'
};
const CAP_STATUT_COLORS = {
  normal:'#22c55e', tension:'#f59e0b', critique:'#ef4444',
  ferme:'#6b7280', inconnu:'#374151'
};

// ── Chargement ──────────────────────────────────────────────────────────
async function loadCapacite() {
  try {
    const tok = localStorage.getItem('scribe_token') || '';
    const r = await apiFetch('/api/v1/capacite/referentiel', {
      headers: {'Authorization': 'Bearer ' + tok}
    });
    const data = await r.json();
    capData = Array.isArray(data) ? data : [];
    if (!Array.isArray(data)) {
      console.warn('loadCapacite: réponse inattendue', data);
    }
    capRenderGrid();
    capCheckSilences();
    document.getElementById('cap-last-update').textContent =
      'Mis à jour ' + new Date().toLocaleTimeString('fr-FR', {hour:'2-digit',minute:'2-digit'});
  } catch(e) {
    console.error('loadCapacite:', e);
  }
}

// ── Filtre par site ─────────────────────────────────────────────────────
function capFilterSite(btn) {
  document.querySelectorAll('.cap-site-btn').forEach(b => b.classList.remove('active'));
  btn.classList.add('active');
  capCurrentSite = btn.dataset.site;
  capRenderGrid();
  capRenderSynthese();
}

function capToggleSynthese() {
  capSyntheseMode = !capSyntheseMode;
  document.getElementById('cap-grid').style.display = capSyntheseMode ? 'none' : '';
  document.getElementById('cap-synthese-view').style.display = capSyntheseMode ? '' : 'none';
  document.querySelector('.cap-synthese-btn').textContent = capSyntheseMode ? '🃏 Cartes' : '📊 Synthèse';
  if (capSyntheseMode) capRenderSynthese();
}

// ── Rendu de la grille ──────────────────────────────────────────────────
function capRenderGrid() {
  const grid = document.getElementById('cap-grid');
  // Générer les boutons de site dynamiquement depuis les vraies données
  const dynSpan = document.getElementById('cap-site-btns-dyn');
  if (dynSpan) {
    const sites = [...new Set(capData.map(r => r.site).filter(Boolean))].sort();
    dynSpan.innerHTML = sites.map(s =>
      '<button class="cap-site-btn' + (capCurrentSite===s?' active':'') + '" data-site="' + s + '" onclick="capFilterSite(this)">' + s + '</button>'
    ).join('');
  }
  const filtered = capCurrentSite === 'all'
    ? capData
    : capData.filter(r => r.site === capCurrentSite);

  // Grouper par pôle
  const byPole = {};
  filtered.forEach(r => {
    const p = r.pole || 'Autre';
    if (!byPole[p]) byPole[p] = [];
    byPole[p].push(r);
  });

  let html = '';
  Object.entries(byPole).forEach(([pole, units]) => {
    const nAlertes = units.filter(u =>
      u.derniere_declaration &&
      (u.derniere_declaration.alerte_lits || u.derniere_declaration.alerte_rh || u.derniere_declaration.alerte_materiel)
    ).length;
    const nCritiques = units.filter(u => u.statut_global === 'critique' || u.statut_global === 'ferme').length;

    let poleColor = '#6b7280';
    if (nAlertes > 0 || nCritiques > 0) poleColor = '#ef4444';
    else if (units.some(u => u.statut_global === 'tension')) poleColor = '#f59e0b';
    else if (units.some(u => u.statut_global === 'normal')) poleColor = '#22c55e';

    html += `<div class="cap-pole-section">
      <div class="cap-pole-title">
        <span style="width:8px;height:8px;border-radius:50%;background:${poleColor};display:inline-block"></span>
        ${pole}
        ${nAlertes > 0 ? `<span style="color:#ef4444;font-size:8px">⚡ ${nAlertes} alerte(s)</span>` : ''}
        <span style="margin-left:auto;font-weight:400;color:var(--muted)">${units.length} services</span>
      </div>
      <div class="cap-cards">`;

    units.forEach(ref => {
      html += capRenderCard(ref);
    });
    html += `</div></div>`;
  });

  grid.innerHTML = html || '<div style="padding:40px;text-align:center;font-family:var(--head);color:var(--muted)">Aucune unité pour ce site</div>';
}

function capRenderCard(ref) {
  const d = ref.derniere_declaration;
  const statut = ref.statut_global || 'inconnu';
  const hasAlerte = d && (d.alerte_lits || d.alerte_rh || d.alerte_materiel);
  const color = CAP_STATUT_COLORS[statut] || '#6b7280';

  // Lits vides
  let litsHtml = '';
  if (d) {
    if (ref.accept_homme) {
      const v = d.lits_vides_h || 0;
      litsHtml += `<div class="cap-lit-cell">
        <div class="cap-input-label" style="justify-content:center"><span class="sexe-badge sexe-h">H</span></div>
        <div class="cap-lit-val ${v === 0 ? 'zero' : 'positive'}">${v}</div>
      </div>`;
    }
    if (ref.accept_femme) {
      const v = d.lits_vides_f || 0;
      litsHtml += `<div class="cap-lit-cell">
        <div class="cap-input-label" style="justify-content:center"><span class="sexe-badge sexe-f">F</span></div>
        <div class="cap-lit-val ${v === 0 ? 'zero' : 'positive'}">${v}</div>
      </div>`;
    }
    if (ref.accept_indiffer) {
      const v = d.lits_vides_i || 0;
      litsHtml += `<div class="cap-lit-cell">
        <div class="cap-input-label" style="justify-content:center"><span class="sexe-badge sexe-i">I</span></div>
        <div class="cap-lit-val ${v === 0 ? 'zero' : 'positive'}">${v}</div>
      </div>`;
    }
  } else {
    litsHtml = `<div class="cap-lit-cell" style="grid-column:1/-1;text-align:center">
      <div class="cap-lit-label">PAS DE DÉCLARATION</div>
    </div>`;
  }

  // Horodatage
  let metaTxt = '';
  if (d && d.horodatage) {
    const dt = new Date(d.horodatage);
    const heure = dt.toLocaleTimeString('fr-FR', {hour:'2-digit',minute:'2-digit'});
    const point = {matin:'🌅',aprem:'☀',soir:'🌙'}[d.point] || '';
    metaTxt = `${point} ${heure} — ${d.redacteur || '?'}`;
  }

  // Statuts RH/Mat
  let statutsHtml = '';
  if (d) {
    const rhCol = {complet:'#22c55e',tension:'#f59e0b',critique:'#ef4444',insuffisant:'#ef4444'}[d.statut_rh] || '#6b7280';
    const matCol = {ok:'#22c55e',degrade:'#f59e0b',critique:'#ef4444',hs:'#6b7280'}[d.statut_materiel] || '#6b7280';
    statutsHtml = `<span style="color:${rhCol};font-size:8px">👥 ${d.statut_rh || '?'}</span>
    <span style="color:${matCol};font-size:8px">🔧 ${d.statut_materiel || '?'}</span>`;
  }

  // Couleur de fond selon statut pour renforcer la visibilité
  const cardBg = statut === 'critique' ? 'rgba(239,68,68,.06)'
    : statut === 'tension' ? 'rgba(245,158,11,.06)'
    : statut === 'ferme' ? 'rgba(107,114,128,.06)'
    : '';
  const cardBorder = statut === 'critique' ? '#ef4444'
    : statut === 'tension' ? '#f59e0b'
    : statut === 'normal' ? '#22c55e'
    : statut === 'ferme' ? '#6b7280'
    : 'var(--border2)';

  return `<div class="cap-card statut-${statut} ${hasAlerte ? 'has-alerte' : ''}"
    style="background:${cardBg || ''};border-left:3px solid ${cardBorder}"
    onclick="capOpenPopup(${ref.id})" title="Cliquer pour déclarer">
    <div class="cap-card-title">${ref.service_nom}</div>
    <div class="cap-card-sub">${ref.uf_code ? 'UF ' + ref.uf_code + ' · ' : ''}Réf: ${ref.capacite_totale} lits</div>
    <div class="cap-lits-grid" style="grid-template-columns:${
      [ref.accept_homme, ref.accept_femme, ref.accept_indiffer].filter(Boolean).length === 1 ? '1fr' :
      [ref.accept_homme, ref.accept_femme, ref.accept_indiffer].filter(Boolean).length === 2 ? '1fr 1fr' : '1fr 1fr 1fr'
    }">${litsHtml}</div>
    <div class="cap-card-meta">
      <span class="cap-statut-badge ${statut}" style="color:${color}">${CAP_STATUT_LABELS[statut] || statut}</span>
      ${d && d.mode_degrade ? `<span style="font-family:var(--mono);font-size:7px;background:rgba(249,115,22,.2);color:#f97316;border:1px solid rgba(249,115,22,.4);border-radius:3px;padding:1px 5px;margin-left:3px">⚙ DÉGRADÉ</span>` : ''}
      ${statutsHtml}
    </div>
    ${d && d.mode_degrade && d.besoin_renfort > 0 ? `<div style="font-family:var(--mono);font-size:8px;color:#f97316;margin-top:3px">⚠ Renfort : ${d.besoin_renfort} pers.</div>` : ''}
    ${d && d.peut_preter > 0 ? `<div style="font-family:var(--mono);font-size:8px;color:var(--green);margin-top:2px">🤝 Prête : ${d.peut_preter} pers.</div>` : ''}
    ${metaTxt ? `<div style="font-family:var(--mono);font-size:8px;color:var(--muted);margin-top:4px">${metaTxt}</div>` : ''}
  </div>`;
}

// ── Rendu tableau de synthèse ───────────────────────────────────────────
function capRenderSynthese() {
  const tbody = document.getElementById('cap-synth-body');
  const filtered = capCurrentSite === 'all'
    ? capData
    : capData.filter(r => r.site === capCurrentSite);

  tbody.innerHTML = filtered.map(ref => {
    const d = ref.derniere_declaration;
    const statut = ref.statut_global || 'inconnu';
    const color = CAP_STATUT_COLORS[statut];
    const hasAlerte = d && (d.alerte_lits || d.alerte_rh || d.alerte_materiel);
    const heure = d && d.horodatage
      ? new Date(d.horodatage).toLocaleTimeString('fr-FR', {hour:'2-digit',minute:'2-digit'})
      : '—';
    return `<tr onclick="capOpenPopup(${ref.id})" style="cursor:pointer">
      <td style="font-weight:600">${ref.service_nom}</td>
      <td style="color:var(--muted)">${ref.pole || '—'}</td>
      <td style="color:var(--muted)">${ref.site || '—'}</td>
      <td style="text-align:center">${ref.capacite_totale}</td>
      <td style="text-align:center;color:#60a5fa;font-weight:700">${d ? (d.lits_vides_h ?? '—') : '—'}</td>
      <td style="text-align:center;color:#f472b6;font-weight:700">${d ? (d.lits_vides_f ?? '—') : '—'}</td>
      <td style="text-align:center;color:#c084fc;font-weight:700">${d ? (d.lits_vides_i ?? '—') : '—'}</td>
      <td><span class="cap-statut-badge ${statut}" style="color:${color}">${CAP_STATUT_LABELS[statut]}</span></td>
      <td style="text-align:center">${hasAlerte ? '⚡' : '—'}</td>
      <td style="color:var(--muted)">${d ? heure + (d.redacteur ? ' · ' + d.redacteur : '') : '—'}</td>
    </tr>`;
  }).join('');
}

// ── Alertes silence ─────────────────────────────────────────────────────
function capCheckSilences() {
  const banner = document.getElementById('cap-silence-banner');
  const nonDeclares = capData.filter(r => !r.derniere_declaration);
  if (nonDeclares.length > 0) {
    banner.textContent = `⚠ ${nonDeclares.length} service(s) n'ont pas encore déclaré leur situation : ${nonDeclares.slice(0,3).map(r => r.service_nom).join(', ')}${nonDeclares.length > 3 ? '...' : ''}`;
    banner.style.display = '';
  } else {
    banner.style.display = 'none';
  }
}

// ── Popup déclaration ───────────────────────────────────────────────────
function capOpenPopup(refId) {
  capCurrentRef = capData.find(r => r.id === refId);
  if (!capCurrentRef) return;
  const ref = capCurrentRef;
  const d = ref.derniere_declaration;

  // Titre
  document.getElementById('cap-popup-title').textContent = ref.service_nom;
  document.getElementById('cap-popup-sub').textContent =
    (ref.pole || '') + (ref.site ? ' · ' + ref.site : '') + (ref.uf_code ? ' · UF ' + ref.uf_code : '');

  // Info référence
  document.getElementById('cap-ref-info').innerHTML =
    `<span>🛏 Capacité nominale : <strong>${ref.capacite_totale}</strong></span>` +
    (ref.tension_1 > 0 ? `<span>⚡ Tension 1 : +${ref.tension_1}</span>` : '') +
    (ref.tension_2 > 0 ? `<span>⚡ Tension 2 : +${ref.tension_2}</span>` : '') +
    (ref.telephone_cadre ? `<span>📞 ${ref.telephone_cadre}</span>` : '');

  // Grille lits H/F/I selon accept_*
  const litsGrid = document.getElementById('cap-lits-grid');
  let litsHtml = '';
  if (ref.accept_homme) {
    litsHtml += `<div class="cap-input-group">
      <label class="cap-input-label"><span class="sexe-badge sexe-h">H</span> Lits hommes</label>
      <input type="number" id="cap-h" class="cap-num-input" min="0" max="${ref.capacite_totale}" value="${d ? (d.lits_vides_h || 0) : 0}">
    </div>`;
  }
  if (ref.accept_femme) {
    litsHtml += `<div class="cap-input-group">
      <label class="cap-input-label"><span class="sexe-badge sexe-f">F</span> Lits femmes</label>
      <input type="number" id="cap-f" class="cap-num-input" min="0" max="${ref.capacite_totale}" value="${d ? (d.lits_vides_f || 0) : 0}">
    </div>`;
  }
  if (ref.accept_indiffer) {
    litsHtml += `<div class="cap-input-group">
      <label class="cap-input-label"><span class="sexe-badge sexe-i">I</span> Lits indiff.</label>
      <input type="number" id="cap-i" class="cap-num-input" min="0" max="${ref.capacite_totale}" value="${d ? (d.lits_vides_i || 0) : 0}">
    </div>`;
  }
  litsGrid.innerHTML = litsHtml;
  litsGrid.style.gridTemplateColumns = [ref.accept_homme, ref.accept_femme, ref.accept_indiffer].filter(Boolean).length < 3 ? 'repeat(2,1fr)' : '1fr 1fr 1fr';

  // Pré-remplir depuis dernière déclaration
  if (d) {
    document.getElementById('cap-statut-lits').value = d.statut_lits || 'normal';
    document.getElementById('cap-statut-rh').value = d.statut_rh || 'complet';
    document.getElementById('cap-statut-mat').value = d.statut_materiel || 'ok';
    document.getElementById('cap-tension').value = d.tension_activee || 0;
    document.getElementById('cap-comment-lits').value = d.commentaire_lits || '';
    document.getElementById('cap-comment-rh').value = d.commentaire_rh || '';
    document.getElementById('cap-comment-mat').value = d.commentaire_materiel || '';
    document.getElementById('cap-comment-general').value = d.commentaire_general || '';
    // Alertes — toujours reset à false (nouvelle déclaration)
    ['lits','rh','mat'].forEach(k => {
      document.getElementById('cap-alerte-'+k).checked = false;
      document.getElementById('cap-alerte-'+k+'-lbl').classList.remove('checked');
    });
    // Redacteur
    if (d.redacteur) document.getElementById('cap-redacteur').value = d.redacteur;
  } else {
    ['statut-lits','statut-rh','statut-mat'].forEach(id => {
      const el = document.getElementById('cap-' + id);
      if (el) el.selectedIndex = 0;
    });
    document.getElementById('cap-tension').value = 0;
    ['lits','rh','mat'].forEach(k => {
      document.getElementById('cap-comment-'+k).value = '';
      document.getElementById('cap-alerte-'+k).checked = false;
      document.getElementById('cap-alerte-'+k+'-lbl').classList.remove('checked');
    });
    document.getElementById('cap-comment-general').value = '';
  const mdEl = document.getElementById('cap-mode-degrade');
  if (mdEl) { mdEl.checked = false; capToggleModeDegrade(false); }
  const brEl = document.getElementById('cap-besoin-renfort');
  if (brEl) brEl.value = 0;
  const ppEl = document.getElementById('cap-peut-preter');
  if (ppEl) ppEl.value = 0;
  }

  // Détecter le point selon l'heure
  const h = new Date().getHours();
  const autoPoint = h < 13 ? 'matin' : h < 20 ? 'aprem' : 'soir';
  document.querySelectorAll('.cap-point-btn').forEach(b => {
    b.classList.toggle('active', b.dataset.point === autoPoint);
  });

  document.getElementById('cap-popup').style.display = '';
}

function capPopupClose(e) {
  if (e && e.target !== document.getElementById('cap-popup')) return;
  document.getElementById('cap-popup').style.display = 'none';
  capCurrentRef = null;
}

function capSelectPoint(btn) {
  document.querySelectorAll('.cap-point-btn').forEach(b => b.classList.remove('active'));
  btn.classList.add('active');
}

function capToggleAlerte(type) {
  const cb = document.getElementById('cap-alerte-' + type);
  const lbl = document.getElementById('cap-alerte-' + type + '-lbl');
  // cb.checked est déjà mis à jour par l'événement natif onchange
  lbl.classList.toggle('checked', cb.checked);
}

// ── Soumission ───────────────────────────────────────────────────────────
function capToggleModeDegrade(on) {
  const row = document.getElementById('cap-renfort-row');
  const lbl = document.getElementById('cap-degrade-label');
  if (row) row.style.display = on ? 'block' : 'none';
  if (lbl) { lbl.textContent = on ? 'ON' : 'OFF'; lbl.style.color = on ? '#f97316' : 'var(--muted)'; }
}

async function capSubmitDeclaration() {
  if (!capCurrentRef) return;
  const ref = capCurrentRef;
  const redacteur = document.getElementById('cap-redacteur').value.trim();
  if (!redacteur) { toast('Veuillez indiquer le cadre déclarant', 'warn'); return; }

  const point = document.querySelector('.cap-point-btn.active')?.dataset?.point || 'matin';
  const modeDegrade = document.getElementById('cap-mode-degrade')?.checked || false;
  const payload = {
    referentiel_id:  ref.id,
    redacteur:       redacteur,
    point:           point,
    lits_vides_h:    ref.accept_homme  ? parseInt(document.getElementById('cap-h')?.value || 0) : 0,
    lits_vides_f:    ref.accept_femme  ? parseInt(document.getElementById('cap-f')?.value || 0) : 0,
    lits_vides_i:    ref.accept_indiffer ? parseInt(document.getElementById('cap-i')?.value || 0) : 0,
    tension_activee: parseInt(document.getElementById('cap-tension').value || 0),
    statut_lits:     document.getElementById('cap-statut-lits').value,
    statut_rh:       document.getElementById('cap-statut-rh').value,
    statut_materiel: document.getElementById('cap-statut-mat').value,
    alerte_lits:     document.getElementById('cap-alerte-lits').checked,
    alerte_rh:       document.getElementById('cap-alerte-rh').checked,
    alerte_materiel: document.getElementById('cap-alerte-mat').checked,
    commentaire_lits:     document.getElementById('cap-comment-lits').value,
    commentaire_rh:       document.getElementById('cap-comment-rh').value,
    commentaire_materiel: document.getElementById('cap-comment-mat').value,
    commentaire_general:  document.getElementById('cap-comment-general').value,
    mode_degrade:    modeDegrade,
    besoin_renfort:  modeDegrade ? parseInt(document.getElementById('cap-besoin-renfort')?.value || 0) : 0,
    peut_preter:     parseInt(document.getElementById('cap-peut-preter')?.value || 0),
  };

  const tok = localStorage.getItem('scribe_token') || '';
  try {
    const r = await apiFetch('/api/v1/capacite/declaration', {
      method: 'POST',
      headers: {'Content-Type':'application/json','Authorization':'Bearer '+tok},
      body: JSON.stringify(payload)
    });
    if (!r.ok) { toast('Erreur déclaration : ' + r.status, 'err'); return; }
    const res = await r.json();

    document.getElementById('cap-popup').style.display = 'none';
    capCurrentRef = null;

    if (res.incident_id) {
      toast(`⚡ Alerte transmise à la cellule — Incident #${res.incident_id} créé`, 'warn');
    } else {
      toast('✓ Déclaration enregistrée', 'ok');
    }
    await loadCapacite();
    // Mettre à jour les cartes de l'onglet SOINS
    if (document.getElementById('tab-soins').classList.contains('active')) {
      renderSoins();
    } else {
      capUpdateSoinsStatuts();
    }
  } catch(e) {
    toast('Erreur : ' + e.message, 'err');
  }
}

// ── Mise à jour des cartes SOINS selon statut capacitaire ───────────────
function capUpdateSoinsStatuts() {
  // Calculer le statut capacitaire le plus grave par pôle
  const POIDS = {ferme:3, critique:2, tension:1, normal:0, inconnu:-1};
  const polesCapStatut = {};
  capData.forEach(ref => {
    const pole = ref.pole || 'Autre';
    const poids = POIDS[ref.statut_global] ?? -1;
    if (polesCapStatut[pole] === undefined || poids > polesCapStatut[pole]) {
      polesCapStatut[pole] = poids;
    }
  });

  // Mettre à jour les badges dans les cartes SOINS (.soins-card)
  document.querySelectorAll('.soins-card').forEach(card => {
    const poleName = card.querySelector('.soins-pole-name')?.textContent?.trim();
    if (!poleName) return;

    const capPoids = polesCapStatut[poleName] ?? -1;
    if (capPoids < 1) return; // pas de statut capacitaire dégradé → rien à faire

    const badge = card.querySelector('.soins-status-badge');
    if (!badge) return;

    // Seulement dégrader si le statut incidents actuel est moins grave
    const isCritique = badge.classList.contains('soins-critique');
    const isDegrade  = badge.classList.contains('soins-degrade');

    if (capPoids >= 2 && !isCritique) {
      // Capacité critique → forcer critique
      badge.className = 'soins-status-badge soins-critique';
      badge.textContent = '⚠ CRITIQUE CAPA';
    } else if (capPoids >= 1 && !isCritique && !isDegrade) {
      // Capacité en tension → forcer dégradé
      badge.className = 'soins-status-badge soins-degrade';
      badge.textContent = '⚡ TENSION CAPA';
    }
    // Ajouter indicateur visuel sur la carte
    card.style.borderColor = capPoids >= 2 ? '#f87171' : '#fbbf24';
  });
}


// ── Albert CAPACITÉ ──────────────────────────────────────────────────────
function capAlbertAnalyse() {
  const panel = document.getElementById('cap-albert-panel');
  panel.style.display = panel.style.display === 'none' ? '' : 'none';
  if (panel.style.display !== 'none' && capData.length) {
    capAlbertQuestion('Analyse la situation capacitaire globale. Quels services sont en difficulté ?');
  }
}

async function capAlbertQuestion(question) {
  if (!question || !question.trim()) return;
  const resultEl = document.getElementById('cap-albert-result');
  const inputEl  = document.getElementById('cap-albert-input');
  if (inputEl) inputEl.value = '';

  resultEl.innerHTML = '<span style="color:var(--muted);font-style:italic">\u25c8 Analyse en cours\u2026</span>';

  const alertes  = capData.filter(r => r.derniere_declaration &&
    (r.derniere_declaration.alerte_lits || r.derniere_declaration.alerte_rh || r.derniere_declaration.alerte_materiel));
  const critiques = capData.filter(r => r.statut_global === 'critique' || r.statut_global === 'ferme');
  const tensions  = capData.filter(r => r.statut_global === 'tension');
  const nonDecl   = capData.filter(r => !r.derniere_declaration);

  const lignes = capData
    .filter(r => r.derniere_declaration)
    .map(r => {
      const d = r.derniere_declaration;
      const vides = (d.lits_vides_h||0)+(d.lits_vides_f||0)+(d.lits_vides_i||0);
      const alerteTxt = [
        d.alerte_lits ? 'ALERTE LITS' : '',
        d.alerte_rh   ? 'ALERTE RH'   : '',
        d.alerte_materiel ? 'ALERTE MATERIEL' : ''
      ].filter(Boolean).join(', ');
      const note = d.commentaire_general ? ' Note:' + d.commentaire_general : '';
      const al   = alerteTxt ? ' [' + alerteTxt + ']' : '';
      return '- ' + r.service_nom + ' (' + r.pole + ', ' + r.site + '): lits=' + r.capacite_totale +
             ' vides=' + vides + ' lits=' + d.statut_lits + ' RH=' + d.statut_rh +
             ' mat=' + d.statut_materiel + al + note;
    }).join('\n');

  const now = new Date().toLocaleString('fr-FR');
  const context = 'SITUATION CAPACITAIRE — ' + now + '\n' +
    'Services declares: ' + capData.filter(r=>r.derniere_declaration).length + '/' + capData.length + '\n' +
    'Alertes: ' + alertes.length + ' | Critiques: ' + critiques.length +
    ' | Tensions: ' + tensions.length + ' | Non declares: ' + nonDecl.length + '\n\n' +
    'DETAIL PAR SERVICE:\n' + (lignes || 'Aucune declaration disponible');

  try {
    const tok = localStorage.getItem('scribe_token') || '';
    const resp = await apiFetch('/api/v1/albert/analyse-crise', {
      method: 'POST',
      headers: {'Content-Type':'application/json','Authorization':'Bearer '+tok},
      body: JSON.stringify({
        main_courante: context,
        question: question,
        type_analyse: 'capacitaire'
      })
    });
    if (!resp.ok) throw new Error('HTTP ' + resp.status);
    const data = await resp.json();
    const text = data.analyse || data.reponse || data.text || JSON.stringify(data);
    resultEl.textContent = text;
  } catch(e) {
    resultEl.innerHTML = '<span style="color:#f87171">Erreur : ' + e.message + '</span>';
  }
}

(function() {
  const _prevOpenTab = openTab;
  openTab = function(id, btn) {
    _prevOpenTab(id, btn);
    if (id === 'tab-capacite') {
      loadCapacite();
      if (!window._capInterval) {
        window._capInterval = setInterval(loadCapacite, 60000);
      }
      // v2311 — Marquer les alertes capacité actuelles comme "vues"
      // pour résorber le badge. Se fait peu après le chargement des
      // données pour avoir la dernière déclaration sous la main.
      setTimeout(() => {
        try {
          const viewedKey = 'scribe_capacite_viewed_ids';
          const viewed = new Set(JSON.parse(localStorage.getItem(viewedKey) || '[]'));
          (capData || []).forEach(u => {
            const d = u && u.derniere_declaration;
            if (!d) return;
            const key = u.id + ':' + (d.horodatage || d.timestamp || '');
            viewed.add(key);
          });
          // Garder max 500 entrées pour ne pas saturer localStorage
          const arr = [...viewed].slice(-500);
          localStorage.setItem(viewedKey, JSON.stringify(arr));
          const badge = document.getElementById('capacite-badge');
          if (badge) badge.style.display = 'none';
        } catch(e) {}
      }, 800);
    }
  };
})();

/* ════════════════════════════════════════════════════════════ */

// ═══════════════════════════════════════════════════════════════
// SCRIBE v2.3.65 — MESSAGERIE INTERNE
// ═══════════════════════════════════════════════════════════════

let _msgBoite = 'reception';
let _msgCurrentId = null;

async function msgLoad(boite) {
  boite = boite || _msgBoite;
  _msgBoite = boite;
  const listEl = document.getElementById('msg-list');
  if (!listEl) return;
  listEl.innerHTML = '<div style="font-family:var(--mono);font-size:10px;color:var(--muted);padding:24px;text-align:center">Chargement…</div>';
  try {
    const r = await apiFetch('/api/v1/messagerie?boite=' + boite);
    if (!r.ok) { listEl.innerHTML = '<div style="font-family:var(--mono);font-size:10px;color:var(--muted);padding:24px;text-align:center">Erreur ' + r.status + '</div>'; return; }
    const msgs = await r.json();
    if (!msgs.length) {
      listEl.innerHTML = '<div style="font-family:var(--mono);font-size:10px;color:var(--muted);padding:40px;text-align:center;opacity:.6">' + (boite === 'reception' ? 'Aucun message reçu' : 'Aucun message envoyé') + '</div>';
      return;
    }
    listEl.innerHTML = msgs.map(m => {
      const isUnread = !m.lu && boite === 'reception';
      const date = parseUTC(m.created_at).toLocaleString('fr-FR', {day:'2-digit',month:'2-digit',hour:'2-digit',minute:'2-digit'});
      const contact = boite === 'reception' ? (m.expediteur_nom || '—') : ('→ ' + (m.destinataire_nom || '—'));
      return `<div onclick="msgOpen(${m.id},'${boite}')" style="padding:12px 14px;border-bottom:1px solid var(--border);cursor:pointer;background:${isUnread ? 'rgba(37,99,235,.08)' : 'transparent'};transition:background .1s" onmouseover="this.style.background='rgba(255,255,255,.04)'" onmouseout="this.style.background='${isUnread ? 'rgba(37,99,235,.08)' : 'transparent'}'">
        <div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:3px">
          <span style="font-family:var(--mono);font-size:10px;font-weight:${isUnread ? '700' : '500'};color:var(--muted2)">${contact}</span>
          <span style="font-family:var(--mono);font-size:9px;color:var(--muted)">${date}</span>
        </div>
        <div style="font-family:var(--mono);font-size:10px;font-weight:${isUnread ? '700' : '400'};color:var(--text);margin-bottom:2px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis">${m.sujet || '(sans objet)'}</div>
        <div style="font-family:var(--mono);font-size:9px;color:var(--muted);white-space:nowrap;overflow:hidden;text-overflow:ellipsis">${(m.contenu || '').substring(0, 72)}</div>
        ${isUnread ? '<span style="display:inline-block;width:6px;height:6px;background:#2563eb;border-radius:50%;margin-top:4px"></span>' : ''}
      </div>`;
    }).join('');
  } catch(e) { listEl.innerHTML = '<div style="font-family:var(--mono);font-size:10px;color:var(--muted);padding:24px;text-align:center">Erreur réseau</div>'; }
}

async function msgOpen(id, boite) {
  _msgCurrentId = id;
  if (boite === 'reception') {
    await apiFetch('/api/v1/messagerie/' + id + '/lire', { method:'PUT' }).catch(()=>{});
  }
  await msgLoad(boite);
  const detailEl = document.getElementById('msg-detail');
  if (!detailEl) return;
  detailEl.innerHTML = '<div style="padding:24px;text-align:center;color:var(--muted);font-family:var(--mono);font-size:10px">Chargement…</div>';
  try {
    const allMsgs = await (await apiFetch('/api/v1/messagerie?boite=all')).json().catch(() => []);
    const m = allMsgs.find(x => x.id === id);
    if (!m) return;
    const rootId = m.reply_to ? m.reply_to : m.id;
    const root   = allMsgs.find(x => x.id === rootId) || m;
    const thread = [root, ...allMsgs.filter(x => x.reply_to === rootId && x.id !== rootId)]
                   .sort((a,b) => new Date(a.created_at) - new Date(b.created_at));

    const renderBubble = (msg) => {
      const isMine = !!msg.is_mine;
      const date   = parseUTC(msg.created_at).toLocaleString('fr-FR', {day:'2-digit',month:'2-digit',hour:'2-digit',minute:'2-digit'});
      const who    = isMine ? 'Vous' : (msg.expediteur_nom || msg.ght_source || '—');
      const replyBtn = !isMine
        ? '<button class="conv-reply-btn" onclick="msgReply(' + msg.id + ',&quot;' + (msg.expediteur_nom||'').replace(/"/g,'') + '&quot;)">↩ Répondre</button>'
        : '';
      return '<div class="conv-row ' + (isMine ? 'mine' : 'theirs') + '">' +
        '<div class="conv-meta">' + who + ' · ' + date + '</div>' +
        '<div class="conv-bubble ' + (isMine ? 'mine' : 'theirs') + '">' +
          (msg.contenu||'').replace(/</g,'&lt;') +
        '</div>' + replyBtn +
      '</div>';
    };

    detailEl.innerHTML =
      '<div style="padding:8px 12px">' +
        '<div style="font-family:var(--mono);font-size:9px;font-weight:700;color:var(--muted);letter-spacing:1px;margin-bottom:10px;text-transform:uppercase;text-align:center;padding:4px 0">' +
          (root.sujet || '(sans objet)') + '</div>' +
        '<div class="conv-container">' +
          thread.map(renderBubble).join('') +
        '</div>' +
      '</div>';
    // Scroll en bas
    detailEl.scrollTop = detailEl.scrollHeight;
  } catch(e) { console.warn('msgOpen', e); }
  msgPollBadge();
}
function switchMsgBoite(boite, btn) {
  _msgBoite = boite;
  document.querySelectorAll('.msg-tab-btn').forEach(b => {
    b.style.background = 'transparent'; b.style.borderColor = 'transparent'; b.style.color = 'var(--muted)';
  });
  if (btn) { btn.style.background = 'var(--surface2)'; btn.style.borderColor = 'var(--border2)'; btn.style.color = 'var(--text)'; }
  document.getElementById('msg-detail').innerHTML = '<div style="display:flex;flex-direction:column;align-items:center;justify-content:center;height:100%;gap:12px;color:var(--muted)"><span style="font-size:36px;opacity:.3">✉️</span><span style="font-family:var(--mono);font-size:10px;letter-spacing:1px">Sélectionnez un message</span></div>';
  msgLoad(boite);
}

let _msgAllUsers = [];  // cache des utilisateurs pour la messagerie
let _msgSitesExercice = null;  // v2309-hotfix : sites engagés dans l'exercice courant (null = pas de filtrage)

async function msgOpenCompose(prefillUserId, prefillSite) {
  ['msg-compose-sujet','msg-compose-body'].forEach(id => { const el = document.getElementById(id); if (el) el.value = ''; });
  // v2309-hotfix — Reset du hint "message externe" à chaque ouverture
  // classique (il sera réactivé depuis msgReply si nécessaire).
  const hint = document.getElementById('msg-compose-externe-hint');
  if (hint) hint.style.display = 'none';
  
  // Charger le statut fédération + annuaire inter-GHT pour les options destinataire
  await loadFedStatus();
  if (!_annInterGHT.length) await loadAnnuaireMessagerie();

  // v2309-hotfix — Si un exercice est en cours sur le collecteur, récupérer
  // la liste des sites engagés pour filtrer le dropdown. Cela évite de
  // présenter tout l'univers SCRIBE (pollution visuelle + risque d'envoyer
  // un message à un hôpital non concerné). Fail-safe : si la route n'est
  // pas dispo ou aucun exo actif, on retombe sur le comportement actuel.
  _msgSitesExercice = null;  // null = pas de filtrage, [] = filtrage strict
  try {
    if (_fedStatus?.ready && _fedStatus?.collecteur_url) {
      const collBase = _fedStatus.collecteur_url.replace('/api/push','');
      const rExo = await fetch(`${collBase}/api/exercice/sites-actifs`);
      if (rExo.ok) {
        const dExo = await rExo.json();
        if (dExo.running && Array.isArray(dExo.sites) && dExo.sites.length) {
          _msgSitesExercice = dExo.sites.map(s => String(s).toUpperCase());
        }
      }
    }
  } catch(e) { /* fail-safe : pas de filtrage */ }

  // Charger la liste des utilisateurs
  try {
    const r = await apiFetch('/api/v1/auth/users');
    if (r.ok) {
      const users = await r.json();
      const me = currentUser && currentUser.id;
      _msgAllUsers = users.filter(u => u.active && u.id !== me);
    }
  } catch(e) { _msgAllUsers = []; }

  // Peupler le filtre par site (extrait du username: <service>_demo_<site>)
  const siteSel = document.getElementById('msg-compose-site');
  if (siteSel) {
    // Extraire les "sites" depuis les usernames: tout ce qui est après _demo_ ou le display_name
    const sites = new Set();
    _msgAllUsers.forEach(u => {
      // Grouper par : présence dans allSites (hostname match) ou tag dans username
      const match = u.username.match(/_demo_(.+)$/) || u.username.match(/_(.{3,12})$/);
      if (match) sites.add(match[1]);
      // Aussi ajouter via display_name — "X — Site Y" → "Site Y"
      const dn = u.display_name || '';
      const dnMatch = dn.match(/— (.+)$/);
      if (dnMatch) sites.add(dnMatch[1].substring(0, 30));
    });
    // Aussi ajouter les sites de l'instance courante
    allSites.forEach(s => sites.add(s.nom));

    // v2309-hotfix — Filtrage au périmètre exercice si applicable
    let sortedSites = [...sites].sort();
    if (_msgSitesExercice && _msgSitesExercice.length) {
      const upperSites = new Set(_msgSitesExercice);
      sortedSites = sortedSites.filter(s => {
        const u = s.toUpperCase();
        // Match souple : le sigle exo doit apparaître dans le nom de site
        return [...upperSites].some(sig => u.includes(sig) || sig.includes(u.substring(0,6)));
      });
    }

    siteSel.innerHTML = '<option value="">— Tous les sites —</option>' +
      sortedSites.map(s => `<option value="${s}">${s}</option>`).join('');
    if (prefillSite) siteSel.value = prefillSite;
  }

  msgFilterUsers(prefillUserId);
  const m = document.getElementById('msg-modal-compose');
  if (m) m.style.display = 'flex';
}

function msgFilterUsers(prefillId) {
  const site = document.getElementById('msg-compose-site')?.value || '';
  const sel = document.getElementById('msg-compose-dest');
  if (!sel) return;
  
  let filtered = _msgAllUsers;
  if (site) {
    filtered = _msgAllUsers.filter(u => {
      const tag = site.toLowerCase().replace(/[^a-z0-9]/g, '_').substring(0, 14);
      return u.username.includes(tag) || 
             u.username.includes(site.toLowerCase().substring(0,8)) ||
             (u.display_name || '').toLowerCase().includes(site.toLowerCase().substring(0, 12));
    });
  }
  
  // Option inter-GHT via collecteur (si fédération active)
  let interGHTopts = '';
  if (_fedStatus?.ready && _fedStatus?.collecteur_url) {
    const autresGHTs = _annInterGHT.filter(e => e.ght !== (_fedStatus?.etablissement || ''));
    interGHTopts = '<optgroup label="━━ Inter-GHT (via supervision) ━━">' +
      '<option value="INTERGHT:TOUS">📢 Diffuser à tous les GHTs</option>' +
      autresGHTs.map(e =>
        `<option value="INTERGHT:${e.ght}">${e.ght} — ${e.ght_nom||e.ght}</option>`
      ).join('') +
      '</optgroup>';
  }
  
  sel.innerHTML = interGHTopts + (filtered.length
    ? filtered.map(u => `<option value="${u.id}">${u.display_name || u.username}</option>`).join('')
    : '<option value="">Aucun correspondant local</option>');
  
  if (prefillId) sel.value = prefillId;
}

function msgCloseCompose() {
  const m = document.getElementById('msg-modal-compose');
  if (m) m.style.display = 'none';
}

async function msgSend() {
  const destVal = document.getElementById('msg-compose-dest')?.value || '';
  const sujet   = document.getElementById('msg-compose-sujet')?.value?.trim() || '';
  const contenu = document.getElementById('msg-compose-body')?.value?.trim() || '';
  if (!destVal) { toast('Sélectionnez un destinataire', 'err'); return; }
  if (!contenu) { toast('Le message est vide', 'err'); return; }

  // Envoi inter-GHT via collecteur
  if (destVal.startsWith('INTERGHT:')) {
    const sigle = destVal.replace('INTERGHT:', '');
    const destinataire = sigle === 'TOUS' ? 'TOUS' : sigle;
    // Charger _fedStatus si pas encore disponible (ex: onglet Inter-GHT jamais ouvert)
    if (!_fedStatus) await loadFedStatus();
    const collBase = (_fedStatus?.collecteur_url || '').replace('/api/push', '');
    if (!collBase) { toast('Supervision non configurée', 'err'); return; }
    const token = _fedStatus?.token || '';
    if (!token) { toast('Token fédération manquant — vérifier config.js', 'err'); return; }
    try {
      const r = await fetch(collBase + '/api/messages', {
        method: 'POST',
        headers: { 'Authorization': 'Bearer ' + token, 'Content-Type': 'application/json' },
        body: JSON.stringify({
          destinataire,
          sujet,
          contenu,
          expediteur_nom: currentUser?.display_name || currentUser?.username || 'SCRIBE'
        })
      });
      if (r.ok) {
        toast('Message inter-GHT envoyé ✓', 'ok');
        msgCloseCompose();
      } else {
        toast('Erreur envoi inter-GHT (' + r.status + ')', 'err');
      }
    } catch(e) { toast('Erreur réseau collecteur', 'err'); }
    return;
  }

  // Envoi local
  const destId = parseInt(destVal);
  if (!destId || isNaN(destId)) { toast('Sélectionnez un destinataire', 'err'); return; }
  try {
    const r = await apiFetch('/api/v1/messagerie', { method:'POST', headers: authHeaders(), body: JSON.stringify({ destinataire_id: destId, sujet, contenu }) });
    if (!r.ok) { const d = await r.json().catch(()=>{}); toast(d?.detail || 'Erreur envoi', 'err'); return; }
    toast('✓ Message envoyé', 'ok');
    msgCloseCompose();
    const msgTabBtn = document.getElementById('tab-btn-messagerie');
    if (msgTabBtn) openTab('tab-messagerie', msgTabBtn);
    setTimeout(() => switchMsgBoite('envoi', document.getElementById('msg-tab-envoi')), 150);
  } catch(e) { toast('Erreur réseau', 'err'); }
}

// v2309-hotfix — Répondre à un message (interne ou externe).
// Distinction : si le nom de l'expéditeur ne correspond à aucun user
// interne (cas d'un message externe injecté via broadcast-externe :
// CHU Grenoble, ARS, CERT Santé, SAMU...), on ne peut pas répondre
// directement à cet émetteur (il n'existe pas en tant que compte).
// Dans ce cas, on ouvre le compose en indiquant que la réponse sera
// vue par l'équipe de crise locale et on pré-remplit le sujet avec
// "Re: ...". L'utilisateur choisit ensuite le destinataire interne
// à qui transmettre sa réponse (admin/directeur de crise).
function msgReply(id, nom) {
  msgOpenCompose().then(() => {
    const sujetEl = document.getElementById('msg-compose-sujet');
    const bodyEl  = document.getElementById('msg-compose-body');
    if (sujetEl) sujetEl.value = 'Re: ' + (nom ? 'message de ' + nom : 'votre message');
    // Pré-remplir le corps avec un contexte clair pour l'animateur/joueur
    // si l'émetteur est un acteur externe identifié (ARS/CERT/SAMU/CHU/...)
    const externes = ['ARS','CERT','SAMU','CHU','CH ','CELLULE','PRÉFET','ANSSI','MINISTÈRE'];
    const isExterne = nom && externes.some(e => nom.toUpperCase().includes(e));
    if (isExterne && bodyEl && !bodyEl.value) {
      bodyEl.value =
        `[Réponse destinée à ${nom} — sera vue par la cellule de crise pour validation avant envoi effectif]\n\n`;
    }
    // Signaler visuellement dans le modal que c'est une réponse externe
    const hint = document.getElementById('msg-compose-externe-hint');
    if (hint) {
      if (isExterne) {
        hint.style.display = 'block';
        hint.innerHTML = '💡 <strong>Message externe</strong> — Le destinataire d\'origine (' +
          (nom || 'acteur externe') + ') n\'est pas un compte SCRIBE. ' +
          'Sélectionnez un collègue interne à qui transmettre votre projet de réponse ' +
          'pour validation avant envoi par canal officiel (mail, téléphone, fax).';
      } else {
        hint.style.display = 'none';
      }
    }
  });
}

async function msgPollBadge() {
  if (!authToken) return;
  try {
    const r = await apiFetch('/api/v1/messagerie/non-lus', { headers: authHeaders() });
    if (!r.ok) return;
    const d = await r.json();
    const badge = document.getElementById('msg-badge');
    if (badge) { if (d.count > 0) { badge.textContent = d.count; badge.style.display = 'inline'; } else { badge.style.display = 'none'; } }
  } catch(e) {}
}

// Poll badge toutes les 30s
setInterval(msgPollBadge, 30000);

// Patch openTab pour charger messagerie/inter-ght

// ═══════════════════════════════════════════════════════════════

let _ightMode = 'demandes';
let _reponseCurrentDemId = null;

function switchIGHT(mode, btn) {
  _ightMode = mode;
  document.querySelectorAll('.ight-tab-btn').forEach(b => {
    b.style.background = 'transparent'; b.style.borderColor = 'transparent'; b.style.color = 'var(--muted)';
  });
  if (btn) { btn.style.background = 'var(--surface2)'; btn.style.borderColor = 'var(--border2)'; btn.style.color = 'var(--text)'; }
  const declPane = document.getElementById('ight-decl-pane');
  const demPane  = document.getElementById('ight-dem-pane');
  const msgsPane = document.getElementById('ight-msgs-pane');
  const newBtn   = document.getElementById('ight-btn-new');
  if (declPane) declPane.style.display = 'none';
  if (demPane)  demPane.style.display  = 'none';
  if (msgsPane) msgsPane.style.display = 'none';
  if (mode === 'demandes') {
    if (demPane)  demPane.style.display  = 'block';
    if (newBtn)   { newBtn.style.display=''; newBtn.textContent = '+ Nouvelle demande'; newBtn.style.background = '#7c3aed'; }
    ightLoadDem();
  } else if (mode === 'messages') {
    if (msgsPane) msgsPane.style.display = 'flex';
    if (newBtn)   newBtn.style.display = 'none';
    ightLoadMsgsCollecteur();
  }
}

(function patchOpenTabV14() {
  const _prev = openTab;
  openTab = function(id, btn) {
    _prev(id, btn);
    if (id === 'tab-messagerie') { msgLoad(); msgPollBadge(); }
    if (id === 'tab-declarations') {
      // Toujours ouvrir sur les demandes (déclarations de situation supprimées)
      const demBtn = document.getElementById('ight-tab-dem');
      switchIGHT('demandes', demBtn);
      setTimeout(ightLoadDem, authToken ? 0 : 500);
    }
  };
})();

// ═══════════════════════════════════════════════════════════════
// SCRIBE v2.3.65 — INTER-GHT / DÉCLARATIONS

async function ightOpenNew() {
  if (_ightMode === 'declarations') {
    ['decl-site','decl-uf','decl-desc'].forEach(id => { const el = document.getElementById(id); if (el) el.value = ''; });
    const m = document.getElementById('ight-modal-decl');
    if (m) m.style.display = 'flex';
  } else {
    // Réinitialiser les champs libres
    ['dem-uf','dem-desc'].forEach(id => { const el = document.getElementById(id); if (el) el.value = ''; });
    // Charger _fedStatus et annuaire si pas encore disponibles
    if (!_fedStatus) await loadFedStatus();
    if (!_annInterGHT.length) await loadAnnuaireMessagerie();
    // Pré-remplir émetteur depuis config (readonly)
    const em = document.getElementById('dem-emetteur');
    if (em) em.value = (window.SCRIBE_CONFIG?.etablissement?.sigle) || (_fedStatus?.etablissement) || '';
    // Peupler le select destinataire
    const destSel = document.getElementById('dem-destinataire');
    if (destSel) {
      const monSigle = em?.value || '';
      const autresGHTs = _annInterGHT.filter(e => e.ght !== monSigle);
      destSel.innerHTML = '<option value="">📢 Tous les GHTs</option>' +
        autresGHTs.map(e => `<option value="${e.ght}">${e.ght} — ${e.ght_nom||e.ght}</option>`).join('');
      destSel.value = '';
    }
    const m = document.getElementById('ight-modal-dem');
    if (m) m.style.display = 'flex';
  }
}

function ightCloseModal(id) {
  const m = document.getElementById(id);
  if (m) m.style.display = 'none';
}

async function ightLoadDecl() {
  const pane = document.getElementById('ight-decl-pane');
  if (!pane) return;
  if (!authToken) {
    // Race condition possible au chargement — retry après 800ms
    pane.innerHTML = '<div style="font-family:var(--mono);font-size:10px;color:var(--muted);padding:40px;text-align:center">⏳ Initialisation…</div>';
    setTimeout(() => {
      if (authToken) ightLoadDecl();
      else {
        const overlay = document.getElementById('login-overlay');
        if (overlay) { overlay.classList.remove('hidden'); overlay.style.display = 'flex'; }
      }
    }, 800);
    return;
  }
  pane.innerHTML = '<div style="font-family:var(--mono);font-size:10px;color:var(--muted);padding:40px;text-align:center">Chargement…</div>';
  try {
    // Charger les déclarations locales
    const r = await apiFetch('/api/v1/declarations');
    if (!r.ok) { pane.innerHTML = '<div style="font-family:var(--mono);font-size:10px;color:#f87171;padding:24px;text-align:center">Erreur ' + r.status + '</div>'; return; }
    const localDecls = await r.json();

    // Charger les déclarations des autres GHTs depuis le collecteur
    let remoteDecls = [];
    if (!_fedStatus) await loadFedStatus();
    if (_fedStatus?.ready && _fedStatus?.collecteur_url) {
      try {
        const collBase = _fedStatus.collecteur_url.replace('/api/push', '');
        const rc = await fetch(collBase + '/api/declarations', {
          headers: { 'Authorization': 'Bearer ' + (_fedStatus.token || '') }
        });
        if (rc.ok) {
          const allRemote = await rc.json();
          // Exclure les déclarations de notre propre établissement (déjà dans local)
          const monSigle = (SCRIBE_CONFIG?.etablissement?.sigle || '').toUpperCase();
          remoteDecls = allRemote.filter(d => d.ght_emetteur !== monSigle);
        }
      } catch(e) {}
    }

    // Fusionner : locales d'abord, puis inter-GHT
    const niveauLabel = { 1: '⚠️ Vigilance', 2: '🔶 Tension', 3: '🔴 Crise' };
    const niveauColor = { 1: '#d97706', 2: '#ea580c', 3: '#dc2626' };

    if (!localDecls.length && !remoteDecls.length) {
      pane.innerHTML = `<div style="display:flex;flex-direction:column;align-items:center;justify-content:center;padding:60px 20px;gap:10px;color:var(--muted)">
        <span style="font-size:32px;opacity:.3">📡</span>
        <span style="font-family:var(--mono);font-size:10px;letter-spacing:1px">Aucune déclaration de situation active</span>
        <span style="font-family:var(--mono);font-size:9px;opacity:.6">Cliquez "Nouvelle déclaration" pour signaler une situation au GHT</span>
      </div>`;
      return;
    }

    const renderDecl = (d, isRemote) => `
      <div style="background:var(--surface);border:1px solid var(--border2);border-left:3px solid ${niveauColor[d.niveau_tension]||'#6b7280'};border-radius:6px;padding:14px 16px;margin-bottom:10px;display:flex;align-items:flex-start;justify-content:space-between;gap:12px">
        <div style="flex:1">
          <div style="display:flex;align-items:center;gap:8px;margin-bottom:6px;flex-wrap:wrap">
            <span style="font-family:var(--mono);font-size:10px;font-weight:700;color:var(--text)">${(d.type_crise||'').toUpperCase().replace('_',' ')}</span>
            <span style="font-family:var(--mono);font-size:9px;padding:2px 7px;border-radius:10px;background:${niveauColor[d.niveau_tension]}22;color:${niveauColor[d.niveau_tension]}">${niveauLabel[d.niveau_tension]||''}</span>
            ${d.unite_fonct ? `<span style="font-family:var(--mono);font-size:9px;color:var(--muted)">— ${d.unite_fonct}</span>` : ''}
            ${isRemote ? `<span style="font-family:var(--mono);font-size:9px;padding:2px 7px;border-radius:10px;background:rgba(99,102,241,.15);color:#a5b4fc">📡 ${d.ght_nom||d.ght_emetteur}</span>` : ''}
          </div>
          <div style="font-family:var(--mono);font-size:9px;color:var(--muted);margin-bottom:6px">📍 ${d.site_id} · ${new Date(d.created_at).toLocaleString('fr-FR',{day:'2-digit',month:'2-digit',hour:'2-digit',minute:'2-digit'})} · par ${d.created_by||'—'}</div>
          ${d.description ? `<div style="font-size:12px;color:var(--text);line-height:1.5">${d.description}</div>` : ''}
        </div>
        ${!isRemote ? `<button onclick="ightCloturerDecl(${d.id})" style="font-family:var(--mono);font-size:9px;padding:4px 10px;background:var(--surface2);border:1px solid var(--border2);border-radius:4px;color:var(--muted);cursor:pointer;flex-shrink:0;white-space:nowrap">Clôturer</button>` : '<span style="font-family:var(--mono);font-size:8px;color:var(--muted);flex-shrink:0">inter-GHT</span>'}
      </div>`;

    pane.innerHTML =
      (localDecls.length ? `<div style="font-family:var(--mono);font-size:9px;color:var(--muted);margin-bottom:8px;padding:0 2px">— Déclarations de cet établissement</div>` : '') +
      localDecls.map(d => renderDecl(d, false)).join('') +
      (remoteDecls.length ? `<div style="font-family:var(--mono);font-size:9px;color:var(--muted);margin:12px 0 8px;padding:0 2px">— Déclarations des autres GHTs</div>` : '') +
      remoteDecls.map(d => renderDecl(d, true)).join('');

  } catch(e) { pane.innerHTML = '<div style="font-family:var(--mono);font-size:10px;color:#f87171;padding:24px;text-align:center">Erreur réseau</div>'; }
}

let _supervisionMsgReplyTo = null;

async function ightReplySuperMsg(msgId, expediteur) {
  _supervisionMsgReplyTo = msgId;
  const reponse = prompt('Votre réponse à ' + expediteur + ' :');
  if (!reponse || !reponse.trim()) return;
  if (!_fedStatus) await loadFedStatus();
  if (!_fedStatus?.ready || !_fedStatus?.collecteur_url) { toast('Supervision non disponible', 'warn'); return; }
  const collBase = _fedStatus.collecteur_url.replace('/api/push', '');
  const token    = _fedStatus.token || '';
  const monSigle = (SCRIBE_CONFIG?.etablissement?.sigle || '').toUpperCase();
  try {
    const r = await fetch(collBase + '/api/messages', {
      method: 'POST',
      headers: {'Authorization': 'Bearer ' + token, 'Content-Type': 'application/json'},
      body: JSON.stringify({
        destinataire: expediteur || 'TOUS',
        sujet: 'Re: message #' + msgId,
        contenu: '[' + monSigle + '] ' + reponse.trim(),
        expediteur_sigle: monSigle,
        reply_to: msgId
      })
    });
    if (r.ok) { toast('✓ Réponse envoyée', 'ok'); ightLoadMsgsCollecteur(); }
    else toast('Erreur envoi', 'err');
  } catch(e) { toast('Erreur réseau', 'err'); }
}

async function ightLoadMsgsCollecteur() {
  const list = document.getElementById('ight-msgs-list');
  if (!list) return;
  list.innerHTML = '<div style="font-family:var(--mono);font-size:10px;color:var(--muted);padding:24px;text-align:center">Chargement…</div>';

  // Charger le statut fédération
  await loadFedStatus();
  if (!_fedStatus?.ready || !_fedStatus?.collecteur_url) {
    list.innerHTML = '<div style="font-family:var(--mono);font-size:10px;color:var(--muted);padding:40px;text-align:center">⚠ Supervision non configurée ou non joignable</div>';
    return;
  }

  const collBase = _fedStatus.collecteur_url.replace('/api/push', '');
  const token = _fedStatus.token || (SCRIBE_CONFIG?.federation?.token || '');

  try {
    const r = await fetch(collBase + '/api/messages', {
      headers: { 'Authorization': 'Bearer ' + token }
    });
    if (!r.ok) {
      list.innerHTML = `<div style="font-family:var(--mono);font-size:10px;color:#f87171;padding:24px;text-align:center">Erreur ${r.status} — token de fédération non autorisé</div>`;
      return;
    }
    const data = await r.json();
    const msgs = [...(data.received || []), ...(data.sent || [])].sort((a,b) =>
      new Date(b.created_at) - new Date(a.created_at));

    if (!msgs.length) {
      list.innerHTML = '<div style="font-family:var(--mono);font-size:10px;color:var(--muted);padding:40px;text-align:center">Aucun message inter-GHT</div>';
      return;
    }

    // Grouper par thread (reply_to)
    let _selMsgId = null;
    const roots = msgs.filter(m => !m.reply_to);
    const replies = msgs.filter(m => m.reply_to);

    const renderSuperMsg = (m, isReply) => {
      const date = parseUTC(m.created_at).toLocaleString('fr-FR', {day:'2-digit',month:'2-digit',hour:'2-digit',minute:'2-digit'});
      const dest = m.destinataire === 'TOUS' ? '📢 Tous' : ('→ ' + m.destinataire);
      const who  = m.expediteur_nom || m.expediteur || '?';
      const ml   = isReply ? 'margin-left:20px;' : '';
      const bg   = isReply ? 'var(--surface2)' : 'var(--surface)';
      const bdr  = isReply ? '1px solid var(--border)' : '1px solid var(--border2)';
      return `<div style="${ml}background:${bg};border:${bdr};border-radius:6px;padding:10px 14px;margin-bottom:6px">
        <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:4px">
          <div style="display:flex;align-items:center;gap:8px">
            <span style="font-family:var(--mono);font-size:10px;font-weight:700;color:var(--text)">${who}</span>
            <span style="font-family:var(--mono);font-size:9px;color:var(--muted)">${dest}</span>
          </div>
          <div style="display:flex;align-items:center;gap:8px">
            <span style="font-family:var(--mono);font-size:8px;color:var(--muted)">${date}</span>
            ${!isReply ? `<button onclick="ightReplySuperMsg(${m.id},'${(m.expediteur||'').replace(/'/g,'')}')" style="font-family:var(--mono);font-size:8px;padding:2px 8px;background:transparent;border:1px solid var(--border2);border-radius:3px;color:var(--muted);cursor:pointer">↩ Répondre</button>` : ''}
          </div>
        </div>
        <div style="font-family:var(--mono);font-size:10px;font-weight:700;color:var(--muted2);margin-bottom:4px">${m.sujet || '(sans objet)'}</div>
        <div style="font-size:12px;color:var(--text);line-height:1.6;white-space:pre-wrap">${(m.contenu||'').replace(/</g,'&lt;')}</div>
      </div>`;
    };

    list.innerHTML = roots.map(m => {
      const threadReplies = replies.filter(r => r.reply_to === m.id);
      return renderSuperMsg(m, false) + threadReplies.map(r => renderSuperMsg(r, true)).join('');
    }).join('') || '<div style="font-family:var(--mono);font-size:10px;color:var(--muted);padding:40px;text-align:center">Aucun message</div>';
  } catch(e) {
    list.innerHTML = `<div style="font-family:var(--mono);font-size:10px;color:#f87171;padding:24px;text-align:center">Erreur réseau: ${e.message}</div>`;
  }
}

async function ightSubmitDecl() {
  const site  = (document.getElementById('decl-site')?.value||'').trim();
  const uf    = (document.getElementById('decl-uf')?.value||'').trim();
  const type  = document.getElementById('decl-type')?.value || 'sanitaire';
  const niv   = parseInt(document.getElementById('decl-niveau')?.value)||1;
  const desc  = (document.getElementById('decl-desc')?.value||'').trim();
  if (!site) { toast('Saisissez le site concerné', 'err'); return; }
  try {
    const r = await apiFetch('/api/v1/declarations', { method:'POST', headers: authHeaders(), body: JSON.stringify({ site_id: site, unite_fonct: uf||null, type_crise: type, niveau_tension: niv, description: desc }) });
    if (!r.ok) { const d = await r.json().catch(()=>{}); toast(d?.detail || 'Erreur', 'err'); return; }
    toast('Déclaration enregistrée ✓', 'ok');
    ightCloseModal('ight-modal-decl');
    ightLoadDecl();
  } catch(e) { toast('Erreur réseau', 'err'); }
}

async function ightCloturerDecl(id) {
  if (!confirm('Clôturer cette déclaration de situation ?')) return;
  try {
    await apiFetch(`/api/v1/declarations/${id}/cloturer`, { method:'PUT', headers: authHeaders() });
    toast('Déclaration clôturée', 'ok');
    ightLoadDecl();
  } catch(e) { toast('Erreur réseau', 'err'); }
}

let _ightDemandes = [];  // cache des demandes inter-GHT pour retrouver l'émetteur

async function ightLoadDem() {
  const pane = document.getElementById('ight-dem-pane');
  if (!pane) return;
  if (!authToken) {
    // Race condition possible au chargement — retry après 800ms
    pane.innerHTML = '<div style="font-family:var(--mono);font-size:10px;color:var(--muted);padding:40px;text-align:center">⏳ Initialisation…</div>';
    setTimeout(() => {
      if (authToken) ightLoadDem();
      else {
        // Vraiment pas connecté — afficher la mire
        const overlay = document.getElementById('login-overlay');
        if (overlay) { overlay.classList.remove('hidden'); overlay.style.display = 'flex'; }
      }
    }, 800);
    return;
  }
  pane.innerHTML = '<div style="font-family:var(--mono);font-size:10px;color:var(--muted);padding:40px;text-align:center">Chargement…</div>';
  try {
    // Charger les demandes locales
    const r = await apiFetch('/api/v1/interght/demandes');
    if (!r.ok) { pane.innerHTML = '<div style="font-family:var(--mono);font-size:10px;color:#f87171;padding:24px;text-align:center">Erreur ' + r.status + '</div>'; return; }
    const localDems = await r.json();
    _ightDemandes = [...localDems];  // cache pour retrouver l'émetteur au reply

    // Charger les demandes des autres GHTs depuis le collecteur
    let remoteDems = [];
    if (!_fedStatus) await loadFedStatus();
    if (_fedStatus?.ready && _fedStatus?.collecteur_url) {
      try {
        const collBase = _fedStatus.collecteur_url.replace('/api/push', '');
        const rc = await fetch(collBase + '/api/demandes', {
          headers: { 'Authorization': 'Bearer ' + (_fedStatus.token || '') }
        });
        if (rc.ok) {
          const allRemote = await rc.json();
          const monSigle = (SCRIBE_CONFIG?.etablissement?.sigle || _fedStatus?.etablissement || '').toUpperCase();
          // Garder les demandes qui nous sont destinées (tous ou notre sigle) et pas les nôtres
          remoteDems = allRemote.filter(d =>
            d.ght_emetteur !== monSigle &&
            (!d.ght_destinataire || d.ght_destinataire === monSigle || d.ght_destinataire === '')
          );
          // Enrichir les localDems avec la réponse du collecteur (si la demande a été répondue)
          localDems.forEach(ld => {
            const match = allRemote.find(rd => rd.id === ld.id || (rd.ght_emetteur === monSigle && rd.description === ld.description));
            if (match && match.reponse && !ld.reponse) {
              ld.reponse = match.reponse;
              ld.statut = match.statut;
            }
          });
        }
      } catch(e) {}
    }

    // Badge inter-GHT
    const _nonTraites = remoteDems.filter(d => d.statut !== 'traite').length;
    const _ightBadge = document.getElementById('ight-badge');
    if (_ightBadge) { _ightBadge.textContent = _nonTraites||''; _ightBadge.style.display = _nonTraites > 0 ? 'inline' : 'none'; }

    const statutColor = { en_attente:'#d97706', transmis:'#2563eb', recu:'#7c3aed', traite:'#16a34a' };
    const statutLabel = { en_attente:'En attente', transmis:'Transmis', recu:'Reçu', traite:'Traité' };

    if (!localDems.length && !remoteDems.length) {
      pane.innerHTML = `<div style="display:flex;flex-direction:column;align-items:center;justify-content:center;padding:60px 20px;gap:10px;color:var(--muted)">
        <span style="font-size:32px;opacity:.3">📤</span>
        <span style="font-family:var(--mono);font-size:10px;letter-spacing:1px">Aucune demande inter-GHT</span>
        <span style="font-family:var(--mono);font-size:9px;opacity:.6">Cliquez "Nouvelle demande" pour solliciter un autre établissement</span>
      </div>`;
      return;
    }

    const renderDem = (d, isRemote) => `
      <div style="background:var(--surface);border:1px solid var(--border2);${isRemote ? 'border-left:3px solid #7c3aed;' : ''}border-radius:6px;padding:14px 16px;margin-bottom:10px">
        <div style="display:flex;align-items:flex-start;justify-content:space-between;gap:12px">
          <div style="flex:1">
            <div style="display:flex;align-items:center;gap:8px;margin-bottom:5px;flex-wrap:wrap">
              <span style="font-family:var(--mono);font-size:10px;font-weight:700;color:var(--text)">${(d.type_situation||'').toUpperCase().replace('_',' ')}</span>
              ${d.unite_concernee ? `<span style="font-family:var(--mono);font-size:9px;color:var(--muted)">— ${d.unite_concernee}</span>` : ''}
              <span style="font-family:var(--mono);font-size:9px;padding:2px 7px;border-radius:10px;background:${statutColor[d.statut]||'#6b7280'}22;color:${statutColor[d.statut]||'#9ca3af'}">${statutLabel[d.statut]||d.statut}</span>
              ${isRemote ? `<span style="font-family:var(--mono);font-size:9px;padding:2px 7px;border-radius:10px;background:rgba(124,58,237,.15);color:#a78bfa">📡 ${d.ght_nom||d.ght_emetteur}</span>` : ''}
            </div>
            <div style="font-family:var(--mono);font-size:9px;color:var(--muted);margin-bottom:6px">${d.ght_emetteur} → ${d.ght_destinataire||'Tous GHT'} · ${new Date(d.created_at).toLocaleString('fr-FR',{day:'2-digit',month:'2-digit',hour:'2-digit',minute:'2-digit'})}</div>
            <div style="font-size:12px;color:var(--text);line-height:1.5;margin-bottom:6px">${d.description}</div>
            ${d.reponse ? `<div style="padding:8px 10px;background:rgba(22,163,74,.1);border-left:3px solid #16a34a;border-radius:4px;font-size:11px;color:#4ade80"><div style="font-family:var(--mono);font-size:9px;opacity:.7;margin-bottom:2px">✓ Réponse${d.repondu_par?' de <b>'+d.repondu_par+'</b>':''} :</div>${d.reponse}</div>` : ''}
          </div>
          ${!isRemote && d.statut !== 'traite' ? `<button onclick="ightRepondre(${d.id})" style="font-family:var(--mono);font-size:9px;padding:4px 10px;background:rgba(124,58,237,.15);border:1px solid #7c3aed;border-radius:4px;color:#a78bfa;cursor:pointer;flex-shrink:0;white-space:nowrap">Répondre</button>` : ''}
          ${isRemote && d.statut !== 'traite' ? `<button onclick="ightRepondreId(${d.id})" style="font-family:var(--mono);font-size:9px;padding:4px 10px;background:rgba(124,58,237,.15);border:1px solid #7c3aed;border-radius:4px;color:#a78bfa;cursor:pointer;flex-shrink:0;white-space:nowrap">Répondre</button>` : ''}
          ${isRemote && d.statut === 'traite' ? '<span style="font-family:var(--mono);font-size:8px;color:#4ade80;flex-shrink:0">✓ traité</span>' : ''}
        </div>
      </div>`;

    pane.innerHTML =
      (localDems.length ? `<div style="font-family:var(--mono);font-size:9px;color:var(--muted);margin-bottom:8px;padding:0 2px">— Demandes envoyées par cet établissement</div>` : '') +
      localDems.map(d => renderDem(d, false)).join('') +
      (remoteDems.length ? `<div style="font-family:var(--mono);font-size:9px;color:var(--muted);margin:12px 0 8px;padding:0 2px">— Demandes reçues des autres GHTs</div>` : '') +
      remoteDems.map(d => renderDem(d, true)).join('');

  } catch(e) { pane.innerHTML = '<div style="font-family:var(--mono);font-size:10px;color:#f87171;padding:24px;text-align:center">Erreur réseau</div>'; }
}

async function ightSubmitDem() {
  const type  = document.getElementById('dem-type')?.value || 'sanitaire';
  const uf    = (document.getElementById('dem-uf')?.value||'').trim();
  const emet  = (document.getElementById('dem-emetteur')?.value||'').trim();
  const dest  = (document.getElementById('dem-destinataire')?.value||'').trim();
  const desc  = (document.getElementById('dem-desc')?.value||'').trim();
  if (!desc)  { toast('La description est obligatoire', 'err'); return; }
  try {
    const r = await apiFetch('/api/v1/interght/demandes', { method:'POST', headers: authHeaders(), body: JSON.stringify({ type_situation: type, unite_concernee: uf||null, description: desc, ght_emetteur: emet, ght_destinataire: dest||null }) });
    if (!r.ok) { const d = await r.json().catch(()=>{}); toast(d?.detail || 'Erreur', 'err'); return; }
    toast('Demande envoyée ✓', 'ok');
    ightCloseModal('ight-modal-dem');
    ightLoadDem();
  } catch(e) { toast('Erreur réseau', 'err'); }
}

async function ightRepondreId(id) {
  // Répondre à une demande distante reçue du collecteur
  // La demande n'est PAS en DB locale (elle vient d'une autre instance) → pas d'appel local
  const reponse = prompt('Votre réponse à cette demande inter-GHT :');
  if (!reponse || !reponse.trim()) return;
  const monSigle = (SCRIBE_CONFIG?.etablissement?.sigle||'').toUpperCase();

  // 2. Envoyer la réponse au collecteur avec le sigle destinataire = l'émetteur d'origine
  if (!_fedStatus) await loadFedStatus();
  if (_fedStatus?.ready && _fedStatus?.collecteur_url) {
    const collBase = _fedStatus.collecteur_url.replace('/api/push','');
    const token = _fedStatus.token || '';
    // Récupérer le sigle émetteur depuis la liste des demandes
    const dem = (_ightDemandes || []).find(d => d.id === id);
    const emetteur = dem?.ght_emetteur || '';
    try {
      // PATCH la demande dans le collecteur → l'émetteur (8000) verra la réponse au prochain refresh
      await fetch(collBase + '/api/demandes/' + id, {
        method: 'PATCH',
        headers: {'Authorization':'Bearer '+token,'Content-Type':'application/json'},
        body: JSON.stringify({reponse: reponse.trim(), statut: 'traite'})
      });
      // Aussi envoyer un message inter-GHT pour notification
      if (emetteur) {
        await fetch(collBase + '/api/messages', {
          method: 'POST',
          headers: {'Authorization':'Bearer '+token,'Content-Type':'application/json'},
          body: JSON.stringify({
            destinataire: emetteur,
            sujet: 'Réponse demande #' + id,
            contenu: '[' + monSigle + '] ' + reponse.trim(),
            expediteur_sigle: monSigle
          })
        });
      }
    } catch(e) {}
  }

  toast('✓ Réponse transmise à ' + ((_ightDemandes||[]).find(d=>d.id===id)?.ght_emetteur||'émetteur'), 'ok');
  ightLoadDem();
}

async function ightRepondre(id) {
  const reponse = prompt('Votre réponse à cette demande :');
  if (!reponse || !reponse.trim()) return;
  try {
    const r = await apiFetch(`/api/v1/interght/demandes/${id}/repondre`, { method:'POST', headers: authHeaders(), body: JSON.stringify({ reponse: reponse.trim(), statut: 'traite' }) });
    if (!r.ok) { toast('Erreur', 'err'); return; }
    toast('Réponse envoyée ✓', 'ok');
    ightLoadDem();
  } catch(e) { toast('Erreur réseau', 'err'); }
}

// Fermeture modaux inter-GHT en cliquant dehors
['ight-modal-decl','ight-modal-dem','msg-modal-compose'].forEach(id => {
  const el = document.getElementById(id);
  if (!el) return;
  el.addEventListener('click', function(e) { if (e.target === this) this.style.display = 'none'; });
});

// ═══════════════════════════════════════════════════════════════
// SCRIBE v2.3.65 — CHANGEMENT MDP FORCÉ + IMPORT COMPTES
// ═══════════════════════════════════════════════════════════════

function openForcedPasswordChange() {
  ['fpw-old','fpw-new','fpw-confirm'].forEach(id => {
    const el = document.getElementById(id); if (el) el.value = '';
  });
  const errEl = document.getElementById('fpw-err');
  if (errEl) { errEl.style.display = 'none'; errEl.textContent = ''; }
  const m = document.getElementById('modal-forced-pw');
  if (m) m.style.display = 'flex';
}

async function submitForcedPw() {
  const ancien  = document.getElementById('fpw-old')?.value || '';
  const nouveau = document.getElementById('fpw-new')?.value || '';
  const confirm = document.getElementById('fpw-confirm')?.value || '';
  const errEl   = document.getElementById('fpw-err');
  errEl.style.display = 'none';

  if (nouveau.length < 8) {
    errEl.textContent = 'Le mot de passe doit contenir au moins 8 caractères.';
    errEl.style.display = 'block'; return;
  }
  if (nouveau !== confirm) {
    errEl.textContent = 'Les mots de passe ne correspondent pas.';
    errEl.style.display = 'block'; return;
  }
  if (ancien === nouveau) {
    errEl.textContent = 'Le nouveau mot de passe doit être différent du mot de passe temporaire.';
    errEl.style.display = 'block'; return;
  }

  try {
    const r = await apiFetch('/api/v1/auth/change-password', {
      method: 'POST', headers: authHeaders(),
      body: JSON.stringify({ ancien_mdp: ancien, nouveau_mdp: nouveau })
    });
    if (!r.ok) {
      const d = await r.json().catch(() => ({}));
      errEl.textContent = d.detail || 'Mot de passe actuel incorrect.';
      errEl.style.display = 'block'; return;
    }
    // Succès
    const m = document.getElementById('modal-forced-pw');
    if (m) m.style.display = 'none';
    if (currentUser) currentUser.must_change_password = false;
    toast('Mot de passe mis à jour ✓ Bienvenue !', 'ok');
  } catch(e) {
    errEl.textContent = 'Erreur réseau. Réessayez.';
    errEl.style.display = 'block';
  }
}

async function importComptes() {
  const fileInput = document.getElementById('import-file');
  const resultEl  = document.getElementById('import-result');
  if (!fileInput || !fileInput.files || !fileInput.files[0]) {
    toast('Sélectionnez un fichier Excel', 'err'); return;
  }
  const formData = new FormData();
  formData.append('file', fileInput.files[0]);
  resultEl.style.display = 'none';
  resultEl.textContent = 'Import en cours…';
  resultEl.style.display = 'block';

  try {
    const r = await apiFetch('/api/v1/auth/import-comptes', {
      method: 'POST',
      headers: { 'Authorization': 'Bearer ' + authToken },
      body: formData
    });
    const d = await r.json().catch(() => ({}));
    if (!r.ok) {
      resultEl.style.borderColor = '#f87171';
      resultEl.style.color = '#f87171';
      resultEl.textContent = d.detail || 'Erreur import';
      return;
    }
    resultEl.style.borderColor = '#4ade80';
    resultEl.style.color = '#4ade80';
    resultEl.textContent = d.message + (d.errors && d.errors.length ? ' | Avertissements: ' + d.errors.join(' ; ') : '');
    toast(d.message, 'ok');
    loadUsers(); // Rafraîchir la liste
  } catch(e) {
    resultEl.style.borderColor = '#f87171';
    resultEl.style.color = '#f87171';
    resultEl.textContent = 'Erreur réseau';
  }
}

// Vérifier must_change_password au chargement (token persisté)
(function checkMustChangePwOnLoad() {
  if (currentUser && currentUser.must_change_password) {
    setTimeout(() => openForcedPasswordChange(), 800);
  }
})();

/* ════════════════════════════════════════════════════════════ */

// ── v2184 : conversion rapport Albert → actions SCRIBE ────────────────────
// Parse le rapport généré par Albert (sections numérotées Markdown), extrait :
//   - Section "ACTIONS PRIORITAIRES"  → tâches Kanban (cochées par défaut)
//   - Section "POINTS DE VIGILANCE"   → tâches Kanban à priorité moyenne
//   - Items contenant "transfert/brancardage/transport" → bons de brancardage
//
// IMPORTANT v2184 : on ne crée PLUS de décisions de cellule depuis l'IA.
// La cellule doit refléter uniquement les vraies décisions des joueurs,
// sinon impossible de juger leur travail à la fin de l'exercice.

function albertConvertToActions() {
  // Conservé pour compat : convertit le rapport global affiché dans gap-body
  var body = document.getElementById('gap-body');
  if (!body || !body.textContent || body.textContent.trim().length < 30) {
    if (typeof toast === 'function') toast('Aucun rapport à convertir', 'err');
    return;
  }
  _acvOpenFromText(body.textContent, null);
}

// v2184 — Lance la conversion depuis le modal d'avis incident
function incAlbertConvertToActions() {
  var modal = document.getElementById('inc-albert-modal');
  if (!modal) return;
  var txt = modal.dataset.recommandation || '';
  var incId = parseInt(modal.dataset.incidentId || '0') || null;
  if (!txt || txt.length < 30) {
    if (typeof toast === 'function') toast('Aucun rapport à convertir', 'err');
    return;
  }
  closeIncidentAlbertModal();
  _acvOpenFromText(txt, incId);
}

function _acvOpenFromText(txt, incidentIdContext) {
  var parsed = _acvParseAlbertReport(txt);
  // Détecter les brancardages dans toutes les sections d'actions
  parsed.brancardages = _acvDetectBrancardages(
    (parsed.actions || []).concat(parsed.vigilance || [])
  );
  if (!parsed.actions.length && !parsed.vigilance.length && !parsed.brancardages.length) {
    if (typeof toast === 'function') toast('Rapport non structuré (aucune action détectée)', 'err');
    return;
  }
  acvShow(parsed, incidentIdContext);
}

function _acvParseAlbertReport(txt) {
  var sections = { actions: [], vigilance: [] };
  var clean = txt.replace(/\*\*/g, '');
  var actMatch = clean.match(/(?:^|\n)\s*\d+\.\s*ACTIONS?\s+PRIORITAIRES?\s*\n([\s\S]+?)(?=\n\s*\d+\.\s*[A-ZÉÈÊÀÂÔÛÎÏÇ]|$)/i);
  var vigMatch = clean.match(/(?:^|\n)\s*\d+\.\s*POINTS?\s+DE\s+VIGILANCE\s*\n([\s\S]+?)(?=\n\s*\d+\.\s*[A-ZÉÈÊÀÂÔÛÎÏÇ]|$)/i);
  if (actMatch) sections.actions = _acvExtractItems(actMatch[1]);
  if (vigMatch) sections.vigilance = _acvExtractItems(vigMatch[1]);
  // Si aucune section formelle détectée, prendre tous les items markdown du rapport
  if (!sections.actions.length && !sections.vigilance.length) {
    sections.actions = _acvExtractItems(clean);
  }
  return sections;
}

function _acvExtractItems(blockText) {
  var lines = blockText.split('\n');
  var items = [];
  var current = null;
  lines.forEach(function(line) {
    var m = line.match(/^\s*[-•*]\s+(.+)$/);
    if (m) {
      if (current) items.push(current.trim());
      current = m[1];
    } else if (current !== null && line.trim()) {
      current += ' ' + line.trim();
    }
  });
  if (current) items.push(current.trim());
  return items.map(function(it) {
    return it.replace(/\*\*/g, '').replace(/\s+/g, ' ').trim().substring(0, 240);
  }).filter(function(it) { return it.length > 5; });
}

// v2184 — détecte les actions qui ressemblent à un brancardage / transport
// patient et les présente comme bons de brancardage pré-remplis.
function _acvDetectBrancardages(items) {
  var KEYWORDS = /\b(transport|brancard|transf[eé]r(?:t|er|ement)?\b|d[ée]placer\s+(?:le|la)\s+patient|amener|conduire\s+(?:le|la)\s+patient)/i;
  return items.filter(function(it) { return KEYWORDS.test(it); }).map(function(it) {
    // Tenter d'extraire service origine / destination via heuristique
    var dest = '';
    var orig = '';
    var matchDest = it.match(/vers\s+(?:le|la|l['])\s*([A-Za-zÀ-ÿ\s\-']+?)(?:[\s,.;]|$)/i);
    if (matchDest) dest = matchDest[1].trim().substring(0, 50);
    var matchOrig = it.match(/depuis\s+(?:le|la|l['])\s*([A-Za-zÀ-ÿ\s\-']+?)(?:[\s,.;]|$)/i);
    if (matchOrig) orig = matchOrig[1].trim().substring(0, 50);
    return { texte: it, origine: orig, destination: dest };
  });
}

var _acvCurrent = null;
var _acvIncidentContext = null;

function acvShow(parsed, incidentIdContext) {
  _acvCurrent = parsed;
  _acvIncidentContext = incidentIdContext || null;
  var body = document.getElementById('acv-body');
  var html = '';

  // Bandeau de contexte si incident
  if (_acvIncidentContext) {
    var inc = (typeof allIncidents !== 'undefined') ? allIncidents.find(function(i) { return i.id === _acvIncidentContext; }) : null;
    var label = inc ? ('#' + inc.id + ' — ' + (inc.fait||'').substring(0,80)) : ('Incident #' + _acvIncidentContext);
    html += '<div style="padding:8px 12px;background:rgba(124,58,237,.1);border-left:3px solid #7c3aed;border-radius:4px;margin-bottom:14px;font-size:11px"><b>Contexte :</b> ' + _acvEsc(label) + '<br><span style="font-size:10px;color:var(--muted)">Les tâches créées seront liées à cet incident.</span></div>';
  }

  // Brancardages détectés
  if (parsed.brancardages && parsed.brancardages.length) {
    html += '<div style="margin-bottom:18px"><div style="font-family:var(--mono);font-size:10px;font-weight:700;color:#06b6d4;letter-spacing:1px;margin-bottom:8px;border-bottom:1px solid var(--border);padding-bottom:5px">🚑 BONS DE BRANCARDAGE (' + parsed.brancardages.length + ')</div>';
    parsed.brancardages.forEach(function(b, i) {
      html += '<div style="background:var(--surface2);border:1px solid var(--border);border-radius:5px;padding:8px;margin-bottom:6px">' +
        '<label style="display:flex;align-items:flex-start;gap:8px;cursor:pointer;margin-bottom:6px">' +
          '<input type="checkbox" class="acv-cb-brc" data-idx="' + i + '" checked style="margin-top:3px;flex-shrink:0;accent-color:#06b6d4">' +
          '<div style="flex:1;font-size:11px;color:var(--text)">' + _acvEsc(b.texte) + '</div>' +
        '</label>' +
        '<div style="display:grid;grid-template-columns:1fr 80px 1fr 80px;gap:6px;font-family:var(--mono);font-size:10px;margin-top:4px;padding-left:24px">' +
          '<input type="text" class="acv-brc-orig" data-idx="' + i + '" placeholder="Service origine" value="' + _acvEsc(b.origine) + '" style="padding:4px 6px;background:var(--surface);border:1px solid var(--border);border-radius:3px;color:var(--text);font-size:10px">' +
          '<input type="text" class="acv-brc-ch-orig" data-idx="' + i + '" placeholder="Ch." style="padding:4px 6px;background:var(--surface);border:1px solid var(--border);border-radius:3px;color:var(--text);font-size:10px">' +
          '<input type="text" class="acv-brc-dest" data-idx="' + i + '" placeholder="Service destination" value="' + _acvEsc(b.destination) + '" style="padding:4px 6px;background:var(--surface);border:1px solid var(--border);border-radius:3px;color:var(--text);font-size:10px">' +
          '<input type="text" class="acv-brc-ch-dest" data-idx="' + i + '" placeholder="Ch." style="padding:4px 6px;background:var(--surface);border:1px solid var(--border);border-radius:3px;color:var(--text);font-size:10px">' +
        '</div>' +
      '</div>';
    });
    html += '</div>';
  }

  // Actions prioritaires → tâches Kanban (priorité haute)
  if (parsed.actions && parsed.actions.length) {
    html += '<div style="margin-bottom:18px"><div style="font-family:var(--mono);font-size:10px;font-weight:700;color:#a78bfa;letter-spacing:1px;margin-bottom:8px;border-bottom:1px solid var(--border);padding-bottom:5px">📋 TÂCHES KANBAN — PRIORITÉ HAUTE (' + parsed.actions.length + ')</div>';
    parsed.actions.forEach(function(item, i) {
      var titre = item.split(/\s*[:.]\s+/)[0].substring(0, 70);
      html += '<div style="background:var(--surface2);border:1px solid var(--border);border-radius:5px;padding:8px;margin-bottom:5px">' +
        '<label style="display:flex;align-items:flex-start;gap:8px;cursor:pointer;margin-bottom:6px">' +
          '<input type="checkbox" class="acv-cb-action" data-idx="' + i + '" checked style="margin-top:3px;flex-shrink:0;accent-color:#a78bfa">' +
          '<input type="text" class="acv-action-titre" data-idx="' + i + '" value="' + _acvEsc(titre) + '" style="flex:1;padding:5px 8px;background:var(--surface);border:1px solid var(--border);border-radius:3px;color:var(--text);font-size:11px;font-weight:600">' +
        '</label>' +
        '<textarea class="acv-action-desc" data-idx="' + i + '" rows="2" style="width:100%;padding:5px 8px;background:var(--surface);border:1px solid var(--border);border-radius:3px;color:var(--muted2);font-size:11px;font-family:inherit;line-height:1.4;resize:vertical">' + _acvEsc(item) + '</textarea>' +
      '</div>';
    });
    html += '</div>';
  }

  // Vigilance → tâches Kanban (priorité moyenne, pas décisions)
  if (parsed.vigilance && parsed.vigilance.length) {
    html += '<div><div style="font-family:var(--mono);font-size:10px;font-weight:700;color:#f59e0b;letter-spacing:1px;margin-bottom:8px;border-bottom:1px solid var(--border);padding-bottom:5px">⚠ POINTS DE VIGILANCE → TÂCHES KANBAN PRIORITÉ MOYENNE (' + parsed.vigilance.length + ')</div>';
    parsed.vigilance.forEach(function(item, i) {
      var titre = item.split(/\s*[:.]\s+/)[0].substring(0, 70);
      html += '<div style="background:var(--surface2);border:1px solid var(--border);border-radius:5px;padding:8px;margin-bottom:5px">' +
        '<label style="display:flex;align-items:flex-start;gap:8px;cursor:pointer;margin-bottom:6px">' +
          '<input type="checkbox" class="acv-cb-vig" data-idx="' + i + '" checked style="margin-top:3px;flex-shrink:0;accent-color:#f59e0b">' +
          '<input type="text" class="acv-vig-titre" data-idx="' + i + '" value="' + _acvEsc(titre) + '" style="flex:1;padding:5px 8px;background:var(--surface);border:1px solid var(--border);border-radius:3px;color:var(--text);font-size:11px;font-weight:600">' +
        '</label>' +
        '<textarea class="acv-vig-desc" data-idx="' + i + '" rows="2" style="width:100%;padding:5px 8px;background:var(--surface);border:1px solid var(--border);border-radius:3px;color:var(--muted2);font-size:11px;font-family:inherit;line-height:1.4;resize:vertical">' + _acvEsc(item) + '</textarea>' +
      '</div>';
    });
    html += '</div>';
  }

  // v2185 — Section "Action sur-mesure" : permet au joueur d'ajouter des
  // tâches Kanban qui ne sont pas issues du parsing, par exemple pour
  // compléter une recommandation manquante ou adapter au contexte local.
  html += '<div style="margin-top:14px;padding-top:14px;border-top:1px dashed var(--border)">' +
    '<div style="font-family:var(--mono);font-size:10px;font-weight:700;color:#22d3ee;letter-spacing:1px;margin-bottom:8px">➕ ACTIONS SUR-MESURE (optionnel)</div>' +
    '<div id="acv-custom-list"></div>' +
    '<button type="button" onclick="acvAddCustom()" style="font-family:var(--mono);font-size:10px;padding:5px 12px;background:transparent;border:1px dashed var(--border2);border-radius:4px;color:var(--muted2);cursor:pointer;margin-top:4px">+ Ajouter une action</button>' +
  '</div>';

  body.innerHTML = html;
  _acvUpdateSummary();
  document.querySelectorAll('#acv-body input[type=checkbox]').forEach(function(cb) {
    cb.addEventListener('change', _acvUpdateSummary);
  });
  document.getElementById('acv-modal').style.display = 'flex';
}

// v2185 — Ajout d'une action sur-mesure dans le modal de conversion
var _acvCustomCounter = 0;
function acvAddCustom() {
  var list = document.getElementById('acv-custom-list');
  if (!list) return;
  var i = _acvCustomCounter++;
  var div = document.createElement('div');
  div.style.cssText = 'background:var(--surface2);border:1px solid var(--border);border-radius:5px;padding:8px;margin-bottom:5px;position:relative';
  div.innerHTML =
    '<label style="display:flex;align-items:flex-start;gap:8px;cursor:pointer;margin-bottom:6px">' +
      '<input type="checkbox" class="acv-cb-custom" data-cidx="' + i + '" checked style="margin-top:3px;flex-shrink:0;accent-color:#22d3ee">' +
      '<input type="text" class="acv-custom-titre" data-cidx="' + i + '" placeholder="Titre de l\'action (ex: Appeler la préfecture)" style="flex:1;padding:5px 8px;background:var(--surface);border:1px solid var(--border);border-radius:3px;color:var(--text);font-size:11px;font-weight:600">' +
      '<select class="acv-custom-prio" data-cidx="' + i + '" style="padding:5px 6px;background:var(--surface);border:1px solid var(--border);border-radius:3px;color:var(--text);font-size:10px;font-family:var(--mono)">' +
        '<option value="3">HAUTE</option><option value="2" selected>MOYENNE</option><option value="1">BASSE</option>' +
      '</select>' +
      '<button type="button" onclick="acvRemoveCustom(' + i + ')" style="background:transparent;border:none;color:var(--muted);cursor:pointer;font-size:14px" title="Supprimer">✕</button>' +
    '</label>' +
    '<textarea class="acv-custom-desc" data-cidx="' + i + '" rows="2" placeholder="Description détaillée (optionnel)" style="width:100%;padding:5px 8px;background:var(--surface);border:1px solid var(--border);border-radius:3px;color:var(--muted2);font-size:11px;font-family:inherit;line-height:1.4;resize:vertical"></textarea>';
  div.dataset.cidx = String(i);
  list.appendChild(div);
  // Hook le checkbox pour update résumé
  div.querySelector('.acv-cb-custom').addEventListener('change', _acvUpdateSummary);
  div.querySelector('.acv-custom-titre').focus();
  _acvUpdateSummary();
}

function acvRemoveCustom(i) {
  var list = document.getElementById('acv-custom-list');
  if (!list) return;
  var el = list.querySelector('[data-cidx="' + i + '"]');
  if (el) el.remove();
  _acvUpdateSummary();
}

function _acvUpdateSummary() {
  var na = document.querySelectorAll('#acv-body .acv-cb-action:checked').length;
  var nv = document.querySelectorAll('#acv-body .acv-cb-vig:checked').length;
  var nb = document.querySelectorAll('#acv-body .acv-cb-brc:checked').length;
  var nc = document.querySelectorAll('#acv-body .acv-cb-custom:checked').length;
  var summary = [];
  if (nb) summary.push(nb + ' brancardage(s)');
  if (na) summary.push(na + ' tâche(s) priorité haute');
  if (nv) summary.push(nv + ' priorité moyenne');
  if (nc) summary.push(nc + ' sur-mesure');
  document.getElementById('acv-summary').textContent = summary.join(' + ') || 'Rien à créer';
  document.getElementById('acv-btn-create').disabled = (na + nv + nb + nc === 0);
}

function _acvEsc(s) {
  return String(s||'').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;')
    .replace(/"/g,'&quot;');
}

function acvClose() {
  document.getElementById('acv-modal').style.display = 'none';
  _acvCurrent = null;
  _acvIncidentContext = null;
}

async function acvCreateAll() {
  if (!_acvCurrent) return;
  var btn = document.getElementById('acv-btn-create');
  btn.disabled = true; btn.textContent = '⏳ Création en cours…';

  var nOk = 0, nErr = 0;
  var incCtx = _acvIncidentContext;

  // Brancardages → POST /api/v1/brancardage/missions
  var brcCbs = document.querySelectorAll('#acv-body .acv-cb-brc:checked');
  for (var i = 0; i < brcCbs.length; i++) {
    var idx = parseInt(brcCbs[i].dataset.idx);
    var b = _acvCurrent.brancardages[idx];
    var orig = (document.querySelector('.acv-brc-orig[data-idx="' + idx + '"]') || {}).value || b.origine || '';
    var chOrig = (document.querySelector('.acv-brc-ch-orig[data-idx="' + idx + '"]') || {}).value || '';
    var dest = (document.querySelector('.acv-brc-dest[data-idx="' + idx + '"]') || {}).value || b.destination || '';
    var chDest = (document.querySelector('.acv-brc-ch-dest[data-idx="' + idx + '"]') || {}).value || '';
    try {
      var rb = await apiFetch('/api/v1/brancardage/missions', {
        method: 'POST', headers: {'Content-Type':'application/json'},
        body: JSON.stringify({
          ref_type: 'autre',
          ref_value: '[Recommandation IA]',
          priorite: 'normale',
          type_mission: 'interne',
          uf_origine: orig, chambre_origine: chOrig,
          uf_destination: dest, chambre_destination: chDest,
          motif: b.texte.substring(0, 200),
          commentaire: 'Créé depuis l\'analyse IA' + (incCtx ? ' incident #' + incCtx : '')
        })
      });
      if (rb && rb.ok) nOk++; else nErr++;
    } catch(e) { nErr++; }
  }

  // Actions prioritaires → tâches Kanban priorité 3 (haute)
  var actCbs = document.querySelectorAll('#acv-body .acv-cb-action:checked');
  for (var j = 0; j < actCbs.length; j++) {
    var idx2 = parseInt(actCbs[j].dataset.idx);
    var titre = (document.querySelector('.acv-action-titre[data-idx="' + idx2 + '"]') || {}).value
                || _acvCurrent.actions[idx2].split(/\s*[:.]\s+/)[0];
    var desc = (document.querySelector('.acv-action-desc[data-idx="' + idx2 + '"]') || {}).value
                || _acvCurrent.actions[idx2];
    try {
      var rt = await apiFetch('/api/v1/tasks/', {
        method: 'POST', headers: {'Content-Type':'application/json'},
        body: JSON.stringify({
          titre: titre.substring(0, 80), description: desc,
          priorite: 3, colonne: 'BACKLOG',
          incident_id: incCtx
        })
      });
      if (rt && rt.ok) nOk++; else nErr++;
    } catch(e) { nErr++; }
  }

  // Vigilance → tâches Kanban priorité 2 (moyenne)
  var vigCbs = document.querySelectorAll('#acv-body .acv-cb-vig:checked');
  for (var k = 0; k < vigCbs.length; k++) {
    var idx3 = parseInt(vigCbs[k].dataset.idx);
    var titreV = (document.querySelector('.acv-vig-titre[data-idx="' + idx3 + '"]') || {}).value
                 || _acvCurrent.vigilance[idx3].split(/\s*[:.]\s+/)[0];
    var descV = (document.querySelector('.acv-vig-desc[data-idx="' + idx3 + '"]') || {}).value
                || _acvCurrent.vigilance[idx3];
    try {
      var rt2 = await apiFetch('/api/v1/tasks/', {
        method: 'POST', headers: {'Content-Type':'application/json'},
        body: JSON.stringify({
          titre: titreV.substring(0, 80), description: descV,
          priorite: 2, colonne: 'BACKLOG',
          incident_id: incCtx
        })
      });
      if (rt2 && rt2.ok) nOk++; else nErr++;
    } catch(e) { nErr++; }
  }

  // v2185 — Actions sur-mesure ajoutées manuellement
  var customCbs = document.querySelectorAll('#acv-body .acv-cb-custom:checked');
  for (var m = 0; m < customCbs.length; m++) {
    var ci = customCbs[m].dataset.cidx;
    var titreC = (document.querySelector('.acv-custom-titre[data-cidx="' + ci + '"]') || {}).value || '';
    var descC = (document.querySelector('.acv-custom-desc[data-cidx="' + ci + '"]') || {}).value || '';
    var prioC = parseInt((document.querySelector('.acv-custom-prio[data-cidx="' + ci + '"]') || {}).value || '2') || 2;
    titreC = titreC.trim();
    if (!titreC) continue;  // titre obligatoire
    try {
      var rtC = await apiFetch('/api/v1/tasks/', {
        method: 'POST', headers: {'Content-Type':'application/json'},
        body: JSON.stringify({
          titre: titreC.substring(0, 80), description: descC,
          priorite: prioC, colonne: 'BACKLOG',
          incident_id: incCtx
        })
      });
      if (rtC && rtC.ok) nOk++; else nErr++;
    } catch(e) { nErr++; }
  }

  btn.disabled = false; btn.textContent = '✓ Créer les actions';
  acvClose();
  if (typeof toast === 'function') {
    if (nErr === 0) toast('✓ ' + nOk + ' action(s) créée(s)', 'ok');
    else toast(nOk + ' OK · ' + nErr + ' erreur(s)', 'warn');
  }
  try { if (typeof refreshAll === 'function') refreshAll(); } catch(e) {}
}

/* ════════════════════════════════════════════════════════════ */

(function() {
  // Liste standard — rôles métiers hospitaliers fréquents pendant une crise
  var ACTEURS_STANDARDS = [
    "Brancardier 1", "Brancardier 2", "Brancardier 3",
    "IDE maternité", "IDE bloc opératoire", "IDE urgences", "IDE réanimation",
    "Sage-femme coordinatrice", "Sage-femme de garde",
    "Cadre de santé", "Cadre de garde administratif",
    "Médecin de garde", "Médecin réanimateur", "Médecin chef de service",
    "Interne de garde",
    "Anesthésiste de garde", "IADE de garde",
    "Pharmacien de garde", "Préparateur pharmacie",
    "Biomédical de garde", "Technicien biomédical",
    "Agent DSI", "Technicien support DSI", "RSSI",
    "Directeur de garde", "Directeur de crise",
    "Standardiste", "Secrétaire médicale",
    "Régulateur SAMU 15", "Ambulancier SMUR",
    "Agent de sécurité", "Agent logistique"
  ];

  function populateDatalist() {
    var dl = document.getElementById('acteurs-generiques');
    if (!dl) return;
    var items = ACTEURS_STANDARDS.slice();

    // En mode exercice : compléter avec les joueurs du scénario si la
    // config les expose (SCRIBE_CONFIG.exercice_joueurs fourni par
    // config.js régénéré, sinon reste vide — la liste standard suffit).
    try {
      if (typeof SCRIBE_CONFIG !== 'undefined'
          && SCRIBE_CONFIG.exercice_mode
          && Array.isArray(SCRIBE_CONFIG.exercice_joueurs)) {
        SCRIBE_CONFIG.exercice_joueurs.forEach(function(j) {
          var nom = j.display_name || j.username;
          var role = j.role_exercice || '';
          if (nom) items.unshift(role ? nom + ' — ' + role : nom);
        });
      }
    } catch(e) {}

    // Dédoublonnage en conservant l'ordre
    var seen = {};
    var uniq = items.filter(function(x) { if(seen[x]) return false; seen[x]=1; return true; });
    dl.innerHTML = uniq.map(function(x) { return '<option value="'+
      x.replace(/"/g,'&quot;') +'">'; }).join('');
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', populateDatalist);
  } else {
    populateDatalist();
  }
})();