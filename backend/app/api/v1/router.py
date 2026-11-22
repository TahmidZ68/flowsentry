from fastapi import APIRouter

from app.api.v1 import auth, projects, workspaces

api_v1_router = APIRouter()
api_v1_router.include_router(auth.router)
api_v1_router.include_router(workspaces.router)
api_v1_router.include_router(projects.router)
