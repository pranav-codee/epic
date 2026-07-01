// Initialise Microsoft Teams JS SDK when running inside a Teams tab.
// Outside Teams (browser dev), this is a safe no-op.
import * as microsoftTeams from '@microsoft/teams-js'

export function initTeams() {
  try {
    if (window.parent !== window) {
      microsoftTeams.app.initialize().catch(() => {})
    }
  } catch (_) { /* not in Teams */ }
}

export function isInsideTeams() {
  return window.parent !== window
}
