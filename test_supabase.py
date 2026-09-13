from supabase import create_client, Client

# PASTE YOUR DETAILS HERE
url: str = "https://dtxamirjwbdeyixujucw.supabase.co"
key: str = "sb_publishable_GZvftCqOX1skZOZLNH8IQg_AodyfpLu"

print("Connecting to Supabase...")

try:
    supabase: Client = create_client(url, key)
    print("✅ SUCCESS! Connected to Supabase!")
    print(f"Project URL: {url}")
except Exception as e:
    print("❌ FAILED! Connection error:")
    print(e)
