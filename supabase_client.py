from supabase import create_client, Client
import os

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")
SUPABASE_SERVICE_ROLE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY", SUPABASE_KEY)

# Regular client for normal operations
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

# Admin client for privileged operations (like changing passwords)
supabase_admin: Client = create_client(SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY)

print("✅ Supabase client initialized successfully")