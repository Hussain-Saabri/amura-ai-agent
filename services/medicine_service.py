from typing import Optional, Dict, Any, Union, List
import db
import re
from difflib import SequenceMatcher

def get_medicine_catalogue_prompt(data=None) -> Dict[str, str]:
    """Fetch medicine details from DB and format into agent catalog prompt."""
    if data is None:
        data = db.get_all_medicines_details()
        limited_data = data[:10]
        total_matches = len(data)
    else:
        limited_data = data
        total_matches = len(data)
        
    catalog_lines = []
    for m in limited_data:
        p_code = m.get("product_code")
        code_str = f" [Code: {p_code}]" if p_code else ""
        if m.get('substitute'):
            subs = m['substitute']
            if isinstance(subs, list):
                sub_text = ", ".join(subs[:6])
            else:
                sub_text = str(subs)
            catalog_lines.append(f"- {m['medicine_name']}{code_str}: OUT OF STOCK (Substitute available: {sub_text})")
        else:
            catalog_lines.append(f"- {m['medicine_name']}{code_str}: Stock {m['quantity']} {m['package_type']}, Price {m['price']}")
            
    catalog_text = "\n".join(catalog_lines)
    
    note_text = ""
    if data is None and total_matches > 10:
        note_text = (
            f"\n\nNOTE: Found {total_matches} matching variants. Showing top 10 above. "
            "If the exact form or dosage is not listed above, ask the user to specify the exact form (e.g. 500mg Tablet, Ointment, Cream, Syrup, or Drops)."
        )

    full_text = (
        "Medicine catalogue:\n"
        f"{catalog_text}"
        f"{note_text}\n\n"
        "Each entry has medicine name, product_code, stock (with package type), and price. "
        "If a medicine is OUT OF STOCK, ask the user if they want the suggested substitute instead. "
        "DO NOT place an order or add a medicine if the requested quantity exceeds the available stock listed; inform the user of the available stock limit instead. "
        "IMPORTANT: When placing an order, ALWAYS pass 'product_code', 'medicine_name', and 'quantity' (e.g., {'product_code': '1019', 'medicine_name': 'Shelcal 500', 'quantity': 10}). "
        "When asking the user for the quantity, ONLY ask for the specific medicine(s) requested by the user. ALWAYS use the package type listed (e.g., ask 'How many strips?' or 'How many bottles?'). DO NOT ask for quantities of unrelated catalogue items."
    )
    return {"agent_prompt": full_text}


def normalize_dosage(text: str) -> str:
    """Normalize dosage strings and common STT multi-word phonetics."""
    if not text:
        return ""
    text_clean = text.strip()
    text_clean = re.sub(r'\b(can|candy)\s*(?:b|be)?\s*(?:fourth|four|4)\b', 'candiforce', text_clean, flags=re.IGNORECASE)
    normalized = re.sub(r'(\d+)\s+(mg|g|ml|mcg|kg|l)\b', r'\1\2', text_clean, flags=re.IGNORECASE)
    normalized = re.sub(r'\s+', ' ', normalized).strip().lower()
    return normalized

def split_brand_and_dosage(text: str):
    """Separate medicine brand/base name from dosage numbers."""
    if not text:
        return "", set()
    text_clean = normalize_dosage(text)
    dosages = set(re.findall(r'\b\d+(?:\.\d+)?\b', text_clean))
    brand_base = re.sub(r'\b\d+(?:\.\d+)?(?:mg|g|ml|mcg|kg|l)?\b', '', text_clean).strip()
    brand_base = re.sub(r'\b(?:mg|g|ml|mcg|kg|l)\b', '', brand_base)
    brand_base = re.sub(r'\s+', ' ', brand_base).strip()
    return brand_base, dosages

LAST_DISAMBIGUATION_STATE = {}

