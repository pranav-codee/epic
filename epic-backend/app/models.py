"""Aggregator import so Alembic + tests can pick up every ORM model in one place."""
from .modules.catalogue.models import (  # noqa
    Location, AssignmentGroup, UserAssignmentGroup,
    CatalogueCategory, CatalogueSubcategory, CatalogueItem,
)
from .modules.users.models import UserProfile, UserRoleAssignment  # noqa
from .modules.tickets.models import Ticket, TicketComment, TicketAttachment  # noqa
from .modules.audit.models import TicketAuditLog  # noqa
from .modules.notifications.models import NotificationRecord  # noqa
from .modules.knowledge_base.models import KnowledgeBaseArticle  # noqa