from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.auth.jwks import build_jwks_provider
from app.config import get_settings
from app.routers import entries, events, pod_roles, pods


@asynccontextmanager
async def lifespan(app: FastAPI):
    resolve_settings = app.dependency_overrides.get(get_settings, get_settings)
    settings = resolve_settings()
    build_jwks_provider(settings)
    yield


app = FastAPI(title="OpenTourney", lifespan=lifespan)
app.include_router(events.router)
app.include_router(pods.router)
app.include_router(entries.router)
app.include_router(pod_roles.router)


@app.get("/healthz")
def healthz() -> dict[str, str]:
    return {"status": "ok"}
