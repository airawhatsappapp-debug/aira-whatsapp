from fastapi import FastAPI

from src.api.routes import admin_router, business_router, health_router, menu_router, order_router, webhook_router
from src.db.database import bootstrap_database


def create_app() -> FastAPI:
    app = FastAPI(title="Aira Beta", version="0.1.0")
    bootstrap_database()
    app.include_router(health_router)
    app.include_router(admin_router)
    app.include_router(webhook_router)
    app.include_router(order_router)
    app.include_router(menu_router)
    app.include_router(business_router)
    return app


app = create_app()
