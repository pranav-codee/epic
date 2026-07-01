"""Optional: seed a few demo users + roles + tickets so local dev has something to look at."""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.database import SessionLocal, Base, engine
from app import models  # noqa
from app.modules.users.models import UserProfile, UserRoleAssignment
from app.modules.users.service import upsert_from_identity, set_roles
from app.core.rbac import Role
from app.modules.tickets.service import create_ticket


Base.metadata.create_all(bind=engine)

db = SessionLocal()
try:
    alice = upsert_from_identity(db, entra_oid="mock-alice.engineer@epl.local",
                                  email="alice.engineer@epl.local",
                                  display_name="Alice Engineer", department="IT")
    set_roles(db, alice.id, [Role.EMPLOYEE.value, Role.IT_ENGINEER.value])

    bob = upsert_from_identity(db, entra_oid="mock-bob.employee@epl.local",
                                email="bob.employee@epl.local",
                                display_name="Bob Employee", department="Finance")

    cara = upsert_from_identity(db, entra_oid="mock-cara.admin@epl.local",
                                 email="cara.admin@epl.local",
                                 display_name="Cara Admin", department="IT")
    set_roles(db, cara.id, [Role.EMPLOYEE.value, Role.SYSTEM_ADMIN.value, Role.IT_MANAGER.value])

    bob.roles = [Role.EMPLOYEE.value]
    t = create_ticket(db, creator=bob, title="VPN keeps disconnecting on Wi-Fi",
                      description="Office VPN drops every ~15 minutes from my MacBook.",
                      category="VPN", priority="HIGH")
    print(f"Seeded ticket {t.ticket_number}")
finally:
    db.close()
