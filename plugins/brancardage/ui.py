"""
plugins/brancardage/ui.py — Interface HTML brancardage SCRIBE v2.2.6
"""
from fastapi import APIRouter
from fastapi.responses import HTMLResponse

ui_router = APIRouter()

BRC_HTML = r"""<!DOCTYPE html>
<html lang="fr">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Brancardage</title>
<style>
:root{--blue:#003189;--red:#e1000f;--green:#16a34a;--yellow:#d97706;--purple:#7c3aed;
  --bg:#f8fafc;--surface:#fff;--surface2:#f1f5f9;--surface3:#e2e8f0;--border:#e2e8f0;
  --text:#0f172a;--muted:#64748b;--mono:'Share Tech Mono',monospace}
*{box-sizing:border-box;margin:0;padding:0}
body{font-family:system-ui,sans-serif;background:var(--bg);color:var(--text);height:100vh;display:flex;flex-direction:column;overflow:hidden}
#hdr{background:var(--blue);color:#fff;padding:8px 14px;display:flex;align-items:center;gap:10px;flex-shrink:0;min-height:44px}
#hdr h1{font-family:var(--mono);font-size:12px;font-weight:700;letter-spacing:1px}
.stat{font-family:var(--mono);font-size:9px;padding:2px 9px;border-radius:10px;background:rgba(255,255,255,.15)}
.stat.urg{background:rgba(225,0,15,.4)}
#tabs{display:flex;gap:0;padding:0 14px;background:var(--surface);border-bottom:2px solid var(--border);flex-shrink:0}
.tab{font-family:var(--mono);font-size:10px;padding:8px 14px;background:transparent;border:none;cursor:pointer;color:var(--muted);border-bottom:2px solid transparent;margin-bottom:-2px}
.tab.active{color:var(--blue);border-bottom-color:var(--blue);font-weight:700}
#body{flex:1;overflow:auto;padding:14px}
.grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(290px,1fr));gap:10px}
.card{background:var(--surface);border:1px solid var(--border);border-radius:7px;overflow:hidden}
.card.P1{border-left:4px solid var(--red)}
.card.P2{border-left:4px solid var(--blue)}
.card.P3{border-left:4px solid var(--muted)}
.card.EN_COURS{border-left:4px solid var(--yellow)}
.card-hdr{padding:8px 12px;background:var(--surface2);display:flex;align-items:center;gap:6px;font-family:var(--mono);font-size:9px;color:var(--muted)}
.badge{font-family:var(--mono);font-size:8px;padding:2px 6px;border-radius:8px;flex-shrink:0}
.badge.P1{background:#fee2e2;color:var(--red)}
.badge.P2{background:#dbeafe;color:var(--blue)}
.badge.P3{background:#f1f5f9;color:var(--muted)}
.badge.EN_ATTENTE{background:#fef9c3;color:#a16207}
.badge.EN_COURS{background:#fff7ed;color:#c2410c}
.badge.TERMINE{background:#dcfce7;color:var(--green)}
.badge.ANNULE{background:#f1f5f9;color:var(--muted)}
.badge.AMB{background:#ede9fe;color:var(--purple)}
.card-body{padding:10px 12px}
.route{font-size:12px;font-weight:700;color:var(--text);margin-bottom:5px}
.route .etab{font-size:10px;color:var(--purple);font-weight:600}
.meta{font-size:10px;color:var(--muted);line-height:1.8}
.agent-badge{display:inline-block;padding:3px 8px;background:rgba(0,49,137,.08);border:1px solid rgba(0,49,137,.2);border-radius:12px;font-size:10px;color:var(--blue);margin-top:4px}
.card-btns{padding:6px 10px;border-top:1px solid var(--border);display:flex;gap:5px;flex-wrap:wrap}
.btn{font-family:var(--mono);font-size:9px;padding:4px 10px;border-radius:4px;cursor:pointer;border:1px solid;transition:opacity .1s}
.btn:active{opacity:.7}
.btn-blue{background:var(--blue);color:#fff;border-color:var(--blue)}
.btn-green{background:var(--green);color:#fff;border-color:var(--green)}
.btn-red{background:rgba(225,0,15,.08);color:var(--red);border-color:var(--red)}
.btn-ghost{background:transparent;color:var(--muted);border-color:var(--border)}
.btn-purple{background:rgba(124,58,237,.1);color:var(--purple);border-color:var(--purple)}
.form{background:var(--surface);border:1px solid var(--border);border-radius:8px;padding:18px;max-width:700px}
.fg{display:grid;grid-template-columns:1fr 1fr;gap:10px}
.ff{display:flex;flex-direction:column;gap:3px}
.ff label{font-family:var(--mono);font-size:9px;color:var(--muted);text-transform:uppercase;letter-spacing:.5px}
.ff input,.ff select,.ff textarea{font-family:var(--mono);font-size:11px;padding:6px 8px;background:var(--surface2);border:1px solid var(--border);border-radius:4px;color:var(--text);width:100%}
.ff.full{grid-column:1/-1}
.fsep{grid-column:1/-1;font-family:var(--mono);font-size:8px;letter-spacing:2px;color:var(--muted);text-transform:uppercase;padding-top:10px;border-top:1px solid var(--border);margin-top:4px}
.ref-row{display:flex;gap:8px;align-items:flex-end}
.ref-row .ff:first-child{flex:0 0 130px}
.ref-row .ff:last-child{flex:1}
.jtable{width:100%;border-collapse:collapse;font-size:11px}
.jtable th{font-family:var(--mono);font-size:9px;text-align:left;padding:7px;background:var(--surface2);border-bottom:2px solid var(--border);color:var(--muted)}
.jtable td{padding:7px;border-bottom:1px solid var(--border);vertical-align:top}
#toast{position:fixed;bottom:16px;right:16px;font-family:var(--mono);font-size:11px;padding:9px 14px;border-radius:5px;display:none;z-index:9999;max-width:320px}
#toast.ok{background:#dcfce7;color:#15803d;border:1px solid #86efac}
#toast.err{background:#fee2e2;color:#dc2626;border:1px solid #fca5a5}
.modal{display:none;position:fixed;inset:0;background:rgba(0,0,0,.45);z-index:9000;align-items:center;justify-content:center}
.modal.open{display:flex}
.modal-box{background:var(--surface);border-radius:8px;padding:20px;width:360px;max-width:95vw}
.modal-title{font-family:var(--mono);font-size:11px;font-weight:700;margin-bottom:12px}
.empty{text-align:center;padding:50px 20px;color:var(--muted);font-family:var(--mono);font-size:10px}
.empty-icon{font-size:40px;margin-bottom:10px;opacity:.35}
.ext-badge{display:inline-flex;align-items:center;gap:4px;padding:2px 7px;background:#ede9fe;color:var(--purple);border-radius:10px;font-size:9px;font-family:var(--mono)}
</style>
</head>
<body>
<div id="hdr">
  <span>🛏</span>
  <h1>BRANCARDAGE</h1>
  <button class="btn btn-blue" onclick="showTab('new')" style="font-size:10px;margin-right:10px">+ Nouvelle demande</button>
  <span class="stat" id="s-actives">—</span>
  <span class="stat urg" id="s-urg" style="display:none">⚡ —</span>
  <span class="stat" id="s-cours" style="display:none">🚀 —</span>
  <div style="flex:1"></div>
  <button class="btn btn-ghost" onclick="loadAll()" style="font-size:10px;color:#fff;border-color:rgba(255,255,255,.3)">🔄</button>
</div>

<div id="tabs">
  <button class="tab active" id="t-wait"    onclick="showTab('wait')">⏳ En attente</button>
  <button class="tab"        id="t-running" onclick="showTab('running')">🚀 En cours</button>
  <button class="tab"        id="t-new"     onclick="showTab('new')">+ Nouvelle</button>
  <button class="tab"        id="t-journal" onclick="showTab('journal')">📋 Journal</button>
</div>

<div id="body">

<!-- En attente -->
<div id="p-wait">
  <div id="g-wait" class="grid"></div>
</div>

<!-- En cours -->
<div id="p-running" style="display:none">
  <div id="g-running" class="grid"></div>
</div>

<!-- Nouvelle demande -->
<div id="p-new" style="display:none">
  <div class="form">
    <div style="font-family:var(--mono);font-size:12px;font-weight:700;margin-bottom:14px">📋 Nouvelle demande</div>
    <div class="fg">
      <!-- Référence patient -->
      <div class="fsep">Référence patient</div>
      <div class="ff full">
        <label>Référence *</label>
        <div class="ref-row">
          <div class="ff">
            <label> </label>
            <select id="f-ref-type">
              <option value="REF">Réf. libre</option>
              <option value="IPP">IPP</option>
              <option value="NOM">Nom</option>
            </select>
          </div>
          <div class="ff" style="flex:1">
            <label> </label>
            <input type="text" id="f-ref" placeholder="ex: Ch.12A, 123456, Martin J.">
          </div>
        </div>
      </div>

      <!-- Transport -->
      <div class="fsep">Transport</div>
      <div class="ff">
        <label>Priorité *</label>
        <select id="f-prio">
          <option value="P1">⚡ P1 — Urgente</option>
          <option value="P2" selected>P2 — Normale</option>
          <option value="P3">P3 — Différable</option>
        </select>
      </div>
      <div class="ff">
        <label>Mode *</label>
        <select id="f-type" onchange="onTypeChange()">
          <option value="BRANCARD">🛏 Brancard</option>
          <option value="FAUTEUIL">🪑 Fauteuil roulant</option>
          <option value="LIT">🛌 Au lit</option>
          <option value="MARCHE">🚶 Marche assistée</option>
          <option value="AMBULANCE">🚑 Ambulance (externe)</option>
        </select>
      </div>
      <div class="ff">
        <label>UF / Service origine *</label>
        <select id="f-uf-orig"><option value="">— Sélectionner —</option></select>
      </div>
      <div class="ff">
        <label>Chambre départ</label>
        <input type="text" id="f-ch-dep" placeholder="ex: 214">
      </div>

      <!-- Destination interne -->
      <div id="dest-interne">
        <div class="fg" style="grid-template-columns:1fr 1fr;gap:10px;display:grid;grid-column:1/-1">
          <div class="ff">
            <label>UF / Service destination *</label>
            <select id="f-uf-dest"><option value="">— Sélectionner —</option></select>
          </div>
          <div class="ff">
            <label>Chambre arrivée</label>
            <input type="text" id="f-ch-arr" placeholder="ex: Radio 1">
          </div>
        </div>
      </div>

      <!-- Destination externe (AMBULANCE) -->
      <div id="dest-externe" style="display:none;grid-column:1/-1">
        <div class="fg" style="grid-template-columns:1fr 1fr;gap:10px;display:grid">
          <div class="ff">
            <label>Établissement destination *</label>
            <select id="f-etab-dest"><option value="">— Sélectionner —</option></select>
          </div>
          <div class="ff">
            <label>Service / UF destination</label>
            <input type="text" id="f-uf-dest-ext" placeholder="ex: Urgences (autre site)">
          </div>
        </div>
        <div style="margin-top:6px;padding:6px 10px;background:#ede9fe;border-radius:4px;font-size:10px;color:var(--purple);font-family:var(--mono)">
          🚑 Un transfert sera automatiquement créé dans le module Transferts SCRIBE.
        </div>
      </div>

      <div class="ff">
        <label>Motif</label>
        <input type="text" id="f-motif" placeholder="ex: Imagerie, Bloc, Consultation…">
      </div>
      <div class="ff">
        <label>Commentaire</label>
        <input type="text" id="f-comment" placeholder="…">
      </div>

      <!-- Options -->
      <div class="fsep">Options</div>
      <div class="ff">
        <label>Programmé ?</label>
        <select id="f-prog" onchange="toggleProg()">
          <option value="0">Non — dès que possible</option>
          <option value="1">Oui — heure prévue</option>
        </select>
      </div>
      <div class="ff" id="w-heure" style="display:none">
        <label>Heure prévue</label>
        <input type="time" id="f-heure">
      </div>
      <div class="ff">
        <label>Prévoir le retour ?</label>
        <select id="f-retour" onchange="toggleRetour()">
          <option value="0">Non</option>
          <option value="1">Oui</option>
        </select>
      </div>
      <div class="ff" id="w-retour" style="display:none">
        <label>Heure de retour</label>
        <input type="time" id="f-heure-retour">
      </div>
    </div>

    <div style="margin-top:14px;display:flex;gap:8px">
      <button class="btn btn-blue" onclick="submitMission()" style="font-size:11px;padding:7px 18px">✓ Créer la demande</button>
      <button class="btn btn-ghost" onclick="showTab('wait')" style="font-size:11px">Annuler</button>
    </div>
  </div>
</div>

<!-- Journal -->
<div id="p-journal" style="display:none">
  <div style="margin-bottom:10px;display:flex;gap:8px;align-items:center">
    <select id="j-filter" onchange="loadJournal()" style="font-family:var(--mono);font-size:10px;padding:4px 8px;background:var(--surface2);border:1px solid var(--border);border-radius:4px">
      <option value="all">Toutes</option>
      <option value="TERMINE">Terminées</option>
      <option value="ANNULE">Annulées</option>
      <option value="EN_ATTENTE">En attente</option>
      <option value="EN_COURS">En cours</option>
    </select>
    <button class="btn btn-ghost" onclick="loadJournal()" style="font-size:10px">🔄</button>
  </div>
  <div id="j-content"></div>
</div>

</div><!-- /#body -->

<!-- Modal prise en charge -->
<div class="modal" id="m-pec">
  <div class="modal-box">
    <div class="modal-title">✋ Prise en charge — Mission <span id="m-pec-id"></span></div>
    <div class="ff" style="margin-bottom:10px">
      <label>Nom du brancardier *</label>
      <input type="text" id="m-nom" placeholder="Prénom NOM" list="brc-acteurs" autocomplete="off">
    </div>
    <div class="ff" style="margin-bottom:14px">
      <label>Téléphone (optionnel)</label>
      <input type="tel" id="m-tel" placeholder="06 XX XX XX XX">
    </div>
    <div style="display:flex;gap:8px">
      <button class="btn btn-blue" onclick="confirmPec()">✓ Confirmer prise en charge</button>
      <button class="btn btn-ghost" onclick="closeModal('m-pec')">Annuler</button>
    </div>
  </div>
</div>

<!-- Modal terminée / commentaire -->
<div class="modal" id="m-action">
  <div class="modal-box">
    <div class="modal-title" id="m-action-title">Action</div>
    <div class="ff" style="margin-bottom:14px">
      <label>Commentaire (optionnel)</label>
      <input type="text" id="m-action-comment" placeholder="…">
    </div>
    <div style="display:flex;gap:8px">
      <button class="btn btn-green" id="m-action-confirm" onclick="confirmAction()">Confirmer</button>
      <button class="btn btn-ghost" onclick="closeModal('m-action')">Annuler</button>
    </div>
  </div>
</div>

<div id="toast"></div>

<script>
// ── Auth ──────────────────────────────────────────────────────────────────────
function tok() {
  try { return window.parent.localStorage.getItem('scribe_token') || localStorage.getItem('scribe_token') || ''; }
  catch(e) { return localStorage.getItem('scribe_token') || ''; }
}
async function api(url, opts={}) {
  if (!opts.headers) opts.headers = {};
  opts.headers['Authorization'] = 'Bearer ' + tok();
  if (opts.body && !opts.headers['Content-Type'])
    opts.headers['Content-Type'] = 'application/json';
  return fetch(url, opts);
}

// ── Données ───────────────────────────────────────────────────────────────────
let _missions = [];
let _ufs = [];
let _etabs = [];  // établissements distants (depuis collecteur/fédération)
let _pec_id = null;
let _action_id = null, _action_statut = null;

// ── Toast ─────────────────────────────────────────────────────────────────────
function toast(msg, type='ok') {
  const el = document.getElementById('toast');
  el.textContent = msg; el.className = type; el.style.display = 'block';
  clearTimeout(el._t); el._t = setTimeout(() => el.style.display='none', 3500);
}

// ── Navigation ─────────────────────────────────────────────────────────────────
function showTab(name) {
  ['wait','running','new','journal'].forEach(t => {
    document.getElementById('p-'+t).style.display = t===name?'block':'none';
    const b = document.getElementById('t-'+t);
    if (b) b.classList.toggle('active', t===name);
  });
  if (name==='wait'||name==='running') loadAll();
  if (name==='journal') loadJournal();
  if (name==='new') { loadUFs(); loadEtabs(); }
}

// ── UFs & Établissements ──────────────────────────────────────────────────────
async function loadUFs() {
  if (_ufs.length) { fillUFSelects(); return; }
  try {
    const r = await api('/api/v1/cartographie/ufs');
    if (r.ok) { const d = await r.json(); _ufs = Array.isArray(d) ? d : (d.ufs||[]); }
  } catch(e) {}
  if (!_ufs.length) {
    try {
      const r = await api('/api/v1/cartographie/sites');
      if (r.ok) { const s = await r.json(); _ufs = s.map(x => ({libelle:x.nom||x.name,code:x.id})); }
    } catch(e) {}
  }
  fillUFSelects();
}

function fillUFSelects() {
  const opts = _ufs.map(u => `<option value="${esc(u.libelle||u.code||u)}">${esc(u.libelle||u.code||u)}</option>`).join('');
  ['f-uf-orig','f-uf-dest'].forEach(id => {
    const el = document.getElementById(id);
    if (el) el.innerHTML = '<option value="">— Sélectionner —</option>' + opts;
  });
}

async function loadEtabs() {
  if (_etabs.length) { fillEtabSelect(); return; }
  try {
    const r = await api('/api/v1/federation/collecteur-sites');
    if (r.ok) {
      const data = await r.json();
      _etabs = data.map ? data : [];
    }
  } catch(e) {}
  // Fallback : charger depuis les établissements GHT fédérés
  if (!_etabs.length) {
    try {
      const r = await api('/api/v1/cartographie/ght-sites');
      if (r.ok) _etabs = await r.json();
    } catch(e) {}
  }
  fillEtabSelect();
}

function fillEtabSelect() {
  const sel = document.getElementById('f-etab-dest');
  if (!sel) return;
  const opts = _etabs.map(e => {
    const label = e.nom || e.name || e.sigle || e;
    const value = e.sigle || e.nom || e.name || e;
    return `<option value="${esc(value)}">${esc(label)}</option>`;
  }).join('');
  sel.innerHTML = '<option value="">— Établissement externe —</option>' + opts;
}

// ── Formulaire ────────────────────────────────────────────────────────────────
function onTypeChange() {
  const v = document.getElementById('f-type').value;
  const isAmb = v === 'AMBULANCE';
  document.getElementById('dest-interne').style.display = isAmb ? 'none' : 'contents';
  document.getElementById('dest-externe').style.display = isAmb ? 'block' : 'none';
}

function toggleProg() {
  document.getElementById('w-heure').style.display =
    document.getElementById('f-prog').value==='1' ? 'block' : 'none';
}
function toggleRetour() {
  document.getElementById('w-retour').style.display =
    document.getElementById('f-retour').value==='1' ? 'block' : 'none';
}

async function submitMission() {
  const ref  = document.getElementById('f-ref').value.trim();
  const type = document.getElementById('f-type').value;
  const isAmb = type === 'AMBULANCE';
  const orig = document.getElementById('f-uf-orig').value;
  const dest = isAmb ? (document.getElementById('f-uf-dest-ext').value||'') : document.getElementById('f-uf-dest').value;
  const etab = isAmb ? document.getElementById('f-etab-dest').value : null;

  if (!ref)  { toast('Référence patient requise', 'err'); return; }
  if (!orig) { toast('UF origine requise', 'err'); return; }
  if (!dest && !etab) { toast('Destination requise', 'err'); return; }

  const body = {
    ref_type:         document.getElementById('f-ref-type').value,
    ref_patient:      ref,
    uf_origine:       orig,
    chambre_depart:   document.getElementById('f-ch-dep').value||null,
    uf_destination:   dest || (etab||''),
    etab_destination: etab||null,
    chambre_arrivee:  isAmb ? null : (document.getElementById('f-ch-arr').value||null),
    type_transport:   type,
    priorite:         document.getElementById('f-prio').value,
    motif:            document.getElementById('f-motif').value||null,
    commentaire:      document.getElementById('f-comment').value||null,
    programmee:       parseInt(document.getElementById('f-prog').value),
    heure_prevue:     document.getElementById('f-heure').value||null,
    avec_retour:      parseInt(document.getElementById('f-retour').value),
    heure_retour:     document.getElementById('f-heure-retour').value||null,
  };

  try {
    const r = await api('/api/v1/brancardage/missions', {method:'POST', body:JSON.stringify(body)});
    if (r.ok) {
      const d = await r.json();
      toast('✓ Mission #'+d.id+' créée'+(body.avec_retour?' + retour':'')+(body.etab_destination?' — transfert créé':''), 'ok');
      ['f-ref','f-ch-dep','f-ch-arr','f-motif','f-comment','f-uf-dest-ext'].forEach(id => {
        const el = document.getElementById(id); if (el) el.value='';
      });
      document.getElementById('f-prio').value='P2';
      document.getElementById('f-type').value='BRANCARD'; onTypeChange();
      document.getElementById('f-prog').value='0'; toggleProg();
      document.getElementById('f-retour').value='0'; toggleRetour();
      showTab('wait');
    } else {
      const d = await r.json().catch(()=>({}));
      toast('Erreur : '+(d.detail||r.status), 'err');
    }
  } catch(e) { toast('Erreur réseau', 'err'); }
}

// ── Missions ──────────────────────────────────────────────────────────────────
async function loadAll() {
  try {
    const r = await api('/api/v1/brancardage/missions');
    if (!r.ok) return;
    _missions = await r.json();
    render();
    updateStats();
  } catch(e) {}
}

function updateStats() {
  const actives = _missions.filter(m => !['TERMINE','ANNULE'].includes(m.statut));
  const urg     = actives.filter(m => m.priorite==='P1');
  const cours   = actives.filter(m => m.statut==='EN_COURS');
  document.getElementById('s-actives').textContent = actives.length + ' actives';
  const su = document.getElementById('s-urg');
  su.style.display = urg.length ? 'inline-block' : 'none';
  su.textContent = '⚡ ' + urg.length + ' urgente(s)';
  const sc = document.getElementById('s-cours');
  sc.style.display = cours.length ? 'inline-block' : 'none';
  sc.textContent = '🚀 ' + cours.length + ' en cours';
}

function render() {
  const wait    = _missions.filter(m => m.statut==='EN_ATTENTE');
  const running = _missions.filter(m => m.statut==='EN_COURS');
  document.getElementById('g-wait').innerHTML = wait.length
    ? wait.map(renderCard).join('')
    : '<div class="empty"><div class="empty-icon">✅</div>Aucune mission en attente</div>';
  document.getElementById('g-running').innerHTML = running.length
    ? running.map(renderCard).join('')
    : '<div class="empty"><div class="empty-icon">🎉</div>Aucune mission en cours</div>';
}

function renderCard(m) {
  const dt = m.created_at ? parseUTCDate(m.created_at).toLocaleTimeString('fr-FR',{hour:'2-digit',minute:'2-digit'}) : '—';
  const isAmb = m.type_transport === 'AMBULANCE';
  const destLabel = m.etab_destination
    ? `<span class="etab">🏥 ${esc(m.etab_destination)}</span>`
    : esc(m.uf_destination);
  const refLabel = m.ref_type && m.ref_type !== 'REF'
    ? `<span style="font-family:var(--mono);font-size:9px;color:var(--muted)">[${m.ref_type}]</span> `
    : '';
  const agentHtml = m.agent_nom
    ? `<div class="agent-badge">👤 ${esc(m.agent_nom)}${m.agent_tel ? ' · ' + esc(m.agent_tel) : ''}</div>`
    : '';
  const btns = getBtns(m);
  return `<div class="card ${m.priorite} ${m.statut}">
    <div class="card-hdr">
      <span>#${m.id} · ${dt}</span>
      <span class="badge ${m.priorite}">${m.priorite_label}</span>
      <span class="badge ${m.statut}" style="margin-left:2px">${m.statut_label}</span>
      ${isAmb ? '<span class="badge AMB">🚑 Amb.</span>' : ''}
    </div>
    <div class="card-body">
      <div class="route">
        ${esc(m.uf_origine)}${m.chambre_depart?' <small style="font-weight:400">Ch.'+esc(m.chambre_depart)+'</small>':''}
        <span style="color:var(--blue);margin:0 5px">→</span>
        ${destLabel}
      </div>
      <div class="meta">
        🔖 ${refLabel}${esc(m.ref_patient)}<br>
        ${m.motif ? '📋 '+esc(m.motif)+'<br>' : ''}
        ${m.heure_prevue ? '🕐 Prévu : '+esc(m.heure_prevue)+'<br>' : ''}
        ${m.commentaire ? '💬 '+esc(m.commentaire)+'<br>' : ''}
        <span style="font-size:9px;color:var(--muted)">Par ${esc(m.demandeur_nom||'—')}</span>
      </div>
      ${agentHtml}
    </div>
    ${btns ? `<div class="card-btns">${btns}</div>` : ''}
  </div>`;
}

function getBtns(m) {
  const id = m.id;
  if (m.statut === 'EN_ATTENTE')
    return `<button class="btn btn-blue" onclick="openPec(${id})">✋ Prendre en charge</button>
            <button class="btn btn-red"  onclick="openAction(${id},'ANNULE','Annuler la mission')">✕</button>`;
  if (m.statut === 'EN_COURS')
    return `<button class="btn btn-green"  onclick="openAction(${id},'TERMINE','Confirmer arrivée')">✓ Arrivée confirmée</button>
            <button class="btn btn-red"    onclick="openAction(${id},'ANNULE','Annuler')">✕</button>`;
  return '';
}

// ── Modal prise en charge ─────────────────────────────────────────────────────
function openPec(id) {
  _pec_id = id;
  document.getElementById('m-pec-id').textContent = '#'+id;
  document.getElementById('m-nom').value = '';
  document.getElementById('m-tel').value = '';
  document.getElementById('m-pec').classList.add('open');
  setTimeout(() => document.getElementById('m-nom').focus(), 100);
}

async function confirmPec() {
  const nom = document.getElementById('m-nom').value.trim();
  const tel = document.getElementById('m-tel').value.trim();
  if (!nom) { toast('Nom du brancardier requis', 'err'); return; }
  closeModal('m-pec');
  try {
    const r = await api('/api/v1/brancardage/missions/'+_pec_id+'/prendre_en_charge', {
      method:'POST', body:JSON.stringify({agent_nom:nom, agent_tel:tel||null})
    });
    if (r.ok) { toast('✓ Mission prise en charge par '+nom, 'ok'); loadAll(); }
    else { const d=await r.json().catch(()=>({})); toast('Erreur : '+(d.detail||r.status), 'err'); }
  } catch(e) { toast('Erreur réseau', 'err'); }
}

// ── Modal action ──────────────────────────────────────────────────────────────
function openAction(id, statut, label) {
  _action_id=id; _action_statut=statut;
  document.getElementById('m-action-title').textContent = label + ' — #'+id;
  document.getElementById('m-action-comment').value = '';
  document.getElementById('m-action').classList.add('open');
}

async function confirmAction() {
  const comment = document.getElementById('m-action-comment').value;
  closeModal('m-action');
  try {
    const r = await api('/api/v1/brancardage/missions/'+_action_id, {
      method:'PATCH', body:JSON.stringify({statut:_action_statut, commentaire:comment})
    });
    if (r.ok) { toast('✓ Mission mise à jour', 'ok'); loadAll(); }
    else { const d=await r.json().catch(()=>({})); toast('Erreur : '+(d.detail||r.status), 'err'); }
  } catch(e) { toast('Erreur réseau', 'err'); }
}

function closeModal(id) { document.getElementById(id).classList.remove('open'); }

// ── Journal ───────────────────────────────────────────────────────────────────
async function loadJournal() {
  const filter = document.getElementById('j-filter').value;
  const el = document.getElementById('j-content');
  el.innerHTML = '<div class="empty"><div class="empty-icon" style="font-size:20px">⏳</div>Chargement…</div>';
  try {
    const r = await api('/api/v1/brancardage/missions/all?limit=200');
    if (!r.ok) { el.innerHTML='<div class="empty">Erreur</div>'; return; }
    let ms = await r.json();
    if (filter !== 'all') ms = ms.filter(m => m.statut===filter);
    if (!ms.length) { el.innerHTML='<div class="empty"><div class="empty-icon">📋</div>Aucune mission</div>'; return; }
    el.innerHTML = `<table class="jtable">
      <thead><tr>
        <th>#</th><th>Référence</th><th>Trajet</th>
        <th>Mode</th><th>Priorité</th><th>Statut</th>
        <th>Agent</th><th>Créée</th><th>Durée</th>
      </tr></thead>
      <tbody>${ms.map(m => {
        const dt = m.created_at ? parseUTCDate(m.created_at).toLocaleString('fr-FR',{day:'2-digit',month:'2-digit',hour:'2-digit',minute:'2-digit'}) : '—';
        const ref = (m.ref_type && m.ref_type!=='REF' ? '['+m.ref_type+'] ' : '') + (m.ref_patient||'—');
        const dest = m.etab_destination ? '🏥'+m.etab_destination+' / '+m.uf_destination : m.uf_destination;
        let dur = '—';
        if (m.prise_en_charge_at && m.termine_at) {
          const min = Math.round((new Date(m.termine_at+'Z')-new Date(m.prise_en_charge_at+'Z'))/60000);
          dur = min+'min';
        }
        return `<tr>
          <td style="font-family:var(--mono);font-size:9px">#${m.id}</td>
          <td style="font-size:10px">${esc(ref)}</td>
          <td style="font-size:10px">${esc(m.uf_origine)} → ${esc(dest)}</td>
          <td><span class="badge" style="background:var(--surface2);color:var(--muted)">${esc(m.type_transport)}</span></td>
          <td><span class="badge ${m.priorite}">${m.priorite_label}</span></td>
          <td><span class="badge ${m.statut}">${m.statut_label}</span></td>
          <td style="font-size:10px">${m.agent_nom ? esc(m.agent_nom)+(m.agent_tel?' · '+esc(m.agent_tel):'') : '—'}</td>
          <td style="font-family:var(--mono);font-size:9px">${dt}</td>
          <td style="font-family:var(--mono);font-size:10px">${dur}</td>
        </tr>`;
      }).join('')}</tbody></table>`;
  } catch(e) { el.innerHTML='<div class="empty">Erreur réseau</div>'; }
}

// ── Utilitaires ───────────────────────────────────────────────────────────────
function esc(s) { return String(s||'').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;'); }
function parseUTCDate(s) {
  if (!s) return new Date();
  if (s.includes('Z') || s.includes('+')) return new Date(s);
  return new Date(s.includes('T') ? s+'Z' : s.replace(' ','T')+'Z');
}

// ── Init ──────────────────────────────────────────────────────────────────────
window.addEventListener('load', async () => {
  await loadUFs();
  await loadAll();
  setInterval(loadAll, 30000);

// Exposer dans window
try{ window.tok=tok; }catch(e){}
try{ window.toast=toast; }catch(e){}
try{ window.showTab=showTab; }catch(e){}
try{ window.fillUFSelects=fillUFSelects; }catch(e){}
try{ window.fillEtabSelect=fillEtabSelect; }catch(e){}
try{ window.onTypeChange=onTypeChange; }catch(e){}
try{ window.toggleProg=toggleProg; }catch(e){}
try{ window.toggleRetour=toggleRetour; }catch(e){}
try{ window.updateStats=updateStats; }catch(e){}
try{ window.render=render; }catch(e){}
try{ window.renderCard=renderCard; }catch(e){}
try{ window.getBtns=getBtns; }catch(e){}
try{ window.openPec=openPec; }catch(e){}
try{ window.openAction=openAction; }catch(e){}
try{ window.closeModal=closeModal; }catch(e){}
try{ window.esc=esc; }catch(e){}
try{ window.parseUTCDate=parseUTCDate; }catch(e){}
});

// v2183 — Populer la datalist des acteurs génériques pour le champ brancardier
(function() {
  var ACTEURS = [
    "Brancardier 1", "Brancardier 2", "Brancardier 3",
    "Coursier 1", "Coursier 2",
    "Agent de service logistique",
    "IDE accompagnant", "IDE maternité", "IDE urgences"
  ];
  function populate() {
    var dl = document.getElementById('brc-acteurs');
    if (!dl) return;
    try {
      if (typeof SCRIBE_CONFIG !== 'undefined' && SCRIBE_CONFIG.exercice_mode) {
        // Mode exercice : le champ se suffit d'une liste standardisée
        dl.innerHTML = ACTEURS.map(function(x){ return '<option value="'+x+'">'; }).join('');
      } else {
        dl.innerHTML = ACTEURS.map(function(x){ return '<option value="'+x+'">'; }).join('');
      }
    } catch(e) {}
  }
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', populate);
  } else {
    populate();
  }
})();
</script>
<datalist id="brc-acteurs"></datalist>
</body>
</html>"""

@ui_router.get("/ui", response_class=HTMLResponse)
def brancardage_ui():
    return HTMLResponse(BRC_HTML)
