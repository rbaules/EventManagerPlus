from __future__ import annotations

from supabase import Client, create_client

from config import SUPABASE_PUBLISHABLE_KEY, SUPABASE_URL, validate_config


def create_supabase_client() -> Client:
    """Create a new Supabase client for one Flet Page/session.

    The returned client must not be cached or shared because supabase-py keeps
    authentication state on the client instance.
    """
    validate_config()
    return create_client(SUPABASE_URL, SUPABASE_PUBLISHABLE_KEY)


def get_supabase_client() -> Client:
    """Compatibility factory; always returns a new, independent client."""
    return create_supabase_client()
