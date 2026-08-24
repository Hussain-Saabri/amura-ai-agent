import logging
from typing import Optional
from fastapi import APIRouter, Query, Request
import controllers.medicine_controller as medicine_controller

logger = logging.getLogger("uvicorn.info")

router = APIRouter(prefix="/api", tags=["Medicines"])

@router.get(
    "/check-medicine",
    summary="Check Medicine Availability / Search Catalogue",
    description="Check stock, price, substitutes, and variants for a medicine."
)

async def check_medicine(
    request: Request,
    medicine_name: str | None = Query(
        None,
        description="Name of the medicine to check (e.g. 'soframycin', 'calpol 500', 'razo plus').",
        examples="soframycin"
    )
):  
    logger.info(f"medicine_name in router:-{medicine_name}")
    
    
    if not medicine_name:
        try:
            raw_body = await request.body()
            
            
            if raw_body:
                import json
                data = json.loads(raw_body.decode("utf-8"))
               
                if isinstance(data, dict):
                    
                    medicine_name = data.get("medicine_name")
                    if medicine_name == "":
                        return {"error": "medicine name is required"}            
        except Exception:
            pass

    logger.info(f"[AI REQUEST - /api/check-medicine]: medicine_name='{medicine_name}'")
    res = medicine_controller.check_medicine_controller(medicine_name)
    agent_prompt = res.get("agent_prompt") if isinstance(res, dict) else res
    logger.info(f"📤 [AI RESPONSE agent_prompt]:\n{agent_prompt}\n")
    return res


@router.post("/save-stt-alias", summary="Save Learned STT Alias")
async def save_stt_alias_endpoint(request: Request):
    import db, json
    stt_m = ""
    corr_m = ""
    try:
        raw_body = await request.body()
        if raw_body:
            data = json.loads(raw_body.decode("utf-8"))
            if isinstance(data, dict):
                clean_data = {str(k).strip(): str(v).strip() for k, v in data.items()}
                stt_m = clean_data.get("stt_mishearing", "")
                corr_m = clean_data.get("correct_medicine", "")
                if stt_m.lower().startswith("stt_mishearing:"):
                    stt_m = stt_m[len("stt_mishearing:"):].strip()
                if corr_m.lower().startswith("correct_medicine:"):
                    corr_m = corr_m[len("correct_medicine:"):].strip()
    except Exception as e:
        logger.error(f"Error parsing save-stt-alias payload: {e}")

    success = db.save_learned_stt_alias(stt_m, corr_m)
    return {"status": "success" if success else "failed", "stt_mishearing": stt_m, "correct_medicine": corr_m}
