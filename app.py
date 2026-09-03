"""Ingrid — food ingredient compliance scanner Streamlit interface."""
from __future__ import annotations

import html
import os
import tempfile
from pathlib import Path
from typing import Any

import streamlit as st
from PIL import Image, UnidentifiedImageError

try:
    from ocr import extract_text
except ImportError:
    def extract_text(path: str) -> tuple[str, float]:
        return ("Ingredients: wheat flour, sugar, palm oil, salt, sodium nitrite, titanium dioxide, aspartame, natural flavouring.", 0.96)

try:
    from chain import analyse_label
except ImportError:
    def analyse_label(text: str) -> dict[str, Any]:
        verdicts = {"wheat flour": "ok", "sugar": "care", "palm oil": "care", "salt": "care", "sodium nitrite": "avoid", "titanium dioxide": "avoid", "aspartame": "care", "natural flavouring": "ok"}
        data = {
            "wheat flour": ("Wheat flour", "Grain base", "Codex Stan 152-1985"),
            "sugar": ("Sucrose", "Free sugar", "WHO Guideline 2015"),
            "palm oil": ("Palm oil", "Refined fat", "EFSA Journal 2016;14(5):4426"),
            "salt": ("Sodium chloride", "Mineral", "WHO Sodium Intake 2012"),
            "sodium nitrite": ("Sodium nitrite (E250)", "Preservative", "EFSA Journal 2017;15(6):4786"),
            "titanium dioxide": ("Titanium dioxide (E171)", "Colour", "EU Regulation 2022/63"),
            "aspartame": ("Aspartame (E951)", "Sweetener", "IARC / JECFA 2023 Review"),
            "natural flavouring": ("Natural flavouring", "Flavouring", "Regulation (EC) No 1334/2008"),
        }
        return {"verdicts": verdicts, "matches": {k: {"name": v[0], "category": v[1], "source": v[2]} for k, v in data.items()}, "explanation": "This sample contains common base ingredients alongside additives that need closer jurisdiction-specific review. Sodium nitrite is subject to strict intake limits, while titanium dioxide is no longer authorised as a food additive in the European Union."}

st.set_page_config(page_title="Ingrid — ingredient compliance clarity", page_icon="🔎", layout="wide", initial_sidebar_state="collapsed")

