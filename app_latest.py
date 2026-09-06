"""Ingrid — barcode-based food product compliance scanner Streamlit interface."""
from __future__ import annotations

import html
import os
import tempfile
from pathlib import Path
from typing import Any

import streamlit as st
from PIL import Image, UnidentifiedImageError

try:
    from barcode_detector import extract_text
except ImportError:
    def extract_text(path: str) -> tuple[str, float]:
        return ("5449000000996", 1.0)

try:
    from chain import analyse_label
except ImportError:
    def analyse_label(source: str) -> dict[str, Any]:
        return {
            "barcode": source,
            "product_name": "Sample Cola",
            "product_verdict": "avoid",
            "reasons": ["Nutri-Score E", "contains additive(s) flagged for avoidance: e150a"],
            "explanation": "This sample product scores poorly on Nutri-Score and is classified as ultra-processed (NOVA group 4). It contains a caramel colour additive flagged for avoidance.",
            "nutriscore_grade": "e",
            "nova_group": 4,
            "flagged_additives": ["e150a"],
            "ingredients": ["carbonated water", "sugar", "caramel colour", "phosphoric acid", "caffeine"],
            "violations": [],
            "source": "Sample data (chain.py not connected)",
        }

st.set_page_config(page_title="Ingrid — product compliance clarity", page_icon="🔎", layout="wide", initial_sidebar_state="collapsed")

COPY = {
    "en": {
        "lang": "中文", "product": "AI food product compliance scanner",
        "headline": "Scan a barcode. Get a grounded compliance verdict.",
        "subhead": "Ingrid looks up the product, applies a fixed rating rubric, and explains the result — the verdict is never guessed by the AI.",
        "upload_title": "1. Upload or photograph the barcode", "upload_label": "Barcode image",
        "upload_help": "PNG, JPG or JPEG · up to 20 MB · a clear, well-lit photo of the barcode works best",
        "review_title": "2. Review the detected barcode", "barcode_label": "Detected barcode",
        "placeholder": "The detected barcode will appear here. You can also type or correct it manually.",
        "samples": "Try a sample barcode", "sample_coke": "Coca-Cola", "sample_nutella": "Nutella",
        "clear": "Clear", "audit": "Run compliance check", "empty_warning": "Add a barcode before running the check.",
        "scan_running": "Reading the barcode…", "audit_running": "Looking up the product and generating a verdict…",
        "image_error": "This file could not be read as an image. Choose a valid PNG, JPG or JPEG file.",
        "barcode_error": "The barcode could not be read. Try a clearer photo or enter the code manually.",
        "barcode_empty": "No barcode was detected. Try a clearer, closer photo or enter the code manually.",
        "audit_error": "The check could not be completed. Your barcode is still available; please try again.",
        "results": "3. Compliance verdict",
        "overall_safe": "No concerns found", "overall_attention": "Review before deciding",
        "overall_restricted": "Recommended to avoid", "overall_unknown": "Not enough data to assess",
        "safe": "Permitted", "care": "Attention", "avoid": "Avoid", "unknown": "Unknown",
        "why": "Why this verdict", "no_reasons": "No specific rubric rules were triggered.",
        "product_details": "Product details", "ingredients": "Ingredients", "flagged_additives": "Flagged additives",
        "none_flagged": "None flagged", "nutriscore": "Nutri-Score", "nova": "NOVA group",
        "barcode_result": "Barcode", "source": "Source", "summary": "Ingrid summary", "not_found": "not found",
        "awaiting": "Your grounded verdict will appear here after the check.",
        "guardrail_notice": "Part of the generated explanation was withheld because it resembled medical advice.",
        "disclaimer": "Screening support only — status can differ by jurisdiction and product formulation. Verify cited sources before making dietary or purchasing decisions.",
    },
    "zh": {
        "lang": "English", "product": "AI 食品合规扫描器",
        "headline": "扫描条形码，获得有依据的合规结论。",
        "subhead": "Ingrid 会查找产品信息，套用固定评分规则，并对结果做出解释——结论从不由 AI 随意猜测。",
        "upload_title": "1. 上传或拍摄条形码", "upload_label": "条形码图片",
        "upload_help": "支持 PNG、JPG、JPEG · 最大 20 MB · 光线均匀、清晰的条形码照片效果最佳",
        "review_title": "2. 核对识别出的条形码", "barcode_label": "识别出的条形码",
        "placeholder": "识别出的条形码会显示在这里。你也可以手动输入或修正。",
        "samples": "试用示例条形码", "sample_coke": "可口可乐", "sample_nutella": "能多益",
        "clear": "清空", "audit": "开始合规检查", "empty_warning": "请先输入条形码后再开始检查。",
        "scan_running": "正在识别条形码…", "audit_running": "正在查找产品并生成结论…",
        "image_error": "无法读取这张图片，请选择有效的 PNG、JPG 或 JPEG 文件。",
        "barcode_error": "未能识别条形码。请换一张更清晰的照片，或手动输入代码。",
        "barcode_empty": "未检测到条形码。请换一张更清楚、更近的照片，或手动输入代码。",
        "audit_error": "暂时无法完成检查。条形码已保留，请稍后重试。",
        "results": "3. 合规结论",
        "overall_safe": "未发现问题", "overall_attention": "建议核对后再判断",
        "overall_restricted": "建议避免", "overall_unknown": "数据不足，无法评估",
        "safe": "允许", "care": "需要注意", "avoid": "避免", "unknown": "未知",
        "why": "结论依据", "no_reasons": "未触发任何评分规则。",
        "product_details": "产品详情", "ingredients": "配料", "flagged_additives": "被标记的添加剂",
        "none_flagged": "无标记项", "nutriscore": "Nutri-Score 营养评分", "nova": "NOVA 加工分级",
        "barcode_result": "条形码", "source": "数据来源", "summary": "Ingrid 综合说明", "not_found": "未找到",
        "awaiting": "执行检查后，这里会显示有依据的结论。",
        "guardrail_notice": "部分生成的说明因疑似医疗建议内容而被保留。",
        "disclaimer": "本工具仅用于初步筛查；不同司法辖区和产品配方的规定可能不同。做出饮食或购买决定前，请核对所列数据来源。",
    },
}
SAMPLES = {
    "coke": "5449000000996",
    "nutella": "3017620422003",
}


