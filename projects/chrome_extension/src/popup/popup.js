import { messageForError } from '../core/messages.js';
import { sendToTab } from '../core/messaging.js';
import { getModulesForUrl } from '../core/registry.js';

const contextEl = document.getElementById('context');
const modulesEl = document.getElementById('modules');
const statusEl = document.getElementById('status');

function setStatus(text, kind = '') {
  statusEl.textContent = text;
  statusEl.className = kind ? `status ${kind}` : 'status';
}

async function runModule(tab, entry, button) {
  button.disabled = true;
  setStatus('Exporting…');

  const response = await sendToTab(tab.id, { module: entry.module.id, action: 'export' });
  if (!response.ok) {
    setStatus(messageForError(response.error), 'error');
    button.disabled = false;
    return;
  }

  const { filename, dataUrl } = response.data;
  try {
    await chrome.downloads.download({ url: dataUrl, filename, saveAs: true });
    setStatus(`Saved ${filename}`, 'success');
  } catch (error) {
    // Cancelling the save dialog also lands here, which is why the copy is neutral.
    setStatus(`Download did not complete (${error?.message ?? 'unknown error'}).`, 'error');
  }
  button.disabled = false;
}

async function render() {
  const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
  const entries = getModulesForUrl(tab?.url ?? '');

  if (entries.length === 0) {
    setStatus(messageForError({ code: 'NOT_A_CHARACTER_PAGE' }));
    return;
  }

  contextEl.textContent = `Character ${entries[0].context.characterId}`;
  for (const entry of entries) {
    const button = document.createElement('button');
    button.textContent = entry.module.actionLabel;
    button.addEventListener('click', () => {
      runModule(tab, entry, button).catch((error) => {
        console.error('[dnd-toolkit] Export failed unexpectedly', error);
        setStatus('Unexpected error during export.', 'error');
        button.disabled = false;
      });
    });
    modulesEl.append(button);
  }
}

// A rejection here leaves the popup blank with no explanation, so it needs an
// answer of its own rather than an unhandled rejection in the popup console.
render().catch((error) => {
  console.error('[dnd-toolkit] Popup failed to render', error);
  setStatus('Could not read the active tab.', 'error');
});
