import { characterExportModule } from '../modules/character-export/module.js';

// To add a module: import its descriptor and append it here, then add a
// matching entry to content_scripts in manifest.json.
export const MODULES = [characterExportModule];

export function getModulesForUrl(url) {
  if (typeof url !== 'string') return [];
  return MODULES
    .map((module) => ({ module, context: module.resolveContext(url) }))
    .filter((entry) => entry.context !== null);
}
