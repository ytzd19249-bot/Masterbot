from fastapi import FastAPI, Request
import requests, os

app = FastAPI()

RENDER_API_KEY = os.getenv("RENDER_API_KEY")

@app.post("/redeploy")
async def redeploy(request: Request):
    data = await request.json()
    service_id = data.get("service_id")

    headers = {
        "Authorization": f"Bearer {RENDER_API_KEY}",
        "Content-Type": "application/json"
    }

    url = f"https://api.render.com/v1/services/{service_id}/deploys"
    r = requests.post(url, headers=headers)

    return {"status": r.status_code, "response": r.text}
