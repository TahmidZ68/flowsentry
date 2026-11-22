from fastapi import APIRouter

from app.api.v1 import (
    auth,
    demo,
    executions,
    incidents,
    ingest,
    integrations,
    investigations,
    outcome_monitors,
    overview,
    projects,
    workflows,
    workspaces,
)

api_v1_router = APIRouter()
api_v1_router.include_router(auth.router)
api_v1_router.include_router(demo.router)
api_v1_router.include_router(workspaces.router)
api_v1_router.include_router(projects.router)
api_v1_router.include_router(integrations.router)
api_v1_router.include_router(ingest.router)
api_v1_router.include_router(workflows.router)
api_v1_router.include_router(executions.router)
api_v1_router.include_router(incidents.router)
api_v1_router.include_router(investigations.router)
api_v1_router.include_router(outcome_monitors.router)
api_v1_router.include_router(overview.router)
