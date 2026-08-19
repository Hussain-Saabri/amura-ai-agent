from typing import Dict, Any
from schemas.order import UnifiedOrderRequest
import services.order_service as order_service

def place_order_controller(req: UnifiedOrderRequest) -> Dict[str, Any]:
    return order_service.place_order(req)
