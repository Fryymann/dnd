# D&D Toolkit Chrome Extension — Foundation + Character Export

Date: 2026-07-25
Status: Approved for implementation

## Purpose

A Manifest V3 Chrome extension that hosts a growing set of D&D-related tools. This
spec covers two things at once: the shared foundation every future module sits on,
and the first module, `character-export`.

`character-export` lets a user viewing their own D&D Beyond character sheet download
that character's complete data as a JSON file.

## Background: the D&D Beyond API path

Verified live against character 168889417 before this spec was written.

1. Site login sets a `CobaltSession` cookie on `dndbeyond.com`.
2. `POST https://auth-service.dndbeyond.com/v1/cobalt-token` with
   `credentials: 'include'` exchanges that cookie for a short-lived JWT.
   Response: `{"token": "<JWT>"}`.
3. `GET https://character-service.dndbeyond.com/character/v5/character/{characterId}`
   with `Authorization: Bearer <JWT>` returns the full character.
   Response is wrapped: `{"success":true,"message":null,"data":{...}}` — the character
   is `.data`, 71 top-level keys, roughly 479KB.
4. Calling the character endpoint with only the cookie returns 403
   "Unauthorized Access Attempt". The bearer token is mandatory.
5. Character id comes from the page URL: `https://www.dndbeyond.com/characters/{id}`.

Access control is enforced server-side. The extension can only export characters the
signed-in user is already allowed to view.

## Scope

In scope:

- Extension skeleton: manifest, popup shell, module registry, shared API client,
  shared logging and download helpers.
- The `character-export` module end to end.
- Unit tests over the logic that can silently rot.

Out of scope (explicitly deferred until a second module needs it):

- Background service worker.
- Per-module permissions, settings UI, or lifecycle hooks.
- Dynamic content-script registration.
- Any derived or normalized view of character data.
- Publishing to the Chrome Web Store.

## Repository placement

The extension stays at `projects/chrome_extension/` as an ordinary folder, per
`projects/README.md` — promote to a submodule only when it needs its own history or
release cycle. Everything it owns lives under that folder so the promotion is clean.

Specs live at `projects/chrome_extension/docs/specs/`. They deliberately do not go in
the repository-root `docs/`, which holds published site output.

```
projects/chrome_extension/
  manifest.json
  package.json                        # vitest devDependency only; no build step
  README.md                           # install + manual verification checklist
  icons/                              # 16, 48, 128
  src/
    core/
      registry.js                     # module descriptors, getModulesForUrl(url)
      messaging.js                    # tab messaging + uniform {ok,data,error} envelope
      logger.js                       # namespaced logging, redacts token-shaped values
      download.js                     # buildDataUrl(json), filename sanitizing
    api/
      dndbeyond.js                    # getCobaltToken(), fetchCharacter(id), DndBeyondError
    modules/
      character-export/
        module.js                     # registry descriptor
        content.js                    # classic content-script bootstrap
        export.js                     # orchestration
        envelope.js                   # buildEnvelope(), buildFilename()
    popup/
      popup.html  popup.js  popup.css
  tests/
```

## Architecture

### No background service worker

Popup pages have full `chrome.*` API access, including `chrome.downloads`, so v1 needs
no service worker. Adding one later is a single manifest key.

### Two runtime contexts

**Content script** — matches `https://www.dndbeyond.com/characters/*`, runs in the page
origin, and owns every network call. It must be here: `credentials: 'include'` only
picks up the `CobaltSession` cookie from the page's own origin.

Content scripts cannot use static `import`. To get real ES modules without a bundler,
`content.js` is a thin classic script that dynamic-imports the module entry point via
`chrome.runtime.getURL()`. The imported files are declared in
`web_accessible_resources`, scoped to `dndbeyond.com`.

**Popup** — extension origin. Owns the UI, the module list, and the
`chrome.downloads.download` call. `popup.html` uses `<script type="module">`, which
works natively.

### Export flow

1. User clicks the toolbar icon; the popup opens.
2. Popup reads the active tab's URL and calls `registry.getModulesForUrl(url)`.
3. Popup renders each matching module as a labeled button, plus context (character id).
4. Click sends `{module: 'character-export', action: 'export'}` to the tab.
5. Content script parses the id, requests a fresh cobalt token, fetches the character,
   builds the envelope, and returns `{filename, dataUrl}`.
6. Popup calls `chrome.downloads.download({url: dataUrl, filename, saveAs: true})` and
   reports the result in the popup body.

### Why a data URL rather than a blob URL

MV3 removes `URL.createObjectURL` from service workers, and a blob URL created in the
popup is revoked when the popup closes — which can happen mid-download. A data URL is
self-contained and survives popup teardown.

