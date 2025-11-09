from fastapi import FastAPI, Request
import requests, os

app = FastAPI()

# Claves desde las variables de entorno en Render
RENDER_API_KEY = os.getenv("RENDER_API_KEY")

@app.get("/")
def home():
    return {"message": "Masterbot listo 🚀"}

@app.post("/redeploy")
async def redeploy(request: Request):
    try:
        data = await request.json()
        service_id = data.get("service_id")

        if not service_id:
            return {"error": "Falta el service_id"}

        headers = {
            "Authorization": f"Bearer {RENDER_API_KEY}",
            "Content-Type": "application/json"
        }

        url = f"https://api.render.com/v1/services/{service_id}/deploys"
        r = requests.post(url, headers=headers)

        try:
            response_json = r.json()
        except:
            response_json = {"text": r.text}

        return {
            "status": r.status_code,
            "response": response_json
        }

    except Exception as e:
        return {"error": str(e)}
