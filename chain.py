from __future__ import annotations
 
import json
import os
import re
from pathlib import Path
from typing import Any
 
import requests
from dotenv import load_dotenv
 
from barcode_detector import extract_text
 
load_dotenv()
 
# ----------------------------------------------------------------------------
# Config
# ----------------------------------------------------------------------------
 
# Check console.anthropic.com for current model names before submitting.
MODEL = os.getenv("ANTHROPIC_MODEL", "claude-sonnet-5")
 
PINECONE_API_KEY = os.getenv("PINECONE_API_KEY", "").strip()
PINECONE_PRODUCT_INDEX = os.getenv("PINECONE_PRODUCT_INDEX", "ingrid-beverages")
 
OPENFOODFACTS_API_URL = "https://world.openfoodfacts.org/api/v2/product/{code}.json"
 
BANNED_PHRASES = [
    "cures", "will prevent", "treats your", "safe for you",
    "you should stop eating", "diagnos", "prescrib",
]
 
# First-draft rubric. Confirm with the team and write the final version into the report.
# Additive codes are lowercase E-numbers without punctuation, e.g. "e171".
AVOID_ADDITIVES = {"e171", "e250", "e251", "e320", "e321", "e924"}
CARE_ADDITIVES = {"e211", "e621", "e102", "e110", "e124", "e951", "e950"}
AVOID_NUTRISCORE = {"e", "f"}       # some sources use e/f, others only a-e; guard for both
CARE_NUTRISCORE = {"c", "d"}
AVOID_NOVA_GROUP = 5                 # rarely present; 4 is "ultra-processed", not automatic avoid
CARE_NOVA_GROUP = 4
 
 
# ----------------------------------------------------------------------------
# Step 1 — barcode in, barcode out (already solved by barcode_detector.py)
# ----------------------------------------------------------------------------
 
def read_barcode(source: str) -> str:
    """Accept either a raw barcode string or a path to a photo containing one."""
    if not source:
        return ""
    candidate = str(source).strip()
    try:
        if Path(candidate).is_file():
            barcode, _confidence = extract_text(candidate)
            return barcode
    except OSError:
        pass
    return candidate
 
 
# ----------------------------------------------------------------------------
# Step 2 — product lookup: Pinecone first, OpenFoodFacts as a public fallback
# ----------------------------------------------------------------------------
 
def lookup_pinecone_barcode(barcode: str) -> dict[str, Any] | None:
    """Fetch a product record from the team's Pinecone index by exact barcode ID.
 
    STUB until PINECONE_API_KEY / PINECONE_PRODUCT_INDEX are set and the real
    ingest script confirms field names. Returns None (falls through to
    OpenFoodFacts) whenever Pinecone isn't configured or the barcode isn't found.
    """
    code = str(barcode).strip()
    if not re.fullmatch(r"\d{8,14}", code):
        return None
 
    if not PINECONE_API_KEY:
        return None
 
    try:
        from pinecone import Pinecone  # imported lazily so the module works without the package
 
        index = Pinecone(api_key=PINECONE_API_KEY).Index(PINECONE_PRODUCT_INDEX)
        vector = index.fetch(ids=[code]).vectors.get(code)
    except Exception as exc:
        print(f"[pinecone] lookup failed ({exc}), falling back to OpenFoodFacts")
        return None
 
    if not vector:
        return None
 
    # Confirmed against the real ingest_beverages_json_pinecone.py: id = barcode,
    # metadata carries these exact field names. nutrient_levels is never stored;
    # raw per-100g nutrition values are embedded inside the "text" field instead,
    # so we parse them out separately for optional future use in the rubric.
    metadata = dict(vector.metadata or {})
    return {
        "product_name": _dedupe_semicolon_field(metadata.get("product_name")),
        "ingredients_text": metadata.get("ingredients_text", ""),
        "ingredients_tags": metadata.get("ingredients_tags", ""),
        "nutriscore_grade": metadata.get("nutriscore_grade"),
        "nova_group": _safe_int(metadata.get("nova_group")),
        "nutrition": _extract_nutrition_from_text(metadata.get("text", "")),
        "source": f"Pinecone: {PINECONE_PRODUCT_INDEX}",
    }
 
 
