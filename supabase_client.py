import logging
import os
from typing import Optional

from supabase import Client, create_client

logger = logging.getLogger(__name__)

# We support both NEXT_PUBLIC_* (what you pasted) and backend-style names.
SUPABASE_URL = (
    os.environ.get("SUPABASE_URL")
    or os.environ.get("NEXT_PUBLIC_SUPABASE_URL")
)
SUPABASE_KEY = (
    # Recommended: set this in your hosting env, DO NOT commit it
    os.environ.get("SUPABASE_SERVICE_ROLE_KEY")
    # Fallback to anon key for now if service key not set
    or os.environ.get("NEXT_PUBLIC_SUPABASE_ANON_KEY")
)

_supabase_client: Optional[Client] = None


def init_supabase() -> Optional[Client]:
    """
    Initialize a singleton Supabase client.

    This logs useful debug info but never logs your keys.
    """
    global _supabase_client

    if _supabase_client is not None:
        logger.debug("Supabase client already initialized.")
        return _supabase_client

    if not SUPABASE_URL:
        logger.error("SUPABASE_URL / NEXT_PUBLIC_SUPABASE_URL is not set.")
        return None

    if not SUPABASE_KEY:
        logger.error(
            "Supabase key is not set. "
            "Set SUPABASE_SERVICE_ROLE_KEY (recommended) "
            "or NEXT_PUBLIC_SUPABASE_ANON_KEY as a fallback."
        )
        return None

    try:
        logger.info("Initializing Supabase client.")
        client = create_client(SUPABASE_URL, SUPABASE_KEY)
        _supabase_client = client
        logger.info("Supabase client initialized successfully.")
        return client
    except Exception as e:
        logger.exception("Failed to initialize Supabase client: %s", e)
        return None


def get_supabase() -> Optional[Client]:
    """
    Helper to get the Supabase client, with debug logging.
    """
    client = init_supabase()
    if client is None:
        logger.error("Supabase client not available. Check environment variables.")
    return client
