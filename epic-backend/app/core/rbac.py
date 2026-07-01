"""
Role definitions + route guards. Server-side enforced — never trust the client UI to hide things.
SRS REQ-4.1-4, REQ-4.2-3, NFR-5.3-3.
"""
from enum import Enum
from typing import Iterable
from fastapi import Depends, HTTPException, status
from ..dependencies import get_current_user


class Role(str, Enum):
    EMPLOYEE = "EMPLOYEE"
    IT_ENGINEER = "IT_ENGINEER"
    IT_MANAGER = "IT_MANAGER"
    SYSTEM_ADMIN = "SYSTEM_ADMIN"


def require_role(*allowed: Role):
    """Dependency factory. Use as: Depends(require_role(Role.IT_ENGINEER, Role.SYSTEM_ADMIN))."""
    allowed_set = {r.value for r in allowed}

    def _checker(user=Depends(get_current_user)):
        user_roles = set(user.roles or [])
        if not user_roles & allowed_set:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Requires one of: {sorted(allowed_set)}",
            )
        return user

    return _checker


def has_role(user, *roles: Role) -> bool:
    return any(r.value in (user.roles or []) for r in roles)
