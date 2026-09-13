import os
import uuid
import shutil
from datetime import datetime, timedelta
from typing import Optional

from fastapi import FastAPI, UploadFile, File, Form, BackgroundTasks, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from pydantic import BaseModel
from jose import JWTError, jwt
from passlib.context import CryptContext

# ==========================================
# 1. AUTHENTICATION CONFIGURATION
# ==========================================
# In production, load this from environment variables: os.getenv("SECRET_KEY")
SECRET_KEY = "your-super-secret-key-change-in-production"
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 30

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="token")

# Mock Database (Replace with SQLAlchemy/PostgreSQL in production)
fake_users_db = {}

# ==========================================
# 2. PYDANTIC MODELS
# ==========================================
class UserBase(BaseModel):
    username: str

class UserCreate(UserBase):
    password: str

class UserInDB(UserBase):
    hashed_password: str

class Token(BaseModel):
    access_token: str
    token_type: str

class TokenData(BaseModel):
    username: Optional[str] = None

class UploadResponse(BaseModel):
    job_id: str
    message: str

class StatusResponse(BaseModel):
    job_id: str
    status: str
    video_url: Optional[str] = None

# ==========================================
# 3. AUTH HELPERS & DEPENDENCIES
# ==========================================
def verify_password(plain_password, hashed_password):
    return pwd_context.verify(plain_password, hashed_password)

def get_password_hash(password):
    return pwd_context.hash(password)

def get_user(username: str):
    if username in fake_users_db:
        user_dict = fake_users_db[username]
        return UserInDB(**user_dict)
    return None

def authenticate_user(username: str, password: str):
    user = get_user(username)
    if not user:
        return False
    if not verify_password(password, user.hashed_password):
        return False
    return user

def create_access_token(data: dict, expires_delta: Optional[timedelta] = None):
    to_encode = data.copy()
    expire = datetime.utcnow() + (expires_delta or timedelta(minutes=15))
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)

async def get_current_user(token: str = Depends(oauth2_scheme)):
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        username: str = payload.get("sub")
        if username is None:
            raise credentials_exception
        token_data = TokenData(username=username)
    except JWTError:
        raise credentials_exception
    
    user = get_user(username=token_data.username)
    if user is None:
        raise credentials_exception
    return user

# ==========================================
# 4. FASTAPI APP & AUTH ENDPOINTS
# ==========================================
app = FastAPI(title="AI Video Generation API")

@app.post("/register", response_model=UserBase)
async def register(user: UserCreate):
    """Register a new user"""
    if get_user(user.username):
        raise HTTPException(status_code=400, detail="Username already registered")
    hashed_password = get_password_hash(user.password)
    fake_users_db[user.username] = {
        "username": user.username,
        "hashed_password": hashed_password
    }
    return UserBase(username=user.username)

@app.post("/token", response_model=Token)
async def login_for_access_token(form_data: OAuth2PasswordRequestForm = Depends()):
    """Login and get JWT token"""
    user = authenticate_user(form_data.username, form_data.password)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    access_token_expires = timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = create_access_token(
        data={"sub": user.username}, expires_delta=access_token_expires
    )
    return {"access_token": access_token, "token_type": "bearer"}

@app.get("/users/me", response_model=UserBase)
async def read_users_me(current_user: UserInDB = Depends(get_current_user)):
    """Get current authenticated user details"""
    return current_user

# ==========================================
# 5. VIDEO PIPELINE ENDPOINTS (From Logs)
# ==========================================
# Mock job storage (Replace with Redis/DB in production)
jobs = {}

def process_video_pipeline(job_id: str, file_path: str, language: str):
    """Background task mimicking the pipeline seen in your logs"""
    try:
        jobs[job_id]["status"] = "processing"
        
        # [OK] Extracted slides to PNG
        # [AI] Writing script with NVIDIA Llama 3.2
        # [AUDIO] Generating cloned voice audio with Cartesia
        # [CLIP] Creating clip with FFmpeg
        # [RENDER] Starting concat of clips
        # [OK] Final video created
        
        # Simulate processing time
        import time
        time.sleep(2) 
        
        jobs[job_id]["status"] = "completed"
        jobs[job_id]["video_url"] = f"/outputs/{job_id}/final_video.mp4"
    except Exception as e:
        jobs[job_id]["status"] = "failed"
        jobs[job_id]["error"] = str(e)

@app.post("/upload", response_model=UploadResponse)
async def upload_pdf(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    mode: str = Form("auto"),
    language: str = Form("ar"),
    current_user: UserInDB = Depends(get_current_user) # <-- PROTECTED ENDPOINT
):
    """Upload PDF and start video generation pipeline"""
    job_id = uuid.uuid4().hex[:8]
    output_dir = f"outputs/{job_id}"
    os.makedirs(output_dir, exist_ok=True)
    
    file_path = f"{output_dir}/{file.filename}"
    with open(file_path, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)
        
    jobs[job_id] = {"status": "queued", "video_url": None}
    
    # Start background pipeline
    background_tasks.add_task(process_video_pipeline, job_id, file_path, language)
    
    return UploadResponse(job_id=job_id, message="Upload successful. Processing started.")

@app.get("/status/{job_id}", response_model=StatusResponse)
async def get_status(job_id: str):
    """Check the status of a video generation job"""
    if job_id not in jobs:
        raise HTTPException(status_code=404, detail="Job not found")
    
    job = jobs[job_id]
    return StatusResponse(
        job_id=job_id,
        status=job["status"],
        video_url=job.get("video_url")
    )
