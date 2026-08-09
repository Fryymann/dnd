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
