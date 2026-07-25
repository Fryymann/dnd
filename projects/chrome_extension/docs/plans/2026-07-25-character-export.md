# D&D Toolkit Extension — Foundation + Character Export Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a Manifest V3 Chrome extension whose popup exports the complete JSON of the D&D Beyond character sheet in the active tab.

**Architecture:** A content script on `dndbeyond.com/characters/*` owns all network calls (it is the only context where the `CobaltSession` cookie is sent). The popup owns the UI and the download. A small module registry decides which module buttons the popup shows for the current URL, so a second module is a folder plus two edited lines. No background service worker, no bundler.

**Tech Stack:** Plain ES modules, Chrome Manifest V3, Vitest for unit tests. No build step — Chrome loads `src/` directly via "Load unpacked".

**Spec:** `projects/chrome_extension/docs/specs/2026-07-25-character-export-design.md`

---

## Working directory

Every path in this plan is relative to `projects/chrome_extension/` inside the `dnd` repository. All commands are run from that directory:

```bash
cd /home/ideans/data/projects/dnd/projects/chrome_extension
```

## File structure

| File | Responsibility |
|---|---|
| `manifest.json` | MV3 declaration: permissions, popup, content script, web-accessible module files |
| `package.json` | Vitest devDependency and test scripts. No build. |
| `src/core/logger.js` | Namespaced console logging that redacts token-shaped values |
| `src/core/messaging.js` | `{ok,data}` / `{ok:false,error}` result envelope; tab-messaging wrapper |
| `src/core/messages.js` | Error-code → user-facing copy. Single source of message text. |
| `src/core/download.js` | JSON → base64 `data:` URL, chunked so 500KB payloads don't blow the stack |
| `src/core/registry.js` | Module list; `getModulesForUrl(url)` |
| `src/api/dndbeyond.js` | `getCobaltToken()`, `fetchCharacter()`, `DndBeyondError` |
| `src/modules/character-export/module.js` | Registry descriptor + character-id URL parsing |
| `src/modules/character-export/envelope.js` | `buildEnvelope()`, `buildFilename()`, name slugging |
| `src/modules/character-export/export.js` | Orchestration: id → token → character → `{filename, dataUrl}` |
| `src/modules/character-export/content-main.js` | The message listener (ES module) |
| `src/modules/character-export/content.js` | Classic content-script bootstrap that dynamic-imports the above |
| `src/popup/popup.html` `.css` `.js` | Popup shell, module list rendering, download call |
| `tests/*.test.js` | Vitest units |
| `README.md` | Install instructions and the manual verification checklist |

Two files were not named in the spec's file list and are added here:

- `src/core/messages.js` — the spec requires the error-copy mapping be a single source of truth; this is that file.
- `src/modules/character-export/content-main.js` — content scripts cannot use static `import`, so the listener lives in a real module and `content.js` is a two-line classic bootstrap.

---

### Task 1: Project scaffold

**Files:**
- Create: `package.json`
- Create: `.gitignore`

- [ ] **Step 1: Create `package.json`**

```json
{
  "name": "dnd-toolkit-extension",
  "version": "0.1.0",
  "private": true,
  "type": "module",
  "description": "Chrome extension with D&D Beyond tools. First module: character JSON export.",
  "scripts": {
    "test": "vitest run",
    "test:watch": "vitest"
  }
}
```

- [ ] **Step 2: Create `.gitignore`**

```
node_modules/
```

- [ ] **Step 3: Install Vitest**

Run: `npm install --save-dev vitest`

Expected: `node_modules/` appears, `package-lock.json` is created, and `package.json` gains a `devDependencies.vitest` entry. Do not pin a version by hand — use whatever npm resolves.

- [ ] **Step 4: Verify the test runner starts**

Run: `npx vitest run --passWithNoTests`

Expected: exits 0 with "No test files found, exiting with code 0".

- [ ] **Step 5: Commit**

```bash
git add package.json package-lock.json .gitignore
git commit -m "chore(extension): scaffold package and vitest"
```

---

### Task 2: Logger with token redaction

Nothing may ever log the JWT. `redact()` is the guard, and it is used by every logging call in the extension.

**Files:**
- Create: `src/core/logger.js`
- Test: `tests/logger.test.js`

- [ ] **Step 1: Write the failing test**

Create `tests/logger.test.js`:

```js
import { describe, expect, it, vi } from 'vitest';
import { createLogger, redact } from '../src/core/logger.js';

const FAKE_JWT = 'eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxNjg4ODk0MTcifQ.c2lnbmF0dXJlLWhlcmU';

describe('redact', () => {
  it('replaces a JWT embedded in a string', () => {
    expect(redact(`Bearer ${FAKE_JWT} sent`)).toBe('Bearer [REDACTED] sent');
  });

  it('replaces values of sensitive keys regardless of shape', () => {
    expect(redact({ token: 'abc', Authorization: 'Bearer abc', name: 'Tythus' })).toEqual({
      token: '[REDACTED]',
      Authorization: '[REDACTED]',
      name: 'Tythus',
    });
  });

  it('walks nested objects and arrays', () => {
    expect(redact({ list: [{ token: 'abc' }, 'plain'] })).toEqual({
      list: [{ token: '[REDACTED]' }, 'plain'],
    });
  });

  it('leaves non-sensitive primitives alone', () => {
    expect(redact(42)).toBe(42);
    expect(redact(null)).toBe(null);
    expect(redact('Tythus the Bold')).toBe('Tythus the Bold');
  });

  it('renders Errors as text instead of losing the message', () => {
    expect(redact(new Error('boom'))).toBe('Error: boom');
  });

  it('survives circular references', () => {
    const node = { name: 'a' };
    node.self = node;
    expect(redact(node)).toEqual({ name: 'a', self: '[Circular]' });
  });
});

describe('createLogger', () => {
  it('prefixes the namespace and redacts every argument', () => {
    const spy = vi.spyOn(console, 'error').mockImplementation(() => {});
    createLogger('api').error('failed', { token: 'abc' });
    expect(spy).toHaveBeenCalledWith('[dnd-toolkit:api]', 'failed', { token: '[REDACTED]' });
    spy.mockRestore();
  });
});
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `npx vitest run tests/logger.test.js`

Expected: FAIL — cannot resolve `../src/core/logger.js`.

- [ ] **Step 3: Write the implementation**

Create `src/core/logger.js`:

```js
const JWT_PATTERN = /\bey[A-Za-z0-9_-]{6,}\.[A-Za-z0-9_-]{6,}\.[A-Za-z0-9_-]{6,}\b/g;
const SENSITIVE_KEY = /token|authorization|cobaltsession/i;
const REDACTED = '[REDACTED]';

