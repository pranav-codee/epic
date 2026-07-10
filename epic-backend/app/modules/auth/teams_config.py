"""
Minimal Teams configurable-tab configuration endpoint. Lets a Teams channel/team admin
pin either the Employee or Admin tab; sends the chosen URL back to Teams via the SDK.
Hosted separately so manifest.json's configurationUrl is not a 404.
"""
from fastapi import APIRouter
from fastapi.responses import HTMLResponse

from ...config import get_settings

router = APIRouter()

@router.get("/teams/config", include_in_schema=False)
def teams_config():
    # FIX: was hardcoded to "https://epic.epl.local" — the same placeholder host that
    # docs/GAP_LIST.md (G4) already tracks for manifest.json/.env. Route it through the
    # one setting (FRONTEND_BASE_URL) so dev/pilot/prod all get the right host without
    # editing this file, and so there's only one place left to update at go-live.
    frontend_base_url = get_settings().FRONTEND_BASE_URL

    return HTMLResponse(f"""<!doctype html>
<html><head><title>EPIC Teams Tab</title>
<script src="https://res.cdn.office.net/teams-js/2.24.0/js/MicrosoftTeams.min.js"></script>
</head><body style="font-family:system-ui;padding:20px;max-width:480px;margin:auto;">
<h2>Configure EPIC tab</h2>
<p>Choose which view to pin:</p>
<label><input type="radio" name="view" value="employee" checked> Employee Portal (My Tickets)</label><br/>
<label><input type="radio" name="view" value="admin"> Admin Portal (engineer queue)</label>
<script>
  microsoftTeams.app.initialize().then(() => {{
    microsoftTeams.pages.config.registerOnSaveHandler(function (saveEvent) {{
      const view = document.querySelector('input[name=view]:checked').value;
      microsoftTeams.pages.config.setConfig({{
        suggestedDisplayName: "EPIC",
        entityId: "epic-" + view,
        contentUrl: "{frontend_base_url}/" + view,
        websiteUrl: "{frontend_base_url}/" + view
      }}).then(() => saveEvent.notifySuccess());
    }});
    microsoftTeams.pages.config.setValidityState(true);
  }});
</script>
</body></html>""")