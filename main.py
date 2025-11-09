from fastapi import FastAPI, Request
import requests, os

app = FastAPI()

RENDER_API_KEY = os.getenv("RENDER_API_KEY")
RENDER_OWNER_ID = os.getenv("RENDER_OWNER_ID")

@app.post("/crear_bot")
async def crear_bot(request: Request):
    data = await request.json()
    nombre = data.get("nombre")
    repo_url = data.get("repo_url")

    headers = {
        "Authorization": f"Bearer {RENDER_API_KEY}",
        "Content-Type": "application/json"
    }

    payload = {
        "ownerId": RENDER_OWNER_ID,
        "name": nombre,
        "serviceDetails": {
            "type": "web_service",
            "env": "python",
            "repo": repo_url,
            "branch": "main",
            "buildCommand": "pip install -r requirements.txt",
            "startCommand": "python main.py",
            "autoDeploy": True
        },
        "plan": "free"
    }

    r = requests.post("https://api.render.com/v1/services", headers=headers, json=payload)

    try:
        response_json = r.json()
    except:
        response_json = {"text": r.text}

    return {"status": r.status_code, "response": response_json}