def get_best_fuzzy_match(term: str, all_data: list):
    """
    Smart High-Confidence Auto-Resolution Engine:
    - Separates brand base name from dosage numbers to avoid false matches on common dosages (e.g. '500').
    - Auto-resolves STT mishearings (e.g. 'Hybriprofen 500' -> 'Ibuprofen 500', 'Poraco 200' -> 'Foracort 200', 'City Rizin' -> 'Cetirizine')
      when brand similarity is >= 0.68 and overall score >= 0.60.
    """
    b_t, d_t = split_brand_and_dosage(term)
    if not b_t and not d_t:
        return None, []

    scored = []
    for m in all_data:
        m_name = m.get("medicine_name", "")
        b_m, d_m = split_brand_and_dosage(m_name)
        
        if b_t and b_m:
            if b_t == b_m:
                brand_score = 1.0
            else:
                seq_score = SequenceMatcher(None, b_t, b_m).ratio()
                seq_collapsed = SequenceMatcher(None, b_t.replace(" ", ""), b_m.replace(" ", "")).ratio()
                best_seq = max(seq_score, seq_collapsed)
                if b_t in b_m or b_m in b_t:
                    len_ratio = min(len(b_t), len(b_m)) / max(len(b_t), len(b_m))
                    sub_score = 0.65 + 0.35 * len_ratio
                    brand_score = max(best_seq, sub_score)
                else:
                    brand_score = best_seq
        else:
            brand_score = 1.0 if (b_t == b_m) else 0.0

        if brand_score < 0.68:
            continue

        if d_t and d_m:
            if d_t == d_m:
                score = brand_score
            else:
                # Different dosage specified (e.g. Dolo 500 vs Dolo 650)
                score = min(brand_score, 0.58)
        else:
            score = brand_score

        if score >= 0.55:
            scored.append((score, m))

    if not scored:
        return None, []

    scored.sort(key=lambda x: x[0], reverse=True)
    top_score, top_item = scored[0]
    
    # High Confidence Auto-Resolution (>= 0.60 score)
    if top_score >= 0.60:
        if len(scored) > 1:
            second_score, second_item = scored[1]
            # Genuine tie between close variants (e.g. Dolo 500 vs Dolo 650)
            if second_score >= 0.60 and (top_score - second_score) < 0.08:
                return None, [m for s, m in scored[:5]]
        
        # Clear #1 winner! Auto-resolve to #1 candidate directly!
        return top_item, []

    # Moderate score candidates -> Return for disambiguation
    return None, [m for s, m in scored[:5]]

