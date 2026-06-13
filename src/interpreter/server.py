import os
import sys
import subprocess
import json
from natsort import natsorted
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from fastapi import FastAPI, Request, Response, HTTPException
from collections import defaultdict
from fastapi.responses import JSONResponse
import sqlite3 as sql
import uuid, time
from dotenv import load_dotenv

# methods: /session /generate /models

#log stuff
request_log: dict[str, list] = defaultdict(list)
daily_log: dict[str, list] = defaultdict(list)

app = FastAPI()


app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "https://tariqgpt.duckdns.org"],
    allow_methods=["*"],
    allow_headers=["*"],
    allow_credentials=True,
)

#setup sqlite if it doesn't exist
conn = sql.connect("sessions.db")
cursor = conn.cursor()
cursor.execute("CREATE TABLE IF NOT EXISTS sessions (session_id TEXT PRIMARY KEY, created_at INTEGER NOT NULL, expires_at INTEGER NOT NULL, ip TEXT NOT NULL);")
conn.commit()
conn.close()


INTERPRETER = os.path.join(os.path.dirname(__file__), "model_interpreter.py")
    
BANNED_IPS_FILE = "banned_ips.txt"
RATE_LIMIT = 3
DAILY_LIMIT = 10000
WHITE_LIST = {"127.0.0.1", "192.168.1.215"} #, "141.156.89.100"
EXCLUDED = {"/models"}

ENV_PATH = "../../.env"
load_dotenv(ENV_PATH)

COOKIE_SECURE = os.getenv("secure") == "true"
SAME_SITE = os.getenv("samesite", "lax")
MAX_AGE = 259200


class GenerateRequest(BaseModel):
    prompt: str
    max_tokens: int = 250
    temperature: float = 1.0
    model_name: str = None

def getExpDate(session_id: str):
    conn = sql.connect()
    cursor = conn.cursor()
    cursor.execute("SELECT expires_at FROM sessions WHERE sessions_id = ?", (session_id,))
    result = cursor.fetchone()
    if result is None:
        return None
    else:
        return result[0]

def checkSession(session_id: str, ip: str, ua: str):
    conn = sql.connect("sessions.db")
    cursor = conn.cursor()
    cursor.execute("SELECT expires_at FROM sessions WHERE session_id = ?", (session_id,))
    result = cursor.fetchone()
    
    if result is None:
        conn.close()
        return False
    
    expires_at = result[0]
    
    if expires_at < int(time.time()):
        cursor.execute("DELETE FROM sessions WHERE session_id = ?",(session_id,))
        conn.commit()
        conn.close()
        return False
    
    conn.close()
    
    conn = sql.connect("sessions.db")
    cursor = conn.cursor()
    cursor.execute("SELECT ip FROM sessions WHERE session_id = ?",(session_id,))
    result = cursor.fetchone()
    
    if result is None:
        conn.close()
        return False
    
    session_ip = result[0]
    
    if session_ip is None:
        cursor.execute("UPDATE sessions SET ip = ? WHERE session_id = ?", (ip, session_id,))
        conn.commit()
        conn.close()
        return True;
    
    conn = sql.connect("sessions.db")
    cursor = conn.cursor()
    cursor.execute("SELECT user_agent FROM sessions WHERE session_id = ?",(session_id,))
    result = cursor.fetchone()
    
    if result is None:
        conn.close()
        return False
    
    user_agent = result[0]
    
    if user_agent is None:
        cursor.execute("UPDATE sessions SET user_agent = ? WHERE session_id = ?", (ua, session_id,))
        conn.commit()
        conn.close()
        return True;
        
    
    conn.close()
    return True



def createSession(ip: str, ua: str):
    conn = sql.connect("sessions.db")
    cursor = conn.cursor()
    newSession_id = str(uuid.uuid4())
    created_at = int(time.time())
    expires_at = int(time.time())+MAX_AGE #3 days from time.ctime()
    cursor.execute(f"INSERT into sessions (session_id, created_at, expires_at, ip, user_agent) values (?,?,?,?,?)", (newSession_id, created_at, expires_at, ip, ua))
    conn.commit()
    conn.close()
    return newSession_id


