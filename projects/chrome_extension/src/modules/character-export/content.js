// Classic content script. Content scripts cannot use static imports, so the real
// module graph is loaded dynamically from an extension URL. Every file it pulls
// in must appear in web_accessible_resources in manifest.json.
(async () => {
  const url = chrome.runtime.getURL('src/modules/character-export/content-main.js');
  const { registerCharacterExportListener } = await import(url);
  registerCharacterExportListener();
})().catch((error) => {
  // Without this the listener is never registered and the popup reports a
  // generic "reload the sheet" instead of the real bootstrap failure. Uses
  // console directly because the logger is part of the graph that just failed.
  console.error('[dnd-toolkit] Content script bootstrap failed', error);
});
