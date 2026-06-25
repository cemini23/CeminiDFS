(function() {
  'use strict';

  let panel = null;
  let pollInterval = null;
  let config = { apiBase: 'http://127.0.0.1:8765', draftId: '' };

  const ICON_SVG = `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M12 2L2 7l10 5 10-5-10-5zM2 17l10 5 10-5M2 12l10 5 10-5"/></svg>`;

  function loadConfig() {
    return new Promise((resolve) => {
      chrome.storage.local.get(['apiBase', 'draftId'], (result) => {
        config.apiBase = result.apiBase || 'http://127.0.0.1:8765';
        config.draftId = result.draftId || '';
        resolve(config);
      });
    });
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
    const skipPatterns = /pick|draft|round|timer|clock|queue|my turn|best available/i;

    document.querySelectorAll('[aria-label]').forEach(el => {
      const label = el.getAttribute('aria-label')?.trim();
      if (!label || skipPatterns.test(label)) return;

      const words = label.split(/\s+/);
      if (words.length >= 2 && /^[A-Za-z\-\'\.]+$/.test(words[0])) {
        names.add(label);
      }
    });

    document.querySelectorAll('button, div, span').forEach(el => {
      const text = el.textContent?.trim();
      if (!text || text.length < 3 || text.length > 40) return;
      if (skipPatterns.test(text)) return;

      const words = text.split(/\s+/);
      if (words.length === 2 && /^[A-Z][a-z]+$/.test(words[0]) && /^[A-Z][a-z\-\'\.]+$/.test(words[1])) {
        names.add(text);
      }
    });

    return Array.from(names).slice(0, 50);
  }

  async function scanBoard() {
    const statusEl = panel.querySelector('#bbm-sync-status');
    statusEl.textContent = 'Scanning...';

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
      statusEl.textContent = `Synced ${data.count || names.length} players`;
      setTimeout(() => statusEl.textContent = '', 3000);
    } catch (e) {
      statusEl.textContent = 'Sync failed';
      setTimeout(() => statusEl.textContent = '', 3000);
    }
  }

  async function fetchRecommendations() {
    if (!config.draftId) {
      panel.querySelector('#bbm-recs').innerHTML = '<div class="bbm-empty">Set draft ID in popup</div>';
      return;
    }

    try {
      const res = await fetch(`${config.apiBase}/api/recommendations?draft_id=${encodeURIComponent(config.draftId)}`);
      const data = await res.json();
      renderRecommendations(data.recommendations || []);
    } catch (e) {
      panel.querySelector('#bbm-recs').innerHTML = '<div class="bbm-error">API unreachable</div>';
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
          <div class="bbm-meta">${escapeHtml(r.position || '')} ${escapeHtml(r.team || '')}</div>
        </div>
        <div class="bbm-score">${r.value || r.score || '-'}</div>
      </div>
    `).join('');
  }

  function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
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

  function init() {
    loadConfig().then(() => {
      createPanel();
      const hint = panel.querySelector('#bbm-hint');
      hint.textContent = config.draftId ? `Draft: ${config.draftId}` : 'Draft ID not set';
      fetchRecommendations();
      startPolling();
    });

    chrome.storage.onChanged.addListener((changes) => {
      if (changes.apiBase) config.apiBase = changes.apiBase.newValue;
      if (changes.draftId) {
        config.draftId = changes.draftId.newValue;
        panel.querySelector('#bbm-hint').textContent = config.draftId ? `Draft: ${config.draftId}` : 'Draft ID not set';
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
