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
