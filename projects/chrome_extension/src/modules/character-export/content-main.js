import { createLogger } from '../../core/logger.js';
import { fail, ok } from '../../core/messaging.js';
import { exportCharacter } from './export.js';
import { characterExportModule } from './module.js';

const log = createLogger('character-export');

export function registerCharacterExportListener({
  chromeApi = chrome,
  getHref = () => location.href,
  runExport = exportCharacter,
} = {}) {
  chromeApi.runtime.onMessage.addListener((message, sender, sendResponse) => {
    if (message?.module !== characterExportModule.id || message?.action !== 'export') return false;

    const context = characterExportModule.resolveContext(getHref());
    if (!context) {
      sendResponse(fail({ code: 'NOT_A_CHARACTER_PAGE', message: 'Not a character sheet page' }));
      return false;
    }

    runExport(context.characterId)
      .then((result) => sendResponse(ok(result)))
      .catch((error) => {
        log.error('Export failed', error);
        sendResponse(fail(error));
      });

    return true; // keep the message channel open for the async reply
  });
}
