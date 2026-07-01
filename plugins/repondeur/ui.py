"""
plugins/repondeur/ui.py — Interface HTML du plugin `repondeur` (SCRIBE)
=======================================================================
Page autonome rendue dans une iframe (même origine → token + langue via le
localStorage parent). Charte « Suite numérique » : Bleu France #000091.

Onglet RÉPONDEUR : gestion des lignes d'information de crise (Twilio).
"""
import json
import pathlib

from fastapi import APIRouter
from fastapi.responses import HTMLResponse

ui_router = APIRouter()

_I18N = {}
try:
    _I18N = json.loads(
        (pathlib.Path(__file__).parent / "_i18n_data.json").read_text(encoding="utf-8"))
except Exception:
    _I18N = {"fr": {}, "en": {}}


_HTML = r"""<!DOCTYPE html>
<html lang="fr">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Répondeur</title>
<style>
  :root{ --bf:#000091; --rm:#e1000f; --bg:#f6f6f9; --card:#fff; --bd:#e5e5ec;
         --tx:#161616; --mu:#666; --ok:#18753c; --warn:#b34000; --mo:ui-monospace,Menlo,Consolas,monospace; }
  *{ box-sizing:border-box; }
  body{ margin:0; font-family:system-ui,-apple-system,"Segoe UI",Roboto,sans-serif;
        background:var(--bg); color:var(--tx); font-size:14px; }
  .wrap{ max-width:980px; margin:0 auto; padding:18px 16px 60px; }
  .head{ display:flex; align-items:center; justify-content:space-between; gap:12px; flex-wrap:wrap; margin-bottom:14px; }
  .h-l{ display:flex; align-items:baseline; gap:10px; }
  h1{ font-size:20px; margin:0; color:var(--bf); }
  .sub{ color:var(--mu); font-size:12px; }
  .pill{ font-size:11px; font-weight:700; padding:4px 10px; border-radius:20px; white-space:nowrap; }
  .pill.dev{ background:#fff4e5; color:var(--warn); }
  .pill.live{ background:#e8f5ee; color:var(--ok); }
  .ovh-stats{ margin:8px 0 0; font-size:13px; color:var(--muted); }
  .ovh-stats.live{ background:#e8edff; color:#000091; border:1px solid #cdcdf6; border-radius:8px; padding:8px 12px; font-size:14px; font-weight:500; }
  .ovh-stats.live b{ font-size:18px; font-weight:700; }
  .ovh-stats-src{ font-size:11px; color:#666; font-weight:400; }
  .vm-badge{ display:none; min-width:16px; height:16px; line-height:16px; padding:0 5px; margin-left:2px; font-size:10px; font-weight:700; color:#fff; background:#e1000f; border-radius:9px; text-align:center; }
  .btn{ border:1px solid var(--bf); background:var(--bf); color:#fff; font-weight:600;
        padding:8px 14px; border-radius:6px; cursor:pointer; font-size:13px; }
  .btn:hover{ background:#1a1aa8; }
  .btn.sec{ background:#fff; color:var(--bf); }
  .btn.sec:hover{ background:#f0f0fb; }
  .btn.ghost{ background:transparent; border-color:var(--bd); color:var(--tx); }
  .btn.danger{ background:#fff; color:var(--rm); border-color:var(--rm); }
  .btn.sm{ padding:5px 10px; font-size:12px; }
  .row{ display:flex; gap:8px; flex-wrap:wrap; align-items:center; }
  .card{ background:var(--card); border:1px solid var(--bd); border-radius:10px; padding:14px 16px; margin-bottom:12px; }
  .card:hover{ border-color:var(--bf); }
  .l-top{ display:flex; align-items:center; justify-content:space-between; gap:10px; flex-wrap:wrap; }
  .l-title{ font-weight:700; font-size:15px; }
  .num{ font-family:var(--mo); font-size:13px; color:var(--bf); }
  .tags{ display:flex; gap:5px; flex-wrap:wrap; margin:6px 0; }
  .tag{ font-size:10px; font-weight:700; background:#eef; color:var(--bf); padding:2px 7px; border-radius:10px; text-transform:uppercase; }
  .dot{ width:9px; height:9px; border-radius:50%; display:inline-block; margin-right:5px; }
  .dot.on{ background:var(--ok); } .dot.off{ background:#bbb; }
  .msg{ color:var(--mu); font-size:13px; margin-top:6px; white-space:pre-wrap; }
  .meta{ color:#999; font-size:11px; margin-top:8px; }
  .empty{ text-align:center; color:var(--mu); padding:46px 16px; }
  label{ display:block; font-size:12px; font-weight:600; color:var(--mu); margin:10px 0 4px; }
  input[type=text], textarea, select{ width:100%; padding:8px 10px; border:1px solid var(--bd);
        border-radius:6px; font-size:13px; font-family:inherit; background:#fff; }
  textarea{ min-height:110px; resize:vertical; }
  .modal-bg{ position:fixed; inset:0; background:rgba(0,0,0,.4); display:none; align-items:center;
        justify-content:center; padding:16px; z-index:50; }
  .modal-bg.show{ display:flex; }
  .modal{ background:#fff; border-radius:12px; max-width:560px; width:100%; max-height:90vh;
        overflow:auto; padding:20px; }
  .modal h2{ font-size:16px; color:var(--bf); margin:0 0 4px; }
  .modal .m-foot{ display:flex; gap:8px; justify-content:flex-end; margin-top:16px; flex-wrap:wrap; }
  .langtabs{ display:flex; gap:6px; flex-wrap:wrap; margin:8px 0; }
  .langtab{ font-size:12px; padding:5px 10px; border:1px solid var(--bd); border-radius:6px; cursor:pointer; background:#fff; }
  .langtab.act{ background:var(--bf); color:#fff; border-color:var(--bf); }
  .hint{ font-size:11px; color:var(--mu); margin-top:4px; }
  .toast{ position:fixed; bottom:18px; left:50%; transform:translateX(-50%);
        background:var(--tx); color:#fff; padding:10px 16px; border-radius:8px; font-size:13px;
        opacity:0; transition:opacity .2s; pointer-events:none; z-index:99; }
  .toast.show{ opacity:1; }
  .src{ font-size:10px; color:#999; }
  hr{ border:none; border-top:1px solid var(--bd); margin:14px 0; }
</style>
</head>
<body>
<div class="wrap">
  <div class="head">
    <div class="h-l">
      <h1 data-i18n="title">Répondeur</h1>
      <span class="sub" data-i18n="subtitle">Lignes d'information de crise</span>
    </div>
    <div class="row">
      <span id="status-pill" class="pill dev"></span>
      <button class="btn sec sm" id="btn-config" data-i18n="config">Configuration</button>
      <button class="btn sm" id="btn-new" data-i18n="new_line">Nouvelle ligne</button>
    </div>
  </div>
  <div id="lines"></div>
</div>

<!-- Modal ligne -->
<div class="modal-bg" id="m-line">
  <div class="modal">
    <h2 id="m-line-title" data-i18n="new_line">Nouvelle ligne</h2>
    <label data-i18n="label">Libellé</label>
    <input type="text" id="f-libelle" data-i18n-ph="label_ph">
    <label data-i18n="number">Numéro Twilio</label>
    <input type="text" id="f-numero" data-i18n-ph="number_ph">
    <div class="row" style="gap:14px">
      <div style="flex:1;min-width:140px">
        <label data-i18n="main_lang">Langue principale</label>
        <select id="f-mainlang"></select>
      </div>
      <div style="flex:1;min-width:140px">
        <label data-i18n="voice">Voix par défaut</label>
        <input type="text" id="f-voice" placeholder="alice / Polly.Lea">
      </div>
    </div>
    <label data-i18n="langs">Langues du serveur vocal</label>
    <div id="f-langs" class="langtabs"></div>
    <div class="row" style="margin-top:10px">
      <label style="margin:0"><input type="checkbox" id="f-actif"> <span data-i18n="active">Active</span></label>
    </div>
    <div class="m-foot">
      <button class="btn ghost" id="m-line-cancel" data-i18n="cancel">Annuler</button>
      <button class="btn" id="m-line-save" data-i18n="save">Enregistrer</button>
    </div>
  </div>
</div>

<!-- Modal message -->
<div class="modal-bg" id="m-msg">
  <div class="modal">
    <h2 id="m-msg-title" data-i18n="message">Message</h2>
    <div id="msg-langtabs" class="langtabs"></div>
    <textarea id="msg-text"></textarea>
    <div class="hint" id="msg-call-hint" data-i18n="call_test"></div>
    <div class="row" style="margin-top:10px">
      <button class="btn sec sm" id="btn-import" data-i18n="import_drive">Importer depuis Fichiers</button>
      <button class="btn sec sm" id="btn-draft" data-i18n="draft_ai">Rédiger avec l'assistant</button>
      <button class="btn ghost sm" id="btn-push" data-i18n="push_twilio">Déclarer le webhook sur Twilio</button>
      <button class="btn sec sm" id="btn-tts" data-i18n="tts_btn">🔊 Générer l'audio (MP3)</button>
    </div>
    <div id="tts-audio" style="margin-top:8px"></div>
    <div id="ovh-apply-box" style="display:none;margin-top:10px;border:1px solid var(--bd,#ddd);border-radius:8px;padding:10px">
      <div class="hint" id="ovh-apply-detail" style="margin-bottom:6px"></div>
      <textarea id="ovh-apply-script" readonly style="width:100%;min-height:90px;font-family:monospace;font-size:12px"></textarea>
    </div>
    <div class="m-foot">
      <button class="btn ghost" id="m-msg-cancel" data-i18n="close">Fermer</button>
      <button class="btn" id="m-msg-save" data-i18n="save">Enregistrer</button>
    </div>
  </div>
</div>

<!-- Modal config -->
<div class="modal-bg" id="m-cfg">
  <div class="modal">
    <h2 data-i18n="provider_config">Configuration du répondeur</h2>
    <label data-i18n="provider">Fournisseur</label>
    <select id="c-provider">
      <option value="twilio">Twilio (répondeur live)</option>
      <option value="ovh">OVH Télécom (SVI assisté)</option>
    </select>

    <div id="cfg-twilio">
      <label data-i18n="account_sid">Account SID</label>
      <input type="text" id="c-sid" placeholder="ACxxxxxxxx">
      <label data-i18n="auth_token">Auth Token</label>
      <input type="text" id="c-token" placeholder="••••••••">
      <div class="hint" id="c-token-state"></div>
      <label data-i18n="public_url">URL publique de cette instance</label>
      <input type="text" id="c-url" placeholder="http://mon-serveur.example.net:8000">
      <div class="hint" data-i18n="public_url_hint"></div>
      <label data-i18n="voice">Voix par défaut</label>
      <input type="text" id="c-voice" placeholder="alice">
    </div>

    <div id="cfg-ovh" style="display:none">
      <div class="hint" data-i18n="ovh_hint" style="margin-bottom:8px"></div>
      <label data-i18n="ovh_endpoint">Endpoint OVH</label>
      <select id="c-ovh-endpoint">
        <option value="ovh-eu">Europe (ovh-eu)</option>
        <option value="ovh-ca">Canada (ovh-ca)</option>
      </select>
      <label data-i18n="ovh_app_key">Application Key</label>
      <input type="text" id="c-ovh-key" placeholder="app key">
      <label data-i18n="ovh_app_secret">Application Secret</label>
      <input type="text" id="c-ovh-secret" placeholder="••••••••">
      <label data-i18n="ovh_consumer_key">Consumer Key</label>
      <input type="text" id="c-ovh-consumer" placeholder="••••••••">
      <div class="hint" id="c-ovh-secret-state"></div>
      <label data-i18n="ovh_billing">Compte de facturation (billingAccount)</label>
      <input type="text" id="c-ovh-billing" placeholder="ovhtel-xxxxx-1">
      <label data-i18n="ovh_service">Numéro / service OVH</label>
      <input type="text" id="c-ovh-service" placeholder="00339xxxxxxx">
    </div>

    <div class="hint" data-i18n="central_hint" style="margin-top:12px"></div>
    <div class="m-foot">
      <button class="btn ghost" id="m-cfg-cancel" data-i18n="close">Fermer</button>
      <button class="btn sec" id="m-cfg-test" data-i18n="test_config">Tester la connexion</button>
      <button class="btn" id="m-cfg-save" data-i18n="save_config">Enregistrer</button>
    </div>
  </div>
</div>

<!-- Modal messagerie vocale -->
<div class="modal-bg" id="m-vocaux">
  <div class="modal">
    <h2 data-i18n="vocaux_title">Messages reçus</h2>
    <div class="hint" id="vocaux-sub"></div>
    <div id="vocaux-body" style="max-height:60vh;overflow:auto;margin-top:10px"></div>
    <div class="m-foot">
      <button class="btn ghost" id="m-vocaux-cancel" data-i18n="close">Fermer</button>
      <button class="btn sec" id="m-vocaux-refresh" data-i18n="vocaux_refresh">Rafraîchir</button>
    </div>
  </div>
</div>

<!-- Modal rédaction assistée -->
<div class="modal-bg" id="m-draft">
  <div class="modal">
    <h2 data-i18n="draft_ai">Rédiger avec l'assistant</h2>
    <div class="hint" data-i18n="ai_consigne_ph">Ex : afflux aux urgences, demander de ne pas se déplacer sauf urgence vitale</div>
    <textarea id="draft-consigne" style="width:100%;min-height:110px;margin-top:8px"></textarea>
    <div class="m-foot">
      <button class="btn ghost" id="m-draft-cancel" data-i18n="close">Fermer</button>
      <button class="btn" id="m-draft-run" data-i18n="generate">Générer</button>
    </div>
  </div>
</div>

<!-- Modal appels reçus -->
<div class="modal-bg" id="m-appels">
  <div class="modal">
    <h2 data-i18n="appels_title">Appels reçus aujourd'hui</h2>
    <div class="hint" id="appels-sub"></div>
    <div id="appels-body" style="max-height:60vh;overflow:auto;margin-top:10px"></div>
    <div class="m-foot">
      <button class="btn ghost" id="m-appels-cancel" data-i18n="close">Fermer</button>
      <button class="btn sec" id="m-appels-refresh" data-i18n="vocaux_refresh">Rafraîchir</button>
    </div>
  </div>
</div>

<div class="toast" id="toast"></div>

<script>
(function(){
"use strict";
var I18N = __I18N_JSON__;
function parentLS(k){
  try{ return window.parent.localStorage.getItem(k) || localStorage.getItem(k) || ""; }
  catch(e){ try{ return localStorage.getItem(k) || ""; }catch(_){ return ""; } }
}
function resolveLang(){
  var c = (parentLS("scribe_lang_pref") || "fr").slice(0,2).toLowerCase();
  return I18N[c] ? c : (I18N["en"] ? "en" : "fr");
}
var LANG = resolveLang();
function t(k){ return (I18N[LANG] && I18N[LANG][k]) || (I18N["en"] && I18N["en"][k]) || k; }
function tok(){ return parentLS("scribe_token"); }
function api(path, opts){
  opts = opts || {};
  opts.headers = opts.headers || {};
  opts.headers["Authorization"] = "Bearer " + tok();
  return fetch("/api/v1/repondeur" + path, opts);
}
function jpost(path, body, method){
  return api(path, { method: method || "POST",
    headers: { "Content-Type": "application/json" }, body: JSON.stringify(body || {}) });
}
function esc(s){ return String(s==null?"":s).replace(/[&<>"]/g,function(c){
  return {"&":"&amp;","<":"&lt;",">":"&gt;","\"":"&quot;"}[c]; }); }
function toast(msg){
  var el = document.getElementById("toast"); el.textContent = msg; el.classList.add("show");
  setTimeout(function(){ el.classList.remove("show"); }, 2200);
}
function applyI18n(root){
  (root||document).querySelectorAll("[data-i18n]").forEach(function(el){
    el.textContent = t(el.getAttribute("data-i18n")); });
  (root||document).querySelectorAll("[data-i18n-ph]").forEach(function(el){
    el.setAttribute("placeholder", t(el.getAttribute("data-i18n-ph"))); });
  document.documentElement.setAttribute("lang", LANG);
}

// Langues UE proposées (code -> nom natif)
var LANGNAMES = { fr:"Français", en:"English", de:"Deutsch", es:"Español", it:"Italiano",
  nl:"Nederlands", pl:"Polski", pt:"Português", sv:"Svenska", da:"Dansk", fi:"Suomi",
  el:"Ελληνικά", cs:"Čeština", ro:"Română", hu:"Magyar", bg:"Български", hr:"Hrvatski",
  sk:"Slovenčina", sl:"Slovenščina", lt:"Lietuvių", lv:"Latviešu", et:"Eesti", ga:"Gaeilge", mt:"Malti" };
var LANG_ORDER = ["fr","en","de","es","it","nl","pl","pt","sv","da","fi","el","cs","ro","hu","bg","hr","sk","sl","lt","lv","et","ga","mt"];
function langName(c){ return LANGNAMES[c] || c; }

var LINES = [];
var EDIT = null;      // ligne en cours d'édition (modal ligne)
var MSG_LINE = null;  // ligne en cours (modal message)
var MSG_LANG = null;
var MSG_CACHE = {};   // langue -> texte (modal message)

// ── Statut ──────────────────────────────────────────────────────────────────
function loadStatus(){
  api("/status").then(function(r){ return r.json(); }).then(function(s){
    var pill = document.getElementById("status-pill");
    var prov = (s.provider === "ovh") ? "OVH" : "Twilio";
    var wasProv = window.PROVIDER;
    window.PROVIDER = s.provider || "twilio";
    if(s.configured){ pill.className = "pill live";
      pill.textContent = prov + " · " + t("status_live") + " · " + s.lignes_actives + " " + t("lines_active"); }
    else { pill.className = "pill dev"; pill.textContent = prov + " · " + t("status_dev"); }
    if(wasProv !== window.PROVIDER && LINES && LINES.length){ renderLines(); }
  }).catch(function(){});
}
function loadOvhStats(){
  api("/ovh-stats").then(function(r){ return r.json(); }).then(function(d){
    if(!d || d.provider !== "ovh" || !d.stats) return;
    Object.keys(d.stats).forEach(function(lid){
      var el = document.getElementById("ovh-stats-" + lid);
      if(!el) return;
      var s = d.stats[lid];
      if(s && s.ok){
        var today = (s.calls_today != null) ? s.calls_today : "—";
        var total = (s.calls_total != null) ? (" · " + s.calls_total + " au total") : "";
        el.className = "ovh-stats live";
        el.style.cursor = "pointer";
        el.title = t("calls_see");
        el.innerHTML = "\uD83D\uDCDE <b>" + today + "</b> " + esc(t("calls_today")) + total +
          " <span class='ovh-stats-src'>\u00B7 live OVH " + esc(s.at||"") + " \u2013 " + esc(t("calls_see")) + "</span>";
        el.onclick = function(){ openAppels(lid); };
      } else {
        el.className = "ovh-stats";
        el.style.cursor = "default"; el.onclick = null;
        el.innerHTML = "<span class='ovh-stats-src'>" + esc((s && s.detail) || "stats OVH indisponibles") + "</span>";
      }
      var badge = document.getElementById("vm-badge-" + lid);
      if(badge){ var n = (s && s.msg_count) || 0; badge.textContent = n > 0 ? n : ""; badge.style.display = n > 0 ? "inline-block" : "none"; }
    });
  }).catch(function(){});
}

// ── Lignes ──────────────────────────────────────────────────────────────────
function loadLines(){
  api("/lignes").then(function(r){ return r.json(); }).then(function(rows){
    LINES = Array.isArray(rows) ? rows : [];
    renderLines();
    loadStatus();
    loadOvhStats();
    if(!window._ovhStatsTimer){ window._ovhStatsTimer = setInterval(loadOvhStats, 20000); }
  }).catch(function(){ renderLines(); });
}
function renderLines(){
  var box = document.getElementById("lines");
  if(!LINES.length){
    box.innerHTML = "<div class='empty'>" + esc(t("no_lines")) + "</div>";
    return;
  }
  box.innerHTML = "";
  LINES.forEach(function(l){
    var card = document.createElement("div"); card.className = "card"; card.setAttribute("data-line-id", l.id);
    var tags = (l.langues||[]).map(function(c){ return "<span class='tag'>" + esc(c) + "</span>"; }).join("");
    var dot = l.actif ? "<span class='dot on'></span>" + esc(t("active"))
                      : "<span class='dot off'></span>" + esc(t("inactive"));
    card.innerHTML =
      "<div class='l-top'>" +
        "<div><div class='l-title'>" + esc(l.libelle) + "</div>" +
          (l.numero ? "<div class='num'>" + esc(l.numero) + "</div>" : "") + "</div>" +
        "<div class='row'>" +
          "<button class='btn sec sm' data-act='msg' data-id='" + l.id + "' title='" + esc(t("compose_communique")) + "'>" + esc(t("compose_communique")) + "</button>" +
          "<button class='btn ghost sm' data-act='edit' data-id='" + l.id + "' title='" + esc(t("edit")) + "'>" + esc(t("edit")) + "</button>" +
          "<button class='btn ghost sm' data-act='toggle' data-id='" + l.id + "' title='" + esc(l.actif?t("deactivate"):t("activate")) + "'>" + (l.actif?"⏸":"▶") + "</button>" +
          ((window.PROVIDER === "ovh") ? "<button class='btn ghost sm' data-act='vocaux' data-id='" + l.id + "' title='" + esc(t("inbox")) + "'>\uD83D\uDCE5 " + esc(t("inbox")) + " <span class='vm-badge' id='vm-badge-" + l.id + "'></span></button>" : "") +
          "<button class='btn danger sm' data-act='del' data-id='" + l.id + "' title='" + esc(t("delete")) + "'>" + esc(t("delete")) + "</button>" +
        "</div>" +
      "</div>" +
      "<div class='tags'>" + tags + "</div>" +
      "<div class='row'><span>" + dot + "</span></div>" +
      "<div class='ovh-stats' id='ovh-stats-" + l.id + "'></div>" +
      "<div class='msg'>" + esc(l.message_preview || "—") + "</div>" +
      (l.updated_at ? "<div class='meta'>" + esc(t("updated")) + " " + esc((l.updated_at||"").slice(0,16).replace("T"," ")) +
        (l.updated_by ? " " + esc(t("by")) + " " + esc(l.updated_by) : "") + "</div>" : "");
    box.appendChild(card);
  });
}

// ── Modal ligne ─────────────────────────────────────────────────────────────
function buildLangCheckboxes(selected){
  var box = document.getElementById("f-langs"); box.innerHTML = "";
  LANG_ORDER.forEach(function(c){
    var on = selected.indexOf(c) >= 0;
    var el = document.createElement("span");
    el.className = "langtab" + (on ? " act" : "");
    el.textContent = langName(c);
    el.setAttribute("data-lang", c);
    el.onclick = function(){ el.classList.toggle("act"); };
    box.appendChild(el);
  });
}
function fillMainLangSelect(sel){
  var s = document.getElementById("f-mainlang"); s.innerHTML = "";
  LANG_ORDER.forEach(function(c){
    var o = document.createElement("option"); o.value = c; o.textContent = langName(c);
    if(c === sel) o.selected = true; s.appendChild(o);
  });
}
function openLineForm(line){
  EDIT = line || null;
  document.getElementById("m-line-title").textContent = line ? esc(line.libelle) : t("new_line");
  document.getElementById("f-libelle").value = line ? line.libelle : "";
  document.getElementById("f-numero").value = line ? (line.numero||"") : "";
  document.getElementById("f-voice").value = line ? (line.voice||"") : "";
  document.getElementById("f-actif").checked = line ? !!line.actif : false;
  fillMainLangSelect(line ? line.langue_principale : "fr");
  buildLangCheckboxes(line ? (line.langues||[]) : ["fr"]);
  show("m-line");
}
function saveLine(){
  var langs = [];
  document.querySelectorAll("#f-langs .langtab.act").forEach(function(el){ langs.push(el.getAttribute("data-lang")); });
  var body = {
    libelle: document.getElementById("f-libelle").value.trim(),
    numero: document.getElementById("f-numero").value.trim(),
    langue_principale: document.getElementById("f-mainlang").value,
    langues: langs,
    voice: document.getElementById("f-voice").value.trim(),
    actif: document.getElementById("f-actif").checked
  };
  if(!body.libelle){ toast(t("label")); return; }
  var p = EDIT ? jpost("/lignes/" + EDIT.id, body, "PUT") : jpost("/lignes", body, "POST");
  p.then(function(r){ if(!r.ok) throw 0; return r.json(); }).then(function(){
    hide("m-line"); toast(t("saved")); loadLines();
  }).catch(function(){ toast(t("error")); });
}
function deleteLine(id){
  if(!confirm(t("confirm_delete"))) return;
  api("/lignes/" + id, { method: "DELETE" }).then(function(r){
    if(r.ok){ toast(t("saved")); loadLines(); } else toast(t("error"));
  });
}
function toggleActive(line){
  jpost("/lignes/" + line.id, { actif: !line.actif }, "PUT").then(function(r){
    if(r.ok){ loadLines(); } else toast(t("error"));
  });
}

// ── Modal message ───────────────────────────────────────────────────────────
function openMessageEditor(line){
  MSG_LINE = line; MSG_CACHE = {};
  document.getElementById("m-msg-title").textContent = t("message") + " — " + line.libelle;
  api("/lignes/" + line.id + "/messages").then(function(r){ return r.json(); }).then(function(d){
    MSG_CACHE = d.messages || {};
    var langs = (d.langues && d.langues.length) ? d.langues : [line.langue_principale || "fr"];
    var tabs = document.getElementById("msg-langtabs"); tabs.innerHTML = "";
    langs.forEach(function(c, i){
      var el = document.createElement("span");
      el.className = "langtab" + (i===0 ? " act" : "");
      el.textContent = langName(c); el.setAttribute("data-lang", c);
      el.onclick = function(){
        document.querySelectorAll("#msg-langtabs .langtab").forEach(function(x){ x.classList.remove("act"); });
        el.classList.add("act"); selectMsgLang(c);
      };
      tabs.appendChild(el);
    });
    selectMsgLang(langs[0]);
    show("m-msg");
  });
}
function selectMsgLang(c){
  // sauver le texte courant en cache avant de switcher
  if(MSG_LANG !== null){ MSG_CACHE[MSG_LANG] = document.getElementById("msg-text").value; }
  MSG_LANG = c;
  document.getElementById("msg-text").value = MSG_CACHE[c] || "";
}
function saveMessage(){
  if(!MSG_LINE) return;
  MSG_CACHE[MSG_LANG] = document.getElementById("msg-text").value;
  jpost("/lignes/" + MSG_LINE.id + "/message", { langue: MSG_LANG, texte: MSG_CACHE[MSG_LANG] }, "PUT")
    .then(function(r){ if(!r.ok) throw 0; return r.json(); })
    .then(function(){ toast(t("saved")); loadLines(); })
    .catch(function(){ toast(t("error")); });
}
// Import depuis le drive
function doImport(){
  if(!MSG_LINE) return;
  api("/fichiers-texte").then(function(r){ return r.json(); }).then(function(files){
    if(!files || !files.length){ toast(t("no_text_files")); return; }
    var names = files.map(function(f, i){ return (i+1) + ". " + f.nom; }).join("\n");
    var pick = prompt(t("pick_file") + "\n" + names, "1");
    if(!pick) return;
    var idx = parseInt(pick, 10) - 1;
    if(isNaN(idx) || idx < 0 || idx >= files.length){ return; }
    jpost("/lignes/" + MSG_LINE.id + "/import-fichier", { fichier_id: files[idx].id, langue: MSG_LANG })
      .then(function(r){ if(!r.ok) throw 0; return r.json(); })
      .then(function(l){
        var m = (l.messages && l.messages[MSG_LANG]) || "";
        MSG_CACHE[MSG_LANG] = m; document.getElementById("msg-text").value = m;
        toast(t("saved")); loadLines();
      }).catch(function(){ toast(t("error")); });
  });
}
// Rédaction assistée
function doDraft(){
  if(!MSG_LINE) return;
  document.getElementById("draft-consigne").value = "";
  show("m-draft");
  setTimeout(function(){ var el=document.getElementById("draft-consigne"); if(el) el.focus(); }, 50);
}
function doDraftRun(){
  if(!MSG_LINE){ hide("m-draft"); return; }
  var consigne = document.getElementById("draft-consigne").value.trim();
  hide("m-draft");
  toast(t("generating"));
  jpost("/lignes/" + MSG_LINE.id + "/rediger", { langue: MSG_LANG, consigne: consigne })
    .then(function(r){ if(!r.ok){ return r.json().then(function(e){ throw e; }); } return r.json(); })
    .then(function(d){
      document.getElementById("msg-text").value = d.texte || "";
      MSG_CACHE[MSG_LANG] = d.texte || ""; toast(d.source || "IA");
    }).catch(function(e){ toast((e && e.detail) ? e.detail : t("error")); });
}
function doTts(){
  var texte = document.getElementById("msg-text").value.trim();
  var slot = document.getElementById("tts-audio");
  if(!texte){ if(slot) slot.textContent = t("error"); return; }
  if(slot) slot.innerHTML = "<span style='font-size:12px;color:#666'>" + esc(t("generating")) + "</span>";
  jpost("/tts", { texte: texte, langue: MSG_LANG || "fr" })
    .then(function(r){ if(!r.ok){ return r.json().then(function(e){ throw e; }); } return r.blob(); })
    .then(function(b){
      var url = URL.createObjectURL(b);
      if(slot) slot.innerHTML = "<audio controls style='width:100%;margin-top:6px' src='" + url + "'></audio>";
      var a = document.createElement("a"); a.href = url; a.download = "repondeur_" + (MSG_LANG || "fr") + ".mp3";
      document.body.appendChild(a); a.click(); a.remove();
    })
    .catch(function(e){ if(slot) slot.textContent = (e && e.detail) ? e.detail : t("error"); });
}
function doPush(){
  if(!MSG_LINE) return;
  jpost("/lignes/" + MSG_LINE.id + "/appliquer", {})
    .then(function(r){ if(!r.ok){ return r.json().then(function(e){ throw e; }); } return r.json(); })
    .then(function(d){
      if(d.provider === "ovh" && d.script){
        // Mode assisté OVH : afficher le texte prêt à coller dans le SVI OVH.
        var box = document.getElementById("ovh-apply-box");
        if(box){
          document.getElementById("ovh-apply-detail").textContent = d.detail || "";
          document.getElementById("ovh-apply-script").value = d.script || "";
          box.style.display = "block";
        }
        toast(d.detail || "OVH");
      } else {
        toast(d.detail || "OK");
      }
    })
    .catch(function(e){ toast((e && e.detail) ? e.detail : t("error")); });
}

// ── Modal config (Twilio / OVH) ──────────────────────────────────────────────
function applyProviderUI(provider){
  var isOvh = (provider === "ovh");
  var tw = document.getElementById("cfg-twilio");
  var ov = document.getElementById("cfg-ovh");
  if(tw) tw.style.display = isOvh ? "none" : "block";
  if(ov) ov.style.display = isOvh ? "block" : "none";
  var pb = document.getElementById("btn-push");
  if(pb) pb.textContent = isOvh ? t("apply_ovh") : t("push_twilio");
}
function openConfig(){
  api("/admin/config").then(function(r){
    if(r.status === 403){ toast(t("error") + " (admin)"); throw 0; }
    return r.json();
  }).then(function(c){
    var prov = c.provider || "twilio";
    document.getElementById("c-provider").value = prov;
    // Twilio
    document.getElementById("c-sid").value = c.account_sid || "";
    document.getElementById("c-url").value = c.public_url || "";
    document.getElementById("c-voice").value = c.default_voice || "";
    document.getElementById("c-token").value = "";
    var st = document.getElementById("c-token-state");
    st.textContent = c.auth_token_set ? (t("auth_token_set") + " · " + (c.auth_token_preview||"")) : t("voice_dev_hint");
    // OVH
    document.getElementById("c-ovh-endpoint").value = c.ovh_endpoint || "ovh-eu";
    document.getElementById("c-ovh-key").value = c.ovh_app_key || "";
    document.getElementById("c-ovh-billing").value = c.ovh_billing_account || "";
    document.getElementById("c-ovh-service").value = c.ovh_service || "";
    document.getElementById("c-ovh-secret").value = "";
    document.getElementById("c-ovh-consumer").value = "";
    var os = document.getElementById("c-ovh-secret-state");
    if(os) os.textContent = c.ovh_app_secret_set ? (t("auth_token_set") + " · " + (c.ovh_app_secret_preview||"")) : t("voice_dev_hint");
    applyProviderUI(prov);
    show("m-cfg");
  }).catch(function(){});
}
function cfgBody(){
  var prov = document.getElementById("c-provider").value;
  var body = {
    provider: prov,
    account_sid: document.getElementById("c-sid").value.trim(),
    public_url: document.getElementById("c-url").value.trim(),
    default_voice: document.getElementById("c-voice").value.trim(),
    ovh_endpoint: document.getElementById("c-ovh-endpoint").value,
    ovh_app_key: document.getElementById("c-ovh-key").value.trim(),
    ovh_billing_account: document.getElementById("c-ovh-billing").value.trim(),
    ovh_service: document.getElementById("c-ovh-service").value.trim()
  };
  var tk = document.getElementById("c-token").value.trim();
  if(tk) body.auth_token = tk;
  var osec = document.getElementById("c-ovh-secret").value.trim();
  if(osec) body.ovh_app_secret = osec;
  var ock = document.getElementById("c-ovh-consumer").value.trim();
  if(ock) body.ovh_consumer_key = ock;
  return body;
}
function saveConfig(){
  jpost("/admin/config", cfgBody()).then(function(r){ if(!r.ok) throw 0; return r.json(); })
    .then(function(){ toast(t("saved")); hide("m-cfg"); loadStatus(); })
    .catch(function(){ toast(t("error")); });
}
function testConfig(){
  // Le test porte sur le fournisseur + identifiants À L'ÉCRAN : on enregistre
  // d'abord (sinon le test utilise la config précédente en base), puis on teste.
  jpost("/admin/config", cfgBody()).then(function(r){ return r.json(); })
    .then(function(){ return api("/admin/config/test", { method: "POST" }); })
    .then(function(r){ return r.json(); })
    .then(function(d){ toast(d.detail || (d.ok ? "OK" : t("error"))); loadStatus(); })
    .catch(function(){ toast(t("error")); });
}

// ── Appels reçus (OVH) ──────────────────────────────────────────────────────
var APPELS_LID = null;
function openAppels(lid){
  APPELS_LID = lid;
  var line = LINES.filter(function(l){ return String(l.id) === String(lid); })[0];
  document.getElementById("appels-sub").textContent = line ? (line.libelle + (line.numero ? " · " + line.numero : "")) : "";
  show("m-appels");
  loadAppels();
}
function loadAppels(){
  if(APPELS_LID == null) return;
  var body = document.getElementById("appels-body");
  body.innerHTML = "<div class='empty'>" + esc(t("loading")) + "</div>";
  api("/lignes/" + APPELS_LID + "/appels").then(function(r){ return r.json(); }).then(function(d){
    if(!d || !d.ok){ body.innerHTML = "<div class='empty'>" + esc((d && d.detail) || t("error")) + "</div>"; return; }
    var calls = d.calls || [];
    if(!calls.length){ body.innerHTML = "<div class='empty'>" + esc(t("appels_none")) + "</div>"; return; }
    body.innerHTML = calls.map(function(c){
      var meta = [];
      var who = c.calling || c.called || "";
      if(who) meta.push(esc(who));
      if(c.date) meta.push(esc((""+c.date).slice(0,16).replace("T"," ")));
      if(c.duration != null) meta.push(esc(c.duration) + "s");
      var way = (c.way === "incoming") ? "\u2199\uFE0F" : (c.way === "outgoing" ? "\u2197\uFE0F" : "\uD83D\uDCDE");
      return "<div style='border:1px solid var(--bd,#ddd);border-radius:8px;padding:10px;margin-bottom:8px;font-size:13px'>" +
        way + " " + (meta.join(" \u00B7 ") || ("#" + esc(c.id))) + "</div>";
    }).join("");
  }).catch(function(){ body.innerHTML = "<div class='empty'>" + esc(t("error")) + "</div>"; });
}

// ── Messagerie vocale (OVH) ─────────────────────────────────────────────────
var VOCAUX_LINE = null;
function openVocaux(line){
  VOCAUX_LINE = line;
  document.getElementById("vocaux-sub").textContent = line.libelle + (line.numero ? " · " + line.numero : "");
  show("m-vocaux");
  loadVocaux();
}
function loadVocaux(){
  if(!VOCAUX_LINE) return;
  var body = document.getElementById("vocaux-body");
  body.innerHTML = "<div class='empty'>" + esc(t("loading")) + "</div>";
  api("/lignes/" + VOCAUX_LINE.id + "/messages-vocaux").then(function(r){ return r.json(); }).then(function(d){
    if(!d || !d.ok){ body.innerHTML = "<div class='empty'>" + esc((d && d.detail) || t("error")) + "</div>"; return; }
    var msgs = d.messages || [];
    if(!msgs.length){ body.innerHTML = "<div class='empty'>" + esc(t("vocaux_none")) + "</div>"; return; }
    body.innerHTML = msgs.map(function(m){
      var meta = [];
      if(m.caller) meta.push(esc(m.caller));
      if(m.date) meta.push(esc((""+m.date).slice(0,16).replace("T"," ")));
      if(m.duration != null) meta.push(esc(m.duration) + "s");
      return "<div style='border:1px solid var(--bd,#ddd);border-radius:8px;padding:10px;margin-bottom:8px'>" +
        "<div style='font-size:13px;font-weight:600'>\uD83D\uDCE8 " + (meta.join(" \u00B7 ") || ("#" + esc(m.id))) + "</div>" +
        "<div class='row' style='margin-top:8px;gap:8px'>" +
          "<button class='btn sec sm' data-vact='play' data-mid='" + esc(m.id) + "' title='" + esc(t("vocaux_play")) + "'>\u25B6</button>" +
          "<button class='btn ghost sm' data-vact='dl' data-mid='" + esc(m.id) + "' title='" + esc(t("vocaux_download")) + "'>\u2B07</button>" +
          "<button class='btn ghost sm' data-vact='tr' data-mid='" + esc(m.id) + "' title='" + esc(t("vocaux_transcript")) + "'>\uD83D\uDCDD</button>" +
        "</div>" +
        "<div class='vocal-audio' data-mid='" + esc(m.id) + "'></div>" +
        "<div class='vocal-tr' data-mid='" + esc(m.id) + "' style='font-size:12px;color:#666;margin-top:6px;white-space:pre-wrap'></div>" +
      "</div>";
    }).join("");
  }).catch(function(){ body.innerHTML = "<div class='empty'>" + esc(t("error")) + "</div>"; });
}
function vocauxBlob(mid){
  return api("/lignes/" + VOCAUX_LINE.id + "/messages-vocaux/" + mid + "/download")
    .then(function(r){ if(!r.ok) throw 0; return r.blob(); });
}
function vocauxPlay(mid){
  var slot = document.querySelector(".vocal-audio[data-mid='" + mid + "']");
  if(slot) slot.innerHTML = "<span style='font-size:12px;color:#666'>" + esc(t("loading")) + "</span>";
  vocauxBlob(mid).then(function(b){
    var url = URL.createObjectURL(b);
    if(slot) slot.innerHTML = "<audio controls autoplay style='width:100%;margin-top:8px' src='" + url + "'></audio>";
  }).catch(function(){ if(slot) slot.innerHTML = "<span style='font-size:12px;color:#c00'>" + esc(t("error")) + "</span>"; });
}
function vocauxDownload(mid){
  vocauxBlob(mid).then(function(b){
    var url = URL.createObjectURL(b);
    var a = document.createElement("a"); a.href = url; a.download = "message_" + mid + ".mp3";
    document.body.appendChild(a); a.click(); a.remove();
    setTimeout(function(){ URL.revokeObjectURL(url); }, 4000);
  }).catch(function(){ toast(t("error")); });
}
function vocauxTranscript(mid){
  var slot = document.querySelector(".vocal-tr[data-mid='" + mid + "']");
  if(slot) slot.textContent = t("transcribing");
  api("/lignes/" + VOCAUX_LINE.id + "/messages-vocaux/" + mid + "/transcript").then(function(r){ return r.json(); }).then(function(d){
    if(slot) slot.textContent = (d && d.ok && d.text) ? d.text : ((d && d.detail) || t("vocaux_no_transcript"));
  }).catch(function(){ if(slot) slot.textContent = t("error"); });
}

// ── Helpers modal ────────────────────────────────────────────────────────────
function show(id){ document.getElementById(id).classList.add("show"); }
function hide(id){ document.getElementById(id).classList.remove("show"); }

// ── Événements ───────────────────────────────────────────────────────────────
document.getElementById("lines").addEventListener("click", function(e){
  var b = e.target.closest("button[data-act]"); if(!b) return;
  var id = parseInt(b.getAttribute("data-id"), 10);
  var line = LINES.filter(function(l){ return l.id === id; })[0];
  if(!line) return;
  var act = b.getAttribute("data-act");
  if(act === "msg") openMessageEditor(line);
  else if(act === "edit") openLineForm(line);
  else if(act === "toggle") toggleActive(line);
  else if(act === "vocaux") openVocaux(line);
  else if(act === "del") deleteLine(id);
});
document.getElementById("btn-new").onclick = function(){ openLineForm(null); };
document.getElementById("btn-config").onclick = openConfig;
document.getElementById("m-line-cancel").onclick = function(){ hide("m-line"); };
document.getElementById("m-line-save").onclick = saveLine;
document.getElementById("m-msg-cancel").onclick = function(){ MSG_LANG=null; hide("m-msg"); };
document.getElementById("m-msg-save").onclick = saveMessage;
document.getElementById("btn-import").onclick = doImport;
document.getElementById("btn-draft").onclick = doDraft;
document.getElementById("btn-tts").onclick = doTts;
document.getElementById("m-draft-cancel").onclick = function(){ hide("m-draft"); };
document.getElementById("m-draft-run").onclick = doDraftRun;
document.getElementById("btn-push").onclick = doPush;
document.getElementById("m-cfg-cancel").onclick = function(){ hide("m-cfg"); };
document.getElementById("m-cfg-save").onclick = saveConfig;
document.getElementById("m-cfg-test").onclick = testConfig;
document.getElementById("c-provider").onchange = function(){ applyProviderUI(this.value); };
document.getElementById("m-vocaux-cancel").onclick = function(){ hide("m-vocaux"); };
document.getElementById("m-vocaux-refresh").onclick = loadVocaux;
document.getElementById("m-appels-cancel").onclick = function(){ hide("m-appels"); };
document.getElementById("m-appels-refresh").onclick = loadAppels;
document.getElementById("vocaux-body").addEventListener("click", function(e){
  var b = e.target.closest("button[data-vact]"); if(!b) return;
  var mid = b.getAttribute("data-mid"); var act = b.getAttribute("data-vact");
  if(act === "play") vocauxPlay(mid);
  else if(act === "dl") vocauxDownload(mid);
  else if(act === "tr") vocauxTranscript(mid);
});
[ "m-line", "m-msg", "m-cfg" ].forEach(function(id){
  document.getElementById(id).addEventListener("click", function(e){ if(e.target.id === id) hide(id); });
});

applyI18n();
loadLines();
})();
</script>
</body>
</html>"""


@ui_router.get("/ui", response_class=HTMLResponse)
def repondeur_ui():
    html = _HTML.replace("__I18N_JSON__", json.dumps(_I18N, ensure_ascii=False))
    return HTMLResponse(html)