export function redact(value, seen = new WeakSet()) {
  if (typeof value === 'string') return value.replace(JWT_PATTERN, REDACTED);
  if (value === null || typeof value !== 'object') return value;
  if (value instanceof Error) return `${value.name}: ${redact(value.message)}`;
  if (seen.has(value)) return '[Circular]';
  seen.add(value);
  if (Array.isArray(value)) return value.map((item) => redact(item, seen));

  const out = {};
  for (const [key, item] of Object.entries(value)) {
    out[key] = SENSITIVE_KEY.test(key) ? REDACTED : redact(item, seen);
  }
  return out;
}

export function createLogger(namespace) {
  const prefix = `[dnd-toolkit:${namespace}]`;
  const emit = (level) => (...args) => console[level](prefix, ...args.map((arg) => redact(arg)));
  return { info: emit('log'), warn: emit('warn'), error: emit('error') };
}
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `npx vitest run tests/logger.test.js`

Expected: PASS, 7 tests.

- [ ] **Step 5: Commit**

```bash
git add src/core/logger.js tests/logger.test.js
git commit -m "feat(extension): add logger with token redaction"
```

---

### Task 3: D&D Beyond API client

The two network calls plus the status → error-code mapping. `fetch` is injected as a parameter so tests never touch globals.

**Files:**
- Create: `src/api/dndbeyond.js`
- Test: `tests/dndbeyond.test.js`

- [ ] **Step 1: Write the failing test**

Create `tests/dndbeyond.test.js`:

```js
import { describe, expect, it, vi } from 'vitest';
import {
  CHARACTER_URL,
  DndBeyondError,
  TOKEN_URL,
  fetchCharacter,
  getCobaltToken,
} from '../src/api/dndbeyond.js';

const response = (status, body) => ({
  ok: status >= 200 && status < 300,
  status,
  json: async () => body,
});

describe('getCobaltToken', () => {
  it('posts to the auth service with cookies and returns the token', async () => {
    const fetchImpl = vi.fn().mockResolvedValue(response(200, { token: 'jwt-value' }));
    await expect(getCobaltToken(fetchImpl)).resolves.toBe('jwt-value');
    expect(fetchImpl).toHaveBeenCalledWith(TOKEN_URL, {
      method: 'POST',
      credentials: 'include',
    });
  });

  it('maps 401 and 403 to NOT_SIGNED_IN', async () => {
    for (const status of [401, 403]) {
      const fetchImpl = vi.fn().mockResolvedValue(response(status, {}));
      await expect(getCobaltToken(fetchImpl)).rejects.toMatchObject({
        code: 'NOT_SIGNED_IN',
        status,
      });
    }
  });

  it('maps other failure statuses to TOKEN_FAILED', async () => {
    const fetchImpl = vi.fn().mockResolvedValue(response(500, {}));
    await expect(getCobaltToken(fetchImpl)).rejects.toMatchObject({
      code: 'TOKEN_FAILED',
      status: 500,
    });
  });

  it('rejects a 200 response with no usable token', async () => {
    const fetchImpl = vi.fn().mockResolvedValue(response(200, { token: '' }));
    await expect(getCobaltToken(fetchImpl)).rejects.toMatchObject({ code: 'TOKEN_FAILED' });
  });

  it('maps a thrown fetch to NETWORK', async () => {
    const fetchImpl = vi.fn().mockRejectedValue(new TypeError('Failed to fetch'));
    await expect(getCobaltToken(fetchImpl)).rejects.toMatchObject({
      code: 'NETWORK',
      status: null,
    });
  });
});

describe('fetchCharacter', () => {
  it('sends the bearer token and unwraps .data', async () => {
    const character = { id: 168889417, name: 'Tythus' };
    const fetchImpl = vi
      .fn()
      .mockResolvedValue(response(200, { success: true, message: null, data: character }));

    await expect(fetchCharacter('168889417', 'jwt-value', fetchImpl)).resolves.toEqual(character);
    expect(fetchImpl).toHaveBeenCalledWith(`${CHARACTER_URL}/168889417`, {
      headers: { Authorization: 'Bearer jwt-value' },
    });
  });

  it('maps 403 to NO_ACCESS, 404 to NOT_FOUND, 401 to NOT_SIGNED_IN', async () => {
    const cases = [
      [403, 'NO_ACCESS'],
      [404, 'NOT_FOUND'],
      [401, 'NOT_SIGNED_IN'],
    ];
    for (const [status, code] of cases) {
      const fetchImpl = vi.fn().mockResolvedValue(response(status, {}));
      await expect(fetchCharacter('1', 'jwt', fetchImpl)).rejects.toMatchObject({ code, status });
    }
  });

  it('maps any other failure status to CHARACTER_FAILED', async () => {
    const fetchImpl = vi.fn().mockResolvedValue(response(503, {}));
    await expect(fetchCharacter('1', 'jwt', fetchImpl)).rejects.toMatchObject({
      code: 'CHARACTER_FAILED',
      status: 503,
    });
  });

  it('treats success:false as API_REJECTED and keeps the API message', async () => {
    const fetchImpl = vi
      .fn()
      .mockResolvedValue(response(200, { success: false, message: 'Character is private', data: null }));
    await expect(fetchCharacter('1', 'jwt', fetchImpl)).rejects.toMatchObject({
      code: 'API_REJECTED',
      message: 'Character is private',
    });
  });

  it('maps a thrown fetch to NETWORK', async () => {
    const fetchImpl = vi.fn().mockRejectedValue(new TypeError('Failed to fetch'));
    await expect(fetchCharacter('1', 'jwt', fetchImpl)).rejects.toMatchObject({ code: 'NETWORK' });
  });
});

describe('DndBeyondError', () => {
  it('carries a code and a status', () => {
    const error = new DndBeyondError('NO_ACCESS', 'nope', 403);
    expect(error).toBeInstanceOf(Error);
    expect(error.name).toBe('DndBeyondError');
    expect(error.code).toBe('NO_ACCESS');
    expect(error.status).toBe(403);
  });
});
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `npx vitest run tests/dndbeyond.test.js`

Expected: FAIL — cannot resolve `../src/api/dndbeyond.js`.

- [ ] **Step 3: Write the implementation**

Create `src/api/dndbeyond.js`:

```js
export const TOKEN_URL = 'https://auth-service.dndbeyond.com/v1/cobalt-token';
export const CHARACTER_URL = 'https://character-service.dndbeyond.com/character/v5/character';

