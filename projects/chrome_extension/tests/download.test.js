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
