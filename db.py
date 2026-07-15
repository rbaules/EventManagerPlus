from __future__ import annotations

from functools import lru_cache

from supabase import Client, create_client

from config import SUPABASE_PUBLISHABLE_KEY, SUPABASE_URL, validate_config


@lru_cache(maxsize=1)
def get_supabase_client() -> Client:
    validate_config()
    return create_client(SUPABASE_URL, SUPABASE_PUBLISHABLE_KEY)