def _dedupe_semicolon_field(value: str | None) -> str | None:
    """Collapse repeated identical segments, e.g. 'Coke 20z; Coke 20z' -> 'Coke 20z'.
 
    Seen in real ingest data — some OpenFoodFacts fields get the same value
    concatenated twice (likely a locale-variant duplicate at source).
    """
    if not value:
        return value
    segments = [s.strip() for s in str(value).split(";")]
    deduped = list(dict.fromkeys(s for s in segments if s))
    return "; ".join(deduped) if deduped else value
 
 
def _safe_int(value: Any) -> int | None:
    """Pinecone/OpenFoodFacts sometimes return numeric fields as strings (e.g. '4').
 
    Without this, apply_rubric's `nova_group == 4` comparisons silently fail
    against a string and never match, even when the data is correct.
    """
    try:
        return int(value)
    except (TypeError, ValueError):
        return None
 
 
def _extract_nutrition_from_text(embedded_text: str) -> dict[str, dict[str, Any]]:
    """Pull the per-100g nutrition rows back out of the ingest script's embedded text blob.
 
    ingest_beverages_json_pinecone.py stores nutrition as a JSON list inside the
    "text" metadata field (e.g. 'Nutrition per 100g: [{"name": "sugars", "100g": 10.5, ...}]'),
    not as its own top-level field. Not used by the rubric yet — available if you
    want to tighten AVOID/CARE thresholds using real gram values later.
    """
    match = re.search(r"Nutrition per 100g: (\[.*?\])\nNutri-Score:", embedded_text, flags=re.DOTALL)
    if not match:
        return {}
    try:
        rows = json.loads(match.group(1))
    except json.JSONDecodeError:
        return {}
    return {
        row["name"]: {"value": row["100g"], "unit": row.get("unit", "")}
        for row in rows
        if isinstance(row, dict) and row.get("name") and row.get("100g") is not None
    }
 
 
def lookup_openfoodfacts_barcode(barcode: str) -> dict[str, Any] | None:
    """Fetch a product record live from the public OpenFoodFacts API.
 
    Fully working today, no credentials required. Useful both as a fallback
    for barcodes missing from the 20K-product Pinecone sample, and as a way
    to test this whole pipeline before Pinecone access exists.
    """
    code = str(barcode).strip()
    if not re.fullmatch(r"\d{8,14}", code):
        return None
 
    try:
        response = requests.get(
            OPENFOODFACTS_API_URL.format(code=code),
            timeout=10,
            headers={"User-Agent": "Ingrid-Ingredient-Checker/1.0 (student project)"},
        )
        response.raise_for_status()
        payload = response.json()
    except (requests.RequestException, ValueError) as exc:
        print(f"[openfoodfacts] lookup failed ({exc})")
        return None
 
    if payload.get("status") != 1:
        return None
 
    product = payload.get("product") or {}
    nutriments = product.get("nutriments") or {}
    nutrition = {}
    for key, value in nutriments.items():
        if not key.endswith("_100g") or value is None:
            continue
        name = key[: -len("_100g")]
        nutrition[name] = {"value": value, "unit": nutriments.get(f"{name}_unit", "")}
 
    return {
        "product_name": _dedupe_semicolon_field(product.get("product_name")),
        "ingredients_text": product.get("ingredients_text") or product.get("ingredients_text_en", ""),
        "ingredients_tags": ";".join(product.get("ingredients_tags") or []),
        "nutriscore_grade": product.get("nutriscore_grade"),
        "nova_group": _safe_int(product.get("nova_group")),
        "nutrition": nutrition,
        "source": "OpenFoodFacts API",
    }
 
 
def lookup_product(barcode: str) -> dict[str, Any] | None:
    """Try Pinecone first (the team's curated 20K sample), then the live API."""
    return lookup_pinecone_barcode(barcode) or lookup_openfoodfacts_barcode(barcode)
 
 
# ----------------------------------------------------------------------------
# Ingredient text cleanup (cosmetic — feeds the UI's ingredient list, not the verdict)
# ----------------------------------------------------------------------------
 
