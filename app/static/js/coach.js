/* SCRIBE — Widget Coach proactif (v3.0.0 / build v3000h)
 * ========================================================
 * Compagnon flottant en bas à droite, façon "Clippy moderne sérieux".
 *
 * - Pastille collapsée 🎓 (avec badge nb messages)
 * - Panneau déplié avec timeline de messages + actions
 * - Polling /api/v1/tuteur/coach/check toutes les 60s
 * - Anti-spam : géré côté backend (snooze)
 * - Activation : si plugin tuteur actif (vérifié via /api/v1/plugins/active)
 *
 * v3000h : widget + 2 règles (incident_sans_action, stagnation)
 * v3000i+ : actions "transformer en tâches", prompt libre, etc.
 */

(function(){
  'use strict';

  // ── État global du coach ────────────────────────────────────────────────
  const COACH = {
    enabled:        false,    // activé seulement si plugin tuteur listé dans /plugins/active
    open:           false,    // panneau déplié ?
    pollMs:         60000,    // 60s
    pollTimer:      null,
    sessionId:      null,
    messages:       [],
    unreadCount:    0,
    mutedUntil:     null,     // timestamp ms ou null
  };

  // ── Style injecté (auto-portant — pas de dépendance CSS externe) ───────
  function injectStyles() {
    if (document.getElementById('coach-styles')) return;
    const css = `
      #coach-bubble {
        position: fixed; right: 20px; bottom: 20px;
        width: 56px; height: 56px; border-radius: 50%;
        background: linear-gradient(135deg, #003189, #1e40af);
        color: white; border: none; cursor: pointer;
        font-size: 26px; box-shadow: 0 8px 24px rgba(0,0,0,0.25);
        z-index: 99998; display: none; align-items: center; justify-content: center;
        transition: transform 0.15s ease, box-shadow 0.15s ease;
      }
      #coach-bubble:hover { transform: scale(1.08); box-shadow: 0 10px 28px rgba(0,0,0,0.32); }
      #coach-bubble .coach-badge {
        position: absolute; top: -4px; right: -4px;
        background: #e1000f; color: white;
        min-width: 20px; height: 20px; padding: 0 5px;
        border-radius: 10px; font-size: 11px; font-weight: 700;
        display: flex; align-items: center; justify-content: center;
        border: 2px solid white; font-family: system-ui, sans-serif;
      }
      #coach-bubble .coach-badge.hidden { display: none; }
      #coach-bubble.pulse { animation: coach-pulse 2.5s ease-in-out infinite; }
      @keyframes coach-pulse {
        0%, 100% { box-shadow: 0 8px 24px rgba(0,0,0,0.25); }
        50%      { box-shadow: 0 8px 24px rgba(0,0,0,0.25), 0 0 0 12px rgba(0, 49, 137, 0.15); }
      }
      /* v3.1.0 — Pulse rouge pour les alertes critiques */
      #coach-bubble.coach-alert-pulse {
        animation: coach-alert-pulse 0.7s ease-in-out 4;
        background: #e1000f !important;
      }
      @keyframes coach-alert-pulse {
        0%, 100% { transform: scale(1); box-shadow: 0 8px 24px rgba(225,0,15,0.5); }
        50%      { transform: scale(1.12); box-shadow: 0 8px 32px rgba(225,0,15,0.85), 0 0 0 14px rgba(225,0,15,0.18); }
      }

      #coach-panel {
        position: fixed; right: 20px; bottom: 20px;
        width: 440px; max-width: calc(100vw - 40px);
        height: 580px; max-height: calc(100vh - 40px);
        background: white; border-radius: 14px;
        box-shadow: 0 24px 64px rgba(0,0,0,0.28);
        display: none; flex-direction: column; overflow: hidden;
        z-index: 99998; font-family: system-ui, -apple-system, "Segoe UI", sans-serif;
        border: 1px solid #e2e8f0;
      }
      #coach-panel.open { display: flex; }

      #coach-header {
        background: linear-gradient(135deg, #003189, #1e40af);
        color: white; padding: 12px 16px;
        display: flex; align-items: center; gap: 10px;
      }
      #coach-header .coach-title { flex: 1; font-weight: 700; font-size: 15px; }
      #coach-header .coach-sub   { font-size: 11px; opacity: 0.85; }
      #coach-header button {
        background: rgba(255,255,255,0.18); color: white; border: none;
        width: 32px; height: 32px; border-radius: 6px; cursor: pointer;
        font-size: 18px; font-weight: 700; line-height: 1;
        display: flex; align-items: center; justify-content: center;
        transition: background 0.15s;
      }
      #coach-header button:hover { background: rgba(255,255,255,0.32); }

      #coach-messages {
        flex: 1; overflow-y: auto; padding: 12px 14px;
        background: #f8fafc; display: flex; flex-direction: column; gap: 10px;
      }
      .coach-msg {
        background: white; border-radius: 10px; padding: 11px 13px;
        border-left: 3px solid #94a3b8; font-size: 13px; line-height: 1.45;
        color: #0f172a; box-shadow: 0 1px 2px rgba(0,0,0,0.04);
      }
      .coach-msg.priorite-3 { border-left-color: #e1000f; }
      .coach-msg.priorite-2 { border-left-color: #f59e0b; }
      .coach-msg.priorite-1 { border-left-color: #3b82f6; }
      .coach-msg .coach-msg-text { margin-bottom: 8px; }
      .coach-msg .coach-msg-time { font-size: 10px; color: #94a3b8; margin-bottom: 6px; }
      .coach-msg-actions { display: flex; gap: 6px; flex-wrap: wrap; }
      .coach-msg-actions button {
        background: #f1f5f9; color: #003189; border: 1px solid #cbd5e1;
        padding: 5px 10px; border-radius: 6px; font-size: 11px; cursor: pointer;
        font-weight: 600; transition: background 0.15s;
        font-family: inherit;
      }
      .coach-msg-actions button:hover { background: #e2e8f0; }
      .coach-msg-actions button.primary {
        background: #003189; color: white; border-color: #003189;
      }
      .coach-msg-actions button.primary:hover { background: #1e40af; }

      #coach-empty {
        text-align: center; color: #94a3b8; padding: 32px 20px;
        font-size: 13px; line-height: 1.5;
      }

      #coach-footer {
        border-top: 1px solid #e2e8f0; padding: 10px 12px; background: white;
        display: flex; gap: 8px; align-items: center;
      }
      #coach-prompt {
        flex: 1; border: 1px solid #cbd5e1; border-radius: 8px;
        padding: 8px 10px; font-size: 13px; font-family: inherit;
        background: #f8fafc;
      }
      #coach-prompt:focus { outline: none; border-color: #003189; background: white; }
      #coach-prompt-send {
        background: #003189; color: white; border: none;
        padding: 8px 12px; border-radius: 8px; cursor: pointer; font-size: 13px;
        font-family: inherit; font-weight: 600;
      }
      #coach-prompt-send:disabled { opacity: 0.5; cursor: not-allowed; }

      /* v3000h14 — barre d'actions stratégiques + synthèse */
      #coach-actions {
        display: flex; gap: 6px; padding: 8px 10px;
        border-bottom: 1px solid #e2e8f0; background: white;
      }
      .coach-act-btn {
        flex: 1; background: #f1f5f9; color: #003189; border: 1px solid #cbd5e1;
        padding: 7px 10px; border-radius: 6px; font-size: 12px;
        cursor: pointer; font-family: inherit; font-weight: 600;
        white-space: nowrap; transition: background 0.15s;
      }
      .coach-act-btn:hover { background: #e2e8f0; }
      .coach-act-btn.coach-act-primary {
        background: #003189; color: white; border-color: #003189;
      }
      .coach-act-btn.coach-act-primary:hover { background: #1e40af; }
      .coach-act-btn:disabled { opacity: 0.6; cursor: wait; }

      /* Bloc synthèse (point de situation) — apparait comme un message */
      .coach-synthese {
        background: white; border-radius: 10px; padding: 12px 14px;
        border-left: 3px solid #003189; box-shadow: 0 1px 2px rgba(0,0,0,0.04);
        font-size: 12.5px; line-height: 1.5; color: #0f172a;
      }
      .coach-synthese h4 {
        font-size: 11px; text-transform: uppercase; letter-spacing: 0.5px;
        color: #64748b; margin: 8px 0 4px; font-weight: 700;
      }
      .coach-synthese h4:first-child { margin-top: 0; }
      .coach-synthese ul { margin: 0 0 0 4px; padding-left: 16px; }
      .coach-synthese li { margin-bottom: 2px; }
      .coach-synthese .coach-syn-priorites { background: #fef3c7; border-radius: 6px; padding: 8px 10px; margin-top: 6px; }
      .coach-synthese .coach-syn-priorites h4 { color: #92400e; margin-top: 0; }
      .coach-synthese .coach-syn-priorites ol { margin: 0; padding-left: 22px; }
      .coach-synthese .coach-syn-source {
        margin-top: 8px; font-size: 10px; color: #94a3b8; font-style: italic;
      }

      /* Réponse à une question libre */
      .coach-question { background: #dbeafe; border-radius: 10px; padding: 10px 12px; font-size: 12.5px; color: #1e3a8a; }
      .coach-question::before { content: "Vous : "; font-weight: 700; }
      .coach-answer { background: white; border-radius: 10px; padding: 11px 13px; border-left: 3px solid #003189; font-size: 12.5px; line-height: 1.5; }
    `;
    const style = document.createElement('style');
    style.id = 'coach-styles';
    style.textContent = css;
    document.head.appendChild(style);
  }

  // ── Construction du DOM ─────────────────────────────────────────────────
  function buildDom() {
    if (document.getElementById('coach-bubble')) return;

    const bubble = document.createElement('button');
    bubble.id = 'coach-bubble';
    bubble.title = "Assistant SCRIBE — clic pour ouvrir";
    bubble.innerHTML = '🎓 <span class="coach-badge hidden" id="coach-badge">0</span>';
    bubble.onclick = togglePanel;
    document.body.appendChild(bubble);

    const panel = document.createElement('div');
    panel.id = 'coach-panel';
    panel.innerHTML = [
      '<div id="coach-header">',
      '  <div style="font-size:22px">🎓</div>',
      '  <div style="flex:1">',
      '    <div class="coach-title">Mon Assistant</div>',
      '    <div class="coach-sub">Copilote stratégique</div>',
      '  </div>',
      '  <button id="coach-mute-btn" title="Faire silence 10 min">🔕</button>',
      '  <button id="coach-close-btn" title="Fermer" aria-label="Fermer">✕</button>',
      '</div>',
      // v3000h14 — Barre d'actions stratégiques (toujours visible en haut)
      // v3.1.0 — Ajout onglet "Historique" entre les deux
      '<div id="coach-actions">',
      '  <button id="coach-act-situation" class="coach-act-btn coach-act-primary" title="Synthèse globale + projection">',
      '    🎯 Point de situation',
      '  </button>',
      '  <button id="coach-act-history" class="coach-act-btn" title="Voir tous les messages déjà reçus">',
      '    🔔 Historique <span id="coach-act-history-count" style="display:none;font-size:10px"></span>',
      '  </button>',
      '  <button id="coach-act-ask" class="coach-act-btn" title="Poser une question libre">',
      '    ❓ Conseil',
      '  </button>',
      '</div>',
      '<div id="coach-messages">',
      '  <div id="coach-empty">Cliquez sur <b>🎯 Point de situation</b> pour une synthèse stratégique<br><span style="font-size:11px">Les alertes proactives apparaîtront aussi ici.</span></div>',
      '</div>',
      '<div id="coach-footer">',
      '  <input type="text" id="coach-prompt" placeholder="Poser une question…" autocomplete="off">',
      '  <button id="coach-prompt-send" title="Envoyer">→</button>',
      '</div>',
    ].join('');
    document.body.appendChild(panel);

    document.getElementById('coach-close-btn').onclick = togglePanel;
    document.getElementById('coach-mute-btn').onclick = onMute;
    document.getElementById('coach-act-situation').onclick = onPointDeSituation;
    document.getElementById('coach-act-history').onclick = onOpenHistory;
    document.getElementById('coach-act-ask').onclick = function() {
      // v3000h18 fix — Action visible : afficher un encart d'aide, animer le
      // champ, et focus. Avant, le bouton ne faisait que focus() invisible.
      const input = document.getElementById('coach-prompt');
      const footer = document.getElementById('coach-footer');
      if (!input) return;
      // 1. Afficher un encart d'invite dans les messages (idempotent)
      const existing = document.getElementById('coach-ask-hint');
      if (!existing) {
        _appendCustomBlock(
          '<div id="coach-ask-hint" class="coach-synthese" style="border-left-color:#0ea5e9;background:#f0f9ff">' +
          '<h4 style="color:#0369a1">💬 Mode Conseil</h4>' +
          '<div style="font-size:13px;color:#0c4a6e">Tapez votre question dans le champ ci-dessous (en bas du panneau) et appuyez sur Entrée.</div>' +
          '<div style="margin-top:8px;font-size:11.5px;color:#475569"><strong>Exemples :</strong></div>' +
          '<ul style="margin:4px 0 0;padding-left:20px;font-size:11.5px;color:#475569;line-height:1.6">' +
          '<li>Faut-il prévenir la CNIL maintenant ?</li>' +
          '<li>Qui doit appeler l\'ANSSI en premier ?</li>' +
          '<li>Dois-je activer la cellule de communication ?</li>' +
          '<li>Quelles sont mes priorités sur les 30 prochaines minutes ?</li>' +
          '</ul></div>'
        );
      }
      // 2. Animer visuellement le champ pour qu'on voie où aller
      if (footer) {
        footer.style.transition = 'background 0.3s';
        const prevBg = footer.style.background;
        footer.style.background = '#dbeafe';
        setTimeout(function() { footer.style.background = prevBg; }, 1200);
      }
      input.style.transition = 'box-shadow 0.3s';
      input.style.boxShadow = '0 0 0 3px rgba(14,165,233,0.4)';
      setTimeout(function() { input.style.boxShadow = ''; }, 1500);
      // 3. Focus le champ
      input.focus();
    };
    document.getElementById('coach-prompt-send').onclick = onAskSubmit;
    document.getElementById('coach-prompt').addEventListener('keydown', function(e) {
      if (e.key === 'Enter') { e.preventDefault(); onAskSubmit(); }
    });

    // v3000h-fix — Afficher la bulle immédiatement (avant le 1er poll). Avant,
    // elle restait cachée (display:none par défaut) tant que pollCheck n'avait
    // pas répondu, ce qui pouvait laisser l'utilisateur sans repère visuel.
    bubble.style.display = 'flex';
  }

  // ── Ouverture / fermeture ───────────────────────────────────────────────
  function togglePanel() {
    COACH.open = !COACH.open;
    const bubble = document.getElementById('coach-bubble');
    const panel  = document.getElementById('coach-panel');
    if (COACH.open) {
      panel.classList.add('open');
      bubble.style.display = 'none';
      bubble.classList.remove('pulse');
      // Reset badge "non lu"
      COACH.unreadCount = 0;
      updateBadge();
      // v3000h13 — CRITIQUE : afficher les messages déjà reçus immédiatement,
      // sinon le panneau apparaît vide alors qu'il y a un badge "1".
      renderMessages();
      // Et déclencher un fetch frais pour récupérer d'éventuels nouveaux
      // messages depuis le dernier poll (qui tourne aux 60s, donc peut être
      // déjà obsolète au moment où l'utilisateur clique).
      pollCheck();
    } else {
      panel.classList.remove('open');
      bubble.style.display = 'flex';
    }
  }

  function updateBadge() {
    const badge = document.getElementById('coach-badge');
    if (!badge) return;
    if (COACH.unreadCount > 0) {
      badge.textContent = COACH.unreadCount > 9 ? '9+' : String(COACH.unreadCount);
      badge.classList.remove('hidden');
      const bubble = document.getElementById('coach-bubble');
      if (bubble && !COACH.open) bubble.classList.add('pulse');
    } else {
      badge.classList.add('hidden');
      const bubble = document.getElementById('coach-bubble');
      if (bubble) bubble.classList.remove('pulse');
    }
  }

  // ── Rendu des messages ──────────────────────────────────────────────────
  function escapeHtml(s) {
    return String(s == null ? '' : s)
      .replace(/&/g,'&amp;').replace(/</g,'&lt;')
      .replace(/>/g,'&gt;').replace(/"/g,'&quot;');
  }

  function formatRelativeTime(iso) {
    if (!iso) return '';
    try {
      const d = new Date(iso);
      const sec = Math.max(0, (Date.now() - d.getTime()) / 1000);
      if (sec < 60) return 'à l\'instant';
      if (sec < 3600) return `il y a ${Math.floor(sec/60)} min`;
      return `à ${d.getHours().toString().padStart(2,'0')}:${d.getMinutes().toString().padStart(2,'0')}`;
    } catch(e) { return ''; }
  }

  function renderMessages() {
    const container = document.getElementById('coach-messages');
    if (!container) return;
    if (!COACH.messages.length) {
      container.innerHTML = '<div id="coach-empty">Cliquez sur <b>🎯 Point de situation</b> pour une synthèse stratégique<br><span style="font-size:11px">Les alertes proactives apparaîtront aussi ici.</span></div>';
      return;
    }
    container.innerHTML = COACH.messages.map(function(m) {
      const actionsHtml = (m.actions || []).map(function(a, idx) {
        const cls = idx === 0 ? 'primary' : '';
        return `<button class="${cls}" data-msg-id="${m.id}" data-action-idx="${idx}">${escapeHtml(a.label)}</button>`;
      }).join('');
      // v3.1.0 — Bordure colorée selon le niveau
      const niveau = m.niveau || 'marker';
      const borderColor =
        niveau === 'alert'  ? '#e1000f' :
        niveau === 'silent' ? '#94a3b8' : '#003189';
      return [
        `<div class="coach-msg priorite-${m.priorite || 1}" data-msg-id="${m.id}" data-niveau="${niveau}" style="border-left:3px solid ${borderColor}">`,
        `  <div class="coach-msg-time">${formatRelativeTime(m.created_at)}${niveau === 'alert' ? ' • <span style="color:#e1000f;font-weight:700">ALERTE</span>' : ''}</div>`,
        `  <div class="coach-msg-text">${escapeHtml(m.message)}</div>`,
        `  <div class="coach-msg-actions">${actionsHtml}</div>`,
        `</div>`,
      ].join('');
    }).join('');
    // Brancher les boutons d'actions
    container.querySelectorAll('.coach-msg-actions button').forEach(function(btn) {
      btn.onclick = function() { onActionClick(btn); };
    });
  }

  // ── Gestion des actions sur les messages ────────────────────────────────
  function onActionClick(btn) {
    const msgId  = parseInt(btn.dataset.msgId, 10);
    const idx    = parseInt(btn.dataset.actionIdx, 10);
    const msg    = COACH.messages.find(function(m) { return m.id === msgId; });
    if (!msg) return;
    const action = msg.actions[idx];
    if (!action) return;
    btn.disabled = true;
    const t = action.action_type;
    if (t === 'snooze') {
      const min = (action.payload && action.payload.minutes) || 10;
      ackMessage(msgId, min);
    } else if (t === 'dismiss') {
      ackMessage(msgId, null);
    } else if (t === 'open_tab') {
      // v3000h14 — Navigation vers un onglet de la SPA + highlight optionnel
      // d'un incident concerné (carte VEILLE).
      const tabId = (action.payload && action.payload.tab) || '';
      const incidentId = action.payload && action.payload.incident_id;
      const wantHighlight = !!(action.payload && action.payload.highlight);
      let opened = false;
      if (tabId) {
        // Le SPA SCRIBE utilise plusieurs patrons selon les onglets :
        // - tab-soins → bouton id="tab-btn-soins"
        // - tab-veille → bouton id="tab-btn-incidents" (pas "veille")
        const explicitMap = {
          'tab-veille':       'tab-btn-incidents',
          'tab-soins':        'tab-btn-soins',
          'tab-kanban':       'tab-btn-kanban',
          'tab-capacite':     'tab-btn-capacite',
          'tab-transferts':   'tab-btn-transferts',
        };
        const tabBtnId = explicitMap[tabId] || tabId.replace('tab-', 'tab-btn-');
        const tabBtn = document.getElementById(tabBtnId)
                    || document.querySelector('[onclick*="' + tabId + '"]')
                    || document.querySelector('[data-tab="' + tabId.replace('tab-', '') + '"]');
        if (tabBtn) { tabBtn.click(); opened = true; }
      }
      // Repli du widget pour laisser la place
      if (COACH.open) togglePanel();
      if (!opened) {
        console.warn('[coach] onglet introuvable :', tabId);
      } else if (wantHighlight && incidentId) {
        // Highlight de l'incident dans l'onglet (le DOM peut mettre un instant
        // à se peupler après le clic onglet → retry court).
        const tryHighlight = function(attempt) {
          const sel =
            '#inc-' + incidentId + ', ' +
            '[data-incident-id="' + incidentId + '"], ' +
            '[data-sitrep-id="'   + incidentId + '"], ' +
            '#incident-' + incidentId + ', ' +
            '#sitrep-'   + incidentId;
          const el = document.querySelector(sel);
          if (el) {
            try { el.scrollIntoView({behavior:'smooth', block:'center'}); } catch(e) {}
            // Si l'incident est replié, le déplier pour donner du contexte
            try {
              if (!el.classList.contains('expanded')) {
                const toggleBtn = el.querySelector('.inc-toggle-btn');
                if (toggleBtn) toggleBtn.click();
              }
            } catch(e) {}
            const prev = el.style.outline;
            const prevBg = el.style.background;
            el.style.outline = '3px solid #f59e0b';
            el.style.background = '#fef3c7';
            el.style.transition = 'background 0.3s, outline 0.3s';
            setTimeout(function() {
              el.style.outline = prev;
              el.style.background = prevBg;
            }, 3500);
          } else if (attempt < 8) {
            // Retry toutes les 200ms (max 1.6s)
            setTimeout(function() { tryHighlight(attempt + 1); }, 200);
          } else {
            console.warn('[coach] incident ' + incidentId + ' non trouvé dans le DOM');
          }
        };
        tryHighlight(0);
      }
      ackMessage(msgId, null);
    } else if (t === 'ask_ai' || t === 'generate_tasks') {
      // v3000h8 — Génération de tâches Kanban via Albert
      // L'incident concerné est dans message.target_id (rempli par la règle)
      const incidentId = msg.target_id;
      if (!incidentId) {
        alert('Aucun incident lié à ce message.');
        btn.disabled = false;
        return;
      }
      // Repli du widget pour laisser la place à la modale
      if (COACH.open) togglePanel();
      // Lancer la suggestion (async)
      showSuggestModal(incidentId, msgId);
    } else if (t === 'focus_prompt') {
      const input = document.getElementById('coach-prompt');
      if (input) input.focus();
      ackMessage(msgId, null);
    } else if (t === 'show_obligation') {
      // v3000h18 — Aide réglementaire : ouvre modale avec coordonnées + modèle
      const obligationId = action.payload && action.payload.obligation_id;
      const incidentId   = action.payload && action.payload.incident_id;
      if (!obligationId) {
        btn.disabled = false;
        return;
      }
      // On NE ack PAS le message (l'info reste utile, le user peut y revenir)
      showObligationModal(obligationId, incidentId);
      btn.disabled = false;
    } else {
      btn.disabled = false;
    }
  }

  // ── v3000h8 — Modale preview + création tâches Kanban ───────────────────
  async function showSuggestModal(incidentId, msgId) {
    // 1. Créer la modale loading
    closeSuggestModal();
    const overlay = document.createElement('div');
    overlay.id = 'coach-suggest-overlay';
    overlay.style.cssText = 'position:fixed;inset:0;background:rgba(15,23,42,0.55);'
      + 'z-index:99999;display:flex;align-items:center;justify-content:center;';
    overlay.innerHTML = [
      '<div style="background:white;border-radius:14px;width:520px;max-width:calc(100vw - 40px);',
      'max-height:calc(100vh - 40px);overflow:auto;box-shadow:0 24px 64px rgba(0,0,0,0.32);">',
      '  <div style="background:linear-gradient(135deg,#003189,#1e40af);color:white;padding:14px 18px;',
      '       border-radius:14px 14px 0 0;display:flex;align-items:center;gap:10px;">',
      '    <div style="font-size:22px">🎓</div>',
      '    <div style="flex:1">',
      '      <div style="font-weight:700;font-size:15px">Suggestion de tâches</div>',
      '      <div style="font-size:11px;opacity:0.85" id="suggest-subtitle">Génération en cours…</div>',
      '    </div>',
      '    <button id="suggest-close" style="background:rgba(255,255,255,0.18);color:white;border:none;',
      '            width:30px;height:30px;border-radius:6px;cursor:pointer;font-size:18px">×</button>',
      '  </div>',
      '  <div id="suggest-body" style="padding:18px;">',
      '    <div style="text-align:center;color:#94a3b8;padding:32px 12px;font-size:13px;">',
      '      <div style="font-size:32px;margin-bottom:10px;">⏳</div>',
      '      L\'Assistant interroge Albert IA…',
      '    </div>',
      '  </div>',
      '</div>',
    ].join('');
    document.body.appendChild(overlay);
    document.getElementById('suggest-close').onclick = closeSuggestModal;
    overlay.onclick = function(e) { if (e.target === overlay) closeSuggestModal(); };

    // 2. Appeler la suggestion
    try {
      const r = await apiFetch('/api/v1/tuteur/coach/suggest-tasks/' + incidentId, {method:'POST'});
      if (!r.ok) {
        const err = await r.json().catch(() => ({}));
        throw new Error(err.detail || ('HTTP ' + r.status));
      }
      const data = await r.json();
      renderSuggestModal(data, msgId);
    } catch(e) {
      const body = document.getElementById('suggest-body');
      if (body) body.innerHTML = '<div style="color:#e1000f;padding:20px;font-size:13px;">'
        + 'Erreur : ' + escapeHtml(e.message) + '</div>';
    }
  }

  function renderSuggestModal(data, msgId) {
    const subtitle = document.getElementById('suggest-subtitle');
    if (subtitle) {
      const src = data.source === 'albert' ? '✨ Propositions Albert IA' : '⚙️ Propositions génériques (Albert indisponible)';
      subtitle.textContent = src + ' — Incident #' + data.incident_id;
    }
    const body = document.getElementById('suggest-body');
    if (!body) return;
    const titre = escapeHtml(data.incident_titre || '(sans titre)');
    const inputs = (data.actions || []).map(function(a, i) {
      return '<div style="margin-bottom:10px;">'
        + '<label style="display:block;font-size:11px;color:#64748b;margin-bottom:3px;">Tâche ' + (i+1) + '</label>'
        + '<input type="text" class="suggest-action-input" value="' + escapeHtml(a) + '" '
        + 'style="width:100%;padding:8px 10px;border:1px solid #cbd5e1;border-radius:6px;font-size:13px;font-family:inherit;box-sizing:border-box;">'
        + '</div>';
    }).join('');
    body.innerHTML = [
      '<div style="font-size:12px;color:#64748b;margin-bottom:4px;">Incident concerné :</div>',
      '<div style="background:#f1f5f9;padding:10px 12px;border-radius:8px;border-left:3px solid #003189;',
      '     font-size:13px;color:#0f172a;margin-bottom:16px;">' + titre + '</div>',
      '<div style="font-size:12px;color:#64748b;margin-bottom:8px;">',
      '  Les tâches seront créées dans le Kanban (colonne BACKLOG) et liées à cet incident.',
      '  Vous pouvez éditer chaque tâche avant validation.',
      '</div>',
      inputs,
      '<div style="display:flex;gap:8px;margin-top:18px;justify-content:flex-end;">',
      '  <button id="suggest-cancel" style="background:#f1f5f9;color:#0f172a;border:1px solid #cbd5e1;',
      '          padding:8px 14px;border-radius:6px;font-size:13px;cursor:pointer;font-family:inherit;">Annuler</button>',
      '  <button id="suggest-create" style="background:#003189;color:white;border:none;',
      '          padding:8px 14px;border-radius:6px;font-size:13px;cursor:pointer;font-family:inherit;font-weight:600;">',
      '    ✓ Créer les tâches dans le Kanban</button>',
      '</div>',
    ].join('');
    document.getElementById('suggest-cancel').onclick = closeSuggestModal;
    document.getElementById('suggest-create').onclick = function() {
      createTasksFromModal(data.incident_id, msgId);
    };
  }

  async function createTasksFromModal(incidentId, msgId) {
    const inputs = document.querySelectorAll('.suggest-action-input');
    const actions = Array.from(inputs).map(function(i) { return i.value.trim(); }).filter(function(s) { return s.length > 0; });
    if (!actions.length) {
      alert('Au moins une tâche est requise.');
      return;
    }
    const btn = document.getElementById('suggest-create');
    if (btn) { btn.disabled = true; btn.style.opacity = '0.6'; btn.textContent = '⏳ Création…'; }
    try {
      const r = await apiFetch('/api/v1/tuteur/coach/create-tasks', {
        method: 'POST',
        headers: {'Content-Type':'application/json'},
        body: JSON.stringify({incident_id: incidentId, actions: actions, priorite: 3}),
      });
      if (!r.ok) {
        const err = await r.json().catch(() => ({}));
        throw new Error(err.detail || ('HTTP ' + r.status));
      }
      const data = await r.json();
      // Succès : ack le message coach et fermer la modale
      if (msgId) await ackMessage(msgId, null);
      closeSuggestModal();
      // Toast confirmation
      showToast('✓ ' + data.created + ' tâche(s) créée(s) dans le Kanban', 'ok');
    } catch(e) {
      if (btn) { btn.disabled = false; btn.style.opacity = ''; btn.textContent = '✓ Créer les tâches dans le Kanban'; }
      alert('Erreur création tâches : ' + e.message);
    }
  }

  function closeSuggestModal() {
    const o = document.getElementById('coach-suggest-overlay');
    if (o) o.remove();
  }

  // ── v3000h18 — Modale d'aide réglementaire (ARS / ANSSI / CNIL) ────────
  async function showObligationModal(obligationId, incidentId) {
    closeObligationModal();
    const overlay = document.createElement('div');
    overlay.id = 'coach-obligation-overlay';
    overlay.style.cssText = 'position:fixed;inset:0;background:rgba(15,23,42,0.55);'
      + 'z-index:99999;display:flex;align-items:center;justify-content:center;padding:20px;';
    overlay.innerHTML = [
      '<div id="coach-obl-card" style="background:white;border-radius:14px;width:680px;',
      '  max-width:100%;max-height:calc(100vh - 40px);overflow:hidden;display:flex;',
      '  flex-direction:column;box-shadow:0 24px 64px rgba(0,0,0,0.32);">',
      '  <div style="background:linear-gradient(135deg,#003189,#1e40af);color:white;',
      '       padding:14px 20px;display:flex;align-items:center;gap:12px;">',
      '    <div style="font-size:24px">📞</div>',
      '    <div style="flex:1">',
      '      <div id="coach-obl-title" style="font-weight:700;font-size:16px">Chargement…</div>',
      '      <div id="coach-obl-sub" style="font-size:12px;opacity:0.85"></div>',
      '    </div>',
      '    <button id="coach-obl-close" style="background:rgba(255,255,255,0.18);color:white;',
      '            border:none;width:32px;height:32px;border-radius:6px;cursor:pointer;',
      '            font-size:18px;font-weight:700">✕</button>',
      '  </div>',
      '  <div id="coach-obl-body" style="padding:20px;overflow:auto;flex:1;',
      '       font-family:system-ui,-apple-system,sans-serif;font-size:13.5px;line-height:1.55">',
      '    <div style="text-align:center;padding:40px;color:#94a3b8">⏳ Chargement de l\'aide…</div>',
      '  </div>',
      '</div>',
    ].join('');
    document.body.appendChild(overlay);
    document.getElementById('coach-obl-close').onclick = closeObligationModal;
    overlay.onclick = function(e) {
      if (e.target === overlay) closeObligationModal();
    };

    // Charger les données
    try {
      const r = await apiFetch('/api/v1/tuteur/kb/obligation/' + encodeURIComponent(obligationId));
      if (!r.ok) {
        const err = await r.json().catch(() => ({}));
        throw new Error(err.detail || ('HTTP ' + r.status));
      }
      const data = await r.json();
      renderObligationBody(data, obligationId, incidentId);
    } catch(e) {
      const body = document.getElementById('coach-obl-body');
      if (body) body.innerHTML = '<div style="color:#e1000f;padding:20px">'
        + 'Erreur : ' + escapeHtml(e.message) + '</div>';
    }
  }

  function closeObligationModal() {
    const o = document.getElementById('coach-obligation-overlay');
    if (o) o.remove();
  }

  function renderObligationBody(data, obligationId, incidentId) {
    const title = document.getElementById('coach-obl-title');
    const sub   = document.getElementById('coach-obl-sub');
    if (title) title.textContent = data.label || 'Aide';
    if (sub) sub.textContent = data.autorite || '';

    // Contacts
    const contactsHtml = (data.contacts || []).map(function(c) {
      const icon = c.type === 'telephone' ? '☎' : (c.type === 'email' ? '✉' : '🔗');
      const valEsc = escapeHtml(c.valeur || '');
      let valDisplay = valEsc;
      if (c.type === 'telephone' && c.valeur && !c.valeur.startsWith('[')) {
        valDisplay = '<a href="tel:' + encodeURIComponent(c.valeur) + '" style="color:#003189;font-weight:600">' + valEsc + '</a>';
      } else if (c.type === 'email' && c.valeur && !c.valeur.startsWith('[')) {
        valDisplay = '<a href="mailto:' + encodeURIComponent(c.valeur) + '" style="color:#003189;font-weight:600">' + valEsc + '</a>';
      } else if (c.type === 'url' && c.valeur && c.valeur.startsWith('http')) {
        valDisplay = '<a href="' + valEsc + '" target="_blank" rel="noopener" style="color:#003189;font-weight:600">' + valEsc + '</a>';
      }
      const noteHtml = c.note ? '<div style="font-size:11px;color:#64748b;margin-top:2px">' + escapeHtml(c.note) + '</div>' : '';
      return [
        '<div style="background:#f8fafc;border-radius:8px;padding:10px 12px;margin-bottom:6px;border-left:3px solid #003189">',
        '  <div style="font-size:11px;color:#64748b;text-transform:uppercase;letter-spacing:0.4px">' + icon + ' ' + escapeHtml(c.label || '') + '</div>',
        '  <div style="font-family:ui-monospace,Menlo,monospace;margin-top:3px">' + valDisplay + '</div>',
        '  ' + noteHtml,
        '</div>',
      ].join('');
    }).join('');

    // Risques
    const risquesHtml = (data.risques || []).map(function(r) {
      return '<li style="margin-bottom:4px">' + escapeHtml(r) + '</li>';
    }).join('');

    // Note critique (CNIL surtout)
    const noteCritiqueHtml = data.note
      ? '<div style="background:#fef3c7;border-left:3px solid #f59e0b;padding:10px 12px;border-radius:6px;margin-top:14px;font-size:12.5px"><strong>⚠ </strong>' + escapeHtml(data.note) + '</div>'
      : '';

    // Bouton message-type
    const modeleBtn = data.has_modele
      ? '<button id="coach-obl-render-msg" style="background:#003189;color:white;border:none;padding:10px 16px;border-radius:8px;cursor:pointer;font-weight:600;font-size:13px;font-family:inherit">📋 Générer un message-type</button>'
      : '<span style="color:#94a3b8;font-style:italic;font-size:12px">Pas de modèle disponible</span>';

    const body = document.getElementById('coach-obl-body');
    if (!body) return;
    body.innerHTML = [
      '<div style="display:flex;gap:14px;margin-bottom:18px;padding:10px 12px;background:#eff6ff;border-radius:8px">',
      '  <div style="flex:1"><div style="font-size:10px;color:#64748b;text-transform:uppercase;letter-spacing:0.4px">Délai légal</div>',
      '    <div style="font-weight:600;margin-top:2px">' + escapeHtml(data.delai || '—') + '</div></div>',
      '  <div style="flex:1"><div style="font-size:10px;color:#64748b;text-transform:uppercase;letter-spacing:0.4px">Fondement</div>',
      '    <div style="font-weight:600;margin-top:2px;font-size:12px">' + escapeHtml(data.fondement || '—') + '</div></div>',
      '</div>',

      '<h3 style="margin:0 0 10px;color:#003189;font-size:13px;text-transform:uppercase;letter-spacing:0.5px">📞 Contacts</h3>',
      contactsHtml || '<div style="color:#94a3b8">Aucun contact renseigné</div>',

      '<h3 style="margin:18px 0 10px;color:#e1000f;font-size:13px;text-transform:uppercase;letter-spacing:0.5px">⚠ Risque si non-déclaration</h3>',
      '<ul style="margin:0;padding-left:20px;color:#0f172a">' + (risquesHtml || '<li>Non documenté</li>') + '</ul>',

      noteCritiqueHtml,

      '<div style="margin-top:20px;text-align:center;padding-top:14px;border-top:1px solid #e2e8f0">',
      '  ' + modeleBtn,
      '</div>',

      '<div id="coach-obl-msg-zone" style="margin-top:14px"></div>',
    ].join('');

    // Brancher bouton message-type
    const renderBtn = document.getElementById('coach-obl-render-msg');
    if (renderBtn) {
      renderBtn.onclick = function() { renderObligationMessage(obligationId, incidentId); };
    }
  }

  async function renderObligationMessage(obligationId, incidentId) {
    const btn = document.getElementById('coach-obl-render-msg');
    const zone = document.getElementById('coach-obl-msg-zone');
    if (!zone) return;
    if (btn) { btn.disabled = true; btn.textContent = '⏳ Génération…'; }
    zone.innerHTML = '<div style="color:#64748b;padding:10px;text-align:center">⏳ Génération du message-type…</div>';
    try {
      const body = {obligation_id: obligationId};
      if (incidentId) body.incident_id = incidentId;
      const r = await apiFetch('/api/v1/tuteur/kb/render-message', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify(body),
      });
      if (!r.ok) {
        const err = await r.json().catch(() => ({}));
        throw new Error(err.detail || ('HTTP ' + r.status));
      }
      const data = await r.json();
      zone.innerHTML = [
        '<div style="background:#f8fafc;border-radius:8px;padding:14px;border:1px solid #e2e8f0">',
        '  <div style="font-size:11px;color:#64748b;text-transform:uppercase;letter-spacing:0.4px;margin-bottom:6px">Objet</div>',
        '  <div style="font-weight:600;margin-bottom:14px">' + escapeHtml(data.objet || '') + '</div>',
        '  <div style="font-size:11px;color:#64748b;text-transform:uppercase;letter-spacing:0.4px;margin-bottom:6px">Corps du message</div>',
        '  <textarea id="coach-obl-msg-text" readonly style="width:100%;min-height:240px;font-family:ui-monospace,Menlo,monospace;font-size:12px;padding:10px;border:1px solid #cbd5e1;border-radius:6px;box-sizing:border-box;resize:vertical;background:white">' + escapeHtml(data.corps || '') + '</textarea>',
        '  <div style="display:flex;gap:8px;margin-top:10px">',
        '    <button id="coach-obl-copy" style="flex:1;background:#10b981;color:white;border:none;padding:9px 14px;border-radius:6px;cursor:pointer;font-weight:600;font-size:13px;font-family:inherit">📋 Copier dans le presse-papier</button>',
        '  </div>',
        '  <div style="font-size:11px;color:#94a3b8;margin-top:8px;line-height:1.4">ⓘ Les zones <code>[à compléter]</code> doivent être renseignées avant envoi. Le message est un brouillon — vérifiez-le.</div>',
        '</div>',
      ].join('');
      // Bouton copier
      const copyBtn = document.getElementById('coach-obl-copy');
      if (copyBtn) {
        copyBtn.onclick = function() {
          const text = (data.objet ? 'Objet : ' + data.objet + '\n\n' : '') + (data.corps || '');
          if (navigator.clipboard && navigator.clipboard.writeText) {
            navigator.clipboard.writeText(text).then(function() {
              copyBtn.textContent = '✓ Copié !';
              copyBtn.style.background = '#059669';
              setTimeout(function() {
                copyBtn.textContent = '📋 Copier dans le presse-papier';
                copyBtn.style.background = '#10b981';
              }, 2000);
            }).catch(function() {
              fallbackCopy(text, copyBtn);
            });
          } else {
            fallbackCopy(text, copyBtn);
          }
        };
      }
    } catch(e) {
      zone.innerHTML = '<div style="color:#e1000f;padding:10px">Erreur : ' + escapeHtml(e.message) + '</div>';
    } finally {
      if (btn) { btn.disabled = false; btn.textContent = '📋 Générer un message-type'; }
    }
  }

  function fallbackCopy(text, btn) {
    const ta = document.createElement('textarea');
    ta.value = text;
    ta.style.position = 'fixed';
    ta.style.left = '-9999px';
    document.body.appendChild(ta);
    ta.select();
    try { document.execCommand('copy'); btn.textContent = '✓ Copié !'; }
    catch(e) { btn.textContent = '✗ Échec copie'; }
    document.body.removeChild(ta);
    setTimeout(function() { btn.textContent = '📋 Copier dans le presse-papier'; }, 2000);
  }

  function showToast(text, type) {
    // Si l'app principale a déjà un toast(), on l'utilise, sinon fallback
    if (typeof window.toast === 'function') {
      try { window.toast(text, type); return; } catch(e) {}
    }
    const t = document.createElement('div');
    t.style.cssText = 'position:fixed;bottom:90px;right:20px;background:#003189;color:white;'
      + 'padding:12px 18px;border-radius:8px;box-shadow:0 8px 24px rgba(0,0,0,0.25);'
      + 'font-family:system-ui;font-size:13px;z-index:99999;';
    t.textContent = text;
    document.body.appendChild(t);
    setTimeout(function() { t.remove(); }, 4000);
  }

  function ackMessage(msgId, snoozeMinutes) {
    const body = snoozeMinutes ? { snooze_minutes: snoozeMinutes } : {};
    apiFetch('/api/v1/tuteur/coach/ack/' + msgId, {
      method: 'POST',
      headers: {'Content-Type':'application/json'},
      body: JSON.stringify(body),
    }).then(function() {
      // Retirer le message de la liste locale
      COACH.messages = COACH.messages.filter(function(m) { return m.id !== msgId; });
      renderMessages();
      // MAJ badge
      if (!COACH.open) {
        COACH.unreadCount = Math.max(0, COACH.unreadCount - 1);
        updateBadge();
      }
    }).catch(function(){});
  }

  function onMute() {
    if (!confirm('Faire silence le coach pendant 10 minutes ?')) return;
    apiFetch('/api/v1/tuteur/coach/mute?minutes=10', {method:'POST'})
      .then(function() {
        COACH.messages = [];
        renderMessages();
        COACH.unreadCount = 0;
        updateBadge();
      }).catch(function(){});
  }

  // ── v3000h14 — Copilote stratégique : point de situation + question libre ──

  function _renderSyntheseHtml(data) {
    function ul(items) {
      if (!items || !items.length) return '<ul><li>(rien)</li></ul>';
      return '<ul>' + items.map(function(i) { return '<li>' + escapeHtml(i) + '</li>'; }).join('') + '</ul>';
    }
    function ol(items) {
      if (!items || !items.length) return '<ol><li>(rien)</li></ol>';
      return '<ol>' + items.map(function(i) { return '<li>' + escapeHtml(i) + '</li>'; }).join('') + '</ol>';
    }
    const srcLabel = data.source === 'ia'
      ? ('IA (' + (data.ai_provider || data.provider || 'inconnu') + ')')
      : (data.source === 'local' ? 'synthèse locale (IA indisponible)' : 'inconnu');
    return [
      '<div class="coach-synthese">',
      '  <h4>🎯 Situation</h4>',
      '  <div>' + escapeHtml(data.situation || '(synthèse non disponible)') + '</div>',
      '  <h4>⏱ Court terme (30 min)</h4>',
      ul(data.court_terme),
      '  <h4>📅 Moyen terme (2h)</h4>',
      ul(data.moyen_terme),
      '  <h4>🔭 Long terme (24h)</h4>',
      ul(data.long_terme),
      '  <div class="coach-syn-priorites">',
      '    <h4>📌 Priorités</h4>',
      ol(data.priorites),
      '  </div>',
      '  <div class="coach-syn-source">Source : ' + escapeHtml(srcLabel)
        + ' — durée exercice : ' + (data.duree_min || 0) + ' min</div>',
      '</div>',
    ].join('');
  }

  function _appendCustomBlock(html) {
    // Insérer un bloc personnalisé (synthèse, Q/R) dans la zone messages,
    // en haut (le plus récent en premier), et masquer le placeholder vide.
    const container = document.getElementById('coach-messages');
    if (!container) return;
    const empty = document.getElementById('coach-empty');
    if (empty) empty.remove();
    const wrap = document.createElement('div');
    wrap.innerHTML = html;
    // Insérer en tête
    container.insertBefore(wrap, container.firstChild);
    // Scroll en haut pour voir le nouveau bloc
    container.scrollTop = 0;
  }

  // v3.1.0 — Ouvrir l'historique complet des messages (lus + non lus)
  async function onOpenHistory() {
    const btn = document.getElementById('coach-act-history');
    if (btn) { btn.disabled = true; }
    try {
      const r = await apiFetch('/api/v1/tuteur/coach/history?limit=100');
      if (!r.ok) {
        const err = await r.json().catch(() => ({}));
        throw new Error(err.detail || ('HTTP ' + r.status));
      }
      const data = await r.json();
      const msgs = data.messages || [];
      _appendCustomBlock(_renderHistoryHtml(msgs));
    } catch(e) {
      _appendCustomBlock(
        '<div class="coach-synthese" style="border-left-color:#e1000f">' +
        '<h4 style="color:#e1000f">Erreur</h4>' +
        '<div>Impossible de charger l\'historique : ' + escapeHtml(e.message) + '</div></div>'
      );
    } finally {
      if (btn) { btn.disabled = false; }
    }
  }

  function _renderHistoryHtml(msgs) {
    if (!msgs.length) {
      return '<div class="coach-synthese"><h4>🔔 Historique</h4><div style="color:#94a3b8">Aucun message reçu pour l\'instant.</div></div>';
    }

    // v3000h18 — Grouper les messages identiques (même rule_id+target_id)
    // Affiche un seul item avec compteur + dropdown des timestamps.
    const groups = {};
    msgs.forEach(function(m) {
      const key = (m.rule_id || 'unk') + '|' + (m.target_type || '') + '|' + (m.target_id || '');
      if (!groups[key]) groups[key] = [];
      groups[key].push(m);
    });

    const items = Object.values(groups).map(function(grp) {
      // grp est trié desc par created_at (l'API renvoie déjà ainsi)
      const latest = grp[0];
      const niveau = latest.niveau || 'marker';
      const bord = niveau === 'alert' ? '#e1000f' : (niveau === 'silent' ? '#94a3b8' : '#003189');
      const isAck = !!latest.ack_at;
      const opacity = isAck ? 0.55 : 1;
      const tsRecent = latest.created_at
        ? new Date(latest.created_at).toLocaleTimeString('fr-FR', {hour:'2-digit',minute:'2-digit'})
        : '';
      const acklabel = isAck ? ' <span style="font-size:10px;color:#94a3b8">(traité)</span>' : '';
      const compteur = grp.length > 1
        ? ' • <span style="background:#fef3c7;color:#92400e;padding:1px 6px;border-radius:8px;font-weight:600;font-size:10px">signalé ' + grp.length + ' fois</span>'
        : '';

      // Liste détaillée des timestamps si plusieurs émissions
      let detailHtml = '';
      if (grp.length > 1) {
        const tsList = grp.map(function(m) {
          const t = m.created_at
            ? new Date(m.created_at).toLocaleTimeString('fr-FR', {hour:'2-digit',minute:'2-digit'})
            : '?';
          const a = m.ack_at ? ' ✓' : '';
          return '<span style="display:inline-block;padding:1px 6px;margin:1px;background:#f1f5f9;border-radius:4px;font-size:10px;color:#475569">' + escapeHtml(t) + a + '</span>';
        }).join('');
        detailHtml = '<div style="margin-top:5px;font-size:10px">' + tsList + '</div>';
      }

      return [
        '<div style="background:white;padding:10px 12px;border-left:3px solid ' + bord + ';',
        'border-radius:6px;font-size:12.5px;line-height:1.45;margin-bottom:6px;opacity:' + opacity + '">',
        '<div style="font-size:10px;color:#94a3b8;margin-bottom:3px">',
        '  ' + escapeHtml(tsRecent) + ' • ' + escapeHtml(niveau) + acklabel + compteur,
        '</div>',
        '<div>' + escapeHtml(latest.message) + '</div>',
        detailHtml,
        '</div>',
      ].join('');
    }).join('');

    const nbGroups = Object.keys(groups).length;
    const titre = nbGroups === msgs.length
      ? '🔔 Historique (' + msgs.length + ' message' + (msgs.length > 1 ? 's' : '') + ')'
      : '🔔 Historique (' + nbGroups + ' sujet' + (nbGroups > 1 ? 's' : '') + ', ' + msgs.length + ' message' + (msgs.length > 1 ? 's' : '') + ')';

    return [
      '<div class="coach-synthese">',
      '  <h4>' + titre + '</h4>',
      '  <div style="margin-top:6px">' + items + '</div>',
      '</div>',
    ].join('');
  }

  async function onPointDeSituation() {
    const btn = document.getElementById('coach-act-situation');
    if (btn) { btn.disabled = true; btn.textContent = '⏳ Analyse…'; }
    try {
      const r = await apiFetch('/api/v1/tuteur/coach/situation', {method: 'POST'});
      if (!r.ok) {
        const err = await r.json().catch(() => ({}));
        throw new Error(err.detail || ('HTTP ' + r.status));
      }
      const data = await r.json();
      _appendCustomBlock(_renderSyntheseHtml(data));
    } catch(e) {
      _appendCustomBlock(
        '<div class="coach-synthese" style="border-left-color:#e1000f">' +
        '<h4 style="color:#e1000f">Erreur</h4>' +
        '<div>Impossible de générer la synthèse : ' + escapeHtml(e.message) + '</div></div>'
      );
    } finally {
      if (btn) { btn.disabled = false; btn.innerHTML = '🎯 Point de situation'; }
    }
  }

  async function onAskSubmit() {
    const input = document.getElementById('coach-prompt');
    const sendBtn = document.getElementById('coach-prompt-send');
    if (!input) return;
    const q = (input.value || '').trim();
    if (!q) return;
    // v3000h18 — retirer le hint "Mode Conseil" maintenant qu'on l'utilise
    const hint = document.getElementById('coach-ask-hint');
    if (hint && hint.parentNode) hint.parentNode.remove();
    if (sendBtn) { sendBtn.disabled = true; sendBtn.textContent = '⏳'; }
    input.disabled = true;

    // Afficher la question immédiatement (UX)
    _appendCustomBlock(
      '<div class="coach-answer">' +
      '<div class="coach-question">' + escapeHtml(q) + '</div>' +
      '<div style="margin-top:6px;color:#94a3b8;font-style:italic">⏳ Réflexion…</div>' +
      '</div>'
    );
    const pendingBlock = document.querySelector('#coach-messages .coach-answer');

    try {
      const r = await apiFetch('/api/v1/tuteur/coach/ask', {
        method: 'POST',
        headers: {'Content-Type':'application/json'},
        body: JSON.stringify({question: q}),
      });
      if (!r.ok) {
        const err = await r.json().catch(() => ({}));
        throw new Error(err.detail || ('HTTP ' + r.status));
      }
      const data = await r.json();
      if (pendingBlock) {
        const srcLabel = data.source === 'ia'
          ? ('IA (' + (data.provider || 'inconnu') + ')')
          : (data.source === 'config_missing' ? 'configuration manquante' : 'erreur');
        pendingBlock.innerHTML =
          '<div class="coach-question">' + escapeHtml(q) + '</div>' +
          '<div style="margin-top:8px">' + escapeHtml(data.reponse || '(vide)') + '</div>' +
          '<div class="coach-syn-source" style="margin-top:6px">Source : ' + escapeHtml(srcLabel) + '</div>';
      }
      input.value = '';
    } catch(e) {
      if (pendingBlock) {
        pendingBlock.innerHTML =
          '<div class="coach-question">' + escapeHtml(q) + '</div>' +
          '<div style="margin-top:6px;color:#e1000f">Erreur : ' + escapeHtml(e.message) + '</div>';
      }
    } finally {
      input.disabled = false;
      if (sendBtn) { sendBtn.disabled = false; sendBtn.textContent = '→'; }
      input.focus();
    }
  }

  // ── Polling ─────────────────────────────────────────────────────────────
  async function pollCheck() {
    if (!COACH.enabled) return;
    try {
      const r = await apiFetch('/api/v1/tuteur/coach/check');
      if (!r.ok) return;
      const data = await r.json();
      const previousIds = new Set(COACH.messages.map(function(m){return m.id;}));
      COACH.messages = data.messages || [];
      COACH.sessionId = data.session_id;
      // Détecter les nouveaux pour le badge
      let nouveaux = 0;
      let nouveauxAlert = 0;
      COACH.messages.forEach(function(m){
        if (!previousIds.has(m.id)) {
          nouveaux++;
          if ((m.niveau || 'marker') === 'alert') nouveauxAlert++;
        }
      });
      if (nouveaux > 0 && !COACH.open) {
        COACH.unreadCount += nouveaux;
        updateBadge();
      }
      // v3.1.0 — Escalade visuelle/sonore pour les ALERTES uniquement
      if (nouveauxAlert > 0 && !COACH.open) {
        _triggerAlertEscalation();
      }
      // Si déjà ouvert, on re-render pour voir les nouveaux
      if (COACH.open) renderMessages();
      // Afficher la bulle (au cas où elle aurait été cachée)
      const bubble = document.getElementById('coach-bubble');
      if (bubble && !COACH.open) bubble.style.display = 'flex';
    } catch(e) { /* silencieux */ }
  }

  // v3.1.0 — Pulse rouge + bip court (1 seul). Désactivable via mute.
  function _triggerAlertEscalation() {
    const bubble = document.getElementById('coach-bubble');
    if (bubble) {
      bubble.classList.add('coach-alert-pulse');
      setTimeout(function() { bubble.classList.remove('coach-alert-pulse'); }, 8000);
    }
    // Bip court — désactivable si le user a mis le coach en mute (localStorage)
    if (localStorage.getItem('coach_mute_sound') === '1') return;
    try {
      // Bip très court 800Hz pendant 150ms via Web Audio API
      const Ctx = window.AudioContext || window.webkitAudioContext;
      if (!Ctx) return;
      const ctx = new Ctx();
      const osc = ctx.createOscillator();
      const gain = ctx.createGain();
      osc.type = 'sine';
      osc.frequency.value = 880;
      gain.gain.value = 0.18;
      osc.connect(gain).connect(ctx.destination);
      osc.start();
      setTimeout(function() {
        gain.gain.exponentialRampToValueAtTime(0.0001, ctx.currentTime + 0.1);
        osc.stop(ctx.currentTime + 0.15);
        setTimeout(function() { try { ctx.close(); } catch(e) {} }, 300);
      }, 150);
    } catch(e) { /* silencieux */ }
  }

  // ── Activation conditionnelle ───────────────────────────────────────────
  async function checkPluginEnabled() {
    try {
      const r = await apiFetch('/api/v1/plugins/active');
      if (!r.ok) return false;
      const plugins = await r.json();
      return plugins.some(function(p){ return p.id === 'tuteur'; });
    } catch(e) { return false; }
  }

  // ── Init publique ───────────────────────────────────────────────────────
  window.coachInit = async function() {
    // Pas de double init
    if (COACH.enabled) return;
    const ok = await checkPluginEnabled();
    if (!ok) return;
    COACH.enabled = true;
    injectStyles();
    buildDom();
    // Premier check immédiat puis polling
    await pollCheck();
    COACH.pollTimer = setInterval(pollCheck, COACH.pollMs);
  };

  // Auto-init après que initAfterLogin ait fini (l'app principale appelle
  // window.coachInit explicitement). Pas d'auto-trigger ici pour éviter
  // les races avec l'authentification.
})();
