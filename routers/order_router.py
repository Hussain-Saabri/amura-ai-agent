import logging
from fastapi import APIRouter, Request
from schemas.order import UnifiedOrderRequest
import controllers.order_controller as order_controller
import json

logger = logging.getLogger("uvicorn.info")

router = APIRouter(prefix="/api", tags=["Orders"])


@router.post("/order")
async def api_place_order(request: Request):
    raw_body = await request.body()
    raw_str = raw_body.decode("utf-8")
    logger.info(f"📦 [AI REQUEST - /api/order]: {raw_str}")
    
    data = {}
    if raw_str:
        try:
            parsed = json.loads(raw_str)
            if isinstance(parsed, dict):
                data = parsed
        except Exception:
            pass
            
    req = UnifiedOrderRequest(**data) if data else UnifiedOrderRequest()
    return order_controller.place_order_controller(req)