def init_state() -> None:
    for key, value in {"lang": "en", "barcode_text": "", "uploaded_signature": None, "analysis_result": None}.items():
        if key not in st.session_state:
            st.session_state[key] = value


def clear_barcode() -> None:
    st.session_state.barcode_text = ""
    st.session_state.analysis_result = None
    st.session_state.uploaded_signature = None


def set_sample(name: str) -> None:
    st.session_state.barcode_text = SAMPLES[name]
    st.session_state.analysis_result = None


def toggle_language() -> None:
    st.session_state.lang = "zh" if st.session_state.lang == "en" else "en"


def esc(value: Any) -> str:
    return html.escape(str(value if value is not None else ""), quote=True)


VALID_VERDICTS = {"ok", "care", "avoid", "unknown"}


def normalize_result(raw: Any) -> dict[str, Any]:
    """Sanitize chain.py's output before rendering, in case any field is missing or malformed."""
    result = raw if isinstance(raw, dict) else {}
    verdict = result.get("product_verdict")
    return {
        "barcode": result.get("barcode"),
        "product_name": result.get("product_name"),
        "product_verdict": verdict if verdict in VALID_VERDICTS else "unknown",
        "reasons": [str(r) for r in result.get("reasons", [])] if isinstance(result.get("reasons"), list) else [],
        "explanation": str(result.get("explanation") or ""),
        "nutriscore_grade": result.get("nutriscore_grade"),
        "nova_group": result.get("nova_group"),
        "flagged_additives": [str(a) for a in result.get("flagged_additives", [])] if isinstance(result.get("flagged_additives"), list) else [],
        "ingredients": [str(i) for i in result.get("ingredients", [])] if isinstance(result.get("ingredients"), list) else [],
        "violations": result.get("violations") if isinstance(result.get("violations"), list) else [],
        "source": result.get("source"),
    }


