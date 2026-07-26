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
