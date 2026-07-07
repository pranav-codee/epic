"""
Shared rate limiter instance. Lives in its own module (rather than app/main.py) so that
router modules can import it without creating a circular import with main.py, which itself
imports all the routers.
"""
from slowapi import Limiter
from slowapi.util import get_remote_address

limiter = Limiter(key_func=get_remote_address)