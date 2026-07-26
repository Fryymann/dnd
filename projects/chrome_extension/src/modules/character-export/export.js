import { fetchCharacter, getCobaltToken } from '../../api/dndbeyond.js';
import { toJsonDataUrl } from '../../core/download.js';
import { buildEnvelope, buildFilename } from './envelope.js';

// Dependencies are injected so the orchestration is testable without globals.
export async function exportCharacter(characterId, deps = {}) {
  const { getToken = getCobaltToken, getCharacter = fetchCharacter, now = () => new Date() } = deps;

  const date = now();
  const token = await getToken();
  const character = await getCharacter(characterId, token);

  return {
    filename: buildFilename(character, characterId, date),
    dataUrl: toJsonDataUrl(buildEnvelope(characterId, character, date)),
  };
}
