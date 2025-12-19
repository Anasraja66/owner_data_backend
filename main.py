"""
Telegram RERA Lookup Backend Service
FastAPI + Telethon for Telegram MTProto communication
"""

import os
import asyncio
import logging
from typing import Optional
from fastapi import FastAPI, HTTPException, Depends, Header
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from telethon import TelegramClient
from telethon.sessions import StringSession
from telethon.errors import SessionPasswordNeededError, PhoneCodeInvalidError
import uvicorn

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Environment variables
API_ID = int(os.getenv("TELEGRAM_API_ID", "0"))
API_HASH = os.getenv("TELEGRAM_API_HASH", "")
API_KEY = os.getenv("API_KEY", "your-secret-api-key")
SESSION_FILE = os.getenv("SESSION_FILE", "session.txt")

# FastAPI app
app = FastAPI(title="Telegram RERA Lookup API")

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Global client and state
client: Optional[TelegramClient] = None
phone_code_hash: Optional[str] = None
pending_phone: Optional[str] = None


# Request/Response models
class PhoneRequest(BaseModel):
    phone: str


class VerifyCodeRequest(BaseModel):
    phone: str
    code: str
    password: Optional[str] = None


class RERARequest(BaseModel):
    rera_number: str


class StatusResponse(BaseModel):
    authenticated: bool
    phone: Optional[str] = None


# API Key authentication
async def verify_api_key(x_api_key: str = Header(...)):
    if x_api_key != API_KEY:
        raise HTTPException(status_code=401, detail="Invalid API key")
    return x_api_key


def load_session() -> str:
    """Load session string from file if exists"""
    if os.path.exists(SESSION_FILE):
        with open(SESSION_FILE, "r") as f:
            return f.read().strip()
    return ""


def save_session(session_string: str):
    """Save session string to file"""
    with open(SESSION_FILE, "w") as f:
        f.write(session_string)


async def get_client() -> TelegramClient:
    """Get or create Telegram client"""
    global client
    
    if client is None:
        session_string = load_session()
        client = TelegramClient(StringSession(session_string), API_ID, API_HASH)
        await client.connect()
    
    return client


@app.on_event("startup")
async def startup():
    """Initialize client on startup"""
    logger.info("Starting Telegram client...")
    try:
        await get_client()
        logger.info("Telegram client initialized")
    except Exception as e:
        logger.error(f"Failed to initialize client: {e}")


@app.on_event("shutdown")
async def shutdown():
    """Disconnect client on shutdown"""
    global client
    if client:
        await client.disconnect()


@app.get("/health")
async def health_check():
    """Health check endpoint"""
    return {"status": "ok"}


@app.get("/session/status", response_model=StatusResponse)
async def get_session_status(_: str = Depends(verify_api_key)):
    """Check if user is authenticated"""
    try:
        tc = await get_client()
        is_authorized = await tc.is_user_authorized()
        
        phone = None
        if is_authorized:
            me = await tc.get_me()
            phone = me.phone if me else None
        
        return StatusResponse(authenticated=is_authorized, phone=phone)
    except Exception as e:
        logger.error(f"Status check error: {e}")
        return StatusResponse(authenticated=False)


@app.post("/auth/start")
async def start_auth(request: PhoneRequest, _: str = Depends(verify_api_key)):
    """Start phone authentication - sends code to Telegram"""
    global phone_code_hash, pending_phone
    
    try:
        tc = await get_client()
        
        # Check if already authenticated
        if await tc.is_user_authorized():
            return {"success": True, "message": "Already authenticated", "code_sent": False}
        
        # Send code
        result = await tc.send_code_request(request.phone)
        phone_code_hash = result.phone_code_hash
        pending_phone = request.phone
        
        logger.info(f"Code sent to {request.phone}")
        return {"success": True, "message": "Code sent to Telegram", "code_sent": True}
    
    except Exception as e:
        logger.error(f"Auth start error: {e}")
        raise HTTPException(status_code=400, detail=str(e))


@app.post("/auth/verify")
async def verify_code(request: VerifyCodeRequest, _: str = Depends(verify_api_key)):
    """Verify the code received on Telegram"""
    global client, phone_code_hash, pending_phone
    
    try:
        tc = await get_client()
        
        # Use stored hash or require it matches pending phone
        if pending_phone != request.phone:
            raise HTTPException(status_code=400, detail="Phone number mismatch. Start auth again.")
        
        if not phone_code_hash:
            raise HTTPException(status_code=400, detail="No pending verification. Start auth first.")
        
        try:
            await tc.sign_in(request.phone, request.code, phone_code_hash=phone_code_hash)
        except SessionPasswordNeededError:
            # 2FA enabled
            if not request.password:
                return {"success": False, "requires_2fa": True, "message": "2FA password required"}
            await tc.sign_in(password=request.password)
        except PhoneCodeInvalidError:
            raise HTTPException(status_code=400, detail="Invalid code")
        
        # Save session
        session_string = tc.session.save()
        save_session(session_string)
        
        # Clear pending state
        phone_code_hash = None
        pending_phone = None
        
        logger.info("Successfully authenticated")
        return {"success": True, "message": "Successfully authenticated"}
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Verify error: {e}")
        raise HTTPException(status_code=400, detail=str(e))


@app.post("/rera/lookup")
async def lookup_rera(request: RERARequest, _: str = Depends(verify_api_key)):
    """Send RERA number to @AtlasDubaiBot and get response"""
    try:
        tc = await get_client()
        
        if not await tc.is_user_authorized():
            raise HTTPException(status_code=401, detail="Not authenticated with Telegram")
        
        bot_username = "AtlasDubaiBot"
        rera_number = request.rera_number.strip()
        
        logger.info(f"Looking up RERA: {rera_number}")
        
        # Get the bot entity
        try:
            bot = await tc.get_entity(bot_username)
        except Exception as e:
            logger.error(f"Could not find bot: {e}")
            raise HTTPException(status_code=404, detail=f"Could not find @{bot_username}")
        
        # Send the RERA number
        await tc.send_message(bot, rera_number)
        logger.info(f"Sent RERA to bot: {rera_number}")
        
        # Wait for response (with timeout)
        await asyncio.sleep(3)  # Give bot time to respond
        
        # Get recent messages from bot
        messages = await tc.get_messages(bot, limit=5)
        
        # Find the response (should be after our message)
        response_text = None
        for msg in messages:
            if msg.out:  # Skip our own messages
                continue
            response_text = msg.text
            break
        
        if response_text:
            logger.info(f"Got response from bot")
            return {
                "success": True,
                "rera_number": rera_number,
                "response": response_text
            }
        else:
            return {
                "success": True,
                "rera_number": rera_number,
                "response": "No response received from bot yet. Please try again in a moment."
            }
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"RERA lookup error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/auth/logout")
async def logout(_: str = Depends(verify_api_key)):
    """Logout and clear session"""
    global client
    
    try:
        if client:
            await client.log_out()
            client = None
        
        # Remove session file
        if os.path.exists(SESSION_FILE):
            os.remove(SESSION_FILE)
        
        return {"success": True, "message": "Logged out"}
    except Exception as e:
        logger.error(f"Logout error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
