from typing import Optional
from fastapi import APIRouter, Request, Body
from schemas.order import UnifiedOrderRequest
import controllers.order_controller as order_controller
import json

router = APIRouter(prefix="/api", tags=["Orders"])

@router.post(
    "/order",
    summary="Place Order / Bulk Order",
    description="Place an order for one or multiple medicines. Pass a list of items with product_code, medicine_name, and quantity."
)
async def api_place_order(
    request: Request,
    payload: Optional[UnifiedOrderRequest] = Body(
        None,
        description="Order payload containing list of items to order"
    )
):
    raw_body = await request.body()
    raw_str = raw_body.decode("utf-8")
    print(f"📦 [AI REQUEST - /api/order]: {raw_str}", flush=True)
    
    data = {}
    if raw_str:
        try:
            parsed = json.loads(raw_str)
            if isinstance(parsed, dict):
                data = parsed
        except Exception:
            pass
            
    req = payload if payload and payload.items else (UnifiedOrderRequest(**data) if data else UnifiedOrderRequest())
    return order_controller.place_order_controller(req)

