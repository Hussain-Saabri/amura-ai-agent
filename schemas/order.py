from typing import Optional, List, Dict, Any, Union
from pydantic import BaseModel, Field

class OrderItem(BaseModel):
    product_code: Optional[str] = Field(None, description="Product code of the medicine (e.g. '1019')", example="1019")
    medicine_name: Optional[str] = Field(None, description="Name of the medicine (e.g. 'Calpol 500')", example="Calpol 500")
    quantity: int = Field(1, description="Quantity to order (e.g. 10)", example=10)

class UnifiedOrderRequest(BaseModel):
    items: Optional[List[OrderItem]] = Field(
        None, 
        description="List of order items containing product_code, medicine_name, and quantity"
    )

    model_config = {
        "json_schema_extra": {
            "example": {
                "items": [
                    {
                        "product_code": "1019",
                        "medicine_name": "Shelcal 500",
                        "quantity": 10
                    },
                    {
                        "product_code": "1041",
                        "medicine_name": "Calpol 500",
                        "quantity": 5
                    }
                ]
            }
        }
    }