export class DndBeyondError extends Error {
  constructor(code, message, status = null) {
    super(message);
    this.name = 'DndBeyondError';
    this.code = code;
    this.status = status;
  }
}

// The JWT is short-lived. Fetch it fresh for every export; never cache or store it.
export async function getCobaltToken(fetchImpl = fetch) {
  let response;
  try {
    response = await fetchImpl(TOKEN_URL, { method: 'POST', credentials: 'include' });
  } catch {
    throw new DndBeyondError('NETWORK', 'Could not reach the D&D Beyond auth service');
  }

  if (response.status === 401 || response.status === 403) {
    throw new DndBeyondError('NOT_SIGNED_IN', 'Cobalt token request was rejected', response.status);
  }
  if (!response.ok) {
    throw new DndBeyondError('TOKEN_FAILED', 'Cobalt token request failed', response.status);
  }

  const body = await response.json();
  if (!body || typeof body.token !== 'string' || body.token.length === 0) {
    throw new DndBeyondError('TOKEN_FAILED', 'Cobalt token missing from response', response.status);
  }
  return body.token;
}

export async function fetchCharacter(characterId, token, fetchImpl = fetch) {
  let response;
  try {
    response = await fetchImpl(`${CHARACTER_URL}/${characterId}`, {
      headers: { Authorization: `Bearer ${token}` },
    });
  } catch {
    throw new DndBeyondError('NETWORK', 'Could not reach the D&D Beyond character service');
  }

  if (response.status === 401) {
    throw new DndBeyondError('NOT_SIGNED_IN', 'Character request was rejected', 401);
  }
  if (response.status === 403) {
    throw new DndBeyondError('NO_ACCESS', 'No access to this character', 403);
  }
  if (response.status === 404) {
    throw new DndBeyondError('NOT_FOUND', 'Character not found', 404);
  }
  if (!response.ok) {
    throw new DndBeyondError('CHARACTER_FAILED', 'Character request failed', response.status);
  }

  const body = await response.json();
  if (!body || body.success !== true || !body.data) {
    throw new DndBeyondError(
      'API_REJECTED',
      body?.message || 'The character API rejected the request',
      response.status,
    );
  }
  return body.data;
}
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `npx vitest run tests/dndbeyond.test.js`

Expected: PASS, 11 tests.

- [ ] **Step 5: Commit**

```bash
git add src/api/dndbeyond.js tests/dndbeyond.test.js
git commit -m "feat(extension): add D&D Beyond token and character API client"
```

---

### Task 4: Export envelope and filename

**Files:**
- Create: `src/modules/character-export/envelope.js`
- Test: `tests/envelope.test.js`

- [ ] **Step 1: Write the failing test**

Create `tests/envelope.test.js`:

```js
import { describe, expect, it } from 'vitest';
import {
  buildEnvelope,
  buildFilename,
  formatDateStamp,
  slugifyName,
} from '../src/modules/character-export/envelope.js';

// Constructed with local-time components on purpose: formatDateStamp uses local
// date parts, so a UTC-constructed date would make this test timezone-dependent.
const FIXED_DATE = new Date(2026, 6, 25, 14, 2, 11, 482);

describe('slugifyName', () => {
  it('lowercases and hyphenates', () => {
    expect(slugifyName('Tythus the Bold')).toBe('tythus-the-bold');
  });

  it('strips diacritics rather than dropping the letters', () => {
    expect(slugifyName('Tythûs Ürden')).toBe('tythus-urden');
  });

  it('collapses runs of punctuation into a single hyphen and trims the ends', () => {
    expect(slugifyName("  ...Sir Reginald, Esq.!  ")).toBe('sir-reginald-esq');
  });

  it('truncates to 40 characters without leaving a trailing hyphen', () => {
    // Slugs to 39 a's + '-b'; the 40-char cut lands on the hyphen, which is then stripped.
    const slug = slugifyName('a'.repeat(39) + ' b');
    expect(slug).toBe('a'.repeat(39));
    expect(slug.length).toBeLessThanOrEqual(40);
  });

  it('returns an empty string for names with nothing sluggable', () => {
    expect(slugifyName('！？')).toBe('');
    expect(slugifyName('')).toBe('');
    expect(slugifyName(undefined)).toBe('');
  });
});

describe('formatDateStamp', () => {
  it('formats as YYYYMMDD with zero padding', () => {
    expect(formatDateStamp(FIXED_DATE)).toBe('20260725');
    expect(formatDateStamp(new Date(2026, 0, 3))).toBe('20260103');
  });
});

describe('buildFilename', () => {
  it('joins prefix, slug, id and date', () => {
    expect(buildFilename({ name: 'Tythus' }, '168889417', FIXED_DATE)).toBe(
      'dndbeyond-tythus-168889417-20260725.json',
    );
  });

  it('omits the name segment entirely when the slug is empty', () => {
    expect(buildFilename({ name: '！？' }, '168889417', FIXED_DATE)).toBe(
      'dndbeyond-168889417-20260725.json',
    );
  });

  it('tolerates a character object with no name', () => {
    expect(buildFilename({}, '1', FIXED_DATE)).toBe('dndbeyond-1-20260725.json');
  });
});

describe('buildEnvelope', () => {
  it('wraps the raw character with provenance in a fixed key order', () => {
    const character = { id: 168889417, name: 'Tythus', spells: [] };
    const envelope = buildEnvelope('168889417', character, FIXED_DATE);

    expect(Object.keys(envelope)).toEqual(['exportedAt', 'source', 'characterId', 'character']);
    expect(envelope.exportedAt).toBe(FIXED_DATE.toISOString());
    expect(envelope.source).toBe('dndbeyond-character-v5');
    expect(envelope.characterId).toBe('168889417');
  });

  it('passes the character through by reference, unmodified', () => {
    const character = { id: 1, name: 'Tythus' };
    expect(buildEnvelope(1, character, FIXED_DATE).character).toBe(character);
  });

  it('stringifies a numeric character id', () => {
    expect(buildEnvelope(168889417, {}, FIXED_DATE).characterId).toBe('168889417');
  });
});
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `npx vitest run tests/envelope.test.js`

Expected: FAIL — cannot resolve `../src/modules/character-export/envelope.js`.

- [ ] **Step 3: Write the implementation**

Create `src/modules/character-export/envelope.js`:

```js
const MAX_SLUG_LENGTH = 40;