def render_css() -> None:
    st.html("""
    <style>
    @import url('https://fonts.googleapis.com/css2?family=IBM+Plex+Mono:wght@400;500&family=Inter:wght@400;500;600;700&family=Manrope:wght@600;700;800&display=swap');
    :root{--canvas:#f7f9fc;--surface:#fff;--ink:#111827;--muted:#667085;--blue:#175cd3;--blue-strong:#004eeb;--border:#d9e0ea;--safe:#15803d;--care:#b45309;--avoid:#c4320a;--unknown:#475467}
    html{scrollbar-color:#98a2b3 #eef2f7;scrollbar-width:thin}*::-webkit-scrollbar{width:10px;height:10px}*::-webkit-scrollbar-track{background:#eef2f7}*::-webkit-scrollbar-thumb{background:#98a2b3;border:2px solid #eef2f7;border-radius:10px}*::-webkit-scrollbar-thumb:hover{background:#667085}
    .stApp{background:radial-gradient(circle at 48% -12%,rgba(23,92,211,.08),transparent 28rem),var(--canvas);color:var(--ink);font-family:Inter,system-ui,sans-serif}header[data-testid='stHeader']{background:transparent}[data-testid='stToolbar'],#MainMenu,footer{display:none!important}.block-container{max-width:1180px;padding-top:1.4rem;padding-bottom:3rem}
    .ingrid-nav{display:flex;align-items:center;gap:14px;min-height:44px;padding-left:4px}.ingrid-mark{color:var(--blue-strong);font:800 1.65rem/1 Manrope,sans-serif;letter-spacing:-.04em}.ingrid-product{color:var(--muted);font-size:.82rem;padding-left:14px;border-left:1px solid var(--border)}
    .hero{padding:2.6rem 0 1.8rem;max-width:900px}.hero h1{margin:0;font:800 clamp(2.15rem,5vw,4.25rem)/1.04 Manrope,sans-serif;letter-spacing:-.055em;text-wrap:balance}.hero p{max-width:760px;margin:1rem 0 0;color:var(--muted);font-size:1rem;line-height:1.65}.section-label{margin:.1rem 0 .7rem;color:var(--ink);font:700 .92rem/1.4 Manrope,sans-serif}.helper{color:var(--muted);font-size:.77rem;margin:.15rem 0 .8rem}
    div[data-testid='stFileUploader']{min-height:180px;display:flex;align-items:center;border:1px dashed #b9c5d6;border-radius:14px;padding:1rem;background:linear-gradient(180deg,#fff,rgba(245,249,255,.9));position:relative;overflow:hidden}div[data-testid='stFileUploader']::after{content:'';position:absolute;left:0;right:0;top:52%;height:1px;background:linear-gradient(90deg,transparent,#3b82f6 20%,#60a5fa 80%,transparent);box-shadow:0 0 14px rgba(59,130,246,.55);opacity:.58;pointer-events:none;animation:scan 4.5s ease-in-out infinite}div[data-testid='stFileUploaderDropzone']{background:transparent;border:0;width:100%}div[data-testid='stFileUploader'] button{border-color:var(--blue)!important;color:var(--blue)!important;background:white!important}
    div[data-testid='stTextInput'] input{border:1px solid var(--border);border-radius:10px;background:#fff;color:var(--ink);font:600 1rem/1.5 'IBM Plex Mono',monospace;padding:.7rem .9rem;box-shadow:0 1px 2px rgba(16,24,40,.03)}div[data-testid='stTextInput'] input:focus{border-color:var(--blue);box-shadow:0 0 0 3px rgba(23,92,211,.17)}
    div[data-testid='stButton'] button{min-height:42px;border-radius:10px;font-weight:650;transition:transform .16s ease,box-shadow .16s ease,border-color .16s ease}div[data-testid='stButton'] button:hover{transform:translateY(-1px);border-color:var(--blue)}div[data-testid='stButton'] button:focus-visible{outline:3px solid rgba(23,92,211,.25);outline-offset:2px}
    div[data-testid='stButton'] button:not([kind='primary']){background:#fff!important;color:var(--ink)!important;border:1px solid var(--border)!important}
    div[data-testid='stButton'] button:not([kind='primary']):hover{color:var(--blue)!important;border-color:var(--blue)!important;background:#fff!important}
    div[data-testid='stButton'] button:not([kind='primary']):disabled{background:#f2f4f7!important;color:#98a2b3!important;border-color:var(--border)!important}
    button[kind='primary']{min-height:50px!important;background:linear-gradient(135deg,var(--blue),var(--blue-strong))!important;border:0!important;color:#fff!important;box-shadow:0 10px 24px rgba(23,92,211,.22)}
    .result-shell{margin-top:2.1rem;border-top:1px solid var(--border);padding-top:1.65rem}.verdict-banner{display:grid;grid-template-columns:minmax(230px,1.35fr) repeat(4,minmax(90px,.48fr));border:1px solid var(--border);border-radius:14px;overflow:hidden;background:#fff;box-shadow:0 8px 26px rgba(30,64,175,.06)}.verdict-lead,.metric{padding:1.15rem 1.25rem}.verdict-lead{display:flex;gap:12px;align-items:center}.verdict-icon{width:38px;height:38px;border-radius:50%;display:grid;place-items:center;font-weight:800;flex-shrink:0}.verdict-title{font:700 1rem/1.35 Manrope,sans-serif}.verdict-note{color:var(--muted);font-size:.76rem;margin-top:3px}.metric{border-left:1px solid #e8edf4}.metric-value{font:700 1.3rem/1 'IBM Plex Mono',monospace}.metric-label{color:var(--muted);font-size:.72rem;margin-top:7px}
    .tone-ok{color:var(--safe);background:#ecfdf3}.tone-care{color:var(--care);background:#fffaeb}.tone-avoid{color:var(--avoid);background:#fff4ed}.tone-unknown{color:var(--unknown);background:#f2f4f7}
    .results-grid{display:grid;grid-template-columns:minmax(0,1.65fr) minmax(260px,.75fr);gap:18px;margin-top:18px;align-items:start}.panel,.summary-panel{border:1px solid var(--border);border-radius:14px;background:#fff;overflow:hidden}.panel-head{padding:1rem 1.15rem;border-bottom:1px solid #e8edf4;font:700 .88rem/1.4 Manrope,sans-serif}.panel-body{padding:1rem 1.15rem}
    .reason-list{margin:0;padding-left:1.2rem;color:#344054;font-size:.85rem;line-height:1.9}
    .detail-row{display:flex;justify-content:space-between;padding:.5rem 0;border-bottom:1px solid #edf1f6;font-size:.85rem}.detail-row:last-child{border-bottom:0}.detail-key{color:var(--muted)}.detail-val{font-weight:650;font-family:'IBM Plex Mono',monospace}
    .chip-row{display:flex;flex-wrap:wrap;gap:6px;margin-top:.4rem}.chip{padding:4px 10px;border-radius:999px;font-size:.72rem;font-weight:650;background:#f2f4f7;color:#344054}
    .summary-copy{padding:1.15rem;color:#344054;font-size:.84rem;line-height:1.7;white-space:pre-wrap}.empty-state{margin-top:2rem;border:1px dashed var(--border);border-radius:14px;padding:1.25rem;color:var(--muted);text-align:center;font-size:.84rem;background:rgba(255,255,255,.55)}.disclaimer{margin-top:2.2rem;padding-top:1.1rem;border-top:1px solid var(--border);color:var(--muted);font-size:.72rem;line-height:1.6}
    .guardrail-note{margin-top:.6rem;padding:.6rem .8rem;border-radius:10px;background:#fff4ed;color:var(--avoid);font-size:.76rem}
    @keyframes scan{0%,100%{transform:translateY(-72px);opacity:.18}50%{transform:translateY(72px);opacity:.72}}@media(max-width:760px){.block-container{padding:1rem 1rem 2.2rem}.ingrid-product{display:none}.hero{padding:1.65rem 0 1.2rem}.hero h1{font-size:2.28rem}.verdict-banner{grid-template-columns:repeat(2,1fr)}.verdict-lead{grid-column:1/-1}.metric:nth-child(2n){border-left:0}.results-grid{grid-template-columns:1fr}}@media(prefers-reduced-motion:reduce){*,*::before,*::after{animation:none!important;transition:none!important;scroll-behavior:auto!important}}
    </style>""")