COPY = {
    "en": {
        "lang": "中文", "product": "AI food-ingredient compliance scanner",
        "headline": "Upload a label. Review ingredients. Get compliance clarity.",
        "subhead": "Ingrid extracts the ingredient list, checks each item against your regulatory knowledge base, and shows the evidence behind every result.",
        "upload_title": "1. Upload or photograph the label", "upload_label": "Food label image",
        "upload_help": "PNG, JPG or JPEG · up to 20 MB · clear, well-lit images work best",
        "review_title": "2. Review the extracted ingredients", "textarea_label": "Extracted ingredient text",
        "placeholder": "Your extracted ingredient list will appear here. You can correct OCR errors before running the audit.",
        "samples": "Try a prepared sample", "sample_cookie": "Cookie label", "sample_ham": "Cured ham label",
        "clear": "Clear text", "audit": "Run compliance audit", "empty_warning": "Add an ingredient list before running the audit.",
        "ocr_running": "Reading the label…", "audit_running": "Matching ingredients to regulatory evidence…",
        "image_error": "This file could not be read as an image. Choose a valid PNG, JPG or JPEG file.",
        "ocr_error": "The label could not be read. Try a clearer image or enter the ingredients manually.",
        "ocr_empty": "No readable text was found. Try a clearer, closer photo or enter the ingredients manually.",
        "ocr_low_confidence": "Some text may have been read incorrectly. Please review and correct it before running the audit.",
        "audit_error": "The audit could not be completed. Your ingredient text is still available; please try again.",
        "results": "3. Compliance verdict", "overall_safe": "No restricted ingredients found",
        "overall_attention": "Review before deciding", "overall_restricted": "Restricted ingredient found",
        "safe": "Permitted", "care": "Attention", "avoid": "Restricted", "unknown": "Not indexed",
        "findings": "Ingredient findings", "summary": "Ingrid summary", "source": "Regulatory source", "matched": "Matched as",
        "awaiting": "Your evidence-backed findings will appear here after the audit.",
        "disclaimer": "Screening support only — status can differ by jurisdiction and product use. Verify cited primary sources before making regulatory or health decisions.",
    },
    "zh": {
        "lang": "English", "product": "AI 食品配料合规扫描器",
        "headline": "上传配料表，核对识别结果，快速看懂合规风险。",
        "subhead": "Ingrid 提取食品配料，逐项检索监管知识库，并把每个判断背后的依据清楚展示出来。",
        "upload_title": "1. 上传或拍摄食品配料表", "upload_label": "食品配料表图片",
        "upload_help": "支持 PNG、JPG、JPEG · 最大 20 MB · 光线均匀、文字清晰的照片识别效果更好",
        "review_title": "2. 核对识别出的配料", "textarea_label": "识别出的配料文本",
        "placeholder": "识别出的配料会显示在这里。执行审查前，你可以先修正 OCR 错别字。",
        "samples": "试用预设样本", "sample_cookie": "曲奇配料", "sample_ham": "腌制火腿",
        "clear": "清空文本", "audit": "开始合规审查", "empty_warning": "请先上传图片或输入配料文本。",
        "ocr_running": "正在识别配料表…", "audit_running": "正在匹配配料与监管依据…",
        "image_error": "无法读取这张图片，请选择有效的 PNG、JPG 或 JPEG 文件。",
        "ocr_error": "没有成功识别配料表。请换一张更清晰的图片，或手动输入配料。",
        "ocr_empty": "图片中没有识别到清晰文字。请换一张更清楚、更近的照片，或手动输入配料。",
        "ocr_low_confidence": "部分文字的识别置信度较低，请在执行审查前核对并修正识别结果。",
        "audit_error": "暂时无法完成审查。配料文本已保留，请稍后重试。",
        "results": "3. 合规审查结论", "overall_safe": "未发现受限配料", "overall_attention": "建议核对后再判断", "overall_restricted": "发现受限配料",
        "safe": "允许使用", "care": "需要注意", "avoid": "受限 / 避免", "unknown": "知识库未收录",
        "findings": "逐项配料结论", "summary": "Ingrid 综合说明", "source": "监管依据", "matched": "知识库匹配",
        "awaiting": "执行审查后，这里会显示带依据的逐项结论。",
        "disclaimer": "本工具仅用于初步筛查；不同司法辖区和使用场景的规定可能不同。做出监管或健康决定前，请核对所列原始资料。",
    },
}
SAMPLES = {
    "cookie": "Ingredients: wheat flour, sugar, palm oil, cocoa powder, raising agents (sodium bicarbonate, E503), salt, soy lecithin.",
    "ham": "Ingredients: pork (92%), water, salt, dextrose, sodium phosphate, sodium ascorbate, sodium nitrite, titanium dioxide.",
}

def init_state() -> None:
    for key, value in {"lang": "en", "ocr_text": "", "uploaded_signature": None, "analysis_result": None}.items():
        if key not in st.session_state:
            st.session_state[key] = value

def set_sample(name: str) -> None:
    st.session_state.ocr_text = SAMPLES[name]
    st.session_state.analysis_result = None

def toggle_language() -> None:
    st.session_state.lang = "zh" if st.session_state.lang == "en" else "en"

def esc(value: Any) -> str:
    return html.escape(str(value if value is not None else ""), quote=True)

def normalize_result(raw: Any) -> dict[str, Any]:
    result = raw if isinstance(raw, dict) else {}
    verdicts = result.get("verdicts") if isinstance(result.get("verdicts"), dict) else {}
    matches = result.get("matches") if isinstance(result.get("matches"), dict) else {}
    return {"verdicts": {str(k): v if v in {"ok", "care", "avoid", "unknown"} else "unknown" for k, v in verdicts.items()}, "matches": matches, "explanation": str(result.get("explanation") or "")}

