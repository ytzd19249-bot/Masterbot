from fastapi import FastAPI, Request
import requests, os, json

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

    # 💥 payload corregido: ownerId en el nivel raíz
    payload = {
        "ownerId": RENDER_OWNER_ID,
        "name": nombre,
        "type": "web_service",
        "plan": "free",
        "autoDeploy": True,
        "serviceDetails": {
            "env": "python",
            "region": "oregon",
            "branch": "main",
            "repo": repo_url,
            "buildCommand": "pip install -r requirements.txt",
            "startCommand": "python main.py"
        }
    }

    r = requests.post(
        "https://api.render.com/v1/services",
        headers=headers,
        data=json.dumps(payload)
    )

    try:
        response_json = r.json()
    except Exception:
        response_json = {"raw": r.text}

    return {"status": r.status_code, "response": response_json}
