import io
import re
import zipfile
from pathlib import Path


# ============================================================
# ONLY THESE FIELDS ARE ALLOWED TO CHANGE
# ============================================================

PLACEHOLDERS = {
    "{{ACCOUNT_NO}}": "account_number",
    "{{CUSTOMER_ID}}": "customer_id",
    "{{NAME}}": "name",
    "{{ADDRESS}}": "address",
    "{{PIN_CODE}}": "pin_code",
}


# ============================================================
# THESE VALUES ARE LOCKED
# THEY MUST NEVER BE CHANGED
# ============================================================

FIXED_VALUES = [
    "BRANCH - JORJA",
    "PUNB0MBGB06",
    "RAVISH KUMAR SAH",
    "PAGHARI CHOWK, 847105",
]


# ============================================================
# XML ESCAPE
# ============================================================

def escape_xml(value):
    value = str(value)

    return (
        value
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
        .replace("'", "&apos;")
    )


# ============================================================
# GET TEXT FROM A WORD PARAGRAPH
# ============================================================

def get_paragraph_text(paragraph_xml):
    """
    Word often splits text into multiple <w:t> runs.

    Example:

    {{CUSTOMER_ID}}

    can internally become:

    {{CUST
    OMER_
    ID}}

    This function joins all visible text.
    """

    nodes = re.findall(
        r"<w:t\b[^>]*>(.*?)</w:t>",
        paragraph_xml,
        flags=re.IGNORECASE | re.DOTALL,
    )

    return "".join(nodes)


# ============================================================
# REPLACE PLACEHOLDER EVEN IF WORD SPLITS IT INTO RUNS
# ============================================================

def replace_placeholder_in_paragraph(
    paragraph_xml,
    placeholder,
    replacement,
):
    """
    Safely replaces a {{PLACEHOLDER}} even when Microsoft Word
    has split that placeholder across multiple XML text runs.

    Formatting of the first run is preserved.
    """

    nodes = list(
        re.finditer(
            r"<w:t\b([^>]*)>(.*?)</w:t>",
            paragraph_xml,
            flags=re.IGNORECASE | re.DOTALL,
        )
    )

    if not nodes:
        return paragraph_xml, False

    # --------------------------------------------------------
    # Build visible text and map every character to a run
    # --------------------------------------------------------

    visible_text = ""

    run_ranges = []

    for node in nodes:
        text = node.group(2)

        start = len(visible_text)
        visible_text += text
        end = len(visible_text)

        run_ranges.append(
            {
                "node": node,
                "start": start,
                "end": end,
            }
        )

    # --------------------------------------------------------
    # Find placeholder
    # --------------------------------------------------------

    position = visible_text.find(placeholder)

    if position == -1:
        return paragraph_xml, False

    placeholder_end = position + len(placeholder)

    # --------------------------------------------------------
    # Find all runs touched by placeholder
    # --------------------------------------------------------

    touched = []

    for item in run_ranges:

        if (
            item["end"] > position
            and item["start"] < placeholder_end
        ):
            touched.append(item)

    if not touched:
        return paragraph_xml, False

    first_run = touched[0]
    last_run = touched[-1]

    first_text = first_run["node"].group(2)
    last_text = last_run["node"].group(2)

    # --------------------------------------------------------
    # Text before placeholder in first run
    # --------------------------------------------------------

    first_start_inside = position - first_run["start"]

    prefix = first_text[:first_start_inside]

    # --------------------------------------------------------
    # Text after placeholder in last run
    # --------------------------------------------------------

    last_end_inside = placeholder_end - last_run["start"]

    suffix = last_text[last_end_inside:]

    # --------------------------------------------------------
    # New content
    # --------------------------------------------------------

    new_text = (
        prefix
        + str(replacement)
        + suffix
    )

    new_text = escape_xml(new_text)

    # --------------------------------------------------------
    # Replace first run
    # --------------------------------------------------------

    first_node = first_run["node"]

    first_replacement = (
        f"<w:t{first_node.group(1)}>"
        f"{new_text}"
        f"</w:t>"
    )

    replacements = []

    replacements.append(
        (
            first_node.start(),
            first_node.end(),
            first_replacement,
        )
    )

    # --------------------------------------------------------
    # Empty all remaining touched runs
    # --------------------------------------------------------

    for item in touched[1:]:

        node = item["node"]

        empty_run = (
            f"<w:t{node.group(1)}></w:t>"
        )

        replacements.append(
            (
                node.start(),
                node.end(),
                empty_run,
            )
        )

    # --------------------------------------------------------
    # Apply replacements backwards
    # --------------------------------------------------------

    for start, end, replacement_text in reversed(
        replacements
    ):

        paragraph_xml = (
            paragraph_xml[:start]
            + replacement_text
            + paragraph_xml[end:]
        )

    return paragraph_xml, True


