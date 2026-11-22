"""
plugins/fichiers/ui.py — Interface HTML du plugin `fichiers` (SCRIBE)
=====================================================================
Page autonome rendue dans une iframe (même origine → accès au token et à la
langue via le localStorage parent). Charte « Suite numérique » : Bleu France
#000091, police système, cartes blanches, liseré bleu au survol.

Multilingue natif : le dictionnaire des 24 langues UE est embarqué depuis
``_i18n_data.json`` (source unique générée par ``_gen_i18n.py``).
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
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Fichiers</title>
<style>
:root{
  --blue:#000091; --blue-dark:#003189; --red:#e1000f; --green:#18753c;
  --bg:#f7f7fb; --surface:#ffffff; --surface2:#f6f6f6; --border:#e5e5ed;
  --text:#161616; --muted:#666; --hover:#000091; --side:#ffffff;
}
*{box-sizing:border-box;margin:0;padding:0}
body{font-family:"Marianne",system-ui,-apple-system,"Segoe UI",Roboto,Arial,sans-serif;
  background:var(--bg);color:var(--text);height:100vh;overflow:hidden;font-size:14px}
#app{display:flex;flex-direction:column;height:100vh}

/* ── Barre supérieure (sobre) ── */
#topbar{background:#fff;border-bottom:1px solid var(--border);height:56px;flex-shrink:0;
  display:flex;align-items:center;gap:16px;padding:0 18px}
.logo{display:inline-flex;align-items:center;font-weight:700;font-size:18px;color:var(--text)}
#topbar .spacer{margin-left:auto}
.avatar{width:32px;height:32px;border-radius:50%;background:var(--blue);color:#fff;
  display:inline-flex;align-items:center;justify-content:center;font-size:12px;font-weight:700}

/* ── Corps ── */
#wrap{display:flex;flex:1;overflow:hidden}

/* ── Sidebar ── */
#side{width:248px;flex-shrink:0;background:var(--side);border-right:1px solid var(--border);
  display:flex;flex-direction:column;padding:16px 12px;overflow-y:auto}
#new-row{display:flex;align-items:center;gap:10px;margin-bottom:18px}
.btn-new{flex:1;display:inline-flex;align-items:center;justify-content:center;gap:8px;
  background:var(--blue);color:#fff;border:none;border-radius:7px;padding:11px 14px;
  font-size:14px;font-weight:600;cursor:pointer}
.btn-new:hover{background:#00007a}
.searchbtn{width:40px;height:40px;border-radius:7px;border:1px solid var(--border);background:#fff;
  color:var(--blue);cursor:pointer;font-size:16px;flex-shrink:0;display:inline-flex;
  align-items:center;justify-content:center}
.searchbtn:hover{border-color:var(--blue)}
#searchbox{display:none;margin-bottom:12px}
#searchbox.show{display:block}
#search{width:100%;padding:9px 12px;border:1px solid var(--border);border-radius:7px;font-size:13px;background:#fff}
#search:focus{outline:none;border-color:var(--blue)}
.nav{display:flex;flex-direction:column;gap:2px}
.nav-item{display:flex;align-items:center;gap:11px;padding:9px 12px;border-radius:7px;
  cursor:pointer;color:var(--text);font-size:14px;font-weight:500;border:none;background:transparent;
  width:100%;text-align:left}
.nav-item .ic{width:20px;text-align:center;font-size:15px;opacity:.85}
.nav-item:hover{background:var(--surface2)}
.nav-item.active{background:#ececfb;color:var(--blue);font-weight:700}
.nav-sep{height:1px;background:var(--border);margin:10px 6px}
.nav-pill{margin-left:auto;min-width:18px;height:18px;line-height:18px;font-size:10px;
  background:var(--blue);color:#fff;border-radius:9px;padding:0 5px;text-align:center}
/* Arborescence des dossiers — VERTICALE, sous « Mes fichiers » */
.folder-tree{display:none;flex-direction:column;gap:1px;margin:2px 0 2px 16px;padding-left:8px;
  border-left:1px solid var(--border)}
.folder-tree.show{display:flex}
.fchip{display:flex;align-items:center;gap:8px;padding:6px 9px;border-radius:6px;cursor:pointer;
  font-size:13px;color:var(--text);overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.fchip:hover{background:var(--surface2)}
.fchip.active{background:#ececfb;color:var(--blue);font-weight:600}
#quota{margin-top:auto;padding-top:16px;font-size:11px;color:var(--muted)}
#quota .gauge{width:100%;height:6px;background:var(--surface2);border-radius:4px;overflow:hidden;margin-top:5px}
#quota .gauge>i{display:block;height:100%;background:var(--blue);width:0%}

/* ── Zone principale ── */
#main{flex:1;overflow:auto;padding:18px 26px}
#filters{margin-bottom:16px}
.type-sel{font-size:13px;padding:7px 12px;border:1px solid var(--border);border-radius:7px;
  background:#fff;color:var(--text);cursor:pointer}
.type-sel:focus{outline:none;border-color:var(--blue)}
#card{background:#fff;border:1px solid var(--border);border-radius:12px;
  box-shadow:0 1px 2px rgba(0,0,0,.03)}
#card-head{display:flex;align-items:center;gap:10px;padding:16px 20px;border-bottom:1px solid var(--surface2)}
#card-title{font-size:16px;font-weight:700}
#card-actions{margin-left:auto;display:flex;align-items:center;gap:14px}
.link-act{display:inline-flex;align-items:center;gap:6px;color:var(--blue);font-size:14px;
  font-weight:600;cursor:pointer;background:none;border:none}
.link-act:hover{text-decoration:underline}
.iconcircle{width:34px;height:34px;border-radius:8px;border:1px solid var(--border);background:#fff;
  color:var(--blue);cursor:pointer;display:inline-flex;align-items:center;justify-content:center;font-size:15px}
.iconcircle:hover{border-color:var(--blue);background:var(--surface2)}
#dropzone{margin:12px 20px 0;border:2px dashed var(--border);border-radius:9px;padding:14px;
  text-align:center;color:var(--muted);font-size:13px;cursor:pointer;background:#fcfcff;transition:.15s}
#dropzone.hl{border-color:var(--blue);background:#eef}
table{width:100%;border-collapse:collapse}
thead th{text-align:left;font-size:12px;color:var(--muted);padding:11px 20px;font-weight:600;
  border-bottom:1px solid var(--surface2)}
thead th .sort{opacity:.5;font-size:10px;margin-left:4px}
tbody td{padding:11px 20px;border-bottom:1px solid var(--surface2);font-size:13.5px;vertical-align:middle}
tbody tr:last-child td{border-bottom:none}
tbody tr.row:hover{background:#fafaff}
.fname{display:flex;align-items:center;gap:11px;font-weight:500}
.ftype{width:30px;height:30px;border-radius:6px;background:var(--surface2);display:inline-flex;
  align-items:center;justify-content:center;font-size:16px;flex-shrink:0;color:var(--blue)}
.sub{display:flex;align-items:center;gap:6px}
.tag-eph{font-size:10px;font-weight:700;color:var(--red);border:1px solid var(--red);border-radius:10px;
  padding:1px 7px;text-transform:uppercase;letter-spacing:.3px}
.tag-pat{font-size:10px;font-weight:700;color:#a16207;background:#fef9c3;border-radius:10px;padding:1px 7px}
.tag-lock{font-size:10px;font-weight:700;color:var(--blue);background:#ececfb;border-radius:10px;padding:1px 7px}
.muted{color:var(--muted)}
.amen{text-align:right;width:48px}
.dots{border:none;background:transparent;border-radius:6px;cursor:pointer;width:32px;height:32px;
  font-size:18px;color:var(--muted);line-height:1}
.dots:hover{background:var(--surface2);color:var(--text)}
/* Menu d'actions : position FIXE (rattaché au body) pour ne pas être rogné par l'iframe */
.menu{position:fixed;background:#fff;border:1px solid var(--border);border-radius:9px;
  box-shadow:0 12px 34px rgba(0,0,0,.18);z-index:200;min-width:192px;padding:5px;display:none}
.menu.open{display:block}
.mi{display:flex;align-items:center;gap:10px;width:100%;text-align:left;border:none;background:none;
  padding:9px 11px;border-radius:6px;cursor:pointer;font-size:13px;color:var(--text)}
.mi:hover{background:var(--surface2)}
.mi.danger{color:var(--red)}
.mi .ic{width:18px;text-align:center}
.menu-sep{font-size:10.5px;text-transform:uppercase;letter-spacing:.5px;color:var(--muted);
  padding:8px 11px 4px;border-top:1px solid var(--border);margin-top:4px}
.fchip .fdots{margin-left:auto;border:none;background:none;cursor:pointer;color:var(--muted);
  font-size:15px;line-height:1;padding:2px 5px;border-radius:5px;opacity:.55}
.fchip:hover .fdots{opacity:1}
.fchip .fdots:hover{background:var(--surface2);color:var(--text)}
.statepill{font-size:11px;padding:2px 9px;border-radius:10px;font-weight:600}
.statepill.on{background:#e3f2e8;color:var(--green)}
.statepill.off{background:#f6f6f6;color:var(--muted)}
.empty{text-align:center;color:var(--muted);padding:54px 12px;font-size:13px}

/* ── Modales ── */
.modal-bg{position:fixed;inset:0;background:rgba(22,22,22,.42);display:none;align-items:center;
  justify-content:center;z-index:80}
.modal-bg.show{display:flex}
.modal{background:#fff;border-radius:12px;width:min(540px,93vw);overflow:hidden;
  box-shadow:0 24px 70px rgba(0,0,0,.32)}
.modal .mh{padding:16px 20px;font-weight:700;font-size:16px;display:flex;align-items:center;gap:9px;
  border-bottom:1px solid var(--surface2)}
.modal .mb{padding:20px;max-height:70vh;overflow:auto}
.modal .mf{padding:13px 20px;border-top:1px solid var(--surface2);display:flex;justify-content:flex-end;gap:9px}
.btn{font-size:14px;padding:9px 16px;border-radius:7px;border:1px solid var(--blue);background:var(--blue);
  color:#fff;cursor:pointer;font-weight:600;display:inline-flex;align-items:center;gap:7px}
.btn:hover{background:#00007a}
.btn.ghost{background:#fff;color:var(--blue)}
.btn.ghost:hover{background:var(--surface2)}
.btn.sm{padding:6px 11px;font-size:12px}
.btn[disabled]{opacity:.5;cursor:default}
.field-lbl{font-size:11px;font-weight:600;color:var(--muted);text-transform:uppercase;
  letter-spacing:.3px;margin:14px 0 6px}
.info{background:#eef;border-left:3px solid var(--blue);padding:10px 12px;border-radius:4px;
  font-size:12.5px;color:var(--blue-dark);margin-bottom:6px}
.seg-wrap{display:inline-flex;border:1px solid var(--border);border-radius:7px;overflow:hidden}
.seg{font-size:12px;padding:8px 13px;background:#fff;border:none;cursor:pointer;color:var(--muted)}
.seg.active{background:var(--blue);color:#fff;font-weight:600}
.seg+.seg{border-left:1px solid var(--border)}
.rcp-pick{width:100%;padding:9px 11px;border:1px solid var(--border);border-radius:7px;font-size:13px;background:#fff}
.rcp-chips{display:flex;flex-wrap:wrap;gap:6px;margin-top:8px;min-height:8px}
.rcp-chip{display:inline-flex;align-items:center;gap:6px;background:#eef;color:var(--blue-dark);
  border:1px solid #ccd;border-radius:14px;padding:3px 6px 3px 10px;font-size:12px}
.rcp-chip .x{cursor:pointer;border:none;background:transparent;color:var(--blue-dark);font-size:14px;line-height:1}
.check{display:flex;align-items:flex-start;gap:9px;font-size:13px;background:var(--surface2);
  border-radius:8px;padding:11px 12px;cursor:pointer;margin-top:6px}
.check input{margin-top:2px;width:16px;height:16px;accent-color:var(--blue)}
.check small{display:block;color:var(--muted);font-size:11.5px;margin-top:2px}
.linkbox{display:flex;gap:8px;margin-top:10px}
.linkbox input{flex:1;padding:9px 11px;border:1px solid var(--border);border-radius:7px;font-size:12px;background:var(--surface2)}
.msg-area{width:100%;min-height:64px;padding:9px 11px;border:1px solid var(--border);border-radius:7px;
  font-size:13px;font-family:inherit;resize:vertical;background:#fff}
.msg-area:focus{outline:none;border-color:var(--blue)}
.ext-sep{text-align:center;color:#9a9aa8;font-size:11px;margin:20px 0 8px;letter-spacing:1px}
#toast{position:fixed;bottom:18px;left:50%;transform:translateX(-50%);background:#161616;color:#fff;
  padding:10px 18px;border-radius:8px;font-size:13px;opacity:0;transition:.25s;pointer-events:none;z-index:300;max-width:90vw}
#toast.show{opacity:1}
#toast.err{background:var(--red)}
#toast.ok{background:var(--green)}
@media(max-width:760px){#side{width:64px;padding:14px 6px}.nav-item span:not(.ic):not(.nav-pill){display:none}
  .btn-new span{display:none}#quota{display:none}.folder-tree{display:none !important}}
</style>
</head>
<body>
<div id="app">
  <div id="topbar">
    <span class="logo"><span data-i18n="title">Fichiers</span></span>
    <span class="spacer"></span>
    <span class="avatar" id="avatar">·</span>
  </div>
  <div id="wrap">
    <div id="side">
      <div id="new-row">
        <button class="btn-new" id="btn-new">＋ <span data-i18n="new_btn">Nouveau</span></button>
        <button class="searchbtn" id="btn-search" title="Rechercher">🔍</button>
      </div>
      <div id="searchbox"><input id="search" data-i18n-ph="search" placeholder="Rechercher…"></div>
      <div class="nav">
        <button class="nav-item" data-view="recent"><span class="ic">🕐</span><span data-i18n="recent">Récents</span></button>
        <button class="nav-item active" data-view="drive"><span class="ic">👤</span><span data-i18n="my_files">Mes fichiers</span></button>
        <div class="folder-tree" id="folders"></div>
        <button class="nav-item" data-view="shared"><span class="ic">👥</span><span data-i18n="shared_with_me">Partagés avec moi</span><span class="nav-pill" id="pill-shared" style="display:none"></span></button>
        <button class="nav-item" data-view="favorites"><span class="ic">★</span><span data-i18n="favorites">Favoris</span></button>
        <div class="nav-sep"></div>
        <button class="nav-item" data-view="trash"><span class="ic">🗑</span><span data-i18n="trash">Corbeille</span><span class="nav-pill" id="pill-trash" style="display:none"></span></button>
      </div>
      <div id="quota"><span data-i18n="quota_used">Espace utilisé</span> : <span id="quota-val">—</span>
        <span class="gauge"><i id="quota-bar"></i></span></div>
    </div>

    <div id="main">
      <div id="filters">
        <select class="type-sel" id="type-filter">
          <option value="" data-i18n="type_all">Type : Tous</option>
          <option value="docs" data-i18n="type_docs">Documents</option>
          <option value="images" data-i18n="type_images">Images</option>
          <option value="pdf" data-i18n="type_pdf">PDF</option>
          <option value="sheets" data-i18n="type_sheets">Tableurs</option>
          <option value="other" data-i18n="type_other">Autres</option>
        </select>
      </div>
      <div id="card">
        <div id="card-head">
          <div id="card-title"><span id="view-name" data-i18n="my_files">Mes fichiers</span></div>
          <div id="card-actions">
            <button class="link-act" id="btn-import">⬆ <span data-i18n="import_btn">Importer</span></button>
            <button class="iconcircle" id="btn-newfolder" title="Nouveau dossier">📁⁺</button>
          </div>
        </div>
        <div id="dropzone" data-i18n="dropzone">Glissez vos fichiers ici ou cliquez pour téléverser</div>
        <div id="body"></div>
      </div>
    </div>
  </div>
</div>

<input type="file" id="file-input" multiple style="display:none">
<div class="menu" id="row-menu"></div>

<!-- Modale import -->
<div class="modal-bg" id="up-bg"><div class="modal">
  <div class="mh">⬆ <span data-i18n="import_title">Importer des fichiers</span></div>
  <div class="mb">
    <div class="field-lbl" data-i18n="permanent">Conservation</div>
    <div class="seg-wrap" id="up-type">
      <button class="seg active" data-up="perm" data-i18n="permanent">Permanent</button>
      <button class="seg" data-up="eph" data-i18n="ephemeral_file">Fichier éphémère</button>
    </div>
    <label class="check"><input type="checkbox" id="up-restrict" checked>
      <span><b data-i18n="restrict_dl">Téléchargement réservé aux destinataires</b>
      <small data-i18n="restrict_dl_hint">Le fichier ne sera téléchargeable que par ses destinataires connectés. Un lien recopié ailleurs sera refusé.</small></span></label>
    <div style="margin-top:16px;display:flex;justify-content:flex-end">
      <button class="btn" id="up-pick">📂 <span data-i18n="choose_files">Choisir des fichiers…</span></button>
    </div>
  </div>
  <div class="mf"><button class="btn ghost" id="up-close" data-i18n="close">Fermer</button></div>
</div></div>

<!-- Modale partage / envoi -->
<div class="modal-bg" id="modal-bg"><div class="modal">
  <div class="mh" id="modal-title">📨 <span data-i18n="share">Partager</span></div>
  <div class="mb" id="modal-body"></div>
  <div class="mf"><button class="btn ghost" id="modal-close" data-i18n="close">Fermer</button></div>
</div></div>

<div id="toast"></div>

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
function t(k){
  return (I18N[LANG] && I18N[LANG][k]) || (I18N["en"] && I18N["en"][k]) || k;
}
function tok(){ return parentLS("scribe_token"); }
function bust(path){ return path + (path.indexOf("?") >= 0 ? "&" : "?") + "_t=" + Date.now(); }
function api(path, opts){
  opts = opts || {};
  opts.headers = opts.headers || {};
  opts.headers["Authorization"] = "Bearer " + tok();
  return fetch("/api/v1/fichiers" + path, opts);
}
function originBase(){
  try{ return window.parent.location.origin; }catch(e){ return location.origin; }
}
function applyI18n(){
  document.querySelectorAll("[data-i18n]").forEach(function(el){
    el.textContent = t(el.getAttribute("data-i18n"));
  });
  document.querySelectorAll("[data-i18n-ph]").forEach(function(el){
    el.setAttribute("placeholder", t(el.getAttribute("data-i18n-ph")));
  });
  document.documentElement.setAttribute("lang", LANG);
}
function esc(s){ return String(s==null?"":s).replace(/[&<>"]/g,function(c){
  return {"&":"&amp;","<":"&lt;",">":"&gt;","\"":"&quot;"}[c]; }); }
function fmtSize(n){
  n = +n || 0;
  if (n < 1024) return n + " o";
  if (n < 1048576) return (n/1024).toFixed(1) + " Ko";
  if (n < 1073741824) return (n/1048576).toFixed(1) + " Mo";
  return (n/1073741824).toFixed(2) + " Go";
}
function fmtDate(s){
  if(!s) return "—";
  try{ var d = new Date(s);
    return d.toLocaleDateString(LANG, {day:"2-digit",month:"2-digit",year:"numeric"}) +
      " " + d.toLocaleTimeString(LANG, {hour:"2-digit",minute:"2-digit"}); }
  catch(e){ return s; }
}
function iconFor(mime){
  mime = (mime||"").toLowerCase();
  if (mime.indexOf("image") === 0) return "🖼";
  if (mime.indexOf("pdf") >= 0) return "📕";
  if (mime.indexOf("video") === 0) return "🎬";
  if (mime.indexOf("audio") === 0) return "🎵";
  if (mime.indexOf("zip") >= 0 || mime.indexOf("compressed") >= 0) return "🗜";
  if (mime.indexOf("sheet") >= 0 || mime.indexOf("excel") >= 0 || mime.indexOf("csv") >= 0) return "📊";
  if (mime.indexOf("word") >= 0 || mime.indexOf("document") >= 0) return "📄";
  if (mime.indexOf("text") === 0) return "📃";
  return "📎";
}
function categoryOf(mime){
  mime = (mime||"").toLowerCase();
  if (mime.indexOf("image") === 0) return "images";
  if (mime.indexOf("pdf") >= 0) return "pdf";
  if (mime.indexOf("sheet") >= 0 || mime.indexOf("excel") >= 0 || mime.indexOf("csv") >= 0) return "sheets";
  if (mime.indexOf("word") >= 0 || mime.indexOf("document") >= 0 || mime.indexOf("text") === 0) return "docs";
  return "other";
}
var toastT;
function toast(msg, kind){
  var el = document.getElementById("toast");
  el.textContent = msg; el.className = "show " + (kind||"");
  clearTimeout(toastT); toastT = setTimeout(function(){ el.className = ""; }, 2600);
}
function err(){ toast(t("error"), "err"); }

// ── État ─────────────────────────────────────────────────────────────────
var VIEW = "drive";
var CURRENT_FOLDER = null;
var FOLDERS = [];
var UPLOAD_TYPE = "perm";
var RESTRICT_DL = true;
var TYPE_FILTER = "";
var ME_NAME = "";
var SHARED_FOLDERS = [];
var SHARED_DATA = [];
var SHARED_SEL = "all";   // all | root | <id dossier>
var ME_UID = null;
var ACCOUNTS = {users:[], etabs:[], loaded:false};
var SHARE = null;
var ROWS = {};       // id -> fichier (pour le menu d'actions)
var MODE = "drive";  // mode de la liste courante

var VIEW_KEY  = {recent:"recent", drive:"my_files", shared:"shared_with_me", favorites:"favorites", trash:"trash"};

function setView(v){
  VIEW = v;
  document.querySelectorAll(".nav-item").forEach(function(b){
    b.classList.toggle("active", b.getAttribute("data-view") === v);
  });
  var showImport = (v === "drive" || v === "recent");
  document.getElementById("card-actions").style.display = showImport ? "" : "none";
  document.getElementById("dropzone").style.display = (v === "drive") ? "" : "none";
  document.getElementById("folders").classList.toggle("show", v === "drive");
  document.getElementById("view-name").textContent = t(VIEW_KEY[v] || "my_files");
  closeMenu();
  refresh();
}

// ── Rendu ────────────────────────────────────────────────────────────────
function renderFolders(){
  var box = document.getElementById("folders");
  var html = '<div class="fchip ' + (CURRENT_FOLDER==null?"active":"") +
    '" data-folder="">🏠 ' + esc(t("root")) + "</div>";
  var byParent = {};
  FOLDERS.forEach(function(d){
    var p = (d.parent_id == null ? "" : String(d.parent_id));
    (byParent[p] = byParent[p] || []).push(d);
  });
  function emit(parentKey, depth){
    if (depth > 20) return;
    (byParent[parentKey] || []).forEach(function(d){
      var pad = 9 + depth * 14;
      html += '<div class="fchip ' + (String(CURRENT_FOLDER)===String(d.id)?"active":"") +
        '" data-folder="' + d.id + '" style="padding-left:' + pad + 'px">' +
        '<span style="flex:1;overflow:hidden;text-overflow:ellipsis;white-space:nowrap">📂 ' + esc(d.nom) + "</span>" +
        '<button class="fdots" data-fmenu="' + d.id + '" title="' + esc(t("folder_actions")) + '">⋯</button></div>';
      emit(String(d.id), depth + 1);
    });
  }
  emit("", 0);
  box.innerHTML = html;
}

function rowHtml(f, mode){
  if (mode === "shared"){
    var st = f.actif ? '<span class="statepill on">' + esc(t("ephemeral_active")) + "</span>"
                     : '<span class="statepill off">' + esc(t("ephemeral_used")) + "</span>";
    var ephTag = f.ephemere ? ' <span class="tag-eph">' + esc(t("ephemeral")) + "</span>" : "";
    return '<tr class="row"><td><div class="fname"><span class="ftype">📄</span><div>' +
      esc(f.nom) + ephTag + "<div class=\"sub\">" + st + "</div></div></div></td>" +
      '<td class="muted">' + fmtDate(f.created_at) + "</td>" +
      '<td class="muted">' + esc(f.expediteur || "—") + "</td>" +
      '<td class="amen"><button class="dots" data-act="menu" data-id="' + f.id + '">⋯</button></td></tr>';
  }
  var badges = "";
  var unavail = (f.disponible === false);
  if (unavail) badges += ' <span class="tag-unavail" style="background:#fff5ed;color:#b34000;border:1px solid #f0c080;padding:1px 6px;border-radius:4px;font-size:10px;white-space:nowrap">⚠ ' + esc(t("content_missing")) + "</span>";
  if (f.ephemere) badges += ' <span class="tag-eph">' + esc(t("ephemeral")) + "</span>";
  if (f.download_restreint) badges += ' <span class="tag-lock">🔒 ' + esc(t("restricted_badge")) + "</span>";
  if (f.contient_donnees_patient) badges += ' <span class="tag-pat">' + esc(t("patient_data")) + "</span>";
  var favmark = f.favori ? ' <span style="color:#eab308">★</span>' : "";
  return '<tr class="row"' + (unavail ? ' style="opacity:.55"' : '') + '><td><div class="fname"><span class="ftype">' + iconFor(f.mime) + "</span><div>" +
    esc(f.nom) + favmark + badges + '<div class="sub muted" style="font-size:11.5px">' + fmtSize(f.taille) + "</div></div></div></td>" +
    '<td class="muted">' + fmtDate(f.updated_at || f.created_at) + "</td>" +
    '<td class="muted">' + esc(ME_NAME || "—") + "</td>" +
    '<td class="amen"><button class="dots" data-act="menu" data-id="' + f.id + '">⋯</button></td></tr>';
}

function applyTypeFilter(list){
  if (!TYPE_FILTER) return list;
  return list.filter(function(f){ return categoryOf(f.mime) === TYPE_FILTER; });
}

function renderTable(list, mode){
  MODE = mode; ROWS = {};
  var body = document.getElementById("body");
  if (mode !== "shared") list = applyTypeFilter(list);
  if (!list.length){
    body.innerHTML = '<div class="empty">' + esc(t("empty")) + "</div>";
    return;
  }
  var col2 = (mode === "shared") ? esc(t("created")) : esc(t("col_modified"));
  var html = "<table><thead><tr>" +
    "<th>" + esc(t("name")) + ' <span class="sort">↕</span></th>' +
    "<th>" + col2 + ' <span class="sort">↕</span></th>' +
    "<th>" + esc(t("col_author")) + ' <span class="sort">↕</span></th>' +
    "<th></th></tr></thead><tbody>";
  list.forEach(function(f){ ROWS[f.id] = f; html += rowHtml(f, mode); });
  html += "</tbody></table>";
  body.innerHTML = html;
}

// ── Menu d'actions (position fixe, hors iframe-clip) ─────────────────────────
function menuItems(f, mode){
  if (mode === "shared"){
    var dl = '<button class="mi" data-act="dlshare" data-url="' + esc(f.url||"") + '" data-ext="' + (f.external ? "1" : "0") + '" data-nom="' + esc(f.nom) + '"><span class="ic">⬇</span>' + esc(t("download")) + "</button>";
    if (f.federe) return dl;  // partage fédéré : non rangeable (fichier distant)
    return dl + '<button class="mi" data-act="moveshare" data-pid="' + f.id + '"><span class="ic">📁</span>' + esc(t("move_to")) + "</button>";
  }
  if (mode === "trash"){
    return '<button class="mi" data-act="restore" data-id="' + f.id + '"><span class="ic">↩</span>' + esc(t("restore")) + "</button>" +
           '<button class="mi danger" data-act="purge" data-id="' + f.id + '"><span class="ic">⊘</span>' + esc(t("purge")) + "</button>";
  }
  return '<button class="mi" data-act="dl" data-id="' + f.id + '"><span class="ic">⬇</span>' + esc(t("download")) + "</button>" +
    '<button class="mi" data-act="share" data-id="' + f.id + '" data-nom="' + esc(f.nom) +
      '" data-eph="' + (f.ephemere?"1":"0") + '" data-restr="' + (f.download_restreint?"1":"0") + '"><span class="ic">📨</span>' + esc(t("share")) + "</button>" +
    '<button class="mi" data-act="fav" data-id="' + f.id + '"><span class="ic">★</span>' + esc(f.favori?t("unfavorite"):t("favorite")) + "</button>" +
    '<button class="mi" data-act="ren" data-id="' + f.id + '" data-nom="' + esc(f.nom) + '"><span class="ic">✎</span>' + esc(t("rename")) + "</button>" +
    '<button class="mi danger" data-act="del" data-id="' + f.id + '"><span class="ic">🗑</span>' + esc(t("delete")) + "</button>";
}
function openRowMenu(id, btn){
  var f = ROWS[id]; if (!f) return;
  var m = document.getElementById("row-menu");
  m.innerHTML = menuItems(f, MODE);
  m.setAttribute("data-for", String(id));
  m.classList.add("open");
  var r = btn.getBoundingClientRect();
  var mw = m.offsetWidth, mh = m.offsetHeight;
  var left = Math.min(r.right - mw, window.innerWidth - mw - 8);
  if (left < 8) left = 8;
  var top = r.bottom + 4;
  if (top + mh > window.innerHeight - 8) top = Math.max(8, r.top - mh - 4);
  m.style.left = left + "px";
  m.style.top = top + "px";
}
function closeMenu(){
  var m = document.getElementById("row-menu");
  if (m){ m.classList.remove("open"); m.removeAttribute("data-for"); }
}
function positionMenu(btn){
  var m = document.getElementById("row-menu");
  var r = btn.getBoundingClientRect();
  var mw = m.offsetWidth, mh = m.offsetHeight;
  var left = Math.min(r.right - mw, window.innerWidth - mw - 8); if (left < 8) left = 8;
  var top = r.bottom + 4; if (top + mh > window.innerHeight - 8) top = Math.max(8, r.top - mh - 4);
  m.style.left = left + "px"; m.style.top = top + "px";
}
function openMenuHtml(btn, html, key){
  var m = document.getElementById("row-menu");
  m.innerHTML = html;
  m.setAttribute("data-for", key || "_html");
  m.classList.add("open");
  positionMenu(btn);
}

// ── Chargements ────────────────────────────────────────────────────────────
function loadQuota(){
  api(bust("/quota")).then(function(r){ return r.json(); }).then(function(d){
    var used = d.utilise || 0, max = d.max_fichier || 1;
    document.getElementById("quota-val").textContent = fmtSize(used);
    var pct = Math.min(100, Math.round(used / max * 100));
    document.getElementById("quota-bar").style.width = pct + "%";
  }).catch(function(){});
}
function loadFolders(){
  return api(bust("/tree")).then(function(r){ return r.json(); }).then(function(d){
    FOLDERS = Array.isArray(d) ? d : []; renderFolders();
  }).catch(function(){ FOLDERS = []; renderFolders(); });
}
function pill(name, n){
  var el = document.getElementById("pill-" + name);
  if (!el) return;
  el.textContent = n; el.style.display = n ? "" : "none";
}
function sortByDateDesc(list){
  return (list||[]).slice().sort(function(a,b){
    return new Date(b.updated_at||b.created_at||0) - new Date(a.updated_at||a.created_at||0);
  });
}
function refresh(){
  loadQuota();
  if (VIEW === "drive"){
    loadFolders();
    var q = (document.getElementById("search").value || "").trim();
    if (q){
      api(bust("/search?q=" + encodeURIComponent(q))).then(function(r){ return r.json(); })
        .then(function(d){ renderTable(d||[], "drive"); }).catch(err);
    } else {
      var path = CURRENT_FOLDER ? "/list?dossier_id=" + CURRENT_FOLDER : "/list";
      api(bust(path)).then(function(r){ return r.json(); })
        .then(function(d){ renderTable(d||[], "drive"); }).catch(err);
    }
  } else if (VIEW === "recent"){
    api(bust("/list")).then(function(r){ return r.json(); })
      .then(function(d){ renderTable(sortByDateDesc(d).slice(0,50), "drive"); }).catch(err);
  } else if (VIEW === "favorites"){
    api(bust("/favoris")).then(function(r){ return r.json(); })
      .then(function(d){ renderTable(d||[], "drive"); }).catch(err);
  } else if (VIEW === "trash"){
    api(bust("/corbeille")).then(function(r){ return r.json(); }).then(function(d){
      renderTable(d||[], "trash"); pill("trash", (d||[]).length);
    }).catch(err);
  } else if (VIEW === "shared"){
    Promise.all([
      api(bust("/partages-dossiers")).then(function(r){ return r.ok ? r.json() : []; }).catch(function(){ return []; }),
      api(bust("/partages")).then(function(r){ return r.ok ? r.json() : []; }).catch(function(){ return []; })
    ]).then(function(res){
      SHARED_FOLDERS = res[0] || [];
      SHARED_DATA = res[1] || [];
      pill("shared", SHARED_DATA.filter(function(x){ return x.actif; }).length);
      renderSharedView();
    }).catch(err);
  }
}

function renderSharedView(){
  var body = document.getElementById("body");
  function chip(key, label, count, actions){
    var on = (String(SHARED_SEL) === String(key));
    return '<span class="sfchip" data-sfsel="' + key + '" style="display:inline-flex;align-items:center;gap:6px;padding:5px 11px;border-radius:16px;border:1px solid ' +
      (on ? '#003189' : 'var(--line,#e2e8f0)') + ';background:' + (on ? 'rgba(0,49,137,.08)' : '#fff') +
      ';cursor:pointer;font-size:12px;white-space:nowrap">' + label +
      (count != null ? (' <span style="color:#64748b;font-size:11px">' + count + '</span>') : '') + (actions || '') + '</span>';
  }
  var rootCount = SHARED_DATA.filter(function(x){ return !x.dossier_dest_id; }).length;
  var bar = '<div style="display:flex;gap:8px;flex-wrap:wrap;align-items:center;padding:4px 0 14px">';
  bar += chip("all", "📥 " + t("all_shares"), SHARED_DATA.length, "");
  bar += chip("root", "🏠 " + t("shared_root"), rootCount, "");
  SHARED_FOLDERS.forEach(function(d){
    var acts = ' <span class="sffa" data-sfren="' + d.id + '" title="' + esc(t("rename")) + '" style="opacity:.55;padding:0 1px">✎</span>' +
               '<span class="sffa" data-sfdel="' + d.id + '" title="' + esc(t("delete")) + '" style="opacity:.55;padding:0 1px">🗑</span>';
    bar += chip(d.id, "📁 " + esc(d.nom), d.count, acts);
  });
  bar += '<span data-sfnew="1" style="cursor:pointer;color:#003189;font-size:12px;padding:5px 8px;font-weight:600">＋ ' + esc(t("new_folder")) + '</span>';
  bar += '</div>';
  var list = SHARED_DATA.filter(function(x){
    if (SHARED_SEL === "all") return true;
    if (SHARED_SEL === "root") return !x.dossier_dest_id;
    return String(x.dossier_dest_id) === String(SHARED_SEL);
  });
  renderTable(list, "shared");
  body.innerHTML = bar + body.innerHTML;
}

// ── Upload ─────────────────────────────────────────────────────────────────
function doUpload(files){
  if (!files || !files.length) return;
  var total = files.length, done = 0;
  toast(t("uploading"));
  Array.prototype.forEach.call(files, function(file){
    var fd = new FormData();
    fd.append("file", file);
    if (CURRENT_FOLDER) fd.append("dossier_id", CURRENT_FOLDER);
    if (UPLOAD_TYPE === "eph") fd.append("ephemere", "1");
    fd.append("download_restreint", RESTRICT_DL ? "1" : "0");
    api("/upload", {method:"POST", body:fd}).then(function(r){
      done++;
      if (!r.ok){ toast(t("error") + " (" + r.status + ")", "err"); }
      if (done === total){ toast(t("upload"), "ok"); refresh(); }
    }).catch(function(){ done++; err(); if (done === total) refresh(); });
  });
}
function newFolder(){
  var nom = prompt(t("folder_name_prompt"));
  if (!nom) return;
  var fd = new FormData(); fd.append("nom", nom);
  if (CURRENT_FOLDER) fd.append("parent_id", CURRENT_FOLDER);
  api("/dossier", {method:"POST", body:fd}).then(function(r){
    if (r.ok){ loadFolders(); } else err();
  }).catch(err);
}

// ── Comptes (users locaux + établissements fédérés) ─────────────────────────
function loadAccounts(){
  if (ACCOUNTS.loaded) return Promise.resolve();
  var pU = fetch("/api/v1/auth/users", {headers:{Authorization:"Bearer "+tok()}})
    .then(function(r){ return r.ok ? r.json() : []; })
    .then(function(d){ ACCOUNTS.users = (d||[]).filter(function(u){ return u.active !== false; }); })
    .catch(function(){ ACCOUNTS.users = []; });
  var pE = fetch("/api/v1/messagerie/correspondants-federes", {headers:{Authorization:"Bearer "+tok()}})
    .then(function(r){ return r.ok ? r.json() : {}; })
    .then(function(d){ ACCOUNTS.etabs = (d && d.etablissements) || []; })
    .catch(function(){ ACCOUNTS.etabs = []; });
  return Promise.all([pU, pE]).then(function(){ ACCOUNTS.loaded = true; });
}

function openShareModal(id, nom, fileEph, restr){
  SHARE = {fid:id, nom:nom, fileEph:!!fileEph, restreint:!!restr,
           mode: fileEph ? "eph" : "perm", recipients:[]};
  document.getElementById("modal-title").innerHTML = "📨 " + esc(t("share"));
  document.getElementById("modal-bg").classList.add("show");
  loadAccounts().then(renderShareModal);
}

function localUids(){
  return SHARE.recipients.filter(function(r){ return r.type === "user"; })
    .map(function(r){ return r.value; });
}

function renderShareModal(){
  var mb = document.getElementById("modal-body");
  var modeHtml = "";
  if (!SHARE.fileEph){
    modeHtml = '<div class="field-lbl">' + esc(t("link_mode")) + "</div>" +
      '<div class="seg-wrap" style="margin-bottom:4px">' +
        '<button class="seg ' + (SHARE.mode==="perm"?"active":"") + '" data-mode="perm">' + esc(t("link_permanent")) + "</button>" +
        '<button class="seg ' + (SHARE.mode==="eph"?"active":"") + '" data-mode="eph">' + esc(t("link_ephemeral")) + "</button>" +
      "</div>";
  } else {
    modeHtml = '<div class="info">' + esc(t("ephemeral_file_info")) + "</div>";
  }
  if (SHARE.restreint){
    modeHtml += '<div class="info">🔒 ' + esc(t("restricted_share_info")) + "</div>";
  }
  var opts = '<option value="">' + esc(t("choose")) + "</option>";
  opts += '<optgroup label="' + esc(t("external")) + '">' +
    '<option value="email">✉ ' + esc(t("email_recipient")) + "</option>" +
    '<option value="sms">📱 ' + esc(t("sms_recipient")) + "</option></optgroup>";
  if (ACCOUNTS.users.length){
    opts += '<optgroup label="' + esc(t("users")) + '">';
    ACCOUNTS.users.forEach(function(u){
      opts += '<option value="u:' + u.id + '">' + esc(u.display_name || u.username) +
        (u.role ? " (" + esc(u.role) + ")" : "") + "</option>";
    });
    opts += "</optgroup>";
  }
  if (ACCOUNTS.etabs.length){
    opts += '<optgroup label="' + esc(t("establishments")) + '">';
    ACCOUNTS.etabs.forEach(function(e){
      opts += '<option value="e:' + esc(e.sigle) + '">🏥 ' + esc(e.sigle) + "</option>";
      (e.agents||[]).forEach(function(a){
        opts += '<option value="a:' + esc(e.sigle) + ":" + esc(a.username) + '">— ' +
          esc(a.display_name || a.username) + " · " + esc(e.sigle) + "</option>";
      });
    });
    opts += "</optgroup>";
  }
  mb.innerHTML = modeHtml +
    '<div class="field-lbl">' + esc(t("recipients")) + "</div>" +
    '<div style="display:flex;gap:8px">' +
      '<select class="rcp-pick" id="rcp-select">' + opts + "</select>" +
      '<button class="btn sm" id="rcp-add">+ ' + esc(t("add")) + "</button></div>" +
    '<div id="rcp-extra-row" style="display:none;margin-top:8px">' +
      '<input id="rcp-extra" class="rcp-pick" type="text" autocomplete="off" placeholder=""></div>' +
    '<div class="rcp-chips" id="rcp-chips"></div>' +
    '<div class="muted" id="rcp-hint" style="font-size:12px;margin-top:8px">' + esc(t("no_recipients_hint")) + "</div>" +
    '<div class="field-lbl">' + esc(t("optional_message")) + "</div>" +
    '<textarea class="msg-area" id="share-msg" placeholder="' + esc(t("optional_message")) + '"></textarea>' +
    '<div style="margin-top:14px;display:flex;justify-content:flex-end;gap:9px">' +
      '<button class="btn ghost" id="share-link">🔗 ' + esc(t("generate_link")) + "</button>" +
      '<button class="btn" id="share-send">📨 ' + esc(t("send")) + "</button></div>" +
    '<div id="share-result" style="margin-top:14px"></div>';

  mb.querySelectorAll(".seg[data-mode]").forEach(function(b){
    b.onclick = function(){ SHARE.mode = b.getAttribute("data-mode"); renderShareModal(); };
  });
  document.getElementById("rcp-add").onclick = shareAddRecipient;
  document.getElementById("share-send").onclick = shareSend;
  document.getElementById("share-link").onclick = shareGenerate;
  var rsel = document.getElementById("rcp-select");
  if (rsel) rsel.onchange = function(){
    var row = document.getElementById("rcp-extra-row");
    var inp = document.getElementById("rcp-extra");
    if (this.value === "email" || this.value === "sms"){
      if (row) row.style.display = "block";
      if (inp){ inp.placeholder = (this.value === "email") ? t("enter_email") : t("enter_phone");
                inp.value = ""; inp.focus(); }
    } else if (row){ row.style.display = "none"; }
  };
  var rextra = document.getElementById("rcp-extra");
  if (rextra) rextra.onkeydown = function(e){ if (e.key === "Enter"){ e.preventDefault(); shareAddRecipient(); } };
  renderShareChips();
}

function renderShareChips(){
  var box = document.getElementById("rcp-chips");
  if (!box) return;
  box.innerHTML = SHARE.recipients.map(function(r, i){
    var ic = r.type === "user" ? "👤" : (r.type === "instance" ? "🏥"
           : (r.type === "email" ? "✉" : (r.type === "sms" ? "📱" : "🧑‍⚕️")));
    return '<span class="rcp-chip">' + ic + ' <b>' + esc(r.display) + "</b>" +
      '<button class="x" data-i="' + i + '">×</button></span>';
  }).join("");
  box.querySelectorAll(".x").forEach(function(b){
    b.onclick = function(){ SHARE.recipients.splice(+b.getAttribute("data-i"), 1); renderShareChips(); };
  });
  var hint = document.getElementById("rcp-hint");
  if (hint) hint.style.display = SHARE.recipients.length ? "none" : "";
}

function shareAddRecipient(){
  var sel = document.getElementById("rcp-select");
  var v = sel.value;
  if (!v){ return; }
  var rec = null;
  if (v === "email"){
    var ei = document.getElementById("rcp-extra");
    var em = ((ei && ei.value) || "").trim();
    if (em.indexOf("@") < 1){ toast(t("invalid_email"), "err"); if (ei) ei.focus(); return; }
    rec = {type:"email", value:em, display:em};
  } else if (v === "sms"){
    var pi = document.getElementById("rcp-extra");
    var ph = ((pi && pi.value) || "").trim();
    if (ph.replace(/\D/g, "").length < 6){ toast(t("invalid_phone"), "err"); if (pi) pi.focus(); return; }
    rec = {type:"sms", value:ph, display:maskPhone(ph)};
  } else if (v.indexOf("u:") === 0){
    var uid = parseInt(v.slice(2), 10);
    var u = ACCOUNTS.users.find(function(x){ return x.id === uid; });
    if (u) rec = {type:"user", value:uid, display:(u.display_name||u.username)};
  } else if (v.indexOf("e:") === 0){
    var sg = v.slice(2);
    rec = {type:"instance", value:sg, display:sg};
  } else if (v.indexOf("a:") === 0){
    var p = v.split(":"); var sg2 = p[1]; var un = p.slice(2).join(":");
    rec = {type:"agent_federe", value:un, etab:sg2, display:un + " · " + sg2};
  }
  if (!rec) return;
  var dup = SHARE.recipients.some(function(r){
    return r.type === rec.type && String(r.value) === String(rec.value) && (r.etab||"") === (rec.etab||""); });
  if (!dup) SHARE.recipients.push(rec);
  sel.value = "";
  var er = document.getElementById("rcp-extra-row"); if (er) er.style.display = "none";
  var ex = document.getElementById("rcp-extra"); if (ex) ex.value = "";
  renderShareChips();
}

function maskPhone(p){
  var d = (p || "").replace(/\s/g, "");
  return d.length > 5 ? d.slice(0, 3) + "…" + d.slice(-2) : d;
}

// ── Envoyer : source unique de destinataires, routée par type ───────────────
//   user → inbox sécurisée ; instance/agent → lien fédéré + message ;
//   email → pli (lien par e-mail, mot de passe affiché) ; sms → pli (mdp par SMS).
function shareSend(){
  var recips = SHARE.recipients;
  var uids  = recips.filter(function(r){ return r.type === "user"; }).map(function(r){ return r.value; });
  var feds  = recips.filter(function(r){ return r.type === "instance" || r.type === "agent_federe"; });
  var mails = recips.filter(function(r){ return r.type === "email"; });
  var smss  = recips.filter(function(r){ return r.type === "sms"; });
  if (!uids.length && !feds.length && !mails.length && !smss.length){ toast(t("need_recipient"), "err"); return; }
  var btn = document.getElementById("share-send"); if (btn) btn.disabled = true;
  var msg = (document.getElementById("share-msg") || {}).value || "";
  var eph = (SHARE.mode === "eph");
  var okAll = true;
  var blocks = [];
  var errs = [];
  var tasks = [];

  if (uids.length){
    var fd = new FormData();
    fd.append("fichier_id", SHARE.fid);
    fd.append("destinataires_uids", uids.join(","));
    if (eph) fd.append("ephemere", "1");
    if (msg.trim()) fd.append("message", msg.trim());
    tasks.push(api("/envoyer", {method:"POST", body:fd})
      .then(function(r){ if (!r.ok) okAll = false; }).catch(function(){ okAll = false; }));
  }
  if (feds.length){
    tasks.push(createShare().then(function(d){
      if (!d || !d.url){ okAll = false; return; }
      return sendShareMessage(feds, originBase() + d.url, msg).then(function(ok){ if (!ok) okAll = false; });
    }).catch(function(){ okAll = false; }));
  }
  mails.forEach(function(r){
    var fdm = new FormData();
    fdm.append("fichier_id", SHARE.fid);
    fdm.append("emails", r.value);
    if (eph) fdm.append("ephemere", "1");
    tasks.push(api("/partage-protege-mail", {method:"POST", body:fdm})
      .then(function(rr){
        if (rr.ok) return rr.json();
        okAll = false;
        return rr.json().then(function(j){ errs.push((j && j.detail) || ("HTTP " + rr.status)); return null; },
                              function(){ errs.push("HTTP " + rr.status); return null; });
      })
      .then(function(d){ if (d) blocks.push(mailResultBlock(r.value, d.password)); })
      .catch(function(){ okAll = false; }));
  });
  smss.forEach(function(r){
    var fds = new FormData();
    fds.append("fichier_id", SHARE.fid);
    fds.append("telephone", r.value);
    if (eph) fds.append("ephemere", "1");
    tasks.push(api("/partage-protege", {method:"POST", body:fds})
      .then(function(rr){
        if (rr.ok) return rr.json();
        okAll = false;
        return rr.json().then(function(j){ errs.push((j && j.detail) || ("HTTP " + rr.status)); return null; },
                              function(){ errs.push("HTTP " + rr.status); return null; });
      })
      .then(function(d){ if (d) blocks.push(smsResultBlock(d.telephone_masque || r.display, originBase() + d.url)); })
      .catch(function(){ okAll = false; }));
  });

  Promise.all(tasks).then(function(){
    var res = document.getElementById("share-result");
    if (res){
      var head = okAll ? ("✅ " + esc(t("sent_ok")))
                       : ("⚠ " + esc(t("error")) + (errs.length ? " — " + esc(errs[0]) : ""));
      res.innerHTML = '<div class="info" style="border-left-color:' + (okAll?"#18753c":"#e1000f") + '">' +
        head + "</div>" + blocks.join("");
      res.querySelectorAll("[data-copy]").forEach(function(b){
        b.onclick = function(){ copyText(b.getAttribute("data-copy")); };
      });
    }
    toast(okAll ? t("sent_ok") : t("error"), okAll ? "ok" : "err");
    if (btn) btn.disabled = false;
    refresh();
  });
}

// Bloc résultat e-mail : mot de passe à transmettre hors-bande (affiché).
function mailResultBlock(email, pwd){
  return '<div class="field-lbl">' + esc(t("password_to_send")) + " — " + esc(email) + "</div>" +
    '<div class="linkbox"><input readonly value="' + esc(pwd) +
      '" style="font-weight:700;letter-spacing:3px;text-align:center;font-size:16px">' +
    '<button class="btn sm" data-copy="' + esc(pwd) + '">📋 ' + esc(t("copy")) + "</button></div>" +
    '<div class="muted" style="font-size:11.5px;margin-top:6px">🔐 ' + esc(t("password_oob_hint")) + "</div>";
}
// Bloc résultat SMS : lien à transmettre (le mot de passe est parti par SMS).
function smsResultBlock(masque, link){
  return '<div class="info" style="border-left-color:#18753c">✅ ' + esc(t("pli_sent")) + " " + esc(masque) + "</div>" +
    '<div class="linkbox"><input readonly value="' + esc(link) + '">' +
    '<button class="btn sm" data-copy="' + esc(link) + '">📋 ' + esc(t("copy_link")) + "</button></div>" +
    '<div class="muted" style="font-size:11.5px;margin-top:6px">' + esc(t("pli_forward_hint")) + "</div>";
}

function shareMsgBody(link, extra){
  var who = ME_NAME || parentLS("scribe_display_name") || "";
  var intro = (who ? (who + " ") : "") + t("share_msg_intro");
  var head = (extra && extra.trim()) ? (extra.trim() + "\n\n") : "";
  return head + "📁 " + intro + " :\n[url=" + link + "]" + (SHARE.nom||"") + "[/url]";
}
function sendShareMessage(recipients, link, extra){
  if (!recipients.length) return Promise.resolve(true);
  var fd = new FormData();
  fd.append("canal", "interne");
  fd.append("sujet", "📁 " + t("share_msg_subject") + " — " + (SHARE.nom||""));
  fd.append("contenu", shareMsgBody(link, extra));
  fd.append("destinataires_json", JSON.stringify(recipients));
  return fetch("/api/v1/messagerie/messages", {
    method:"POST", headers:{Authorization:"Bearer "+tok()}, body:fd
  }).then(function(r){ return r.ok; }).catch(function(){ return false; });
}
function createShare(){
  var ep = SHARE.mode === "eph" ? "/partage-ephemere" : "/partage-permanent";
  var fd = new FormData(); fd.append("fichier_id", SHARE.fid);
  return api(ep, {method:"POST", body:fd}).then(function(r){
    return r.ok ? r.json() : null;
  });
}
// « Générer le lien » : produit seulement un lien à copier (l'envoi se fait via Envoyer).
function shareGenerate(){
  var go = document.getElementById("share-link");
  if (go) go.disabled = true;
  createShare().then(function(d){
    if (!d || !d.url){ err(); if (go) go.disabled = false; return; }
    var full = originBase() + d.url;
    var res = document.getElementById("share-result");
    if (res){
      res.innerHTML = '<div class="linkbox"><input id="sh-link" readonly value="' + esc(full) + '">' +
        '<button class="btn sm" id="sh-copy">📋 ' + esc(t("copy_link")) + "</button></div>";
      var cp = document.getElementById("sh-copy");
      if (cp) cp.onclick = function(){ copyText(full); };
      var inp = document.getElementById("sh-link");
      if (inp){ inp.focus(); inp.select(); }
    }
    if (go) go.disabled = false;
  }).catch(function(){ err(); if (go) go.disabled = false; });
}
function copyText(txt){
  if (navigator.clipboard && navigator.clipboard.writeText){
    navigator.clipboard.writeText(txt).then(function(){ toast(t("link_copied"), "ok"); })
      .catch(function(){ legacyCopy(txt); });
  } else legacyCopy(txt);
}
function legacyCopy(txt){
  var ta = document.createElement("textarea"); ta.value = txt;
  document.body.appendChild(ta); ta.select();
  try{ document.execCommand("copy"); toast(t("link_copied"), "ok"); }catch(e){}
  document.body.removeChild(ta);
}

// ── Actions ──────────────────────────────────────────────────────────────────
function doAction(act, b){
  var id = b.getAttribute("data-id");
  if (act === "dl"){
    api("/download/" + id).then(function(r){ return r.blob().then(function(bl){ return {bl:bl, r:r}; }); })
      .then(function(o){
        if (!o.r.ok){ toast(t("content_unavailable"), "err"); return; }
        var url = URL.createObjectURL(o.bl);
        var cd = o.r.headers.get("Content-Disposition") || "";
        var m = /filename="?([^"]+)"?/.exec(cd);
        var link = document.createElement("a");
        link.href = url; link.download = m ? m[1] : "fichier";
        document.body.appendChild(link); link.click(); document.body.removeChild(link);
        setTimeout(function(){ URL.revokeObjectURL(url); }, 4000);
      }).catch(err);
  } else if (act === "share"){
    openShareModal(id, b.getAttribute("data-nom"), b.getAttribute("data-eph") === "1",
                   b.getAttribute("data-restr") === "1");
  } else if (act === "fav"){
    api("/favori/" + id, {method:"POST"}).then(function(){ refresh(); }).catch(err);
  } else if (act === "ren"){
    var nv = prompt(t("rename_prompt"), b.getAttribute("data-nom") || "");
    if (nv){ var fd = new FormData(); fd.append("nom", nv);
      api("/rename/" + id, {method:"PUT", body:fd}).then(function(){ refresh(); }).catch(err); }
  } else if (act === "del"){
    if (confirm(t("confirm_delete"))){
      api("/" + id, {method:"DELETE"}).then(function(){ toast(t("delete"), "ok"); refresh(); }).catch(err);
    }
  } else if (act === "restore"){
    api("/restore/" + id, {method:"POST"}).then(function(){ refresh(); }).catch(err);
  } else if (act === "purge"){
    if (confirm(t("confirm_purge"))){
      api("/purge/" + id, {method:"DELETE"}).then(function(){ refresh(); }).catch(err);
    }
  } else if (act === "copy"){
    copyText(originBase() + b.getAttribute("data-url"));
  } else if (act === "dlshare"){
    var u = b.getAttribute("data-url") || "";
    if (u) window.open(b.getAttribute("data-ext") === "1" ? u : (originBase() + u), "_blank");
  } else if (act === "moveshare"){
    moveShare(b.getAttribute("data-pid"));
  } else if (act === "revoke"){
    api("/partage/" + b.getAttribute("data-pid"), {method:"DELETE"})
      .then(function(){ refresh(); }).catch(err);
  } else if (act === "newfolder"){
    newFolder();
  } else if (act === "import"){
    openUpload();
  } else if (act === "frename"){
    var fid = b.getAttribute("data-fid");
    var cur = (FOLDERS.find(function(x){ return String(x.id) === String(fid); }) || {}).nom || "";
    var nn = prompt(t("rename_folder"), cur);
    if (nn && nn.trim()){
      var fd = new FormData(); fd.append("nom", nn.trim());
      api("/dossier/" + fid, {method:"PUT", body:fd})
        .then(function(r){ if (r.ok){ loadFolders(); } else err(); }).catch(err);
    }
  } else if (act === "fmoveto"){
    var fid2 = b.getAttribute("data-fid");
    var fd2 = new FormData(); fd2.append("parent_id", b.getAttribute("data-target") || "racine");
    api("/dossier/" + fid2, {method:"PUT", body:fd2})
      .then(function(r){ if (r.ok){ loadFolders(); } else err(); }).catch(err);
  } else if (act === "fdelete"){
    if (confirm(t("confirm_delete"))){
      api("/dossier/" + b.getAttribute("data-fid"), {method:"DELETE"})
        .then(function(){ if (String(CURRENT_FOLDER) === b.getAttribute("data-fid")) CURRENT_FOLDER = null;
                          loadFolders(); refresh(); }).catch(err);
    }
  }
}

// Sous-arbre (ids descendants) d'un dossier — pour exclure des cibles de déplacement.
function folderDescendants(fid){
  var out = [], stack = [String(fid)];
  while (stack.length){
    var cur = stack.pop();
    FOLDERS.forEach(function(d){
      if (String(d.parent_id) === cur){ out.push(String(d.id)); stack.push(String(d.id)); }
    });
  }
  return out;
}

// Menu d'un dossier : renommer / supprimer / déplacer vers (Racine + dossiers valides).
function openFolderMenu(fid, btn){
  var excl = {}; excl[String(fid)] = 1;
  folderDescendants(fid).forEach(function(x){ excl[x] = 1; });
  var html =
    '<button class="mi" data-act="frename" data-fid="' + fid + '"><span class="ic">✎</span>' + esc(t("rename_folder")) + "</button>" +
    '<button class="mi danger" data-act="fdelete" data-fid="' + fid + '"><span class="ic">🗑</span>' + esc(t("delete")) + "</button>" +
    '<div class="menu-sep">' + esc(t("move_to")) + "</div>" +
    '<button class="mi" data-act="fmoveto" data-fid="' + fid + '" data-target="racine"><span class="ic">🏠</span>' + esc(t("root")) + "</button>";
  FOLDERS.forEach(function(d){
    if (excl[String(d.id)]) return;
    html += '<button class="mi" data-act="fmoveto" data-fid="' + fid + '" data-target="' + d.id +
      '"><span class="ic">📂</span>' + esc(d.nom) + "</button>";
  });
  openMenuHtml(btn, html, "f" + fid);
}

// Clic sur « ⋯ » (déclencheur du menu)
document.getElementById("body").addEventListener("click", function(ev){
  // Barre de dossiers « Partagé avec moi »
  var sel = ev.target.closest("[data-sfsel]");
  var ren = ev.target.closest("[data-sfren]");
  var del = ev.target.closest("[data-sfdel]");
  var nw  = ev.target.closest("[data-sfnew]");
  if (ren){ ev.stopPropagation(); sharedFolderRename(ren.getAttribute("data-sfren")); return; }
  if (del){ ev.stopPropagation(); sharedFolderDelete(del.getAttribute("data-sfdel")); return; }
  if (nw){ ev.stopPropagation(); sharedFolderNew(); return; }
  if (sel){ ev.stopPropagation(); SHARED_SEL = sel.getAttribute("data-sfsel"); renderSharedView(); return; }

  var b = ev.target.closest('button[data-act="menu"]');
  if (!b) return;
  ev.stopPropagation();
  var id = b.getAttribute("data-id");
  var m = document.getElementById("row-menu");
  var sameOpen = m.classList.contains("open") && m.getAttribute("data-for") === String(id);
  closeMenu();
  if (!sameOpen) openRowMenu(id, b);
});

// ── « Partagé avec moi » : dossiers d'organisation ───────────────────────────
function sharedFolderNew(){
  var nom = prompt(t("new_folder_prompt") || t("new_folder"));
  if (!nom || !nom.trim()) return;
  var fd = new FormData(); fd.append("nom", nom.trim());
  api("/partages-dossiers", {method:"POST", body:fd})
    .then(function(r){ if (r.ok) refresh(); else err(); }).catch(err);
}
function sharedFolderRename(did){
  var cur = (SHARED_FOLDERS.find(function(x){ return String(x.id) === String(did); }) || {}).nom || "";
  var nn = prompt(t("rename_folder") || t("rename"), cur);
  if (!nn || !nn.trim()) return;
  var fd = new FormData(); fd.append("nom", nn.trim());
  api("/partages-dossiers/" + did, {method:"PUT", body:fd})
    .then(function(r){ if (r.ok) refresh(); else err(); }).catch(err);
}
function sharedFolderDelete(did){
  if (!confirm(t("confirm_delete_folder") || t("confirm_delete"))) return;
  api("/partages-dossiers/" + did, {method:"DELETE"})
    .then(function(r){ if (r.ok){ if (String(SHARED_SEL) === String(did)) SHARED_SEL = "all"; refresh(); } else err(); }).catch(err);
}
function moveShare(pid){
  // Petit sélecteur : Racine + dossiers existants
  var opts = [{id:"", nom:"🏠 " + t("shared_root")}].concat(
    SHARED_FOLDERS.map(function(d){ return {id:d.id, nom:"📁 " + d.nom}; }));
  var prev = document.getElementById("move-share-pop");
  if (prev) prev.remove();
  var pop = document.createElement("div");
  pop.id = "move-share-pop";
  pop.style.cssText = "position:fixed;inset:0;background:rgba(0,0,0,.35);z-index:99999;display:flex;align-items:center;justify-content:center";
  var inner = '<div style="background:#fff;border-radius:10px;min-width:280px;max-width:92vw;max-height:70vh;overflow:auto;box-shadow:0 10px 40px rgba(0,0,0,.2)">' +
    '<div style="padding:14px 16px;border-bottom:1px solid #e2e8f0;font-weight:700;font-size:13px">' + esc(t("move_to")) + '</div><div style="padding:8px">';
  opts.forEach(function(o){
    inner += '<button class="msf-opt" data-mid="' + o.id + '" style="display:block;width:100%;text-align:left;padding:9px 12px;border:none;background:none;cursor:pointer;font-size:13px;border-radius:6px">' + esc(o.nom) + '</button>';
  });
  inner += '</div><div style="padding:10px 16px;border-top:1px solid #e2e8f0;text-align:right"><button id="msf-cancel" style="padding:6px 14px;border:1px solid #e2e8f0;background:#f8fafc;border-radius:6px;cursor:pointer;font-size:12px">' + esc(t("cancel") || "Annuler") + '</button></div></div>';
  pop.innerHTML = inner;
  document.body.appendChild(pop);
  pop.addEventListener("click", function(e){
    if (e.target === pop || e.target.id === "msf-cancel"){ pop.remove(); return; }
    var opt = e.target.closest(".msf-opt");
    if (!opt) return;
    var fd = new FormData();
    var mid = opt.getAttribute("data-mid");
    if (mid) fd.append("dossier_id", mid);
    api("/partages/" + pid + "/ranger", {method:"POST", body:fd})
      .then(function(r){ pop.remove(); if (r.ok){ toast(t("moved") || "OK", "ok"); refresh(); } else err(); })
      .catch(function(){ pop.remove(); err(); });
  });
}
// Clic sur une action du menu
document.getElementById("row-menu").addEventListener("click", function(ev){
  var b = ev.target.closest("button[data-act]");
  if (!b) return;
  closeMenu();
  doAction(b.getAttribute("data-act"), b);
});
// Fermer le menu au clic ailleurs / au scroll
document.addEventListener("click", function(ev){
  if (ev.target.closest("#row-menu")) return;
  if (ev.target.closest('button[data-act="menu"]')) return;
  closeMenu();
});
document.getElementById("main").addEventListener("scroll", closeMenu);

// ── Branchements UI ──────────────────────────────────────────────────────────
document.querySelectorAll(".nav-item").forEach(function(b){
  b.addEventListener("click", function(){ setView(b.getAttribute("data-view")); });
});
document.getElementById("folders").addEventListener("click", function(ev){
  var dots = ev.target.closest("[data-fmenu]");
  if (dots){
    ev.stopPropagation();
    var fid = dots.getAttribute("data-fmenu");
    var m = document.getElementById("row-menu");
    var same = m.classList.contains("open") && m.getAttribute("data-for") === "f" + fid;
    closeMenu();
    if (!same) openFolderMenu(fid, dots);
    return;
  }
  var c = ev.target.closest(".fchip"); if (!c) return;
  var fv = c.getAttribute("data-folder");
  CURRENT_FOLDER = fv ? fv : null;
  renderFolders(); refresh();
});
document.getElementById("type-filter").addEventListener("change", function(){
  TYPE_FILTER = this.value; refresh();
});
document.getElementById("btn-search").onclick = function(){
  var sb = document.getElementById("searchbox");
  sb.classList.toggle("show");
  if (sb.classList.contains("show")) document.getElementById("search").focus();
};
function openUpload(){ document.getElementById("up-bg").classList.add("show"); }
function closeUpload(){ document.getElementById("up-bg").classList.remove("show"); }
document.getElementById("btn-new").onclick = function(ev){
  ev.stopPropagation();
  var m = document.getElementById("row-menu");
  var open = m.classList.contains("open") && m.getAttribute("data-for") === "_new";
  closeMenu();
  if (open) return;
  openMenuHtml(this,
    '<button class="mi" data-act="newfolder"><span class="ic">📁</span>' + esc(t("new_folder_opt")) + "</button>" +
    '<button class="mi" data-act="import"><span class="ic">⬆</span>' + esc(t("import_opt")) + "</button>", "_new");
};
document.getElementById("btn-import").onclick = openUpload;
document.getElementById("up-close").onclick = closeUpload;
document.getElementById("up-bg").addEventListener("click", function(e){ if (e.target.id === "up-bg") closeUpload(); });
document.querySelectorAll("#up-type .seg").forEach(function(b){
  b.addEventListener("click", function(){
    UPLOAD_TYPE = b.getAttribute("data-up");
    document.querySelectorAll("#up-type .seg").forEach(function(x){ x.classList.toggle("active", x === b); });
  });
});
document.getElementById("up-restrict").addEventListener("change", function(){ RESTRICT_DL = this.checked; });
document.getElementById("up-pick").onclick = function(){ document.getElementById("file-input").click(); };
document.getElementById("file-input").onchange = function(e){ var fs = e.target.files; closeUpload(); doUpload(fs); e.target.value = ""; };
document.getElementById("btn-newfolder").onclick = newFolder;
document.getElementById("dropzone").onclick = function(){ openUpload(); };
var dz = document.getElementById("dropzone");
["dragenter","dragover"].forEach(function(ev){ dz.addEventListener(ev, function(e){
  e.preventDefault(); dz.classList.add("hl"); }); });
["dragleave","drop"].forEach(function(ev){ dz.addEventListener(ev, function(e){
  e.preventDefault(); dz.classList.remove("hl"); }); });
dz.addEventListener("drop", function(e){ if (e.dataTransfer && e.dataTransfer.files) doUpload(e.dataTransfer.files); });
var searchT;
document.getElementById("search").addEventListener("input", function(){
  clearTimeout(searchT); searchT = setTimeout(refresh, 280);
});
document.getElementById("modal-close").onclick = function(){ document.getElementById("modal-bg").classList.remove("show"); };
document.getElementById("modal-bg").addEventListener("click", function(e){
  if (e.target.id === "modal-bg") document.getElementById("modal-bg").classList.remove("show");
});

// Nom de l'utilisateur courant (colonne « Créé par » + avatar)
fetch("/api/v1/auth/me", {headers:{Authorization:"Bearer "+tok()}})
  .then(function(r){ return r.ok ? r.json() : null; })
  .then(function(u){ if (u){ ME_NAME = u.display_name || u.username || "";
    var av = document.getElementById("avatar");
    if (av && ME_NAME){ av.textContent = ME_NAME.trim().slice(0,2).toUpperCase(); }
    refresh(); } })
  .catch(function(){});

applyI18n();
setView("drive");
})();
</script>
</body>
</html>"""


@ui_router.get("/ui", response_class=HTMLResponse)
def fichiers_ui():
    html = _HTML.replace("__I18N_JSON__", json.dumps(_I18N, ensure_ascii=False))
    return HTMLResponse(html)
