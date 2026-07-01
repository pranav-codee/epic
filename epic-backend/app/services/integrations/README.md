# Integrations (Reserved — Version 2, NOT IMPLEMENTED)

This folder is a deliberately empty extension point.

The following integrations are **out of scope for EPIC v1** (SRS Chapter 7) and must **not**
be added under any circumstances in this version:

- IBM QRadar
- Fortinet Firewall
- ManageEngine Endpoint Central
- Check Point Harmony Email & Collaboration

When v2 begins, add one sub-package per integration here, each implementing a thin client and
calling into `app.modules.tickets.service` to create/update tickets. The ticket service layer's
contract is the only stable surface third-party integrations should depend on.
