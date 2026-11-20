"""Streamlit app: Saudi dialect -> formal MSA, with the fact check shown.

    streamlit run app/streamlit_app.py

Test mode without Ollama:  D2M_APP_ENGINE=mock streamlit run app/streamlit_app.py
The mock engine is a rule-based stand-in, not a model; the app says so on screen.
"""
from __future__ import annotations

import html
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import streamlit as st  # noqa: E402

from src.facts import extract_facts  # noqa: E402
from src.lexicon import find_dialect_words  # noqa: E402
from src.pipeline import (  # noqa: E402
    DEFAULT_BASE_MODEL,
    DEFAULT_HOST,
    DEFAULT_TUNED_MODEL,
    MockClient,
    OllamaClient,
    RewritePipeline,
    run_model,
)
from src.prompts import build_messages  # noqa: E402

RTL_CSS = """
<style>
.stApp, .stMarkdown, .stTextArea textarea, .stTextInput input, .stAlert, .stTabs, label, p, h1, h2, h3, li {
    direction: rtl; text-align: right;
}
.box { direction: rtl; text-align: right; unicode-bidi: plaintext; border: 1px solid #d0d4da; border-radius: 8px;
       padding: 12px 14px; line-height: 2; font-size: 1.05rem; background: #fafbfc; color: #111; min-height: 3rem; }
.box.withheld { background: #fff4f2; border-color: #e0a39a; }
.fact { background: #e3f0ff; border-radius: 4px; padding: 0 4px; }
.bad { background: #ffd9d4; border-radius: 4px; padding: 0 4px; }
table.facts { direction: rtl; width: 100%; border-collapse: collapse; }
table.facts td, table.facts th { border: 1px solid #d0d4da; padding: 6px 10px; text-align: right; }
code, pre { direction: ltr; text-align: left; }
</style>
"""

KIND_AR = {"number": "رقم", "date": "تاريخ", "time": "وقت", "email": "بريد إلكتروني", "url": "رابط", "latin": "كلمة لاتينية"}


def esc(text: str) -> str:
    """Escape for HTML and keep line breaks. Model output is never trusted as markup."""
    return html.escape(text or "").replace("\n", "<br>")


def box(text: str, withheld: bool = False) -> str:
    return f'<div class="box{" withheld" if withheld else ""}">{esc(text)}</div>'


def facts_table(check: dict, source: str) -> str:
    """Every fact of the original with its state in the rewrite, plus anything added."""
    missing = [(f["kind"], f["canonical"]) for f in check.get("missing", [])]
    rows = []
    for fact in extract_facts(source):
        key = (fact.kind, fact.value)
        if key in missing:
            missing.remove(key)
            state = '<span class="bad">غير موجود في إعادة الصياغة</span>'
        else:
            state = "محفوظ"
        rows.append(f"<tr><td>{esc(fact.raw)}</td><td>{KIND_AR.get(fact.kind, fact.kind)}</td><td>{state}</td></tr>")
    for f in check.get("added", []):
        rows.append(f'<tr><td>{esc(f["value"])}</td><td>{KIND_AR.get(f["kind"], f["kind"])}</td><td><span class="bad">أُضيف ولم يرد في الأصل</span></td></tr>')
    for name in check.get("must_keep_missing", []):
        rows.append(f'<tr><td>{esc(name)}</td><td>اسم</td><td><span class="bad">غير موجود في إعادة الصياغة</span></td></tr>')
    if not rows:
        return "<p>لا توجد في الرسالة أرقام أو تواريخ أو كلمات لاتينية للتحقق منها.</p>"
    return '<table class="facts"><tr><th>العنصر</th><th>النوع</th><th>الحالة</th></tr>' + "".join(rows) + "</table>"


def make_client(engine: str, model: str, host: str, few_shot: bool = False):
    if engine == "mock":
        return MockClient("medium")
    return OllamaClient(model, host, few_shot=few_shot)