# ============================================================
# REPLACE ALL PLACEHOLDERS IN DOCUMENT
# ============================================================

def replace_all_placeholders(xml, data):

    # Find every Word paragraph.
    paragraphs = list(
        re.finditer(
            r"<w:p\b.*?</w:p>",
            xml,
            flags=re.IGNORECASE | re.DOTALL,
        )
    )

    # Work backwards so XML positions remain correct.
    for paragraph_match in reversed(paragraphs):

        original_paragraph = paragraph_match.group(0)

        paragraph = original_paragraph

        # ----------------------------------------------------
        # Replace every allowed placeholder
        # ----------------------------------------------------

        for placeholder, data_key in PLACEHOLDERS.items():

            while True:

                new_paragraph, changed = (
                    replace_placeholder_in_paragraph(
                        paragraph,
                        placeholder,
                        data[data_key],
                    )
                )

                if not changed:
                    break

                paragraph = new_paragraph

        # ----------------------------------------------------
        # Put modified paragraph back into document
        # ----------------------------------------------------

        if paragraph != original_paragraph:

            xml = (
                xml[:paragraph_match.start()]
                + paragraph
                + xml[paragraph_match.end():]
            )

    return xml


# ============================================================
# CHECK REMAINING PLACEHOLDERS
# ============================================================

def find_remaining_placeholders(xml):

    # Reconstruct visible text from every Word text run.
    text_nodes = re.findall(
        r"<w:t\b[^>]*>(.*?)</w:t>",
        xml,
        flags=re.IGNORECASE | re.DOTALL,
    )

    visible_text = "".join(text_nodes)

    return sorted(
        set(
            re.findall(
                r"\{\{[A-Z0-9_]+\}\}",
                visible_text,
            )
        )
    )


# ============================================================
# CHECK LOCKED FIELDS
# ============================================================

def check_fixed_fields(xml):

    text_nodes = re.findall(
        r"<w:t\b[^>]*>(.*?)</w:t>",
        xml,
        flags=re.IGNORECASE | re.DOTALL,
    )

    visible_text = "".join(text_nodes)

    # XML decode common entities.
    visible_text = (
        visible_text
        .replace("&amp;", "&")
        .replace("&lt;", "<")
        .replace("&gt;", ">")
        .replace("&quot;", '"')
        .replace("&apos;", "'")
    )

    missing = []

    for fixed_value in FIXED_VALUES:

        if fixed_value not in visible_text:
            missing.append(fixed_value)

    return missing


# ============================================================
# BUILD FINAL DOCX
# ============================================================