def load_banned_ips() -> set:
    try:
        with open(BANNED_IPS_FILE, "r") as f:
            return set(line.strip() for line in f if line.strip())
    except FileNotFoundError:
        return set()

def ban_ip(ip: str):
    with open(BANNED_IPS_FILE, "a") as f:
        f.write(ip + "\n")

def check_rate(ip: str) -> str | None:
    now = int(time.time())

    # per-second check
    request_log[ip] = [t for t in request_log[ip] if now - t < 1.0]
    request_log[ip].append(now)
    if len(request_log[ip]) > RATE_LIMIT:
        return "rate_limit"

    # per-day check
    daily_log[ip] = [t for t in daily_log[ip] if now - t < 86400]
    daily_log[ip].append(now)
    if len(daily_log[ip]) > DAILY_LIMIT:
        return "daily_limit"

    return None

@app.middleware("http")
async def ban_middleware(request: Request, call_next):
    ip = request.client.host
    print(ip)
    if ip in WHITE_LIST or request.url.path in EXCLUDED:
        return await call_next(request)

    if ip in load_banned_ips():
        return JSONResponse(status_code=403, content={"detail": "Banned"})

    reason = check_rate(ip)
    if reason == "rate_limit":
        ban_ip(ip)
        del request_log[ip]
        print(f"Banned {ip} for spamming")
        return JSONResponse(status_code=429, content={"detail": "Banned for spamming"})
    elif reason == "daily_limit":
        # soft block - don't ban permanently, just reject for now
        return JSONResponse(status_code=429, content={"detail": "Daily limit reached, try again tomorrow"})

    return await call_next(request)

@app.post("/generate")
def generate(req: GenerateRequest, request: Request):
    ip = request.client.host
    ua = request.headers.get("user-agent")
    session_id = request.cookies.get("tariqGPT_session")
    if (not checkSession(session_id, ip, ua)):
        return {
            "response": "Session ID invalid, try refreshing your browser",
            "confidence": None,
        }
    
    args = [
        sys.executable, INTERPRETER,
        str(req.max_tokens),
        str(req.temperature),
    ]
    
    if req.max_tokens > 300:
        args[2] = "300"
        
    if req.model_name:
        args.append(req.model_name)
        
    proc = subprocess.run(
        args,
        input=req.prompt.encode("utf-8"),
        capture_output=True,
        timeout=120,
    )
    if proc.returncode != 0:
        raise HTTPException(status_code=500, detail=proc.stderr.decode("utf-8"))
    
    try:
        result = json.loads(proc.stdout.decode("utf-8"))
        probs = result["token_probs"]
        mean_conf  = sum(probs) / len(probs)
        min_conf   = min(probs)
        tail_mean  = sum(probs[-10:]) / len(probs[-10:])  # last 10 tokens
        confidence = round((mean_conf * 0.4) + (min_conf * 0.3) + (tail_mean * 0.3), 3)

        return {
            "response": result["response"],
            "confidence": confidence
        }
    except (json.JSONDecodeError, KeyError):
        # fallback if model_interpreter hasn't been updated yet
        return {"response": proc.stdout.decode("utf-8").strip(), "confidence": None}

@app.get("/session")
def session(req: Request, res: Response):
    
    session_id = req.cookies.get("tariqGPT_session")
    ip = req.client.host #ip and useragent are purely analytical data to see where and what and do stuff in the future accordingly.
    ua = req.headers.get("user-agent")
    #check session
    if checkSession(session_id, ip, ua):
        
        return {"ok": True, "created": False, "expires_at": getExpDate(session_id),}
    
    
    newSession = createSession(ip, ua)
    res.set_cookie(
        key="tariqGPT_session",
        value=newSession,
        httponly=True,
        secure=COOKIE_SECURE,
        samesite=SAME_SITE,
        max_age=MAX_AGE,
    )
    return {"ok": True, "created": True, "expires_at": getExpDate(session_id),}
        
    

@app.get("/models")
def list_models():
    model_dir = os.path.join(os.path.dirname(__file__), "models")
    if not os.path.exists(model_dir):
        return {"models": []}
    models = [os.path.splitext(f)[0] for f in os.listdir(model_dir) if f.endswith(".pt")]
    models = natsorted(models)
    models.reverse()
    return {"models": models}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
