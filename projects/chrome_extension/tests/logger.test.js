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
