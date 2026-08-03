from fastapi import FastAPI

from app.routers import events, pods

app = FastAPI(title="OpenTourney")
app.include_router(events.router)
app.include_router(pods.router)


@app.get("/healthz")
def healthz() -> dict[str, str]:
    return {"status": "ok"}
