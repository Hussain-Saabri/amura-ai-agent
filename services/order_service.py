import logging
from typing import Dict, Any
from schemas.order import UnifiedOrderRequest
import db

import json

logger = logging.getLogger("uvicorn.info")

def parse_items_node(node):
    items = []
    if not node:
        return items
        
    if isinstance(node, str):
        try:
            node = json.loads(node)
        except Exception:
            return items
            
    if isinstance(node, list):
        for sub in node:
            items.extend(parse_items_node(sub))
    elif isinstance(node, dict):
        if "items" in node:
            items.extend(parse_items_node(node["items"]))
        elif "order_payload" in node:
            items.extend(parse_items_node(node["order_payload"]))
        elif "payload" in node:
            items.extend(parse_items_node(node["payload"]))
        elif "medicine_name" in node:
            med_val = node.get("medicine_name")
            if isinstance(med_val, str) and med_val.strip().startswith(("{", "[")):
                items.extend(parse_items_node(med_val))
            else:
                items.append(node)
    return items

def place_order(req: UnifiedOrderRequest) -> Dict[str, Any]:
    result = db.place_bulk_order(req)
    return {"status": "success", "message": result}


