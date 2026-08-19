from typing import Dict, Any
from schemas.order import UnifiedOrderRequest
import db

import json

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
    try:
        from services.medicine_service import LAST_DISAMBIGUATION_STATE
        parsed_items = parse_items_node(req)
        for item in parsed_items:
            if isinstance(item, dict):
                m_name = item.get("medicine_name") or item.get("product_name")
                if m_name:
                    med_clean = m_name.strip().lower()
                    if med_clean in LAST_DISAMBIGUATION_STATE:
                        stt_wrong_word = LAST_DISAMBIGUATION_STATE.pop(med_clean)
                        db.save_learned_stt_alias(stt_wrong_word, m_name)
    except Exception as e:
        print(f"Note on order alias auto-learn: {e}", flush=True)
        
    result = db.place_bulk_order(req)
    return {"status": "success", "message": result}

