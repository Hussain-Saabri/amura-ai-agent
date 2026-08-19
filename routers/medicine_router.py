from typing import Optional
from pydantic import BaseModel
from fastapi import APIRouter
import controllers.medicine_controller as medicine_controller

from fastapi import APIRouter, Query

router = APIRouter(prefix="/api", tags=["Medicines"])

@router.get(
    "/check-medicine",
    summary="Check Medicine Availability / Search Catalogue",
    description="Check stock, price, substitutes, and variants for a medicine. Pass `medicine_name` query parameter (e.g. 'soframycin', 'calpol 500'). Leave blank to fetch catalogue."
)
def check_medicine(
    medicine_name: Optional[str] = Query(
        None,
        description="Name of the medicine to check (e.g. 'soframycin', 'calpol 500', 'razo plus'). Leave empty for catalogue prompt.",
        example="soframycin"
    )
):
    print(f"🔍 [AI REQUEST - GET /api/check-medicine]: medicine_name='{medicine_name}'", flush=True)
    res = medicine_controller.check_medicine_controller(medicine_name)
    agent_prompt = res.get("agent_prompt") if isinstance(res, dict) else res
    print(f"📤 [AI RESPONSE agent_prompt]:\n{agent_prompt}\n", flush=True)
    return res

from fastapi import Request

@router.post("/save-stt-alias")
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
        print(f"Error parsing save-stt-alias payload: {e}", flush=True)

    success = db.save_learned_stt_alias(stt_m, corr_m)
    return {"status": "success" if success else "failed", "stt_mishearing": stt_m, "correct_medicine": corr_m}