def process_upload(uploaded: Any, copy: dict[str, str]) -> None:
    if uploaded is None:
        return
    payload = uploaded.getvalue()
    signature = (uploaded.name, len(payload))
    if signature == st.session_state.uploaded_signature:
        return
    try:
        image = Image.open(uploaded)
        image.verify()
    except (UnidentifiedImageError, OSError, ValueError):
        st.error(copy["image_error"], icon=":material/broken_image:")
        return
    temp_path = ""
    try:
        with tempfile.NamedTemporaryFile(suffix=Path(uploaded.name).suffix.lower() or ".jpg", delete=False) as temp_file:
            temp_file.write(payload)
            temp_path = temp_file.name
        with st.spinner(copy["scan_running"]):
            barcode, confidence = extract_text(temp_path)
        detected = str(barcode or "").strip()
        st.session_state.barcode_text = detected
        st.session_state.analysis_result = None
        st.session_state.uploaded_signature = signature
        if not detected or not confidence:
            st.warning(copy["barcode_empty"], icon=":material/qr_code_scanner:")
    except Exception:
        st.error(copy["barcode_error"], icon=":material/qr_code_scanner:")
    finally:
        if temp_path:
            try:
                os.unlink(temp_path)
            except OSError:
                pass


def render_results(result: dict[str, Any], copy: dict[str, str]) -> None:
    verdict = result["product_verdict"]
    tone_map = {"ok": ("overall_safe", "✓", "ok"), "care": ("overall_attention", "i", "care"),
                "avoid": ("overall_restricted", "!", "avoid"), "unknown": ("overall_unknown", "?", "unknown")}
    overall_key, symbol, tone = tone_map[verdict]
    labels = {"ok": copy["safe"], "care": copy["care"], "avoid": copy["avoid"], "unknown": copy["unknown"]}

    metrics = "".join(
        f'<div class="metric"><div class="metric-value">{esc(v)}</div><div class="metric-label">{esc(l)}</div></div>'
        for v, l in (
            ((result["nutriscore_grade"] or "—").upper(), copy["nutriscore"]),
            (result["nova_group"] if result["nova_group"] is not None else "—", copy["nova"]),
            (len(result["ingredients"]), copy["ingredients"]),
            (len(result["flagged_additives"]), copy["flagged_additives"]),
        )
    )

    reasons_html = "".join(f"<li>{esc(r)}</li>" for r in result["reasons"]) or f"<li>{esc(copy['no_reasons'])}</li>"

    additive_chips = "".join(f'<span class="chip">{esc(a)}</span>' for a in result["flagged_additives"]) or f'<span class="chip">{esc(copy["none_flagged"])}</span>'
    ingredient_chips = "".join(f'<span class="chip">{esc(i)}</span>' for i in result["ingredients"]) or f'<span class="chip">{esc(copy["none_flagged"])}</span>'

    detail_rows = "".join(
        f'<div class="detail-row"><span class="detail-key">{esc(k)}</span><span class="detail-val">{esc(v)}</span></div>'
        for k, v in (
            (copy["barcode_result"], result["barcode"] or copy["not_found"]),
            (copy["source"], result["source"] or copy["not_found"]),
        )
    )

    explanation = result["explanation"] or copy["awaiting"]
    guardrail_note = f'<div class="guardrail-note">{esc(copy["guardrail_notice"])}</div>' if result["violations"] else ""

    product_title = result["product_name"] or copy["not_found"]

    complete = (
        '<section class="result-shell">'
        f'<div class="section-label">{esc(copy["results"])}</div>'
        '<div class="verdict-banner"><div class="verdict-lead">'
        f'<div class="verdict-icon tone-{tone}">{symbol}</div>'
        f'<div><div class="verdict-title">{esc(product_title)} — {esc(copy[overall_key])}</div>'
        f'<div class="verdict-note">{esc(labels[verdict])}</div></div></div>'
        f'{metrics}</div>'
        '<div class="results-grid">'
        '<div class="panel">'
        f'<div class="panel-head">{esc(copy["why"])}</div>'
        f'<div class="panel-body"><ul class="reason-list">{reasons_html}</ul></div>'
        f'<div class="panel-head">{esc(copy["ingredients"])}</div>'
        f'<div class="panel-body"><div class="chip-row">{ingredient_chips}</div></div>'
        f'<div class="panel-head">{esc(copy["flagged_additives"])}</div>'
        f'<div class="panel-body"><div class="chip-row">{additive_chips}</div></div>'
        f'<div class="panel-head">{esc(copy["product_details"])}</div>'
        f'<div class="panel-body">{detail_rows}</div>'
        '</div>'
        f'<aside class="summary-panel"><div class="panel-head">{esc(copy["summary"])}</div>'
        f'<div class="summary-copy">{esc(explanation)}</div>{guardrail_note}</aside>'
        '</div></section>'
    )
    st.html(complete)