def main() -> None:
    st.set_page_config(page_title="من اللهجة إلى الفصحى", layout="wide")
    st.markdown(RTL_CSS, unsafe_allow_html=True)
    st.title("تحويل اللهجة السعودية إلى الفصحى مع التحقق من التفاصيل")

    engine = os.environ.get("D2M_APP_ENGINE", "ollama")
    with st.sidebar:
        st.header("الإعدادات")
        host = st.text_input("عنوان Ollama", DEFAULT_HOST)
        tuned = st.text_input("النموذج المضبوط", DEFAULT_TUNED_MODEL)
        base = st.text_input("النموذج الأساسي", DEFAULT_BASE_MODEL)
        if engine == "mock":
            st.warning("وضع التجربة: المحرّك بديل قاعدي وليس نموذجاً. النتائج لا تدل على جودة النموذج.")
        else:
            ok, why = OllamaClient(tuned, host).is_available()
            if ok:
                st.success("النموذج المضبوط متاح محلياً.")
            else:
                st.error(f"النموذج غير متاح: {why}")

    tab_run, tab_compare = st.tabs(["إعادة الصياغة", "مقارنة قبل وبعد"])

    with tab_run:
        text = st.text_area("الرسالة باللهجة", height=140, placeholder="ابغى اغير موعدي من يوم 12/4 لين يوم 19/4 الساعة 10:30")
        names = st.text_input("أسماء يجب أن تبقى كما هي (اختياري، افصل بينها بفاصلة)")
        if st.button("حوّل", type="primary"):
            must_keep = [n.strip() for n in names.replace("،", ",").split(",") if n.strip()]
            result = RewritePipeline(make_client(engine, tuned, host)).run(text, must_keep)
            left, right = st.columns(2)
            with right:
                st.subheader("الرسالة الأصلية")
                st.markdown(box(result.original), unsafe_allow_html=True)
            with left:
                st.subheader("النص المعتمد")
                st.markdown(box(result.text, withheld=not result.released), unsafe_allow_html=True)
            if result.released:
                st.success(f"{result.message_ar}  ({result.status})")
            else:
                st.error(f"{result.message_ar}  ({result.status})")
            if result.unavailable:
                st.info("تأكد أن Ollama يعمل وأن النموذج مثبّت، ثم أعد المحاولة.")
            if result.candidate is not None:
                st.subheader("فحص التفاصيل")
                st.markdown(facts_table(result.check, result.original.strip()), unsafe_allow_html=True)
                if not result.released:
                    st.subheader("مخرجات النموذج المحجوبة (للمراجعة فقط)")
                    st.markdown(box(result.candidate, withheld=True), unsafe_allow_html=True)
                if result.attempts > 1 and result.first_candidate:
                    with st.expander("المحاولة الأولى قبل التصحيح"):
                        st.markdown(box(result.first_candidate, withheld=True), unsafe_allow_html=True)
                words = find_dialect_words(result.text)["strong"] if result.released else []
                if words:
                    st.warning("كلمات لهجية باقية في النص: " + "، ".join(words))
                st.caption(f"عدد المحاولات: {result.attempts} · الزمن: {result.elapsed_ms} مللي ثانية")

    with tab_compare:
        st.write("الرسالة نفسها عبر الأنظمة الثلاثة: النموذج الأساسي مع الموجّه الكامل، النموذج المضبوط وحده، والمضبوط داخل النظام.")
        text2 = st.text_area("الرسالة", height=120, key="cmp")
        if st.button("قارن"):
            base_client = MockClient("weak") if engine == "mock" else OllamaClient(base, host, few_shot=True)
            tuned_client = make_client(engine, tuned, host)
            columns = st.columns(3)
            outputs = []
            for client in (base_client, tuned_client):
                r = run_model(client, build_messages(text2.strip(), few_shot=client.few_shot)) if text2.strip() else None
                outputs.append((r.output if r and r.ok else "", (r.error if r else "لم يُدخل نص") or ""))
            full = RewritePipeline(tuned_client).run(text2)
            titles = ["النموذج الأساسي + موجّه", "النموذج المضبوط وحده", "المضبوط داخل النظام"]
            for col, title, (out, err) in zip(columns[::-1], titles, outputs + [(full.text, "")], strict=True):
                with col:
                    st.subheader(title)
                    if err:
                        st.error(err)
                    else:
                        st.markdown(box(out, withheld=(title == titles[2] and not full.released)), unsafe_allow_html=True)
            st.caption(f"حالة النظام الكامل: {full.status} — {full.message_ar}")


if __name__ == "__main__":
    main()
