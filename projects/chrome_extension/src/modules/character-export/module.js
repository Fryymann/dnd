// Anchored to https + the exact host so a lookalike domain can never match.
// The id must be followed by a path, query, fragment, or end of string.
const CHARACTER_URL_PATTERN = /^https:\/\/www\.dndbeyond\.com\/characters\/(\d+)(?:[/?#]|$)/;

export const characterExportModule = {
  id: 'character-export',
  title: 'Character export',
  actionLabel: 'Export character JSON',
  urlPattern: CHARACTER_URL_PATTERN,
  resolveContext(url) {
    if (typeof url !== 'string') return null;
    const match = CHARACTER_URL_PATTERN.exec(url);
    return match ? { characterId: match[1] } : null;
  },
};
