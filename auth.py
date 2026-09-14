from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel, EmailStr
from supabase_client import supabase

router = APIRouter()

class UserSignup(BaseModel):
    email: EmailStr
    password: str
    full_name: str

class UserLogin(BaseModel):
    email: EmailStr
    password: str

@router.post("/signup")
async def signup(user: UserSignup):
    try:
        # Create user in Supabase Auth
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
        
        # Create user profile in database
        try:
            supabase.table("user_profiles").insert({
                "id": auth_response.user.id,
                "email": user.email,
                "full_name": user.full_name,
                "created_at": "now()"
            }).execute()
        except Exception as db_error:
            print(f"Profile creation error: {db_error}")
            # Don't fail signup if profile creation fails
        
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