def parse_ingredients(ingredients_text: str) -> list[str]:
    cleaned = str(ingredients_text or "").lower()
    if "ingredients" in cleaned:
        cleaned = cleaned.split("ingredients", 1)[1].lstrip(": ")
    cleaned = cleaned.replace("(", ",").replace(")", ",")
    cleaned = re.sub(r"[;/\n]+", ",", cleaned)
    ingredients = []
    for part in cleaned.split(","):
        ingredient = re.sub(r"\s+", " ", part).strip(" .,:()")
        if ingredient and len(ingredient) > 1:
            ingredients.append(ingredient)
    return list(dict.fromkeys(ingredients))
 
 
def extract_additive_codes(ingredients_tags: str) -> list[str]:
    """Pull plain E-number codes (e.g. 'e171') out of a semicolon-joined tag string."""
    tags = [t.strip().lower() for t in str(ingredients_tags or "").split(";") if t.strip()]
    codes = []
    for tag in tags:
        match = re.search(r"e\d{3,4}[a-z]?", tag)
        if match:
            codes.append(match.group(0))
    return list(dict.fromkeys(codes))
 
 
# ----------------------------------------------------------------------------
# Step 3 — the verdict is a FIXED RULE, not an LLM guess (this is what keeps it
# grounded / groundable — see the guide's hard rule: "the LLM explains the
# rating, it never assigns it")
# ----------------------------------------------------------------------------
 
def apply_rubric(nutriscore_grade: str | None, nova_group: int | None, additive_codes: list[str]) -> tuple[str, list[str]]:
    """Return (verdict, reasons). Deterministic — same inputs always give the same verdict."""
    reasons = []
    grade = (nutriscore_grade or "").strip().lower()
    avoid_hits = [c for c in additive_codes if c in AVOID_ADDITIVES]
    care_hits = [c for c in additive_codes if c in CARE_ADDITIVES]
 
    if avoid_hits:
        reasons.append(f"contains additive(s) flagged for avoidance: {', '.join(avoid_hits)}")
    if grade in AVOID_NUTRISCORE:
        reasons.append(f"Nutri-Score {grade.upper()}")
    if nova_group == AVOID_NOVA_GROUP:
        reasons.append(f"NOVA group {nova_group}")
 
    if reasons:
        return "avoid", reasons
 
    if care_hits:
        reasons.append(f"contains additive(s) that warrant moderation: {', '.join(care_hits)}")
    if grade in CARE_NUTRISCORE:
        reasons.append(f"Nutri-Score {grade.upper()}")
    if nova_group == CARE_NOVA_GROUP:
        reasons.append(f"NOVA group {nova_group} (ultra-processed)")
 
    if reasons:
        return "care", reasons
 
    if grade in {"a", "b"}:
        reasons.append(f"Nutri-Score {grade.upper()}")
        return "ok", reasons
 
    return "unknown", ["insufficient data to apply the rubric (no Nutri-Score or NOVA group on file)"]
 
 
# ----------------------------------------------------------------------------
# Step 4 — explanation, grounded in the fixed verdict (Claude)
# ----------------------------------------------------------------------------
 
