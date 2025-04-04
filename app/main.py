import uvicorn
from fastapi import FastAPI

from app.conf.app import settings
from app.routers import system_router


# TODO: setup logging config
app = FastAPI(
    title="System Info API",
    description="API for retrieving system information",
    docs_url="/docs/" if settings.swagger_enabled else None,
    redoc_url="/redoc/" if settings.swagger_enabled else None,
)
app.include_router(system_router)

if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)
