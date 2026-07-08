function setStatus(message, isError) {
  const status = document.getElementById('status');
  status.textContent = message;
  status.className = 'status ' + (isError ? 'error' : 'success');
  status.style.display = 'block';
}

document.getElementById('save').addEventListener('click', () => {
  const apiBase = document.getElementById('apiBase').value.trim().replace(/\/$/, '') || 'http://127.0.0.1:8765';
  const draftId = document.getElementById('draftId').value.trim();
  const token = document.getElementById('token').value.trim();

  chrome.storage.local.set({ apiBase, draftId, token }, () => {
    setStatus('Saved!', false);
    setTimeout(() => { document.getElementById('status').style.display = 'none'; }, 2000);
  });
});

document.getElementById('test').addEventListener('click', async () => {
  const apiBase = document.getElementById('apiBase').value.trim().replace(/\/$/, '') || 'http://127.0.0.1:8765';
  const token = document.getElementById('token').value.trim();
  const headers = { 'Content-Type': 'application/json' };
  if (token) headers['X-BBM-Token'] = token;
  try {
    const res = await fetch(`${apiBase}/api/status`, { headers });
    const data = await res.json();
    if (!res.ok || data.error) {
      setStatus(data.error || `Failed (${res.status})`, true);
      return;
    }
    if (data.draft_id) {
      document.getElementById('draftId').value = data.draft_id;
      chrome.storage.local.set({ apiBase, draftId: data.draft_id, token });
    }
    const mode = data.single_entry ? ' · single-entry' : '';
    setStatus(`Connected — round ${data.current_round || '?'}, pick ${data.pick_num || '?'}${mode}`, false);
  } catch (_e) {
    setStatus('Cannot reach API — run: ceminidfs bbm serve --slot 4', true);
  }
});

document.addEventListener('DOMContentLoaded', () => {
  chrome.storage.local.get(['apiBase', 'draftId', 'token'], (result) => {
    if (result.apiBase) document.getElementById('apiBase').value = result.apiBase;
    if (result.draftId) document.getElementById('draftId').value = result.draftId;
    if (result.token) document.getElementById('token').value = result.token;
  });
});