EXPLAIN_SYSTEM_PROMPT = """You are a food product analyst writing for an ordinary shopper.
 
Hard rules:
- The VERDICT below is fixed. Explain why it was reached; never assign a different one.
- Use ONLY the REASONS and PRODUCT DETAILS given. Do not add facts from your own knowledge.
- Do not say a product is safe or unsafe for any person or condition.
- Do not give medical, dietary, or treatment advice.
- Keep it to three or four sentences.
"""
 
 
def _build_explain_prompt(product: dict[str, Any], verdict: str, reasons: list[str]) -> str:
    return f"""VERDICT: {verdict}
 
REASONS
{chr(10).join(f"- {r}" for r in reasons)}
 
PRODUCT DETAILS
{json.dumps(
    {
        "name": product.get("product_name"),
        "nutriscore_grade": product.get("nutriscore_grade"),
        "nova_group": product.get("nova_group"),
        "nutrition_per_100g": product.get("nutrition"),
    },
    ensure_ascii=False,
)}
"""
 
 
def generate_explanation(product: dict[str, Any], verdict: str, reasons: list[str]) -> str:
    """Call an LLM via OpenRouter (OpenAI-compatible endpoint) to explain the fixed verdict.
 
    Uses OPENROUTER_API_KEY + OPENROUTER_MODEL from .env. OpenRouter can route to
    Claude models too (e.g. "anthropic/claude-sonnet-4.6") if you want to match the
    guide's stated stack while still using a key you already have funded.
    """
    api_key = os.getenv("OPENROUTER_API_KEY", "").strip()
    if not api_key:
        return "(Explanation unavailable: OPENROUTER_API_KEY not set.)"
 
    model = os.getenv("OPENROUTER_MODEL", "anthropic/claude-sonnet-4.6")
 
    try:
        response = requests.post(
            "https://openrouter.ai/api/v1/chat/completions",
            headers={"Authorization": f"Bearer {api_key}"},
            json={
                "model": model,
                "max_tokens": 300,
                "messages": [
                    {"role": "system", "content": EXPLAIN_SYSTEM_PROMPT},
                    {"role": "user", "content": _build_explain_prompt(product, verdict, reasons)},
                ],
            },
            timeout=30,
        )
        response.raise_for_status()
        return response.json()["choices"][0]["message"]["content"].strip()
    except Exception as exc:
        return f"(Explanation unavailable: {exc})"
 
 
def check_output(text: str) -> list[str]:
    """Flag medical-claim language. Returns list of violations."""
    lowered = text.lower()
    return [phrase for phrase in BANNED_PHRASES if phrase in lowered]
 
 
# ----------------------------------------------------------------------------
# Orchestrator — this is what app.py should call
# ----------------------------------------------------------------------------
 
def analyse_label(source: str, skip_llm: bool = False) -> dict[str, Any]:
    """Full pipeline: barcode or image path -> product-level verdict + explanation.
 
    Returns a dict shaped for a redesigned app.py results view (product-level,
    not per-ingredient). See the chat discussion for the old per-ingredient
    shape this replaces.
    """
    barcode = read_barcode(source)
    product = lookup_product(barcode)
 
    if not product:
        return {
            "barcode": barcode or None,
            "product_name": None,
            "product_verdict": "unknown",
            "reasons": [],
            "explanation": f"Barcode {barcode or 'not detected'} was not found in Pinecone or OpenFoodFacts.",
            "nutriscore_grade": None,
            "nova_group": None,
            "flagged_additives": [],
            "ingredients": [],
            "violations": [],
            "source": None,
        }
 
    additive_codes = extract_additive_codes(product.get("ingredients_tags", ""))
    verdict, reasons = apply_rubric(product.get("nutriscore_grade"), product.get("nova_group"), additive_codes)
    ingredients = parse_ingredients(product.get("ingredients_text", ""))
 
    result = {
        "barcode": barcode,
        "product_name": product.get("product_name"),
        "product_verdict": verdict,
        "reasons": reasons,
        "explanation": None,
        "nutriscore_grade": product.get("nutriscore_grade"),
        "nova_group": product.get("nova_group"),
        "flagged_additives": additive_codes,
        "ingredients": ingredients,
        "nutrition": product.get("nutrition") or {},
        "violations": [],
        "source": product.get("source"),
    }
 
    if skip_llm:
        result["explanation"] = "(LLM explanation skipped)"
        return result
 
    explanation = generate_explanation(product, verdict, reasons)
    violations = check_output(explanation)
    if violations:
        explanation = (
            "The generated explanation was withheld because it contained "
            "language that reads as medical advice. The verdict above is unaffected."
        )
    result["explanation"] = explanation
    result["violations"] = violations
    return result
 
 
if __name__ == "__main__":
    import sys
 
    test_barcode = sys.argv[1] if len(sys.argv) > 1 else "3017620422003"  # Nutella, for a quick smoke test
    print(json.dumps(analyse_label(test_barcode), indent=2, ensure_ascii=False))
 
