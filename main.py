from fastapi import FastAPI, Request
import requests, os

app = FastAPI()

RENDER_API_KEY = os.getenv("RENDER_API_KEY")
RENDER_OWNER_ID = os.getenv("RENDER_OWNER_ID")

@app.post("/crear_bot")
async def crear_bot(request: Request):
    data = await request.json()
    nombre = data["nombre"]
    repo_url = data["repo_url"]

    headers = {
        "Authorization": f"Bearer {RENDER_API_KEY}",
        "Content-Type": "application/json"
    }

    # JSON plano, sin anidar nada raro
    payload = {
        "ownerId": RENDER_OWNER_ID,
        "name": nombre,
        "type": "web_service",
        "plan": "free",
        "serviceDetails": {
            "env": "python",
            "region": "oregon",
            "branch": "main",
            "repo": repo_url,
            "buildCommand": "pip install -r requirements.txt",
            "startCommand": "python main.py"
        },
        "autoDeploy": True
    }

    r = requests.post(
        "https://api.render.com/v1/services",
        headers=headers,
        json=payload      # 👈 usa el parámetro json correcto
    )

    return {
        "status": r.status_code,
        "text": r.text
    }
