# D&D Toolkit (Chrome extension)

Chrome extension hosting D&D Beyond tools. First module: **character export** —
downloads the complete JSON for the character sheet in the active tab.

## Install (unpacked)

1. Open `chrome://extensions`.
2. Turn on **Developer mode**.
3. Click **Load unpacked** and select this folder.

There is no build step. Chrome loads `src/` directly. After editing any file, hit
**Reload** on the extension card, then reload the D&D Beyond tab.

## Use

1. Sign in to D&D Beyond and open a character sheet.
2. Click the toolbar icon.
3. Click **Export character JSON** and choose where to save.

The file looks like:

```json
{
  "exportedAt": "2026-07-25T14:02:11.482Z",
  "source": "dndbeyond-character-v5",
  "characterId": "168889417",
  "character": { "...": "the raw API payload, verbatim" }
}
```

## Tests

```bash
npm install
npm test
```

Unit tests cover the API client, registry, envelope, encoder, messaging, and the
content-script listener. The popup → content script → downloads wiring is verified
by hand using the checklist below.

## Manual verification checklist

Run after any change to the manifest, the content script bootstrap, or the popup.

- [ ] Load unpacked; the extension card shows no errors.
- [ ] Open `https://www.dndbeyond.com/characters/168889417` while signed in.
- [ ] Click the toolbar icon; the popup names the character id and offers the export.
- [ ] Click **Export character JSON**; the save dialog appears.
- [ ] Save; the popup shows `Saved dndbeyond-<name>-<id>-<date>.json`.
- [ ] The file parses as JSON and `character` has 71 top-level keys:
      `node -e "const f=require('./<file>.json');console.log(Object.keys(f.character).length)"`
- [ ] Open the D&D Beyond home page and click the icon: popup says
      "Open a D&D Beyond character sheet."
- [ ] Sign out of D&D Beyond, reload the sheet, export: popup says
      "Not signed in to D&D Beyond."
- [ ] Open the sheet, then reload the extension without reloading the tab, then export:
      popup says "Reload the character sheet, then try again."
- [ ] Check both consoles for a leaked JWT: right-click inside the popup and choose
      **Inspect** for the popup's own console, and use the page's DevTools console for
      the content script. No token-shaped value should appear in either.
      (There is no background service worker, so there is no third console.)

## Adding a module

1. Create `src/modules/<module-id>/` with a `module.js` exporting a descriptor
   (`id`, `title`, `actionLabel`, `urlPattern`, `resolveContext`).
2. Import it in `src/core/registry.js` and add it to `MODULES`.
3. Add a `content_scripts` entry in `manifest.json` for the URLs it needs, plus a
   `web_accessible_resources` entry if it dynamic-imports module files.

The popup picks it up with no changes.

## Security notes

- The cobalt JWT is fetched fresh for every export and never cached, stored, or logged.
- `src/core/logger.js` redacts token-shaped values and sensitive keys before output.
- The token is sent only to `character-service.dndbeyond.com`.
- Host permissions are limited to three D&D Beyond hosts. No other origin is contacted.
- Access is enforced server-side: you can only export characters your account can view.
