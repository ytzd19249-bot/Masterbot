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
        "plan": "free",
        "autoDeploy": True,
        "serviceDetails": {
            "type": "web_service",
            "env": "python",
            "region": "oregon",
            "branch": "main",
            "repo": repo_url,
            "buildCommand": "pip install -r requirements.txt",
            "startCommand": "python main.py",
            "envVars": [
                {
                    "key": "RENDER_API_KEY",
                    "value": RENDER_API_KEY
                },
                {
                    "key": "RENDER_OWNER_ID",
                    "value": RENDER_OWNER_ID
                }
            ]
        }
    }

    try:
        response = requests.post(
            "https://api.render.com/v1/services",
            headers=headers,
            json=payload
        )

        return {
            "status": response.status_code,
            "response": response.json()
        }

    except Exception as e:
        return {"error": str(e)}
