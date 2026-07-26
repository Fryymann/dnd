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