init_state()
render_css()
copy = COPY[st.session_state.lang]
nav_left, nav_right = st.columns([5, 1], vertical_alignment="center")
with nav_left:
    st.html(f'<div class="ingrid-nav"><span class="ingrid-mark">Ingrid</span><span class="ingrid-product">{esc(copy["product"])}</span></div>')
with nav_right:
    st.button(copy["lang"], on_click=toggle_language, width="stretch")
st.html(f'<section class="hero"><h1>{esc(copy["headline"])}</h1><p>{esc(copy["subhead"])}</p></section>')

capture_col, review_col = st.columns([5, 7], gap="large", vertical_alignment="top")
with capture_col:
    st.html(f'<div class="section-label">{esc(copy["upload_title"])}</div><div class="helper">{esc(copy["upload_help"])}</div>')
    uploaded = st.file_uploader(copy["upload_label"], type=["png", "jpg", "jpeg"], label_visibility="collapsed")
    process_upload(uploaded, copy)
    if uploaded is not None:
        try:
            st.image(uploaded, width="stretch")
        except Exception:
            pass
    st.caption(copy["samples"])
    left, right = st.columns(2)
    with left:
        st.button(copy["sample_coke"], on_click=set_sample, args=("coke",), width="stretch")
    with right:
        st.button(copy["sample_nutella"], on_click=set_sample, args=("nutella",), width="stretch")

