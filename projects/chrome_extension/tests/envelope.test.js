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
    expect(buildFilename({ name: 'Tythus' }, '98057166', FIXED_DATE)).toBe(
      'dndbeyond-tythus-98057166-20260725.json',
    );
  });

  it('omits the name segment entirely when the slug is empty', () => {
    expect(buildFilename({ name: '！？' }, '98057166', FIXED_DATE)).toBe(
      'dndbeyond-98057166-20260725.json',
    );
  });

  it('tolerates a character object with no name', () => {
    expect(buildFilename({}, '1', FIXED_DATE)).toBe('dndbeyond-1-20260725.json');
  });
});

describe('buildEnvelope', () => {
  it('wraps the raw character with provenance in a fixed key order', () => {
    const character = { id: 98057166, name: 'Tythus', spells: [] };
    const envelope = buildEnvelope('98057166', character, FIXED_DATE);

    expect(Object.keys(envelope)).toEqual(['exportedAt', 'source', 'characterId', 'character']);
    expect(envelope.exportedAt).toBe(FIXED_DATE.toISOString());
    expect(envelope.source).toBe('dndbeyond-character-v5');
    expect(envelope.characterId).toBe('98057166');
  });

  it('passes the character through by reference, unmodified', () => {
    const character = { id: 1, name: 'Tythus' };
    expect(buildEnvelope(1, character, FIXED_DATE).character).toBe(character);
  });

  it('stringifies a numeric character id', () => {
    expect(buildEnvelope(98057166, {}, FIXED_DATE).characterId).toBe('98057166');
  });
});
