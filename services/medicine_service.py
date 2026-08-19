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

PHONETIC_ALIASES = {
    "alcohol 500": "calpol 500",
    "alcohol 500mg": "calpol 500",
    "alcohol": "calpol 500",
    "pant 40": "pan 40",
    "pant 40mg": "pan 40",
    "pantocit": "pantocid 40",
    "pantocid": "pantocid 40",
    "otrvin": "otrivin",
    "doloo": "dolo 650",
    "crocin 500": "crocin 500mg",
    "can b fourth 200": "candiforce 200",
    "can b fourth": "candiforce 200",
    "candy 4 200": "candiforce 200",
    "candy 4": "candiforce 200",
    "candy force 200": "candiforce 200",
    "candy force": "candiforce 200",
    "condiforce 200": "candiforce 200",
    "condiforce": "candiforce 200",
    "candiforce": "candiforce 200",
    "city rizin 10 mg": "cetirizine 10mg",
    "city rizin 10mg": "cetirizine 10mg",
    "city rizin": "cetirizine 10mg",
    "citirizine 10 mg": "cetirizine 10mg",
    "citirizine 10mg": "cetirizine 10mg",
    "citirizine": "cetirizine 10mg",
    "reso plus": "razo plus"
}

LAST_DISAMBIGUATION_STATE = {}

def get_disambiguation_prompt(term: str, matches: list) -> Dict[str, str]:
    """Format an ultra-low token disambiguation prompt when multiple medicine variants match."""
    top_matches = matches[:5]
    variants = []
    for m in top_matches:
        pkg = m.get("package_type")
        name = m.get("medicine_name")
        p_code = m.get("product_code")
        code_str = f" [Code: {p_code}]" if p_code else ""
        if pkg:
            variants.append(f"{name}{code_str} ({pkg})")
        else:
            variants.append(f"{name}{code_str}")
            
    variants_str = ", ".join(variants)
    examples_str = f"such as {variants[0]}" if variants else ""
    if len(variants) > 1:
        examples_str += f" or {variants[1]}"
        
    prompt = (
        f" '{term}': {variants_str}. "
        f"Ask the caller specifically which variant or form they need ({examples_str})."
    )
    return {"agent_prompt": prompt}

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

