export function ok(data) {
  return { ok: true, data };
}

export function fail(error) {
  return {
    ok: false,
    error: {
      code: error?.code ?? 'UNKNOWN',
      message: error?.message ?? String(error),
      status: error?.status ?? null,
    },
  };
}

// A missing or throwing content script means the page was loaded before the
// extension was installed or reloaded.
export async function sendToTab(tabId, message, chromeApi = chrome) {
  const missing = { code: 'NO_CONTENT_SCRIPT', message: 'The content script is not loaded' };
  try {
    const response = await chromeApi.tabs.sendMessage(tabId, message);
    return response ?? fail(missing);
  } catch {
    return fail(missing);
  }
}
