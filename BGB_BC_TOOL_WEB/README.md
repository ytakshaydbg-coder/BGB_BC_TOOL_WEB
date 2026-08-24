# BGB_BC_TOOL_WEB

AOF PDF → existing BGB Passbook DOCX generator.

## Important design

The uploaded `template.docx` is the master document.

The tool does NOT rebuild the Word document from scratch.

It edits only these customer-data targets:
- Account Number
- Customer ID
- Name
- Address
- PIN Code

It intentionally does NOT replace:
- Branch Name
- IFSC Code
- KO Name
- KO Location

The document XML, VML textbox, fonts, bold settings, tabs, paragraph spacing and page settings are preserved by editing the existing DOCX package.

## Safety behavior

If a required field cannot be extracted/validated, generation stops.

The tool does not guess missing critical values.

## Run

```bash
pip install -r requirements.txt
streamlit run streamlit_app.py
```

## Deploy

This project is designed for Streamlit Community Cloud.
Main file: `streamlit_app.py`
