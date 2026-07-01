"""Identity provider abstraction. Production = Entra ID. Mock provider exists only for local dev."""
from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass
class IdentityClaims:
    entra_oid: str
    email: str
    display_name: str
    department: str | None = None


class IdentityProvider(ABC):
    @abstractmethod
    def authorize_url(self, state: str) -> str: ...

    @abstractmethod
    async def exchange_code(self, code: str) -> IdentityClaims: ...
