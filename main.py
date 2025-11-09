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
        "serviceDetails": {
            "type": "web_service",
            "env": "python",
            "region": "oregon",
            "buildCommand": "pip install -r requirements.txt",
            "startCommand": "python main.py",
            "repo": repo_url,
            "branch": "main"
        },
        "autoDeploy": True,
        "name": nombre,
        "plan": "free",
        "ownerId": RENDER_OWNER_ID
    }

    r = requests.post("https://api.render.com/v1/services", headers=headers, json=payload)
    try:
        return {"status": r.status_code, "response": r.json()}
    except:
        return {"status": r.status_code, "raw_response": r.text}
