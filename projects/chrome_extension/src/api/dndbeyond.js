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