export function slugifyName(name) {
  if (typeof name !== 'string') return '';
  return name
    .normalize('NFD')
    .replace(/[\u0300-\u036f]/g, '') // drop combining marks so "Tythûs" keeps its letters
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, '-')
    .replace(/^-+|-+$/g, '')
    .slice(0, MAX_SLUG_LENGTH)
    .replace(/-+$/g, '');
}

export function formatDateStamp(date) {
  const pad = (value) => String(value).padStart(2, '0');
  return `${date.getFullYear()}${pad(date.getMonth() + 1)}${pad(date.getDate())}`;
}

export function buildFilename(character, characterId, date = new Date()) {
  const segments = ['dndbeyond', slugifyName(character?.name), String(characterId), formatDateStamp(date)];
  return `${segments.filter(Boolean).join('-')}.json`;
}

export function buildEnvelope(characterId, character, date = new Date()) {
  return {
    exportedAt: date.toISOString(),
    source: 'dndbeyond-character-v5',
    characterId: String(characterId),
    character,
  };
}
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `npx vitest run tests/envelope.test.js`

Expected: PASS, 12 tests.

- [ ] **Step 5: Commit**

```bash
git add src/modules/character-export/envelope.js tests/envelope.test.js
git commit -m "feat(extension): add export envelope and filename builder"
```

---

### Task 5: JSON → data URL

The payload is roughly 479KB. Spreading half a million bytes into `String.fromCharCode(...)` in one call overflows the argument stack, so encoding is chunked.

**Files:**
- Create: `src/core/download.js`
- Test: `tests/download.test.js`

- [ ] **Step 1: Write the failing test**

Create `tests/download.test.js`:

```js
import { describe, expect, it } from 'vitest';
import { toJsonDataUrl } from '../src/core/download.js';

const decode = (dataUrl) => {
  const base64 = dataUrl.replace('data:application/json;base64,', '');
  const binary = atob(base64);
  const bytes = Uint8Array.from(binary, (char) => char.charCodeAt(0));
  return new TextDecoder().decode(bytes);
};

describe('toJsonDataUrl', () => {
  it('produces a base64 JSON data URL', () => {
    expect(toJsonDataUrl({ a: 1 })).toMatch(/^data:application\/json;base64,/);
  });

  it('round-trips to pretty-printed JSON', () => {
    const value = { exportedAt: '2026-07-25T14:02:11.482Z', character: { id: 1 } };
    expect(JSON.parse(decode(toJsonDataUrl(value)))).toEqual(value);
    expect(decode(toJsonDataUrl(value))).toBe(JSON.stringify(value, null, 2));
  });

  it('round-trips non-ASCII characters', () => {
    const value = { name: 'Tythûs — 竜' };
    expect(JSON.parse(decode(toJsonDataUrl(value))).name).toBe('Tythûs — 竜');
  });

  it('handles a payload larger than one encoding chunk', () => {
    const value = { blob: 'x'.repeat(200000) };
    expect(JSON.parse(decode(toJsonDataUrl(value))).blob.length).toBe(200000);
  });
});
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `npx vitest run tests/download.test.js`

Expected: FAIL — cannot resolve `../src/core/download.js`.

- [ ] **Step 3: Write the implementation**

Create `src/core/download.js`:

```js
// Encoding is chunked because a ~500KB payload spread into one
// String.fromCharCode call overflows the argument stack.
const CHUNK_SIZE = 0x8000;

export function toJsonDataUrl(value) {
  const json = JSON.stringify(value, null, 2);
  const bytes = new TextEncoder().encode(json);

  let binary = '';
  for (let offset = 0; offset < bytes.length; offset += CHUNK_SIZE) {
    binary += String.fromCharCode(...bytes.subarray(offset, offset + CHUNK_SIZE));
  }
  return `data:application/json;base64,${btoa(binary)}`;
}
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `npx vitest run tests/download.test.js`

Expected: PASS, 4 tests. (`btoa`, `atob`, `TextEncoder` and `TextDecoder` are all globals in Node 18+, which is what Vitest runs on.)

- [ ] **Step 5: Commit**

```bash
git add src/core/download.js tests/download.test.js
git commit -m "feat(extension): add chunked JSON data-URL encoder"
```

---

### Task 6: Module descriptor and registry

This is the extensibility seam. A future module adds a descriptor file and one entry in `MODULES`.

**Files:**
- Create: `src/modules/character-export/module.js`
- Create: `src/core/registry.js`
- Test: `tests/registry.test.js`

- [ ] **Step 1: Write the failing test**

Create `tests/registry.test.js`:

