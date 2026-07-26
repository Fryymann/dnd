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
    const character = { id: 98057166, name: 'Tythus' };
    const fetchImpl = vi
      .fn()
      .mockResolvedValue(response(200, { success: true, message: null, data: character }));

    await expect(fetchCharacter('98057166', 'jwt-value', fetchImpl)).resolves.toEqual(character);
    expect(fetchImpl).toHaveBeenCalledWith(`${CHARACTER_URL}/98057166`, {
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
