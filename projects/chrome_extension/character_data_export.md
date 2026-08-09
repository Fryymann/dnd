Step 1 — Get an auth token from the cookie session
The main site login sets a CobaltSession cookie. To call the character API you first exchange that cookie for a short-lived JWT:
POST https://auth-service.dndbeyond.com/v1/cobalt-token
credentials: include   (sends the CobaltSession cookie automatically)
Response: {"token": "<JWT>"}. I tested this on your session and it returned 200 with a valid token.
Step 2 — Call the character API with that token
GET https://character-service.dndbeyond.com/character/v5/character/{characterId}
Authorization: Bearer <JWT from step 1>
I tested this against your open character (168889417) and it returned a 200 with a ~479KB JSON payload containing the full character object (top-level fields like id, userId, username, name, decorations, plus presumably stats, inventory, spells, etc. nested inside — 71 top-level keys total). Note the response is wrapped like {"success":true,"message":null,"data":{ ...character fields... }}, so your extension should pull .data out of the response.
Calling the character endpoint with only the cookie (no bearer token) returns a 403 "Unauthorized Access Attempt" — the bearer token is required.
Step 3 — Get the character ID
On a character sheet page the URL is https://www.dndbeyond.com/characters/{characterId}, so a content script can grab it with a regex like /\/characters\/(\d+)/.exec(location.pathname).
Putting it into an extension
manifest.json (Manifest V3):
```
json{
  "manifest_version": 3,
  "name": "DnDBeyond Character JSON Exporter",
  "version": "1.0",
  "permissions": ["activeTab", "downloads"],
  "host_permissions": [
    "https://www.dndbeyond.com/*",
    "https://auth-service.dndbeyond.com/*",
    "https://character-service.dndbeyond.com/*"
  ],
  "action": { "default_title": "Download Character JSON" },
  "background": { "service_worker": "background.js" },
  "content_scripts": [{
    "matches": ["https://www.dndbeyond.com/characters/*"],
    "js": ["content.js"]
  }]
}
```
content.js (runs on the character page, has access to the CobaltSession cookie via credentials:'include'):
```
jsasync function getCharacterJson() {
  const match = /\/characters\/(\d+)/.exec(location.pathname);
  if (!match) throw new Error("Not a character sheet page");
  const characterId = match[1];

  const tokenRes = await fetch('https://auth-service.dndbeyond.com/v1/cobalt-token', {
    method: 'POST', credentials: 'include'
  });
  const { token } = await tokenRes.json();

  const charRes = await fetch(`https://character-service.dndbeyond.com/character/v5/character/${characterId}`, {
    headers: { Authorization: `Bearer ${token}` }
  });
  const { data } = await charRes.json();
  return { characterId, data };
}

chrome.runtime.onMessage.addListener((msg, sender, sendResponse) => {
  if (msg.action === 'downloadCharacter') {
    getCharacterJson().then(sendResponse).catch(e => sendResponse({ error: e.message }));
    return true; // keep channel open for async response
  }
});
```
background.js / popup, to trigger the actual file download when the user clicks your extension's button (using chrome.downloads.download, which requires the downloads permission and a user-initiated click — this fits Manifest V3 service-worker restrictions since Blob/URL.createObjectURL aren't available there, so you'd typically build the blob URL in a popup or content script context instead and pass a data URL to chrome.downloads.download):
```
jschrome.action.onClicked.addListener(async (tab) => {
  const result = await chrome.tabs.sendMessage(tab.id, { action: 'downloadCharacter' });
  if (result.error) { console.error(result.error); return; }
  const json = JSON.stringify(result.data, null, 2);
  const dataUrl = 'data:application/json;base64,' + btoa(unescape(encodeURIComponent(json)));
  chrome.downloads.download({
    url: dataUrl,
    filename: `dndbeyond-character-${result.characterId}.json`,
    saveAs: true
  });
});
```
A few practical notes: the JWT from step 1 is short-lived, so fetch it fresh each time rather than caching it; treat it as sensitive since it grants API access to the account, so don't log it or send it anywhere outside D&D Beyond's own domains; and this only works for characters the logged-in user has permission to view (their own characters or ones shared with them), since the API enforces that server-side regardless of what the extension does.