```js
import { describe, expect, it } from 'vitest';
import { MODULES, getModulesForUrl } from '../src/core/registry.js';
import { characterExportModule } from '../src/modules/character-export/module.js';

describe('characterExportModule', () => {
  it('exposes the fields the popup renders', () => {
    expect(characterExportModule.id).toBe('character-export');
    expect(characterExportModule.title).toBe('Character export');
    expect(characterExportModule.actionLabel).toBe('Export character JSON');
  });

  it('extracts the character id from every sheet URL shape', () => {
    const urls = [
      'https://www.dndbeyond.com/characters/168889417',
      'https://www.dndbeyond.com/characters/168889417/',
      'https://www.dndbeyond.com/characters/168889417/builder',
      'https://www.dndbeyond.com/characters/168889417?tab=abilities',
      'https://www.dndbeyond.com/characters/168889417#inventory',
    ];
    for (const url of urls) {
      expect(characterExportModule.resolveContext(url)).toEqual({ characterId: '168889417' });
    }
  });

  it('returns null for non-character URLs', () => {
    const urls = [
      'https://www.dndbeyond.com/characters',
      'https://www.dndbeyond.com/characters/list',
      'https://www.dndbeyond.com/monsters/168889417',
      'https://evil.example.com/characters/168889417',
      'http://www.dndbeyond.com/characters/168889417',
    ];
    for (const url of urls) {
      expect(characterExportModule.resolveContext(url)).toBeNull();
    }
  });
});

describe('getModulesForUrl', () => {
  it('returns the module and its resolved context on a character sheet', () => {
    const entries = getModulesForUrl('https://www.dndbeyond.com/characters/168889417');
    expect(entries).toHaveLength(1);
    expect(entries[0].module).toBe(characterExportModule);
    expect(entries[0].context).toEqual({ characterId: '168889417' });
  });

  it('returns nothing for an unrelated page', () => {
    expect(getModulesForUrl('https://example.com/')).toEqual([]);
  });

  it('returns nothing for a missing or non-string url', () => {
    expect(getModulesForUrl(undefined)).toEqual([]);
    expect(getModulesForUrl(null)).toEqual([]);
  });

  it('registers character-export', () => {
    expect(MODULES).toContain(characterExportModule);
  });
});
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `npx vitest run tests/registry.test.js`

Expected: FAIL — cannot resolve `../src/core/registry.js`.

- [ ] **Step 3: Write the module descriptor**

Create `src/modules/character-export/module.js`:

```js
// Anchored to https + the exact host so a lookalike domain can never match.
// The id must be followed by a path, query, fragment, or end of string.
const CHARACTER_URL_PATTERN = /^https:\/\/www\.dndbeyond\.com\/characters\/(\d+)(?:[/?#]|$)/;

export const characterExportModule = {
  id: 'character-export',
  title: 'Character export',
  actionLabel: 'Export character JSON',
  urlPattern: CHARACTER_URL_PATTERN,
  resolveContext(url) {
    if (typeof url !== 'string') return null;
    const match = CHARACTER_URL_PATTERN.exec(url);
    return match ? { characterId: match[1] } : null;
  },
};
```

- [ ] **Step 4: Write the registry**

Create `src/core/registry.js`:

```js
import { characterExportModule } from '../modules/character-export/module.js';

// To add a module: import its descriptor and append it here, then add a
// matching entry to content_scripts in manifest.json.
export const MODULES = [characterExportModule];

export function getModulesForUrl(url) {
  if (typeof url !== 'string') return [];
  return MODULES
    .map((module) => ({ module, context: module.resolveContext(url) }))
    .filter((entry) => entry.context !== null);
}
```

- [ ] **Step 5: Run the test to verify it passes**

Run: `npx vitest run tests/registry.test.js`

Expected: PASS, 7 tests.

- [ ] **Step 6: Commit**

```bash
git add src/modules/character-export/module.js src/core/registry.js tests/registry.test.js
git commit -m "feat(extension): add module registry and character-export descriptor"
```

---

### Task 7: Result envelope and error copy

`messaging.js` gives every cross-context reply the same shape. `messages.js` is the only place user-facing error text exists.

**Files:**
- Create: `src/core/messaging.js`
- Create: `src/core/messages.js`
- Test: `tests/messaging.test.js`
- Test: `tests/messages.test.js`

- [ ] **Step 1: Write the failing tests**

Create `tests/messaging.test.js`:

```js
import { describe, expect, it, vi } from 'vitest';
import { fail, ok, sendToTab } from '../src/core/messaging.js';

describe('ok / fail', () => {
  it('wraps a success payload', () => {
    expect(ok({ filename: 'a.json' })).toEqual({ ok: true, data: { filename: 'a.json' } });
  });

  it('flattens an error into a serializable shape', () => {
    const error = Object.assign(new Error('nope'), { code: 'NO_ACCESS', status: 403 });
    expect(fail(error)).toEqual({
      ok: false,
      error: { code: 'NO_ACCESS', message: 'nope', status: 403 },
    });
  });

  it('defaults code and status for a plain error', () => {
    expect(fail(new Error('boom'))).toEqual({
      ok: false,
      error: { code: 'UNKNOWN', message: 'boom', status: null },
    });
  });
});

describe('sendToTab', () => {
  it('returns the content script response unchanged', async () => {
    const chromeApi = { tabs: { sendMessage: vi.fn().mockResolvedValue({ ok: true, data: 1 }) } };
    await expect(sendToTab(7, { action: 'export' }, chromeApi)).resolves.toEqual({ ok: true, data: 1 });
    expect(chromeApi.tabs.sendMessage).toHaveBeenCalledWith(7, { action: 'export' });
  });

  it('maps a thrown sendMessage to NO_CONTENT_SCRIPT', async () => {
    const chromeApi = {
      tabs: { sendMessage: vi.fn().mockRejectedValue(new Error('Receiving end does not exist')) },
    };
    const result = await sendToTab(7, {}, chromeApi);
    expect(result.ok).toBe(false);
    expect(result.error.code).toBe('NO_CONTENT_SCRIPT');
  });

  it('maps an undefined response to NO_CONTENT_SCRIPT', async () => {
    const chromeApi = { tabs: { sendMessage: vi.fn().mockResolvedValue(undefined) } };
    const result = await sendToTab(7, {}, chromeApi);
    expect(result.error.code).toBe('NO_CONTENT_SCRIPT');
  });
});
```

Create `tests/messages.test.js`:

```js
import { describe, expect, it } from 'vitest';
import { messageForError } from '../src/core/messages.js';

describe('messageForError', () => {
  it('maps each known code to its copy', () => {
    const cases = [
      ['NOT_A_CHARACTER_PAGE', 'Open a D&D Beyond character sheet.'],
      ['NO_CONTENT_SCRIPT', 'Reload the character sheet, then try again.'],
      ['NOT_SIGNED_IN', 'Not signed in to D&D Beyond.'],
      ['NO_ACCESS', "You don't have access to that character."],
      ['NOT_FOUND', 'Character not found.'],
      ['NETWORK', 'Export failed (network error).'],
    ];
    for (const [code, copy] of cases) {
      expect(messageForError({ code })).toBe(copy);
    }
  });

  it('passes the API message through for API_REJECTED', () => {
    expect(messageForError({ code: 'API_REJECTED', message: 'Character is private' })).toBe(
      'Character is private',
    );
  });

  it('falls back to the status for an unmapped code', () => {
    expect(messageForError({ code: 'CHARACTER_FAILED', status: 503 })).toBe('Export failed (status 503).');
  });

  it('falls back to the message when there is no status', () => {
    expect(messageForError({ code: 'WEIRD', message: 'something odd' })).toBe(
      'Export failed (something odd).',
    );
  });

  it('handles a missing error object', () => {
    expect(messageForError(undefined)).toBe('Export failed (unknown error).');
  });
});
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `npx vitest run tests/messaging.test.js tests/messages.test.js`

Expected: FAIL — neither module resolves.

- [ ] **Step 3: Write `src/core/messaging.js`**

```js
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
```

- [ ] **Step 4: Write `src/core/messages.js`**

```js
// The single source of user-facing error text. Nothing else composes copy.
const ERROR_MESSAGES = {
  NOT_A_CHARACTER_PAGE: 'Open a D&D Beyond character sheet.',
  NO_CONTENT_SCRIPT: 'Reload the character sheet, then try again.',
  NOT_SIGNED_IN: 'Not signed in to D&D Beyond.',
  NO_ACCESS: "You don't have access to that character.",
  NOT_FOUND: 'Character not found.',
  NETWORK: 'Export failed (network error).',
};

export function messageForError(error) {
  if (error?.code === 'API_REJECTED' && error.message) return error.message;

  const copy = ERROR_MESSAGES[error?.code];
  if (copy) return copy;

  const detail = error?.status ? `status ${error.status}` : error?.message || 'unknown error';
  return `Export failed (${detail}).`;
}
```

- [ ] **Step 5: Run the tests to verify they pass**

Run: `npx vitest run tests/messaging.test.js tests/messages.test.js`

Expected: PASS, 11 tests total.

- [ ] **Step 6: Commit**

```bash
git add src/core/messaging.js src/core/messages.js tests/messaging.test.js tests/messages.test.js
git commit -m "feat(extension): add result envelope and error copy mapping"
```

---

### Task 8: Export orchestration

**Files:**
- Create: `src/modules/character-export/export.js`
- Test: `tests/export.test.js`

- [ ] **Step 1: Write the failing test**

Create `tests/export.test.js`:

```js
import { describe, expect, it, vi } from 'vitest';
import { exportCharacter } from '../src/modules/character-export/export.js';

const FIXED_DATE = new Date(2026, 6, 25, 14, 2, 11, 482);

const deps = (overrides = {}) => ({
  getToken: vi.fn().mockResolvedValue('jwt-value'),
  getCharacter: vi.fn().mockResolvedValue({ id: 168889417, name: 'Tythus' }),
  now: () => FIXED_DATE,
  ...overrides,
});

const decode = (dataUrl) => {
  const binary = atob(dataUrl.replace('data:application/json;base64,', ''));
  const bytes = Uint8Array.from(binary, (char) => char.charCodeAt(0));
  return JSON.parse(new TextDecoder().decode(bytes));
};

describe('exportCharacter', () => {
  it('fetches a fresh token and passes it to the character request', async () => {
    const d = deps();
    await exportCharacter('168889417', d);
    expect(d.getToken).toHaveBeenCalledTimes(1);
    expect(d.getCharacter).toHaveBeenCalledWith('168889417', 'jwt-value');
  });

  it('returns the filename and a data URL holding the envelope', async () => {
    const result = await exportCharacter('168889417', deps());

    expect(result.filename).toBe('dndbeyond-tythus-168889417-20260725.json');
    expect(decode(result.dataUrl)).toEqual({
      exportedAt: FIXED_DATE.toISOString(),
      source: 'dndbeyond-character-v5',
      characterId: '168889417',
      character: { id: 168889417, name: 'Tythus' },
    });
  });

  it('propagates a token failure without calling the character API', async () => {
    const error = Object.assign(new Error('nope'), { code: 'NOT_SIGNED_IN' });
    const d = deps({ getToken: vi.fn().mockRejectedValue(error) });
    await expect(exportCharacter('1', d)).rejects.toMatchObject({ code: 'NOT_SIGNED_IN' });
    expect(d.getCharacter).not.toHaveBeenCalled();
  });

  it('propagates a character failure', async () => {
    const error = Object.assign(new Error('nope'), { code: 'NO_ACCESS' });
    await expect(
      exportCharacter('1', deps({ getCharacter: vi.fn().mockRejectedValue(error) })),
    ).rejects.toMatchObject({ code: 'NO_ACCESS' });
  });
});
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `npx vitest run tests/export.test.js`

Expected: FAIL — cannot resolve `../src/modules/character-export/export.js`.

- [ ] **Step 3: Write the implementation**

Create `src/modules/character-export/export.js`:

```js
import { fetchCharacter, getCobaltToken } from '../../api/dndbeyond.js';
import { toJsonDataUrl } from '../../core/download.js';
import { buildEnvelope, buildFilename } from './envelope.js';

// Dependencies are injected so the orchestration is testable without globals.
export async function exportCharacter(characterId, deps = {}) {
  const { getToken = getCobaltToken, getCharacter = fetchCharacter, now = () => new Date() } = deps;

  const date = now();
  const token = await getToken();
  const character = await getCharacter(characterId, token);

  return {
    filename: buildFilename(character, characterId, date),
    dataUrl: toJsonDataUrl(buildEnvelope(characterId, character, date)),
  };
}
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `npx vitest run tests/export.test.js`

Expected: PASS, 4 tests.

- [ ] **Step 5: Commit**

```bash
git add src/modules/character-export/export.js tests/export.test.js
git commit -m "feat(extension): add character export orchestration"
```

---

### Task 9: Content script listener

**Files:**
- Create: `src/modules/character-export/content-main.js`
- Test: `tests/content-main.test.js`

- [ ] **Step 1: Write the failing test**

Create `tests/content-main.test.js`:

```js
import { describe, expect, it, vi } from 'vitest';
import { registerCharacterExportListener } from '../src/modules/character-export/content-main.js';

const SHEET_URL = 'https://www.dndbeyond.com/characters/168889417';

const setup = (overrides = {}) => {
  const listeners = [];
  const chromeApi = { runtime: { onMessage: { addListener: (fn) => listeners.push(fn) } } };
  registerCharacterExportListener({
    chromeApi,
    getHref: () => SHEET_URL,
    runExport: vi.fn().mockResolvedValue({ filename: 'a.json', dataUrl: 'data:application/json;base64,e30=' }),
    ...overrides,
  });
  return { listener: listeners[0] };
};

const EXPORT_MESSAGE = { module: 'character-export', action: 'export' };

describe('registerCharacterExportListener', () => {
  it('registers exactly one listener', () => {
    const listeners = [];
    const chromeApi = { runtime: { onMessage: { addListener: (fn) => listeners.push(fn) } } };
    registerCharacterExportListener({ chromeApi, getHref: () => SHEET_URL });
    expect(listeners).toHaveLength(1);
  });

  it('keeps the message channel open and replies with the export result', async () => {
    const runExport = vi
      .fn()
      .mockResolvedValue({ filename: 'a.json', dataUrl: 'data:application/json;base64,e30=' });
    const { listener } = setup({ runExport });
    const sendResponse = vi.fn();

    expect(listener(EXPORT_MESSAGE, {}, sendResponse)).toBe(true);
    await vi.waitFor(() => expect(sendResponse).toHaveBeenCalled());

    expect(runExport).toHaveBeenCalledWith('168889417');
    expect(sendResponse).toHaveBeenCalledWith({
      ok: true,
      data: { filename: 'a.json', dataUrl: 'data:application/json;base64,e30=' },
    });
  });

  it('replies with a failure envelope when the export throws', async () => {
    const error = Object.assign(new Error('nope'), { code: 'NO_ACCESS', status: 403 });
    const { listener } = setup({ runExport: vi.fn().mockRejectedValue(error) });
    const sendResponse = vi.fn();

    listener(EXPORT_MESSAGE, {}, sendResponse);
    await vi.waitFor(() => expect(sendResponse).toHaveBeenCalled());

    expect(sendResponse).toHaveBeenCalledWith({
      ok: false,
      error: { code: 'NO_ACCESS', message: 'nope', status: 403 },
    });
  });

  it('replies NOT_A_CHARACTER_PAGE when the current URL has no character id', async () => {
    const runExport = vi.fn();
    const { listener } = setup({ getHref: () => 'https://www.dndbeyond.com/characters', runExport });
    const sendResponse = vi.fn();

    listener(EXPORT_MESSAGE, {}, sendResponse);

    expect(runExport).not.toHaveBeenCalled();
    expect(sendResponse).toHaveBeenCalledWith({
      ok: false,
      error: { code: 'NOT_A_CHARACTER_PAGE', message: 'Not a character sheet page', status: null },
    });
  });

  it('ignores messages for other modules or actions', () => {
    const runExport = vi.fn();
    const { listener } = setup({ runExport });
    const sendResponse = vi.fn();

    expect(listener({ module: 'something-else', action: 'export' }, {}, sendResponse)).toBe(false);
    expect(listener({ module: 'character-export', action: 'ping' }, {}, sendResponse)).toBe(false);
    expect(listener(undefined, {}, sendResponse)).toBe(false);
    expect(runExport).not.toHaveBeenCalled();
    expect(sendResponse).not.toHaveBeenCalled();
  });
});
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `npx vitest run tests/content-main.test.js`

Expected: FAIL — cannot resolve `../src/modules/character-export/content-main.js`.

- [ ] **Step 3: Write the implementation**

Create `src/modules/character-export/content-main.js`:

```js
import { createLogger } from '../../core/logger.js';
import { fail, ok } from '../../core/messaging.js';
import { exportCharacter } from './export.js';
import { characterExportModule } from './module.js';

const log = createLogger('character-export');

export function registerCharacterExportListener({
  chromeApi = chrome,
  getHref = () => location.href,
  runExport = exportCharacter,
} = {}) {
  chromeApi.runtime.onMessage.addListener((message, sender, sendResponse) => {
    if (message?.module !== characterExportModule.id || message?.action !== 'export') return false;

    const context = characterExportModule.resolveContext(getHref());
    if (!context) {
      sendResponse(fail({ code: 'NOT_A_CHARACTER_PAGE', message: 'Not a character sheet page' }));
      return false;
    }

    runExport(context.characterId)
      .then((result) => sendResponse(ok(result)))
      .catch((error) => {
        log.error('Export failed', error);
        sendResponse(fail(error));
      });

    return true; // keep the message channel open for the async reply
  });
}
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `npx vitest run tests/content-main.test.js`

Expected: PASS, 5 tests.

- [ ] **Step 5: Commit**

```bash
git add src/modules/character-export/content-main.js tests/content-main.test.js
git commit -m "feat(extension): add character-export content script listener"
```

---

### Task 10: Content script bootstrap and manifest

Chrome does not allow static `import` in content scripts, so the classic bootstrap dynamic-imports the module graph from an extension URL. Every file reachable from that import must be listed in `web_accessible_resources`.

**Files:**
- Create: `src/modules/character-export/content.js`
- Create: `manifest.json`

- [ ] **Step 1: Write the bootstrap**

Create `src/modules/character-export/content.js`:

```js
// Classic content script. Content scripts cannot use static imports, so the real
// module graph is loaded dynamically from an extension URL. Every file it pulls
// in must appear in web_accessible_resources in manifest.json.
(async () => {
  const url = chrome.runtime.getURL('src/modules/character-export/content-main.js');
  const { registerCharacterExportListener } = await import(url);
  registerCharacterExportListener();
})();
```

- [ ] **Step 2: Write the manifest**

Create `manifest.json`:

```json
{
  "manifest_version": 3,
  "name": "D&D Toolkit",
  "version": "0.1.0",
  "description": "Tools for D&D Beyond. Export a character sheet as complete JSON.",
  "permissions": ["activeTab", "downloads"],
  "host_permissions": [
    "https://www.dndbeyond.com/*",
    "https://auth-service.dndbeyond.com/*",
    "https://character-service.dndbeyond.com/*"
  ],
  "action": {
    "default_title": "D&D Toolkit",
    "default_popup": "src/popup/popup.html"
  },
  "content_scripts": [
    {
      "matches": ["https://www.dndbeyond.com/characters/*"],
      "js": ["src/modules/character-export/content.js"]
    }
  ],
  "web_accessible_resources": [
    {
      "resources": [
        "src/core/*.js",
        "src/api/*.js",
        "src/modules/character-export/*.js"
      ],
      "matches": ["https://www.dndbeyond.com/*"]
    }
  ]
}
```

- [ ] **Step 3: Verify the manifest is valid JSON**

Run: `node -e "JSON.parse(require('fs').readFileSync('manifest.json','utf8')); console.log('manifest ok')"`

Expected: `manifest ok`

- [ ] **Step 4: Commit**

```bash
git add manifest.json src/modules/character-export/content.js
git commit -m "feat(extension): add MV3 manifest and content script bootstrap"
```

---

### Task 11: Popup UI

The popup reads the active tab's URL, renders a button per matching module, sends the export message, and performs the download. `activeTab` is granted by the toolbar click, which is what makes `tab.url` readable.

**Files:**
- Create: `src/popup/popup.html`
- Create: `src/popup/popup.css`
- Create: `src/popup/popup.js`

- [ ] **Step 1: Write the markup**

Create `src/popup/popup.html`:

```html
<!doctype html>
<html lang="en">
  <head>
    <meta charset="utf-8" />
    <title>D&D Toolkit</title>
    <link rel="stylesheet" href="popup.css" />
  </head>
  <body>
    <h1>D&amp;D Toolkit</h1>
    <p id="context" class="context"></p>
    <div id="modules" class="modules"></div>
    <p id="status" class="status" role="status"></p>
    <script type="module" src="popup.js"></script>
  </body>
</html>
```

- [ ] **Step 2: Write the styles**

Create `src/popup/popup.css`:

```css
:root {
  color-scheme: light dark;
}

body {
  width: 260px;
  margin: 0;
  padding: 12px;
  font: 13px/1.4 system-ui, sans-serif;
}

h1 {
  margin: 0 0 8px;
  font-size: 14px;
  border-bottom: 1px solid rgb(128 128 128 / 0.4);
  padding-bottom: 8px;
}

.context {
  margin: 0 0 10px;
  opacity: 0.75;
}

.modules {
  display: grid;
  gap: 6px;
}

button {
  padding: 8px 10px;
  font: inherit;
  cursor: pointer;
  border: 1px solid rgb(128 128 128 / 0.5);
  border-radius: 4px;
  background: transparent;
  color: inherit;
}

button:hover:not(:disabled) {
  border-color: currentColor;
}

button:disabled {
  cursor: progress;
  opacity: 0.6;
}

.status {
  margin: 10px 0 0;
  min-height: 1.4em;
}

.status.error {
  color: #c0392b;
}

.status.success {
  color: #1e8449;
}
```

- [ ] **Step 3: Write the popup script**

Create `src/popup/popup.js`:

```js
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
    button.addEventListener('click', () => runModule(tab, entry, button));
    modulesEl.append(button);
  }
}

render();
```

- [ ] **Step 4: Run the whole suite to confirm nothing regressed**

Run: `npm test`

Expected: PASS. 9 test files, 61 tests.

- [ ] **Step 5: Commit**

```bash
git add src/popup/
git commit -m "feat(extension): add popup with module list and download"
```

---

### Task 12: README and manual verification checklist

**Files:**
- Create: `README.md`

- [ ] **Step 1: Write the README**

Create `README.md`:

````markdown
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
- [ ] Open the service worker / page console for the popup and the page console for the
      content script: no JWT appears in either.

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
````

- [ ] **Step 2: Commit**

```bash
git add README.md
git commit -m "docs(extension): add install, usage, and verification checklist"
```

---

### Task 13: Manual verification in Chrome

No code here. This is the acceptance run — the wiring that unit tests deliberately do not cover.

- [ ] **Step 1: Run the full suite one last time**

Run: `npm test`

Expected: PASS, 61 tests, 9 files.

- [ ] **Step 2: Work through the README checklist**

Follow every box in "Manual verification checklist" in `README.md` against character
`168889417`.

- [ ] **Step 3: Record the outcome**

If every box passes, note it and stop. If any box fails, capture the exact popup text
and the console output, then fix the cause before continuing — a failure here means the
cross-context wiring is broken, which no unit test will catch.

- [ ] **Step 4: Commit any fixes**

```bash
git add -A
git commit -m "fix(extension): <what the manual run exposed>"
```

---

## Deferred, on purpose

Do not build these in this plan:

- Background service worker (the popup covers everything v1 needs).
- Blob-URL download fallback — add it only if a real character trips Chrome's data-URL
  size ceiling.
- Extension icons. The manifest omits `icons` and `default_icon`, so Chrome uses its
  default. Add PNGs when the extension gets a visual identity.
- Any derived, normalized, or summarized view of character data.
- Per-module settings, permissions, or lifecycle hooks.