def check_medicine_stock(medicine_name: Optional[Union[str, List[Any], Dict[str, Any]]] = None) -> Dict[str, Any]:
    """Check stock for specific medicine(s) or return full catalogue prompt if no name is provided."""
    all_data = db.get_all_medicines_details()
    if not medicine_name:
        return get_medicine_catalogue_prompt(all_data)
        
    def extract_terms(val):
        terms = []
        if not val:
            return terms
        if isinstance(val, str):
            val_str = val.strip()
            if val_str.startswith("[") or val_str.startswith("{"):
                import json, ast
                try:
                    parsed = json.loads(val_str)
                    return extract_terms(parsed)
                except Exception:
                    try:
                        parsed = ast.literal_eval(val_str)
                        return extract_terms(parsed)
                    except Exception:
                        pass
            terms.extend([s.strip().strip("'\"[]").lower() for s in val_str.split(",") if s.strip()])
        elif isinstance(val, list):
            for item in val:
                terms.extend(extract_terms(item))
        elif isinstance(val, dict):
            for k in ["medicine_name", "medicines", "medicine", "name"]:
                if val.get(k):
                    terms.extend(extract_terms(val[k]))
        return terms

    raw_terms = extract_terms(medicine_name)

    if not raw_terms or any(t in ["all", "every", "full", "catalogue", "catalog", "everything"] for t in raw_terms):
        return get_medicine_catalogue_prompt(all_data)

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

    learned_aliases = db.get_learned_stt_aliases()
    combined_aliases = {**PHONETIC_ALIASES, **learned_aliases}

    for raw_t in raw_terms:
        raw_clean = raw_t.strip().lower()
        if raw_clean in LAST_DISAMBIGUATION_STATE:
            stt_wrong_word = LAST_DISAMBIGUATION_STATE.pop(raw_clean)
            db.save_learned_stt_alias(stt_wrong_word, raw_t.strip())

        search_t = combined_aliases.get(raw_clean, raw_t)
        norm_search_t = normalize_dosage(search_t)
        
        # O(1) Fast Exact Match
        exact = exact_map.get(norm_search_t, [])
        prefix_variants = [m for m in all_data if m["norm_name"].startswith(norm_search_t + " ")]
        
        if len(exact) == 1:
            if prefix_variants and len(norm_search_t.split()) == 1:
                all_matched_variants = exact + prefix_variants
                top_v = [f"{m['medicine_name']}" + (f" ({m.get('package_type')})" if m.get('package_type') else "") + (f" [Code: {m.get('product_code')}]" if m.get('product_code') else "") for m in all_matched_variants[:5]]
                first_v = top_v[0]
                for cand in all_matched_variants[:5]:
                    c_name = cand['medicine_name'].strip().lower()
                    LAST_DISAMBIGUATION_STATE[c_name] = raw_t.strip().lower()
                second_v = top_v[1] if len(top_v) > 1 else ""
                disambiguation_notes.append(
                    f"For requested medicine '{raw_t}': : [{', '.join(top_v)}]. "
                    f"Ask caller to confirm '{first_v}'."
                )
            else:
                m = exact[0]
                if m["medicine_name"] not in seen_confirmed:
                    seen_confirmed.add(m["medicine_name"])
                    confirmed_matches.append(m)
            continue
        elif len(exact) > 1:
            top_v = [f"{m['medicine_name']}" + (f" ({m.get('package_type')})" if m.get('package_type') else "") + (f" [Code: {m.get('product_code')}]" if m.get('product_code') else "") for m in exact[:5]]
            first_v = top_v[0]
            for cand in exact[:5]:
                c_name = cand['medicine_name'].strip().lower()
                LAST_DISAMBIGUATION_STATE[c_name] = raw_t.strip().lower()
            second_v = top_v[1] if len(top_v) > 1 else ""
            disambiguation_notes.append(
                f"For requested medicine '{raw_t}': : [{', '.join(top_v)}]. "
                f"INSTRUCTION: If there are muliple variants found for partcular medcine then get confirmation from the user if ha for  '{first_v}' and if person says ok/yes/ then same quation needs to ask for the remaining medicines.?'. "
            )
            continue

        # Smart High-Confidence Fuzzy Auto-Resolution
        best_match, fuzzy_candidates = get_best_fuzzy_match(search_t, all_data)
        if best_match:
            best_name = best_match["medicine_name"].strip()
            if best_name not in seen_confirmed:
                seen_confirmed.add(best_name)
                confirmed_matches.append(best_match)
                # Auto-Save Fuzzy STT Mishearing to DB Table!
                if raw_t.strip().lower() != best_name.lower():
                    db.save_learned_stt_alias(raw_t.strip(), best_name)
        elif fuzzy_candidates:
            for cand in fuzzy_candidates[:5]:
                c_name = cand['medicine_name'].strip().lower()
                LAST_DISAMBIGUATION_STATE[c_name] = raw_t.strip().lower()
            variants_summary = ", ".join([f"{m['medicine_name']}" + (f" ({m.get('package_type')})" if m.get('package_type') else "") for m in fuzzy_candidates[:5]])
            top_v_str = ", ".join([f"{m['medicine_name']}" + (f" ({m.get('package_type')})" if m.get('package_type') else "") + (f" [Code: {m.get('product_code')}]" if m.get('product_code') else "") for m in fuzzy_candidates[:5]])
            first_v = fuzzy_candidates[0]['medicine_name'].strip()
            first_code = fuzzy_candidates[0].get('product_code', '')
            code_str = f" [Code: {first_code}]" if first_code else ""
            disambiguation_notes.append(
                f"For requested medicine '{raw_t}': Available variants are [{top_v_str}]. "
                f"INSTRUCTION: Inform the caller that multiple variants are available for '{raw_t}' (such as {variants_summary}), "
                f"and ask them which specific variant, dosage, or package type they need (e.g., 'Aapko Soframycin ka kaunsa variant chahiye?'). "
                f"Wait for the caller to specify their choice before confirming the item."
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

    # Default fallback: full catalogue prompt
    return get_medicine_catalogue_prompt([])

