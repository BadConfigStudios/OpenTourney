from fastapi import FastAPI

from app.routers import events

app = FastAPI(title="OpenTourney")
app.include_router(events.router)


@app.get("/healthz")
def healthz() -> dict[str, str]:
    return {"status": "ok"}
