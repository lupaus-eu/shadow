from fastapi import APIRouter

from app.api.v1.ai_change_sets.router import router as ai_change_sets_router
from app.api.v1.auth.router import router as auth_router
from app.api.v1.customers.router import router as customers_router
from app.api.v1.mcp_oauth.connections_router import router as ai_connections_router
from app.api.v1.notifications.router import router as notifications_router
from app.api.v1.org_states.router import router as org_states_router
from app.api.v1.org_twin_structure.router import router as org_twin_structure_router
from app.api.v1.organisations.router import router as organisations_router
from app.api.v1.predictions.router import router as predictions_router
from app.api.v1.users.router import router as users_router

router = APIRouter(prefix="/api/v1")
router.include_router(auth_router)
router.include_router(customers_router)
router.include_router(users_router)
router.include_router(notifications_router)
router.include_router(organisations_router)
router.include_router(predictions_router)
router.include_router(org_states_router)
router.include_router(org_twin_structure_router)
# ADR-015: registered even with MCP_ENABLED=false, so grants stay revocable
# and staged change sets can still be reviewed, applied or rejected.
router.include_router(ai_connections_router)
router.include_router(ai_change_sets_router)
