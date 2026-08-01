from fastapi import FastAPI

app = FastAPI(title="OpenTourney")


@app.get("/healthz")
def healthz() -> dict[str, str]:
    return {"status": "ok"}
