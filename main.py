import os
import time
from contextlib import asynccontextmanager
from collections import defaultdict
from fastapi import Depends, FastAPI, HTTPException, Request, Header
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional

from fast_redi import SmartCachingRestorer

# Initialize restorer
MODEL_DIR = os.path.join(os.path.dirname(__file__), 'models')
print("Initializing REDI with smart caching...")
restorer = SmartCachingRestorer(MODEL_DIR, preload_languages=['hr'])

@asynccontextmanager
async def lifespan(app: FastAPI):
    print("✅ Service started")
    yield
    print("🔄 Shutting down...")
    restorer.shutdown()

app = FastAPI(
    title="REDI API",
    description="Smart-caching diacritic restoration with rate limiting",
    version="1.0.1",
    lifespan=lifespan
)

# Environment-based CORS
ALLOWED_ORIGINS = os.getenv(
    "CORS_ORIGINS",
    "https://finisherka.ak-varazdin.hr,https://finisherka-dev.ak-varazdin.hr"
).split(",")
API_KEY = os.getenv("REDI_API_KEY", None)
ENABLE_API_KEY = os.getenv("ENABLE_API_KEY", "false").lower() == "true"

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["*"],
)

# Optional API Key authentication
async def verify_api_key(x_api_key: str = Header(None)):
    """Verify API key if enabled"""
    if not ENABLE_API_KEY:
        return True  # Disabled, skip check
    
    if x_api_key != API_KEY:
        raise HTTPException(
            status_code=403,
            detail="Invalid or missing API key"
        )
    
    return True

def get_client_ip(request: Request) -> str:
    """Extract real client IP from headers"""
    # 1. Check X-Real-IP (Django sets this)
    real_ip = request.headers.get('X-Real-IP')
    if real_ip:
        return real_ip
    
    # 2. Check X-Forwarded-For (standard)
    forwarded_for = request.headers.get('X-Forwarded-For')
    if forwarded_for:
        return forwarded_for.split(',')[0].strip()
    
    # 3. Fallback to direct connection
    return request.client.host

# Rate limiting storage
rate_limit_storage = defaultdict(lambda: {"count": 0, "reset_time": time.time()})

# Rate limiting config
RATE_LIMIT_REQUESTS = 20  # requests
RATE_LIMIT_WINDOW = 60    # per 60 seconds
RATE_LIMIT_NON_HR = 10     # Stricter for non-Croatian

def check_rate_limit(request: Request, lang: str) -> bool:
    """Check rate limit for IP and language"""
    client_ip = get_client_ip(request)
    key = f"{client_ip}:{lang}"
    
    now = time.time()
    data = rate_limit_storage[key]
    
    # Reset window if expired
    if now - data["reset_time"] > RATE_LIMIT_WINDOW:
        data["count"] = 0
        data["reset_time"] = now
    
    # Check limit
    limit = RATE_LIMIT_REQUESTS if lang == 'hr' else RATE_LIMIT_NON_HR
    
    if data["count"] >= limit:
        return False
    
    data["count"] += 1
    return True

class SuggestRequest(BaseModel):
    name: str
    lang: str = "hr"

class SuggestResponse(BaseModel):
    original: str
    suggestion: Optional[str]

@app.get("/")
async def root():
    return {
        "service": "REDI API",
        "version": "1.0.1",
        "features": ["smart-caching", "rate-limiting"],
        "available_languages": restorer.languages,
        "loaded_languages": restorer.loaded_languages
    }

@app.get("/health")
async def health_check():
    """
    Health check - ONLY healthy if Croatian (hr) is loaded
    """
    loaded = restorer.loaded_languages
    hr_loaded = 'hr' in loaded
    
    # Service is only healthy if HR is loaded
    if not hr_loaded:
        return JSONResponse(
            status_code=503,  # Service Unavailable
            content={
                "status": "unhealthy",
                "reason": "Croatian model not loaded",
                "loaded_languages": loaded,
                "required": ["hr"]
            }
        )
    
    # Check memory health
    try:
        import psutil
        process = psutil.Process(os.getpid())
        memory_mb = process.memory_info().rss / 1024 / 1024
        memory_healthy = memory_mb < 1900  # Less than 1.9 GB
        
        if not memory_healthy:
            return JSONResponse(
                status_code=503,
                content={
                    "status": "unhealthy",
                    "reason": f"Memory usage too high: {memory_mb:.1f} MB",
                    "loaded_languages": loaded
                }
            )
    except:
        pass  # If psutil not available, skip memory check
    
    # Healthy
    return {
        "status": "healthy",
        "loaded_languages": loaded,
        "required_loaded": hr_loaded,
        "stats": restorer.stats
    }

@app.get("/stats")
async def get_stats():
    """Get cache statistics"""
    return restorer.stats

@app.post("/suggest", response_model=SuggestResponse)
async def suggest_correction(request: Request, body: SuggestRequest, _: bool = Depends(verify_api_key)):
    """Suggest correction with rate limiting"""
    
    # Rate limiting
    if not check_rate_limit(request, body.lang):
        raise HTTPException(
            status_code=429,
            detail=f"Rate limit exceeded for language '{body.lang}'. Try again later."
        )
    
    try:
        suggestion = restorer.suggest_correction(body.name, body.lang)
        
        return SuggestResponse(
            original=body.name,
            suggestion=suggestion,
        )
    
    except Exception as e:
        # Log error but don't expose details
        print(f"ERROR: {str(e)}")
        raise HTTPException(status_code=500, detail="Processing error")