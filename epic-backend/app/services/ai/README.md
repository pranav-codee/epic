# AI Orchestrator (Reserved — Version 2, NOT IMPLEMENTED)

Deliberately empty extension point. No AI Assistant, no chatbot, no LLM client, no semantic search
in v1 (BR-8, NFR-5.2-2). When v2 begins, an AI Orchestrator can live here and call
`app.modules.tickets.service` directly to obtain identical audit + notification behaviour as
the HTTP routes — that is precisely why ticket mutations live in the service layer, not inline
in route handlers.
