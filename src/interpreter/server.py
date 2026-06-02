import os
import sys
import subprocess
import json
from natsort import natsorted
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from fastapi import FastAPI, Request, HTTPException
import time
from collections import defaultdict
from fastapi.responses import JSONResponse

#log stuff
request_log: dict[str, list] = defaultdict(list)
daily_log: dict[str, list] = defaultdict(list)

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_methods=["*"],
    allow_headers=["*"],
)

INTERPRETER = os.path.join(os.path.dirname(__file__), "model_interpreter.py")
    
BANNED_IPS_FILE = "banned_ips.txt"
RATE_LIMIT = 3
DAILY_LIMIT = 250
WHITE_LIST = {"127.0.0.1", "192.168.1.215"} #, "141.156.89.100"
EXCLUDED = {"/models"}

class GenerateRequest(BaseModel):
    prompt: str
    max_tokens: int = 250
    temperature: float = 1.0
    model_name: str = None


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
    now = time.time()

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
def generate(req: GenerateRequest):
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
