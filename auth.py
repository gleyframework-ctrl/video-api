from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, EmailStr
from supabase_client import supabase, supabase_admin
import requests
import os

router = APIRouter()

class UserSignup(BaseModel):
    email: EmailStr
    password: str
    full_name: str

class UserLogin(BaseModel):
    email: EmailStr
    password: str

class UserSettings(BaseModel):
    cartesia_api_key: str
    cartesia_voice_id: str

@router.post("/signup")
async def signup(user: UserSignup):
    try:
        auth_response = supabase.auth.sign_up({
            "email": user.email,
            "password": user.password,
            "options": {
                "data": {
                    "full_name": user.full_name
                }
            }
        })
        
        if not auth_response.user:
            raise HTTPException(status_code=400, detail="Failed to create user")
        
        try:
            supabase.table("user_profiles").insert({
                "id": auth_response.user.id,
                "email": user.email,
                "full_name": user.full_name,
                "cartesia_voice_id": "393e1d0f-483d-44e2-81d8-108b611c7804",
                "created_at": "now()"
            }).execute()
        except Exception as db_error:
            print(f"Profile creation error: {db_error}")
        
        return {
            "message": "Account created successfully",
            "user_id": auth_response.user.id,
            "email": auth_response.user.email
        }
        
    except HTTPException:
        raise
    except Exception as e:
        print(f"Signup error: {str(e)}")
        raise HTTPException(status_code=400, detail=f"Signup failed: {str(e)}")

@router.post("/login")
async def login(user: UserLogin):
    try:
        response = supabase.auth.sign_in_with_password({
            "email": user.email,
            "password": user.password
        })
        
        if not response.session or not response.user:
            raise HTTPException(status_code=401, detail="Invalid email or password")
        
        return {
            "message": "Login successful",
            "access_token": response.session.access_token,
            "refresh_token": response.session.refresh_token,
            "user_id": response.user.id,
            "email": response.user.email
        }
        
    except HTTPException:
        raise
    except Exception as e:
        print(f"Login error: {str(e)}")
        raise HTTPException(status_code=401, detail="Invalid email or password")

@router.get("/user/settings")
async def get_user_settings(user_id: str):
    try:
        response = supabase.table("user_profiles").select(
            "cartesia_api_key, cartesia_voice_id"
        ).eq("id", user_id).execute()
        
        if response.data and len(response.data) > 0:
            return response.data[0]
        
        return {"cartesia_api_key": None, "cartesia_voice_id": "393e1d0f-483d-44e2-81d8-108b611c7804"}
        
    except Exception as e:
        print(f"Error fetching settings: {e}")
        raise HTTPException(status_code=500, detail="Failed to fetch settings")

@router.post("/user/settings")
async def save_user_settings(user_id: str, settings: UserSettings):
    try:
        response = supabase.table("user_profiles").update({
            "cartesia_api_key": settings.cartesia_api_key,
            "cartesia_voice_id": settings.cartesia_voice_id,
            "updated_at": "now()"
        }).eq("id", user_id).execute()
        
        return {"message": "Settings saved successfully"}
        
    except Exception as e:
        print(f"Error saving settings: {e}")
        raise HTTPException(status_code=500, detail="Failed to save settings")

@router.get("/user/videos")
async def get_user_videos(user_id: str):
    try:
        response = supabase.table("videos").select("*").eq("user_id", user_id).order("created_at", desc=True).limit(50).execute()
        return response.data or []
        
    except Exception as e:
        print(f"Error fetching videos: {e}")
        raise HTTPException(status_code=500, detail="Failed to fetch videos")

@router.post("/change-password")
async def change_password(data: dict):
    user_id = data.get("user_id")
    new_password = data.get("new_password")
    
    if not user_id or not new_password:
        raise HTTPException(status_code=400, detail="Missing user ID or new password")
        
    if len(new_password) < 6:
        raise HTTPException(status_code=400, detail="Password must be at least 6 characters")

    try:
        # Use direct REST API call with service role key
        supabase_url = os.getenv("SUPABASE_URL")
        service_role_key = os.getenv("SUPABASE_SERVICE_ROLE_KEY")
        
        headers = {
            "apikey": service_role_key,
            "Authorization": f"Bearer {service_role_key}",
            "Content-Type": "application/json",
            "Prefer": "return=minimal"
        }
        
        # Call Supabase Auth Admin API directly
        response = requests.put(
            f"{supabase_url}/auth/v1/admin/users/{user_id}",
            headers=headers,
            json={"password": new_password}
        )
        
        if response.status_code != 200:
            raise Exception(f"Supabase API error: {response.text}")
        
        return {"message": "Password updated successfully"}
        
    except Exception as e:
        print(f"Error changing password: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to update password: {str(e)}")