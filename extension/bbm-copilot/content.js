(function() {
  'use strict';

  let panel = null;
  let pollInterval = null;
  let config = { apiBase: 'http://127.0.0.1:8765', draftId: '' };

  const ICON_SVG = `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M12 2L2 7l10 5 10-5-10-5zM2 17l10 5 10-5M2 12l10 5 10-5"/></svg>`;

  function loadConfig() {
    return new Promise((resolve) => {
      chrome.storage.local.get(['apiBase', 'draftId'], (result) => {
        config.apiBase = (result.apiBase || 'http://127.0.0.1:8765').replace(/\/$/, '');
        config.draftId = result.draftId || '';
        resolve(config);
      });
    });
  }

  async function syncDraftIdFromServer() {
    try {
      const res = await fetch(`${config.apiBase}/api/status`);
      const data = await res.json();
      if (data.draft_id && !config.draftId) {
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

    return panel;
  }

  function extractPlayerNames() {
    const names = new Set();
    const skipPatterns = /pick|draft|round|timer|clock|queue|my turn|best available|underdog|fantasy|settings|close|menu/i;

    document.querySelectorAll('[aria-label]').forEach(el => {
      const label = el.getAttribute('aria-label')?.trim();
      if (!label || skipPatterns.test(label)) return;
      if (label.length < 4 || label.length > 50) return;

      const words = label.split(/\s+/);
      if (words.length >= 2 && /^[A-Za-z\-\'\.]+$/.test(words[0])) {
        names.add(label.replace(/\s+(WR|RB|QB|TE|FLEX)\b.*$/i, '').trim());
      }
    });

    document.querySelectorAll('button, div, span').forEach(el => {
      const text = el.textContent?.trim();
      if (!text || text.length < 3 || text.length > 40) return;
      if (skipPatterns.test(text)) return;

      const words = text.split(/\s+/);
      if (words.length >= 2 && /^[A-Z]/.test(words[0])) {
        names.add(text);
      }
    });

    return Array.from(names).slice(0, 50);
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

    const names = extractPlayerNames();
    if (names.length === 0) {
      statusEl.textContent = 'No players found';
      return;
    }

    try {
      const res = await fetch(`${config.apiBase}/api/sync`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ draft_id: config.draftId, names })
      });

      const data = await res.json();
      if (!res.ok || data.error) {
        statusEl.textContent = data.error || `Sync failed (${res.status})`;
        return;
      }
      statusEl.textContent = `Synced ${data.synced_count ?? data.synced?.length ?? 0}`;
      fetchRecommendations();
      setTimeout(() => { statusEl.textContent = ''; }, 3000);
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

    container.innerHTML = recs.slice(0, 3).map((r, i) => `
      <div class="bbm-rec">
        <div class="bbm-rank">${i + 1}</div>
        <div class="bbm-info">
          <div class="bbm-name">${escapeHtml(r.name || 'Unknown')}</div>
          <div class="bbm-meta">${escapeHtml(r.position || '')} ${escapeHtml(r.team || '')} ${escapeHtml(r.signal || '')}</div>
        </div>
        <div class="bbm-score">${typeof r.score === 'number' ? Math.round(r.score) : '-'}</div>
      </div>
    `).join('');
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
