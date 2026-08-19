from typing import Optional, Union, List, Dict, Any
from pydantic import BaseModel
from fastapi import APIRouter
import controllers.medicine_controller as medicine_controller

router = APIRouter(prefix="/api", tags=["Medicines"])

class CheckMedicineRequest(BaseModel):
    medicine_name: Optional[Union[str, List[Any], Dict[str, Any]]] = None
    medicines: Optional[Union[List[Any], str]] = None

@router.post("/check-medicine")
def check_medicine_post(req: Optional[CheckMedicineRequest] = None):
    payload = req.model_dump() if req else None
    print(f"🔍 [AI REQUEST - /api/check-medicine]: {payload}", flush=True)
    med_name = None
    if req:
        if req.medicine_name:
            med_name = req.medicine_name
        elif req.medicines:
            med_name = req.medicines
    res = medicine_controller.check_medicine_controller(med_name)
    agent_prompt = res.get("agent_prompt") if isinstance(res, dict) else res
    print(f"📤 [AI RESPONSE agent_prompt]:\n{agent_prompt}\n", flush=True)
    return res

@router.get("/check-medicine")
def check_medicine(medicine_name: Optional[str] = None):
    res = medicine_controller.check_medicine_controller(medicine_name)
    agent_prompt = res.get("agent_prompt") if isinstance(res, dict) else res
    print(f"📤 [AI RESPONSE agent_prompt]:\n{agent_prompt}\n", flush=True)
    return res

@router.get("/medicines")
def api_get_all_medicines():
    return medicine_controller.get_all_medicines_controller()

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


