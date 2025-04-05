import uvicorn
from fastapi import FastAPI

from app.conf.app import settings
from app.routers import system_router


# TODO: setup logging config
app = FastAPI(
    title="System Info API",
    description="API for retrieving system information",
    docs_url="/api/docs/" if settings.swagger_enabled else None,
    # redoc_url="/api/redoc/" if settings.swagger_enabled else None,
)
app.include_router(system_router, prefix="/api")

if __name__ == "__main__":
    uvicorn.run(app, host=settings.app_host, port=settings.app_port)
