import { describe, expect, it, vi } from 'vitest';
import { exportCharacter } from '../src/modules/character-export/export.js';

const FIXED_DATE = new Date(2026, 6, 25, 14, 2, 11, 482);

const deps = (overrides = {}) => ({
  getToken: vi.fn().mockResolvedValue('jwt-value'),
  getCharacter: vi.fn().mockResolvedValue({ id: 98057166, name: 'Tythus' }),
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
    await exportCharacter('98057166', d);
    expect(d.getToken).toHaveBeenCalledTimes(1);
    expect(d.getCharacter).toHaveBeenCalledWith('98057166', 'jwt-value');
  });

  it('returns the filename and a data URL holding the envelope', async () => {
    const result = await exportCharacter('98057166', deps());

    expect(result.filename).toBe('dndbeyond-tythus-98057166-20260725.json');
    expect(decode(result.dataUrl)).toEqual({
      exportedAt: FIXED_DATE.toISOString(),
      source: 'dndbeyond-character-v5',
      characterId: '98057166',
      character: { id: 98057166, name: 'Tythus' },
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
