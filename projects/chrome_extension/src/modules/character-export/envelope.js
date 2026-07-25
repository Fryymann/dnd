const MAX_SLUG_LENGTH = 40;

export function slugifyName(name) {
  if (typeof name !== 'string') return '';
  return name
    .normalize('NFD')
    .replace(/[\u0300-\u036f]/g, '') // drop combining marks so "Tythus" keeps its letters
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, '-')
    .replace(/^-+|-+$/g, '')
    .slice(0, MAX_SLUG_LENGTH)
    .replace(/-+$/g, '');
}

export function formatDateStamp(date) {
  const pad = (value) => String(value).padStart(2, '0');
  return `${date.getFullYear()}${pad(date.getMonth() + 1)}${pad(date.getDate())}`;
}

export function buildFilename(character, characterId, date = new Date()) {
  const segments = ['dndbeyond', slugifyName(character?.name), String(characterId), formatDateStamp(date)];
  return `${segments.filter(Boolean).join('-')}.json`;
}

export function buildEnvelope(characterId, character, date = new Date()) {
  return {
    exportedAt: date.toISOString(),
    source: 'dndbeyond-character-v5',
    characterId: String(characterId),
    character,
  };
}