def check_medicine_stock(medicine_name: Optional[str] = None) -> Dict[str, Any]:
       
    all_data = db.get_medicine_details(medicine_name)  

 
    if not medicine_name or not isinstance(medicine_name, str) or not medicine_name.strip():
        return {"agent_prompt": "Please specify a valid medicine name."}

    raw_t = medicine_name.strip()

    # Pre-normalize medicine names ONCE for ultra-fast matching (< 0.05s for 100 items)
    exact_map = {}
    for m in all_data:
        m_norm = normalize_dosage(m["medicine_name"])
        m["norm_name"] = m_norm
        exact_map.setdefault(m_norm, []).append(m)

    confirmed_matches = []
    disambiguation_notes = []
    not_found_terms = []
    seen_confirmed = set()

    search_t = raw_t
    norm_search_t = normalize_dosage(search_t)
    
    # O(1) Fast Exact Match
    exact = exact_map.get(norm_search_t, [])
    prefix_variants = [m for m in all_data if m["norm_name"].startswith(norm_search_t + " ")]
    
    if (len(exact) == 0 and prefix_variants) or (len(exact) == 1 and prefix_variants and len(norm_search_t.split()) == 1) or len(exact) > 1:
        all_matched_variants = (exact + prefix_variants) if len(exact) <= 1 else exact
        top_v_str = ", ".join([f"{m['medicine_name']}" + (f" [Code: {m.get('product_code')}]" if m.get('product_code') else "") for m in all_matched_variants[:5]])
        for cand in all_matched_variants[:5]:
            c_name = cand['medicine_name'].strip().lower()
            LAST_DISAMBIGUATION_STATE[c_name] = raw_t.strip().lower()
        disambiguation_notes.append(
            f"For requested medicine '{raw_t}': [{top_v_str}]. "
            f"INSTRUCTION: Multiple variants are available ({top_v_str}). "
            f"Inform the caller that multiple variants/dosages are available for '{raw_t}' and ask them to specify which exact form or dosage they need."
        )

    elif len(exact) == 1:
        m = exact[0]
        if m["medicine_name"] not in seen_confirmed:
            seen_confirmed.add(m["medicine_name"])
            confirmed_matches.append(m)

    else:
        # Smart High-Confidence Fuzzy Auto-Resolution
        best_match, fuzzy_candidates = get_best_fuzzy_match(search_t, all_data)
        if best_match:
            best_name = best_match["medicine_name"].strip()
            if best_name not in seen_confirmed:
                seen_confirmed.add(best_name)
                confirmed_matches.append(best_match)

        elif fuzzy_candidates:
            for cand in fuzzy_candidates[:5]:
                c_name = cand['medicine_name'].strip().lower()
                LAST_DISAMBIGUATION_STATE[c_name] = raw_t.strip().lower()
            top_v_str = ", ".join([f"{m['medicine_name']}" + (f" [Code: {m.get('product_code')}]" if m.get('product_code') else "") for m in fuzzy_candidates[:5]])
            first_v = fuzzy_candidates[0]['medicine_name'].strip()
            first_code = fuzzy_candidates[0].get('product_code', '')
            code_str = f" [Code: {first_code}]" if first_code else ""
            disambiguation_notes.append(
                f"For requested medicine '{raw_t}': [{top_v_str}]. "
                f"INSTRUCTION: Multiple possible matches were found due to possible STT/phonetic spelling differences. "
                f"Treat '{first_v}{code_str}' as the most likely intended medicine and ask the user for confirmation using a natural question such as 'Kya aap {first_v} ki baat kar rahe hain?'. "
                f"Do not mention or list the other possible matches to the user. Wait for the user's response before continuing. "
                f"If the user confirms with 'yes', 'ok', 'haan', or equivalent, YOU MUST call the save_stt_alias tool with stt_mishearing='{raw_t}' and correct_medicine='{first_v}', and accept '{first_v}'{code_str} as the requested medicine. "
                f"After confirmation, continue processing the remaining medicines one by one in their original order. "
                f"Do not ask about or mention any remaining medicine in the same response as the confirmation question."
            )
        else:
            not_found_terms.append(raw_t.strip())

    not_found_text = ""
    if not_found_terms:
        formatted_names = ", ".join([f"'{t}'" for t in not_found_terms])
        not_found_text = (
            f"Requested medicine(s) {formatted_names} is NOT available in our database or inventory. "
            f"Inform the caller politely that {formatted_names} is currently out of stock / not available. "
            f"DO NOT suggest, invent, or offer any alternative medicine names or brand names from memory or general knowledge unless explicit substitutes are provided in the stock response."
        )

    # Case 1: ONLY not found terms (no matches and no disambiguation)
    if not confirmed_matches and not disambiguation_notes and not_found_terms:
        return {"agent_prompt": not_found_text}

    # Case 2: ONLY disambiguation notes (with or without not found)
    if disambiguation_notes and not confirmed_matches:
        notes_text = " ".join(disambiguation_notes)
        if not_found_text:
            notes_text += f"\n\nNOTE: {not_found_text}"
        return {"agent_prompt": notes_text}

    # Case 3: Confirmed matches (with optional disambiguation or not found)
    if confirmed_matches:
        base_resp = get_medicine_catalogue_prompt(confirmed_matches)
        prompt = base_resp["agent_prompt"]
        extra_parts = []
        if disambiguation_notes:
            extra_parts.append("DISAMBIGUATION REQUIRED:\n" + "\n".join(f"- {note}" for note in disambiguation_notes))
        if not_found_text:
            extra_parts.append(f"UNAVAILABLE MEDICINES:\n- {not_found_text}")
            
        if extra_parts:
            notes_block = "\n\n" + "\n\n".join(extra_parts)
            split_idx = prompt.find("\n\nEach entry has medicine name")
            if split_idx != -1:
                final_prompt = prompt[:split_idx] + notes_block + prompt[split_idx:]
            else:
                final_prompt = prompt + notes_block
            return {"agent_prompt": final_prompt}
        return base_resp

    
    return get_medicine_catalogue_prompt([])

