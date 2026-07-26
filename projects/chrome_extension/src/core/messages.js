// The single source of user-facing error text. Nothing else composes copy.
const ERROR_MESSAGES = {
  NOT_A_CHARACTER_PAGE: 'Open a D&D Beyond character sheet.',
  NO_CONTENT_SCRIPT: 'Reload the character sheet, then try again.',
  NOT_SIGNED_IN: 'Not signed in to D&D Beyond.',
  NO_ACCESS: "You don't have access to that character.",
  NOT_FOUND: 'Character not found.',
  NETWORK: 'Export failed (network error).',
};

export function messageForError(error) {
  if (error?.code === 'API_REJECTED' && error.message) return error.message;

  const copy = ERROR_MESSAGES[error?.code];
  if (copy) return copy;

  const detail = error?.status ? `status ${error.status}` : error?.message || 'unknown error';
  return `Export failed (${detail}).`;
}