with review_col:
    st.html(f'<div class="section-label">{esc(copy["review_title"])}</div><div class="helper">{esc(copy["barcode_label"])}</div>')
    st.text_input(copy["barcode_label"], key="barcode_text", placeholder=copy["placeholder"], label_visibility="collapsed", max_chars=14)
    left, right = st.columns(2)
    with left:
        clear_clicked = st.button(copy["clear"], on_click=clear_barcode, width="stretch", disabled=not bool(st.session_state.barcode_text))
    with right:
        audit_clicked = st.button(copy["audit"], type="primary", width="stretch")

if audit_clicked:
    if not st.session_state.barcode_text.strip():
        st.warning(copy["empty_warning"], icon=":material/info:")
    else:
        st.toast(copy["audit_running"], icon="🔎")
        try:
            with st.spinner(copy["audit_running"]):
                st.session_state.analysis_result = normalize_result(analyse_label(st.session_state.barcode_text.strip()))
        except Exception:
            st.error(copy["audit_error"], icon=":material/error:")

if st.session_state.analysis_result:
    render_results(st.session_state.analysis_result, copy)
else:
    st.html(f'<div class="empty-state">{esc(copy["awaiting"])}</div>')
st.html(f'<div class="disclaimer">{esc(copy["disclaimer"])}</div>')
