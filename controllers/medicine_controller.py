from typing import Optional, Dict, Any, Union, List
import services.medicine_service as medicine_service

def check_medicine_controller(medicine_name: Optional[Union[str, List[Any], Dict[str, Any]]] = None) -> Dict[str, Any]:
    """Handle medicine stock check request."""
    return medicine_service.check_medicine_stock(medicine_name)
