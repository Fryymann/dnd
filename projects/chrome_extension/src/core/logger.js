const JWT_PATTERN = /\bey[A-Za-z0-9_-]{6,}\.[A-Za-z0-9_-]{6,}\.[A-Za-z0-9_-]{6,}\b/g;
const SENSITIVE_KEY = /token|authorization|cobaltsession/i;
const REDACTED = '[REDACTED]';

export function redact(value, seen = new WeakSet()) {
  if (typeof value === 'string') return value.replace(JWT_PATTERN, REDACTED);
  if (value === null || typeof value !== 'object') return value;
  if (value instanceof Error) return `${value.name}: ${redact(value.message)}`;
  if (seen.has(value)) return '[Circular]';
  seen.add(value);
  if (Array.isArray(value)) return value.map((item) => redact(item, seen));

  const out = {};
  for (const [key, item] of Object.entries(value)) {
    out[key] = SENSITIVE_KEY.test(key) ? REDACTED : redact(item, seen);
  }
  return out;
}

export function createLogger(namespace) {
  const prefix = `[dnd-toolkit:${namespace}]`;
  const emit = (level) => (...args) => console[level](prefix, ...args.map((arg) => redact(arg)));
  return { info: emit('log'), warn: emit('warn'), error: emit('error') };
}
