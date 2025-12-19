# Telegram RERA Lookup Backend

Python FastAPI service using Telethon for Telegram MTProto communication.

## Setup

### 1. Get Telegram API Credentials
1. Go to https://my.telegram.org
2. Log in with your phone number
3. Go to "API Development Tools"
4. Create a new application
5. Copy the `api_id` and `api_hash`

### 2. Environment Variables
Create a `.env` file:
```bash
TELEGRAM_API_ID=your_api_id
TELEGRAM_API_HASH=your_api_hash
API_KEY=generate-a-secure-random-key
SESSION_FILE=session.txt
```

### 3. Local Development
```bash
# Create virtual environment
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Run the server
python main.py
```

### 4. Deploy to Railway

1. Create a new project on https://railway.app
2. Connect your GitHub repo or use "Deploy from GitHub"
3. Add environment variables in Railway dashboard:
   - `TELEGRAM_API_ID`
   - `TELEGRAM_API_HASH`
   - `API_KEY`
4. Railway will auto-detect the Dockerfile and deploy

### 5. Deploy to Render

1. Create a new Web Service on https://render.com
2. Connect your repo
3. Set:
   - Build Command: `pip install -r requirements.txt`
   - Start Command: `uvicorn main:app --host 0.0.0.0 --port $PORT`
4. Add environment variables

## API Endpoints

All endpoints require `X-API-Key` header.

### Health Check
```
GET /health
```

### Check Session Status
```
GET /session/status
Response: { "authenticated": true/false, "phone": "+1234..." }
```

### Start Authentication
```
POST /auth/start
Body: { "phone": "+1234567890" }
Response: { "success": true, "code_sent": true }
```

### Verify Code
```
POST /auth/verify
Body: { "phone": "+1234567890", "code": "12345", "password": "optional-2fa" }
Response: { "success": true }
```

### Lookup RERA
```
POST /rera/lookup
Body: { "rera_number": "12345" }
Response: { "success": true, "rera_number": "12345", "response": "Owner info..." }
```

### Logout
```
POST /auth/logout
Response: { "success": true }
```

## After Deployment

Once deployed, you'll get a URL like:
- Railway: `https://your-app.up.railway.app`
- Render: `https://your-app.onrender.com`

Provide this URL and your API_KEY to configure the Lovable edge function.
