import io
from pathlib import Path

import streamlit as st

from extractor import extract_aof
from formatter import build_docx, verify_result


st.set_page_config(
    page_title="BGB Passbook Generator",
    page_icon="📄",
    layout="centered",
)

st.title("BGB Passbook Generator")
st.caption("AOF PDF → Fixed BGB Passbook DOCX")

st.info(
    "Fixed fields: Branch Name, IFSC Code, KO Name and KO Location "
    "are never replaced."
)

pdf_file = st.file_uploader(
    "Upload AOF PDF",
    type=["pdf"],
    help="Use the original selectable/text PDF whenever possible."
)

if pdf_file:
    if st.button("Read & Verify PDF", type="primary", use_container_width=True):
        try:
            data, checks = extract_aof(pdf_file.getvalue())
            st.session_state["aof_data"] = data
            st.session_state["aof_checks"] = checks
            st.success("PDF read successfully.")
        except Exception as exc:
            st.session_state.pop("aof_data", None)
            st.session_state.pop("aof_checks", None)
            st.error(f"PDF verification failed: {exc}")

data = st.session_state.get("aof_data")
checks = st.session_state.get("aof_checks")

if data:
    st.subheader("Verified data")

    for label, key in [
        ("Account Number", "account_number"),
        ("Customer ID", "customer_id"),
        ("Name", "name"),
        ("Address", "address"),
        ("PIN Code", "pin_code"),
    ]:
        st.text_input(label, value=data.get(key, ""), disabled=True)

    if checks and checks.get("all_required"):
        st.success("All required passbook fields passed validation.")
    else:
        st.error("Verification failed. DOCX generation is disabled.")

    st.subheader("Fixed template fields")
    st.write("🔒 Branch Name — unchanged")
    st.write("🔒 IFSC Code — unchanged")
    st.write("🔒 KO Name — unchanged")
    st.write("🔒 KO Location — unchanged")

    if checks and checks.get("all_required"):
        if st.button("Generate DOCX", type="primary", use_container_width=True):
            try:
                template = Path(__file__).with_name("template.docx")
                output = io.BytesIO()

                build_docx(template, output, data)
                result_bytes = output.getvalue()

                verify_result(result_bytes, data)

                st.download_button(
                    "⬇️ Download BGB_Passbook.docx",
                    data=result_bytes,
                    file_name="BGB_Passbook.docx",
                    mime=(
                        "application/vnd.openxmlformats-officedocument."
                        "wordprocessingml.document"
                    ),
                    use_container_width=True,
                )
                st.success("DOCX generated and verified.")
            except Exception as exc:
                st.error(f"DOCX generation stopped: {exc}")
