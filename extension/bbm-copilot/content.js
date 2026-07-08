(function() {
  'use strict';

  let panel = null;
  let pollInterval = null;
  let config = { apiBase: 'http://127.0.0.1:8765', draftId: '', token: '' };

  const ICON_SVG = `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M12 2L2 7l10 5 10-5-10-5zM2 17l10 5 10-5M2 12l10 5 10-5"/></svg>`;

  const BOARD_SELECTORS = [
    '[class*="draft-board"]',
    '[class*="DraftBoard"]',
    '[class*="drafted"]',
    '[class*="pick-list"]',
    '[data-testid*="board"]',
  ];

  function buildPostHeaders() {
    const headers = { 'Content-Type': 'application/json' };
    if (config.token) headers['X-BBM-Token'] = config.token;
    return headers;
  }

  function loadConfig() {
    return new Promise((resolve) => {
      chrome.storage.local.get(['apiBase', 'draftId', 'token'], (result) => {
        config.apiBase = (result.apiBase || 'http://127.0.0.1:8765').replace(/\/$/, '');
        config.draftId = result.draftId || '';
        config.token = result.token || '';
        resolve(config);
      });
    });
  }

  async function syncDraftIdFromServer() {
    try {
      const res = await fetch(`${config.apiBase}/api/status`);
      const data = await res.json();
      if (data.draft_id) {
        if (config.draftId && config.draftId !== data.draft_id) {
          console.warn(
            `BBM: draft_id updated ${config.draftId} → ${data.draft_id} (serve restarted)`
          );
        }
        config.draftId = data.draft_id;
        chrome.storage.local.set({ draftId: data.draft_id });
      }
      return data;
    } catch (_e) {
      return null;
    }
  }

  function createPanel() {
    if (panel) return panel;

    panel = document.createElement('div');
    panel.id = 'cemini-bbm-panel';
    panel.innerHTML = `
      <div class="bbm-header">
        <div class="bbm-title">
          <span class="bbm-icon">${ICON_SVG}</span>
          <span>CeminiDFS BBM</span>
        </div>
        <div class="bbm-controls">
          <button class="bbm-btn bbm-btn-icon" id="bbm-undo" title="Undo last recorded action">↶</button>
          <button class="bbm-btn bbm-btn-icon" id="bbm-refresh" title="Refresh recommendations">↻</button>
          <button class="bbm-btn bbm-btn-icon" id="bbm-toggle">−</button>
        </div>
      </div>
      <div class="bbm-body">
        <div class="bbm-config-hint" id="bbm-hint"></div>
        <div class="bbm-section">
          <div class="bbm-section-title">Top Recommendations</div>
          <div class="bbm-recs" id="bbm-recs">
            <div class="bbm-empty">Loading...</div>
          </div>
        </div>
        <div class="bbm-section">
          <div class="bbm-sync-row">
            <button class="bbm-btn bbm-btn-primary" id="bbm-scan">Scan Board</button>
            <span class="bbm-sync-status" id="bbm-sync-status"></span>
          </div>
        </div>
      </div>
    `;

    document.body.appendChild(panel);

    const header = panel.querySelector('.bbm-header');
    let isDragging = false, dragOffsetX, dragOffsetY;

    header.addEventListener('mousedown', (e) => {
      isDragging = true;
      const rect = panel.getBoundingClientRect();
      dragOffsetX = e.clientX - rect.left;
      dragOffsetY = e.clientY - rect.top;
      panel.style.transition = 'none';
    });

    document.addEventListener('mousemove', (e) => {
      if (!isDragging) return;
      panel.style.left = (e.clientX - dragOffsetX) + 'px';
      panel.style.top = (e.clientY - dragOffsetY) + 'px';
      panel.style.right = 'auto';
    });

    document.addEventListener('mouseup', () => {
      isDragging = false;
      panel.style.transition = '';
    });

    panel.querySelector('#bbm-toggle').addEventListener('click', () => {
      const body = panel.querySelector('.bbm-body');
      body.classList.toggle('collapsed');
      panel.querySelector('#bbm-toggle').textContent = body.classList.contains('collapsed') ? '+' : '−';
    });

    panel.querySelector('#bbm-refresh').addEventListener('click', fetchRecommendations);
    panel.querySelector('#bbm-scan').addEventListener('click', scanBoard);
    panel.querySelector('#bbm-undo').addEventListener('click', undoLast);

    return panel;
  }

  function collectBoardLabels() {
    let root = null;
    let usedSelector = null;
    let warning = null;
    for (const sel of BOARD_SELECTORS) {
      root = document.querySelector(sel);
      if (root) { usedSelector = sel; break; }
    }
    if (!root) {
      root = document.body;
      usedSelector = 'body-fallback';
      warning = 'Board container not found — page-wide scan (less precise)';
    }
    const labels = [];
    root.querySelectorAll('[aria-label]').forEach((el) => {
      const label = el.getAttribute('aria-label')?.trim();
      if (label && label.length >= 4 && label.length <= 60) labels.push(label);
    });
    return { labels: labels.slice(0, 200), warning, selector: usedSelector };
  }

  async function undoLast() {
    const statusEl = panel.querySelector('#bbm-sync-status');
    if (!config.draftId) { statusEl.textContent = 'Set draft ID in popup'; return; }
    try {
      const res = await fetch(`${config.apiBase}/api/undo`, {
        method: 'POST',
        headers: buildPostHeaders(),
        body: JSON.stringify({ draft_id: config.draftId }),
      });
      const data = await res.json();
      statusEl.textContent = (!res.ok || data.error)
        ? (data.error || `Undo failed (${res.status})`)
        : `Undid ${data.undone} (round ${data.round})`;
      fetchRecommendations();
      setTimeout(() => { statusEl.textContent = ''; }, 3000);
    } catch (_e) {
      statusEl.textContent = 'API unreachable — is serve running?';
    }
  }

  async function scanBoard() {
    const statusEl = panel.querySelector('#bbm-sync-status');
    statusEl.textContent = 'Scanning...';

    if (!config.draftId) {
      await syncDraftIdFromServer();
    }
    if (!config.draftId) {
      statusEl.textContent = 'Set draft ID in popup';
      return;
    }

    const { labels, warning } = collectBoardLabels();
    if (warning) {
      console.warn('BBM:', warning);
      if (labels.length === 0) {
        statusEl.textContent = `${warning} — no labels found`;
        return;
      }
      if (!window.confirm(`${warning}.\nSync ${labels.length} page-wide labels anyway? (may include undrafted players)`)) {
        statusEl.textContent = `${warning} — sync cancelled`;
        return;
      }
    } else if (labels.length === 0) {
      statusEl.textContent = 'No players found';
      return;
    }

    try {
      const res = await fetch(`${config.apiBase}/api/sync`, {
        method: 'POST',
        headers: buildPostHeaders(),
        body: JSON.stringify({ draft_id: config.draftId, labels })
      });

      const data = await res.json();
      if (!res.ok || data.error) {
        statusEl.textContent = data.error || `Sync failed (${res.status})`;
        return;
      }
      const ambiguousCount = data.ambiguous_count ?? 0;
      statusEl.textContent =
        (warning ? 'WARN page-wide scan — ' : '') +
        `Synced ${data.synced_count ?? 0} — ${data.skipped_count ?? 0} known — ` +
        `${data.unmatched_count ?? 0} unmatched` +
        (ambiguousCount ? ` — ${ambiguousCount} ambiguous` : '');
      if (data.unmatched?.length) console.warn('BBM unmatched names:', data.unmatched);
      (data.ambiguous || []).slice(0, 3).forEach((entry) => {
        renderAmbiguous(entry.query, entry.matches, '/api/taken');
      });
      fetchRecommendations();
      if (!ambiguousCount && !warning) setTimeout(() => { statusEl.textContent = ''; }, 3000);
    } catch (_e) {
      statusEl.textContent = 'API unreachable — is serve running?';
      setTimeout(() => { statusEl.textContent = ''; }, 4000);
    }
  }

  async function fetchRecommendations() {
    const recsEl = panel.querySelector('#bbm-recs');

    if (!config.draftId) {
      await syncDraftIdFromServer();
    }
    if (!config.draftId) {
      recsEl.innerHTML = '<div class="bbm-empty">Set draft ID in extension popup (or start serve)</div>';
      return;
    }

    try {
      const url = `${config.apiBase}/api/recommendations?draft_id=${encodeURIComponent(config.draftId)}`;
      const res = await fetch(url);
      const data = await res.json();

      if (!res.ok || data.error) {
        const msg = data.error || `HTTP ${res.status}`;
        recsEl.innerHTML = `<div class="bbm-error">${escapeHtml(msg)}</div>`;
        return;
      }

      renderPivotWarning(data.pivot_warning, data.pivot_to);
      renderRecommendations(data.recommendations || []);
    } catch (_e) {
      recsEl.innerHTML = '<div class="bbm-error">API unreachable — run: ceminidfs bbm serve --slot N</div>';
    }
  }

  function renderRecommendations(recs) {
    const container = panel.querySelector('#bbm-recs');
    if (!recs.length) {
      container.innerHTML = '<div class="bbm-empty">No recommendations</div>';
      return;
    }

    const top = recs.slice(0, 3);
    container.innerHTML = top.map((r, i) => `
      <div class="bbm-rec">
        <div class="bbm-rank">${i + 1}</div>
        <div class="bbm-info">
          <div class="bbm-name">${escapeHtml(r.name || 'Unknown')}</div>
          <div class="bbm-meta">${escapeHtml(r.position || '')} ${escapeHtml(r.team || '')} ${escapeHtml(r.signal || '')}</div>
        </div>
        <div class="bbm-rec-actions">
          <div class="bbm-score">${typeof r.score === 'number' ? Math.round(r.score) : '-'}</div>
          <button class="bbm-btn bbm-btn-record" title="Record pick in ledger (you still draft manually on Underdog)">Rec</button>
        </div>
      </div>
    `).join('');

    container.querySelectorAll('.bbm-btn-record').forEach((btn, i) => {
      btn.addEventListener('click', (e) => {
        e.stopPropagation();
        recordPick(top[i].name || '');
      });
    });
  }

  async function recordPick(name) {
    const statusEl = panel.querySelector('#bbm-sync-status');
    if (!name) return;

    if (!config.draftId) {
      await syncDraftIdFromServer();
    }
    if (!config.draftId) {
      statusEl.textContent = 'Set draft ID in popup';
      return;
    }

    statusEl.textContent = `Recording ${name}...`;

    try {
      const res = await fetch(`${config.apiBase}/api/pick`, {
        method: 'POST',
        headers: buildPostHeaders(),
        body: JSON.stringify({ draft_id: config.draftId, name })
      });
      const data = await res.json();

      if (res.ok && data.ambiguous) {
        statusEl.textContent = `Ambiguous: ${data.query}`;
        renderAmbiguous(data.query, data.matches, '/api/pick');
        return;
      }

      if (!res.ok || data.error) {
        statusEl.textContent = data.error || `Pick failed (${res.status})`;
        setTimeout(() => { statusEl.textContent = ''; }, 4000);
        return;
      }

      statusEl.textContent = `Recorded ${data.player?.name || name}`;
      fetchRecommendations();
      setTimeout(() => { statusEl.textContent = ''; }, 3000);
    } catch (_e) {
      statusEl.textContent = 'API unreachable — is serve running?';
      setTimeout(() => { statusEl.textContent = ''; }, 4000);
    }
  }

  function renderPivotWarning(warning, pivotTo) {
    let el = panel.querySelector('#bbm-pivot');
    if (!warning) { if (el) el.remove(); return; }
    if (!el) {
      el = document.createElement('div');
      el.id = 'bbm-pivot';
      el.className = 'bbm-pivot-warning';
      const body = panel.querySelector('.bbm-body');
      body.insertBefore(el, body.querySelector('.bbm-section'));
    }
    el.innerHTML = `<span>${escapeHtml(warning)}</span>` + (pivotTo
      ? `<button class="bbm-btn bbm-btn-pivot" id="bbm-apply-pivot">Pivot → ${escapeHtml(pivotTo)}</button>`
      : '');
    const btn = el.querySelector('#bbm-apply-pivot');
    if (btn) btn.addEventListener('click', () => applyPivot(pivotTo));
  }

  async function applyPivot(archetype) {
    const statusEl = panel.querySelector('#bbm-sync-status');
    try {
      const res = await fetch(`${config.apiBase}/api/pivot`, {
        method: 'POST',
        headers: buildPostHeaders(),
        body: JSON.stringify({ draft_id: config.draftId, archetype }),
      });
      const data = await res.json();
      statusEl.textContent = (!res.ok || data.error)
        ? (data.error || `Pivot failed (${res.status})`)
        : `Pivoted to ${archetype}`;
      fetchRecommendations();   // warning clears server-side (pivot_applied=1)
      setTimeout(() => { statusEl.textContent = ''; }, 3000);
    } catch (_e) {
      statusEl.textContent = 'API unreachable — is serve running?';
    }
  }

  function renderAmbiguous(query, matches, endpoint) {
    // endpoint: '/api/pick' (Rec button flow) or '/api/taken' (Scan Board flow)
    let box = panel.querySelector('#bbm-ambiguous');
    if (!box) {
      box = document.createElement('div');
      box.id = 'bbm-ambiguous';
      box.className = 'bbm-ambiguous';
      panel.querySelector('.bbm-body').appendChild(box);
    }
    const row = document.createElement('div');
    row.className = 'bbm-ambiguous-row';
    row.innerHTML = `<div class="bbm-ambiguous-query">Which “${escapeHtml(query)}”?</div>`;
    (matches || []).slice(0, 4).forEach((m) => {
      const btn = document.createElement('button');
      btn.className = 'bbm-btn bbm-ambiguous-btn';
      btn.textContent = `${m.name} (${m.position || '?'} ${m.team || '?'})`;
      btn.addEventListener('click', async () => {
        await postResolved(endpoint, m.player_id);
        row.remove();
        if (!box.querySelector('.bbm-ambiguous-row')) box.remove();
      });
      row.appendChild(btn);
    });
    const dismiss = document.createElement('button');
    dismiss.className = 'bbm-btn bbm-btn-icon bbm-ambiguous-dismiss';
    dismiss.textContent = '✕';
    dismiss.addEventListener('click', () => {
      row.remove();
      if (!box.querySelector('.bbm-ambiguous-row')) box.remove();
    });
    row.appendChild(dismiss);
    box.appendChild(row);
  }

  async function postResolved(endpoint, playerId) {
    const statusEl = panel.querySelector('#bbm-sync-status');
    try {
      const res = await fetch(`${config.apiBase}${endpoint}`, {
        method: 'POST',
        headers: buildPostHeaders(),
        body: JSON.stringify({ draft_id: config.draftId, player_id: playerId }),
      });
      const data = await res.json();
      statusEl.textContent = (!res.ok || data.error)
        ? (data.error || `Failed (${res.status})`)
        : `Recorded ${data.player?.name || playerId}`;
      fetchRecommendations();
      setTimeout(() => { statusEl.textContent = ''; }, 3000);
    } catch (_e) {
      statusEl.textContent = 'API unreachable — is serve running?';
    }
  }

  function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = String(text);
    return div.innerHTML;
  }

  function updateHint() {
    const hint = panel.querySelector('#bbm-hint');
    hint.textContent = config.draftId
      ? `Draft: ${config.draftId}`
      : 'No draft ID — click extension icon to configure';
  }

  function startPolling() {
    if (pollInterval) return;
    pollInterval = setInterval(fetchRecommendations, 3000);
  }

  function stopPolling() {
    if (pollInterval) {
      clearInterval(pollInterval);
      pollInterval = null;
    }
  }

  async function init() {
    await loadConfig();
    await syncDraftIdFromServer();
    createPanel();
    updateHint();
    fetchRecommendations();
    startPolling();

    chrome.storage.onChanged.addListener((changes) => {
      if (changes.apiBase) {
        config.apiBase = (changes.apiBase.newValue || '').replace(/\/$/, '');
      }
      if (changes.draftId) {
        config.draftId = changes.draftId.newValue || '';
        updateHint();
        fetchRecommendations();
      }
      if (changes.token) {
        config.token = changes.token.newValue || '';
      }
    });

    document.addEventListener('visibilitychange', () => {
      document.hidden ? stopPolling() : startPolling();
    });
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }
})();