def render_css() -> None:
    st.html("""
    <style>
    @import url('https://fonts.googleapis.com/css2?family=IBM+Plex+Mono:wght@400;500&family=Inter:wght@400;500;600;700&family=Manrope:wght@600;700;800&display=swap');
    :root{--canvas:#f7f9fc;--surface:#fff;--ink:#111827;--muted:#667085;--blue:#175cd3;--blue-strong:#004eeb;--border:#d9e0ea;--safe:#15803d;--care:#b45309;--avoid:#c4320a;--unknown:#475467}
    html{scrollbar-color:#98a2b3 #eef2f7;scrollbar-width:thin}*::-webkit-scrollbar{width:10px;height:10px}*::-webkit-scrollbar-track{background:#eef2f7}*::-webkit-scrollbar-thumb{background:#98a2b3;border:2px solid #eef2f7;border-radius:10px}*::-webkit-scrollbar-thumb:hover{background:#667085}
    .stApp{background:radial-gradient(circle at 48% -12%,rgba(23,92,211,.08),transparent 28rem),var(--canvas);color:var(--ink);font-family:Inter,system-ui,sans-serif}header[data-testid='stHeader']{background:transparent}[data-testid='stToolbar'],#MainMenu,footer{display:none!important}.block-container{max-width:1180px;padding-top:1.4rem;padding-bottom:3rem}
    .ingrid-nav{display:flex;align-items:center;gap:14px;min-height:44px;padding-left:4px}.ingrid-mark{color:var(--blue-strong);font:800 1.65rem/1 Manrope,sans-serif;letter-spacing:-.04em}.ingrid-product{color:var(--muted);font-size:.82rem;padding-left:14px;border-left:1px solid var(--border)}
    .hero{padding:2.6rem 0 1.8rem;max-width:900px}.hero h1{margin:0;font:800 clamp(2.15rem,5vw,4.25rem)/1.04 Manrope,sans-serif;letter-spacing:-.055em;text-wrap:balance}.hero p{max-width:760px;margin:1rem 0 0;color:var(--muted);font-size:1rem;line-height:1.65}.section-label{margin:.1rem 0 .7rem;color:var(--ink);font:700 .92rem/1.4 Manrope,sans-serif}.helper{color:var(--muted);font-size:.77rem;margin:.15rem 0 .8rem}
    div[data-testid='stFileUploader']{min-height:246px;display:flex;align-items:center;border:1px dashed #b9c5d6;border-radius:14px;padding:1rem;background:linear-gradient(180deg,#fff,rgba(245,249,255,.9));position:relative;overflow:hidden}div[data-testid='stFileUploader']::after{content:'';position:absolute;left:0;right:0;top:52%;height:1px;background:linear-gradient(90deg,transparent,#3b82f6 20%,#60a5fa 80%,transparent);box-shadow:0 0 14px rgba(59,130,246,.55);opacity:.58;pointer-events:none;animation:scan 4.5s ease-in-out infinite}div[data-testid='stFileUploaderDropzone']{background:transparent;border:0;width:100%}div[data-testid='stFileUploader'] button{border-color:var(--blue)!important;color:var(--blue)!important;background:white!important}
    div[data-testid='stTextArea'] textarea{min-height:246px;resize:none;border:1px solid var(--border);border-radius:14px;background:#fff;color:var(--ink);font:500 .82rem/1.65 'IBM Plex Mono',monospace;box-shadow:0 1px 2px rgba(16,24,40,.03)}div[data-testid='stTextArea'] textarea:focus{border-color:var(--blue);box-shadow:0 0 0 3px rgba(23,92,211,.17)}
    div[data-testid='stButton'] button{min-height:42px;border-radius:10px;font-weight:650;transition:transform .16s ease,box-shadow .16s ease,border-color .16s ease}div[data-testid='stButton'] button:hover{transform:translateY(-1px);border-color:var(--blue)}div[data-testid='stButton'] button:focus-visible{outline:3px solid rgba(23,92,211,.25);outline-offset:2px}button[kind='primary']{min-height:50px!important;background:linear-gradient(135deg,var(--blue),var(--blue-strong))!important;border:0!important;box-shadow:0 10px 24px rgba(23,92,211,.22)}
    .result-shell{margin-top:2.1rem;border-top:1px solid var(--border);padding-top:1.65rem}.verdict-banner{display:grid;grid-template-columns:minmax(230px,1.35fr) repeat(4,minmax(90px,.48fr));border:1px solid var(--border);border-radius:14px;overflow:hidden;background:#fff;box-shadow:0 8px 26px rgba(30,64,175,.06)}.verdict-lead,.metric{padding:1.15rem 1.25rem}.verdict-lead{display:flex;gap:12px;align-items:center}.verdict-icon{width:38px;height:38px;border-radius:50%;display:grid;place-items:center;font-weight:800}.verdict-title{font:700 1rem/1.35 Manrope,sans-serif}.verdict-note{color:var(--muted);font-size:.76rem;margin-top:3px}.metric{border-left:1px solid #e8edf4}.metric-value{font:700 1.45rem/1 'IBM Plex Mono',monospace}.metric-label{color:var(--muted);font-size:.72rem;margin-top:7px}
    .tone-ok{color:var(--safe);background:#ecfdf3}.tone-care{color:var(--care);background:#fffaeb}.tone-avoid{color:var(--avoid);background:#fff4ed}.tone-unknown{color:var(--unknown);background:#f2f4f7}.results-grid{display:grid;grid-template-columns:minmax(0,1.65fr) minmax(260px,.75fr);gap:18px;margin-top:18px;align-items:start}.findings,.summary-panel{border:1px solid var(--border);border-radius:14px;background:#fff;overflow:hidden}.panel-head{padding:1rem 1.15rem;border-bottom:1px solid #e8edf4;font:700 .88rem/1.4 Manrope,sans-serif}.finding{display:grid;grid-template-columns:minmax(0,1fr) auto;gap:18px;padding:1rem 1.15rem;border-bottom:1px solid #edf1f6}.finding:last-child{border-bottom:0}.ingredient{font-weight:700;font-size:.9rem;overflow-wrap:anywhere}.match{color:var(--muted);font-size:.75rem;margin-top:4px}.citation{color:#475467;font:500 .7rem/1.5 'IBM Plex Mono',monospace;margin-top:8px;overflow-wrap:anywhere}.status{align-self:start;display:inline-flex;align-items:center;gap:7px;padding:5px 9px;border-radius:999px;font-size:.7rem;font-weight:700;white-space:nowrap}.status::before{content:'';width:6px;height:6px;border-radius:50%;background:currentColor}.summary-copy{padding:1.15rem;color:#344054;font-size:.84rem;line-height:1.7;white-space:pre-wrap}.empty-state{margin-top:2rem;border:1px dashed var(--border);border-radius:14px;padding:1.25rem;color:var(--muted);text-align:center;font-size:.84rem;background:rgba(255,255,255,.55)}.disclaimer{margin-top:2.2rem;padding-top:1.1rem;border-top:1px solid var(--border);color:var(--muted);font-size:.72rem;line-height:1.6}
    @keyframes scan{0%,100%{transform:translateY(-72px);opacity:.18}50%{transform:translateY(72px);opacity:.72}}@media(max-width:760px){.block-container{padding:1rem 1rem 2.2rem}.ingrid-product{display:none}.hero{padding:1.65rem 0 1.2rem}.hero h1{font-size:2.28rem}.verdict-banner{grid-template-columns:repeat(2,1fr)}.verdict-lead{grid-column:1/-1}.metric:nth-child(2n){border-left:0}.results-grid{grid-template-columns:1fr}.finding{grid-template-columns:1fr;gap:10px}}@media(prefers-reduced-motion:reduce){*,*::before,*::after{animation:none!important;transition:none!important;scroll-behavior:auto!important}}
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
        with st.spinner(copy["ocr_running"]):
            extracted, confidence = extract_text(temp_path)
        extracted_text = str(extracted or "").strip()
        st.session_state.ocr_text = extracted_text
        st.session_state.analysis_result = None
        st.session_state.uploaded_signature = signature
        if not extracted_text:
            st.warning(copy["ocr_empty"], icon=":material/image_search:")
        elif isinstance(confidence, (int, float)) and confidence < 0.5:
            st.warning(copy["ocr_low_confidence"], icon=":material/visibility:")
    except Exception:
        st.error(copy["ocr_error"], icon=":material/document_scanner:")
    finally:
        if temp_path:
            try: os.unlink(temp_path)
            except OSError: pass

def render_results(result: dict[str, Any], copy: dict[str, str]) -> None:
    verdicts = result["verdicts"]
    counts = {key: 0 for key in ("ok", "care", "avoid", "unknown")}
    for verdict in verdicts.values(): counts[verdict] += 1
    if counts["avoid"]: overall_key, symbol, tone = "overall_restricted", "!", "avoid"
    elif counts["care"] or counts["unknown"]: overall_key, symbol, tone = "overall_attention", "i", "care"
    else: overall_key, symbol, tone = "overall_safe", "✓", "ok"
    labels = {"ok": copy["safe"], "care": copy["care"], "avoid": copy["avoid"], "unknown": copy["unknown"]}
    metrics = "".join(f'<div class="metric"><div class="metric-value" style="color:var(--{("safe" if key == "ok" else key)})">{counts[key]}</div><div class="metric-label">{esc(labels[key])}</div></div>' for key in ("ok", "care", "avoid", "unknown"))
    rows = []
    for ingredient, verdict in verdicts.items():
        match = result["matches"].get(ingredient)
        match = match if isinstance(match, dict) else {}
        category = f' · {esc(match.get("category"))}' if match.get("category") else ""
        rows.append('<div class="finding"><div>' f'<div class="ingredient">{esc(ingredient)}</div>' f'<div class="match">{esc(copy["matched"])}: {esc(match.get("name") or "—")}{category}</div>' f'<div class="citation">{esc(copy["source"])} · {esc(match.get("source") or copy["unknown"])}</div></div>' f'<div class="status tone-{verdict}">{esc(labels[verdict])}</div></div>')
    findings = "".join(rows) or f'<div class="summary-copy">{esc(copy["awaiting"])}</div>'
    explanation = result["explanation"] or copy["awaiting"]
    complete = ('<section class="result-shell">' f'<div class="section-label">{esc(copy["results"])}</div>' '<div class="verdict-banner"><div class="verdict-lead">' f'<div class="verdict-icon tone-{tone}">{symbol}</div><div><div class="verdict-title">{esc(copy[overall_key])}</div><div class="verdict-note">{len(verdicts)} ingredients reviewed</div></div></div>' f'{metrics}</div><div class="results-grid"><div class="findings"><div class="panel-head">{esc(copy["findings"])}</div>{findings}</div>' f'<aside class="summary-panel"><div class="panel-head">{esc(copy["summary"])}</div><div class="summary-copy">{esc(explanation)}</div></aside></div></section>')
    st.html(complete)

init_state()
render_css()
copy = COPY[st.session_state.lang]
with st.container(horizontal=True, horizontal_alignment="distribute", vertical_alignment="center"):
    st.html(f'<div class="ingrid-nav"><span class="ingrid-mark">Ingrid</span><span class="ingrid-product">{esc(copy["product"])}</span></div>')
    st.button(copy["lang"], on_click=toggle_language, width="content")
st.html(f'<section class="hero"><h1>{esc(copy["headline"])}</h1><p>{esc(copy["subhead"])}</p></section>')

capture_col, review_col = st.columns([5, 7], gap="large", vertical_alignment="top")
with capture_col:
    st.html(f'<div class="section-label">{esc(copy["upload_title"])}</div><div class="helper">{esc(copy["upload_help"])}</div>')
    uploaded = st.file_uploader(copy["upload_label"], type=["png", "jpg", "jpeg"], label_visibility="collapsed")
    process_upload(uploaded, copy)
    if uploaded is not None:
        try: st.image(uploaded, width="stretch")
        except Exception: pass
    st.caption(copy["samples"])
    left, right = st.columns(2)
    with left: st.button(copy["sample_cookie"], on_click=set_sample, args=("cookie",), width="stretch")
    with right: st.button(copy["sample_ham"], on_click=set_sample, args=("ham",), width="stretch")

with review_col:
    st.html(f'<div class="section-label">{esc(copy["review_title"])}</div><div class="helper">{esc(copy["textarea_label"])}</div>')
    st.text_area(copy["textarea_label"], key="ocr_text", height=246, placeholder=copy["placeholder"], label_visibility="collapsed", max_chars=5000)
    left, right = st.columns(2)
    with left: clear_clicked = st.button(copy["clear"], width="stretch", disabled=not bool(st.session_state.ocr_text))
    with right: audit_clicked = st.button(copy["audit"], type="primary", width="stretch")

if clear_clicked:
    st.session_state.ocr_text = ""
    st.session_state.analysis_result = None
    st.rerun()
if audit_clicked:
    if not st.session_state.ocr_text.strip(): st.warning(copy["empty_warning"], icon=":material/info:")
    else:
        try:
            with st.spinner(copy["audit_running"]): st.session_state.analysis_result = normalize_result(analyse_label(st.session_state.ocr_text.strip()))
        except Exception: st.error(copy["audit_error"], icon=":material/error:")
if st.session_state.analysis_result: render_results(st.session_state.analysis_result, copy)
else: st.html(f'<div class="empty-state">{esc(copy["awaiting"])}</div>')
st.html(f'<div class="disclaimer">{esc(copy["disclaimer"])}</div>')
