from fastapi import FastAPI

from app.routers import entries, events, pod_roles, pods

app = FastAPI(title="OpenTourney")
app.include_router(events.router)
app.include_router(pods.router)
app.include_router(entries.router)
app.include_router(pod_roles.router)


@app.get("/healthz")
def healthz() -> dict[str, str]:
    return {"status": "ok"}
