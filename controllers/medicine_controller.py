from typing import Optional, Dict, Any, Union, List
import services.medicine_service as medicine_service

async def check_medicine_controller(medicine_name: Optional[Union[str, List[Any], Dict[str, Any]]] = None) -> Dict[str, Any]:
    """Handle medicine stock check request."""
    return await medicine_service.check_medicine_stock(medicine_name)
