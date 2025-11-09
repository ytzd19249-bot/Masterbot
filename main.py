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

    # ⚙️ payload corregido según API Render 2025
    payload = {
        "service": {
            "ownerId": RENDER_OWNER_ID,
            "type": "web_service",
            "name": nombre,
            "plan": "free",
            "repo": repo_url,
            "branch": "main",
            "env": "python",
            "region": "oregon",
            "buildCommand": "pip install -r requirements.txt",
            "startCommand": "python main.py",
            "autoDeploy": True
        }
    }

    try:
        r = requests.post(
            "https://api.render.com/v1/services",
            headers=headers,
            data=json.dumps(payload)
        )
        return {"status": r.status_code, "response": r.json()}
    except Exception as e:
        return {"error": str(e)}
