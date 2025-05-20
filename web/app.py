import os, time, jwt
from dotenv import load_dotenv
from fastapi import FastAPI, Request, Query
from fastapi.responses import PlainTextResponse, HTMLResponse
from fastapi.templating import Jinja2Templates

load_dotenv()

LIVEKIT_URL        = os.getenv("LIVEKIT_URL", "ws://localhost:7880")
LIVEKIT_API_KEY    = os.getenv("LIVEKIT_API_KEY", "devkey")
LIVEKIT_API_SECRET = os.getenv("LIVEKIT_API_SECRET", "secret")

app = FastAPI()
templates = Jinja2Templates(directory="web/templates")

@app.get("/token", response_class=PlainTextResponse)
def get_token(room: str = Query(..., description="Room to join")):
    now = int(time.time())
    payload = {
        "iss": LIVEKIT_API_KEY,
        "sub": f"browser-{now}",
        "iat": now,
        "exp": now + 3600,
        "video": {"roomJoin": True, "room": room},
        "audio": {"roomJoin": True, "room": room},
    }
    token = jwt.encode(payload, LIVEKIT_API_SECRET, algorithm="HS256")
    return token

@app.get("/", response_class=HTMLResponse)
def index(request: Request):
    default_room = os.getenv("ROOM", "")
    return templates.TemplateResponse(
        "index.html",
        {"request": request,
         "livekit_url": LIVEKIT_URL,
         "default_room": default_room},
    )
