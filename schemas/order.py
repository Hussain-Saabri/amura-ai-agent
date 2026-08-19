from typing import Optional, List, Dict, Any, Union
from pydantic import BaseModel

class UnifiedOrderRequest(BaseModel):
   
    items: Optional[Union[List[Dict[str, Any]], str, Any]] = None
    
    