A 479KB payload base64-encodes to roughly 640KB, comfortably under Chrome's data-URL
download ceiling. If an unusually large character ever exceeds it, the fallback is an
`<a download>` click inside the content script. That fallback is not built until a real
failure justifies it.

## The module registry

`core/registry.js` exports an array of descriptors:

```js
{
  id,             // 'character-export'
  title,          // 'Character export'
  actionLabel,    // 'Export character JSON'
  urlPattern,     // RegExp tested against the tab URL
  resolveContext, // (url) => ({ characterId }) | null
}
```

`getModulesForUrl(url)` returns the descriptors whose `urlPattern` matches and whose
`resolveContext` returns non-null. The popup renders that list and nothing else.

Adding module #2 means: a new folder under `src/modules/`, one entry in the registry
array, and one `content_scripts` match in the manifest. That is the entire
extensibility contract. No hooks, no per-module settings, until something concrete
requires them.

## Data format

The downloaded file wraps the untouched payload in a small provenance envelope:

```json
{
  "exportedAt": "2026-07-25T14:02:11.482Z",
  "source": "dndbeyond-character-v5",
  "characterId": "168889417",
  "character": { "...": "the raw .data object, verbatim, all 71 top-level keys" }
}
```

`character` is the API's `.data` with nothing added, removed, or reordered. The envelope
exists so later tooling can tell which endpoint and version produced a file.

Filename: `dndbeyond-<name-slug>-<characterId>-<YYYYMMDD>.json`, for example
`dndbeyond-tythus-168889417-20260725.json`. The slug lowercases the character name,
replaces any run of non-alphanumeric characters with a single hyphen, trims leading and
trailing hyphens, and truncates to 40 characters. If the name slugs to an empty string,
the name segment is omitted entirely. `saveAs: true`, so the user picks the location.

## Error handling

Every failure produces a human-readable sentence in the popup. Nothing is console-only.

| Cause | Popup message |
|---|---|
| Active tab is not a character URL | "Open a D&D Beyond character sheet." |
| Content script not present (extension installed after page load) | "Reload the character sheet, then try again." |
| Token request returns 401 or 403 | "Not signed in to D&D Beyond." |
| Character request returns 403 | "You don't have access to that character." |
| Character request returns 404 | "Character not found." |
| Response `success` is false | The API's `message` field, or a generic fallback |
| Network failure or any other status | "Export failed (<status or reason>)." |

`api/dndbeyond.js` throws a `DndBeyondError` carrying a stable `code` plus the HTTP
status. The popup maps `code` to copy; the mapping table is the single source of
message text.

## Security

- The JWT is short-lived. Fetch it fresh on every export; never cache or persist it.
- Never log the token. `core/logger.js` redacts token-shaped values before output.
- The token is sent only to `character-service.dndbeyond.com`, and nowhere else, ever.
- `host_permissions` is limited to exactly three hosts: `www.dndbeyond.com`,
  `auth-service.dndbeyond.com`, `character-service.dndbeyond.com`.
- Permissions requested: `activeTab`, `downloads`. Nothing broader.
- The extension makes no request to any non-D&D-Beyond origin.

## Testing

Vitest with mocked `fetch` and a mocked `chrome` global. One devDependency, no build
step for the extension itself.

Unit tests:

- `dndbeyond.test.js` — token exchange success; bearer header present on the character
  request; `.data` unwrapping; each status mapped to the right `DndBeyondError` code;
  `success: false` handled.
- `registry.test.js` — URL matching and id extraction across `/characters/168889417`,
  `/characters/168889417/builder`, a trailing slash, and a query string; non-character
  D&D Beyond URLs and unrelated origins return no modules.
- `envelope.test.js` — envelope shape and key order; filename slug over unicode names,
  punctuation, spaces, over-length names, and a name that slugs to empty; date format.
- `download.test.js` — base64 round-trip, including non-ASCII character names.

Manual verification, run once and recorded as a checklist in the extension README:

1. Load unpacked from `projects/chrome_extension/`.
2. Open `https://www.dndbeyond.com/characters/168889417` while signed in.
3. Click the toolbar icon; confirm the popup names the character and offers the export.
4. Export; confirm the save dialog appears and the file downloads.
5. Confirm the file parses as JSON and `character` has 71 top-level keys.
6. Sign out, retry, and confirm the popup shows "Not signed in to D&D Beyond."

## Success criteria

- A signed-in user on their own character sheet gets a complete, valid JSON file in two
  clicks.
- Every failure path named above produces its intended popup message rather than a
  silent failure or a raw stack trace.
- The token never appears in logs, storage, or any request outside D&D Beyond.
- Unit tests pass.
- A second module can be added by creating one folder and touching two shared files.
