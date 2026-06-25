document.getElementById('save').addEventListener('click', () => {
  const apiBase = document.getElementById('apiBase').value.trim() || 'http://127.0.0.1:8765';
  const draftId = document.getElementById('draftId').value.trim();

  chrome.storage.local.set({ apiBase, draftId }, () => {
    const status = document.getElementById('status');
    status.classList.add('success');
    setTimeout(() => status.classList.remove('success'), 2000);
  });
});

document.addEventListener('DOMContentLoaded', () => {
  chrome.storage.local.get(['apiBase', 'draftId'], (result) => {
    if (result.apiBase) document.getElementById('apiBase').value = result.apiBase;
    if (result.draftId) document.getElementById('draftId').value = result.draftId;
  });
});
