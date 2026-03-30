from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import inspect, text

from app.api.router import api_router
from app.core.config import settings
from app.db.session import engine
from app.models.quant_strategy_config import QuantStrategyConfig

app = FastAPI(title=settings.app_name)

origins = ["*"] if settings.cors_allow_origins.strip() == "*" else [
    item.strip() for item in settings.cors_allow_origins.split(",") if item.strip()
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(api_router, prefix=settings.api_prefix)


@app.on_event("startup")
def ensure_runtime_tables() -> None:
    QuantStrategyConfig.__table__.create(bind=engine, checkfirst=True)
    inspector = inspect(engine)
    existing_columns = {column["name"] for column in inspector.get_columns(QuantStrategyConfig.__tablename__)}
    alter_statements: list[str] = []
    if "notes" not in existing_columns:
        alter_statements.append(
            f"ALTER TABLE `{QuantStrategyConfig.__tablename__}` "
            f"ADD COLUMN `notes` VARCHAR(1000) NOT NULL DEFAULT ''"
        )
    if "blue_filter_groups" not in existing_columns:
        alter_statements.append(
            f"ALTER TABLE `{QuantStrategyConfig.__tablename__}` ADD COLUMN `blue_filter_groups` JSON NULL"
        )
    if "red_filter_groups" not in existing_columns:
        alter_statements.append(
            f"ALTER TABLE `{QuantStrategyConfig.__tablename__}` ADD COLUMN `red_filter_groups` JSON NULL"
        )
    if alter_statements:
        with engine.begin() as connection:
            for statement in alter_statements:
                connection.execute(text(statement))


@app.get("/health", tags=["system"])
def health() -> dict:
    return {"status": "ok", "env": settings.app_env}