def build_docx(
    template_file,
    output,
    data,
):
    """
    Reads the existing DOCX template and changes ONLY
    {{...}} placeholders.

    The document is NOT rebuilt from scratch.
    """

    template_file = Path(template_file)

    if not template_file.exists():

        raise FileNotFoundError(
            f"Template not found: {template_file}"
        )

    # --------------------------------------------------------
    # Open DOCX
    # --------------------------------------------------------

    with zipfile.ZipFile(
        template_file,
        "r",
    ) as source:

        files = {
            name: source.read(name)
            for name in source.namelist()
        }

    # --------------------------------------------------------
    # Word document XML
    # --------------------------------------------------------

    if "word/document.xml" not in files:

        raise ValueError(
            "Invalid DOCX: word/document.xml not found."
        )

    xml = files[
        "word/document.xml"
    ].decode(
        "utf-8"
    )

    # --------------------------------------------------------
    # Required data validation
    # --------------------------------------------------------

    required_fields = [
        "account_number",
        "customer_id",
        "name",
        "address",
        "pin_code",
    ]

    for field in required_fields:

        value = data.get(field)

        if value is None or str(value).strip() == "":

            raise ValueError(
                f"Required field is empty: {field}"
            )

    # --------------------------------------------------------
    # Replace placeholders
    # --------------------------------------------------------

    xml = replace_all_placeholders(
        xml,
        data,
    )

    # --------------------------------------------------------
    # Make sure NO placeholder remains
    # --------------------------------------------------------

    remaining = find_remaining_placeholders(
        xml
    )

    if remaining:

        raise ValueError(
            "Unmapped placeholders remain: "
            + ", ".join(remaining)
        )

    # --------------------------------------------------------
    # Make sure locked fields were NOT changed
    # --------------------------------------------------------

    missing_fixed = check_fixed_fields(
        xml
    )

    if missing_fixed:

        raise ValueError(
            "A locked field was changed or removed: "
            + ", ".join(missing_fixed)
        )

    # --------------------------------------------------------
    # Put modified XML back
    # --------------------------------------------------------

    files[
        "word/document.xml"
    ] = xml.encode(
        "utf-8"
    )

    # --------------------------------------------------------
    # Create final DOCX
    # --------------------------------------------------------

    if hasattr(
        output,
        "write",
    ):

        with zipfile.ZipFile(
            output,
            "w",
            zipfile.ZIP_DEFLATED,
        ) as destination:

            for name, content in files.items():

                destination.writestr(
                    name,
                    content,
                )

    else:

        output = Path(output)

        output.parent.mkdir(
            parents=True,
            exist_ok=True,
        )

        with zipfile.ZipFile(
            output,
            "w",
            zipfile.ZIP_DEFLATED,
        ) as destination:

            for name, content in files.items():

                destination.writestr(
                    name,
                    content,
                )


# ============================================================
# FINAL DOCX VERIFICATION
# ============================================================

def verify_result(
    docx_bytes,
    data,
):
    """
    Final safety check before allowing download.
    """

    with zipfile.ZipFile(
        io.BytesIO(docx_bytes),
        "r",
    ) as archive:

        if "word/document.xml" not in archive.namelist():

            raise ValueError(
                "Generated DOCX is invalid."
            )

        xml = archive.read(
            "word/document.xml"
        ).decode(
            "utf-8"
        )

    # --------------------------------------------------------
    # Verify customer fields
    # --------------------------------------------------------

    text_nodes = re.findall(
        r"<w:t\b[^>]*>(.*?)</w:t>",
        xml,
        flags=re.IGNORECASE | re.DOTALL,
    )

    visible_text = "".join(
        text_nodes
    )

    visible_text = (
        visible_text
        .replace("&amp;", "&")
        .replace("&lt;", "<")
        .replace("&gt;", ">")
        .replace("&quot;", '"')
        .replace("&apos;", "'")
    )

    for field in [
        "account_number",
        "customer_id",
        "name",
        "address",
        "pin_code",
    ]:

        value = str(
            data[field]
        )

        if value not in visible_text:

            raise ValueError(
                "Final DOCX verification failed for "
                + field
            )

    # --------------------------------------------------------
    # Verify locked fields
    # --------------------------------------------------------

    missing_fixed = check_fixed_fields(
        xml
    )

    if missing_fixed:

        raise ValueError(
            "Final DOCX verification failed. "
            "Locked field missing: "
            + ", ".join(missing_fixed)
        )

    # --------------------------------------------------------
    # Verify no placeholders remain
    # --------------------------------------------------------

    remaining = find_remaining_placeholders(
        xml
    )

    if remaining:

        raise ValueError(
            "Final DOCX still contains placeholders: "
            + ", ".join(remaining)
        )

    return True
