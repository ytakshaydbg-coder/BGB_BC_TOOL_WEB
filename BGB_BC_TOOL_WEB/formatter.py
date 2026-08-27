import io
import re
import zipfile
from pathlib import Path


# ============================================================
# CUSTOMER FIELDS
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
# LOCKED FIELDS
# THESE MUST NEVER BE CHANGED BY THE PROGRAM
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
    """
    Safely converts normal text into XML-safe text.
    """

    return (
        str(value)
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
        .replace("'", "&apos;")
    )


# ============================================================
# NORMALIZE TEXT
# USED ONLY FOR VERIFICATION
# DOES NOT MODIFY THE DOCX
# ============================================================

def normalize_text(text):
    """
    Normalizes text only for comparison/verification.

    Different dash characters are treated as the same:

        -   normal hyphen
        –   en dash
        —   em dash
        ‐   hyphen
        ‒   figure dash
        −   minus
        ﹘  small dash
        ﹣  small minus
        －  fullwidth hyphen

    This does NOT modify the actual Word document.
    """

    if text is None:
        return ""

    text = str(text)

    # Decode common XML entities
    text = (
        text
        .replace("&amp;", "&")
        .replace("&lt;", "<")
        .replace("&gt;", ">")
        .replace("&quot;", '"')
        .replace("&apos;", "'")
        .replace("\xa0", " ")
    )

    # Normalize different dash characters
    dash_characters = "‐-‒–—―−﹘﹣－"

    for dash in dash_characters:
        text = text.replace(dash, "-")

    # Normalize whitespace
    text = re.sub(r"\s+", " ", text)

    return text.strip().upper()


# ============================================================
# GET ALL VISIBLE WORD TEXT
# ============================================================

def get_visible_text(xml):
    """
    Extracts all visible Word text from document.xml.

    Word can split visible text across many <w:t> runs.
    Joining them allows reliable verification.
    """

    text_nodes = re.findall(
        r"<w:t\b[^>]*>(.*?)</w:t>",
        xml,
        flags=re.IGNORECASE | re.DOTALL,
    )

    combined = "".join(text_nodes)

    return normalize_text(combined)


# ============================================================
# REPLACE PLACEHOLDER INSIDE ONE PARAGRAPH
# ============================================================

def replace_placeholder_in_paragraph(
    paragraph_xml,
    placeholder,
    replacement,
):
    """
    Replaces a placeholder even if Microsoft Word has split it
    across multiple <w:t> runs.

    Example:

        {{CUSTOMER_ID}}

    could internally be:

        {{CUST
        OMER_
        ID}}

    This function still detects and replaces it.

    The formatting/properties of the first affected text run
    are preserved.
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
    # Build visible paragraph text
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

    position = visible_text.find(
        placeholder
    )

    if position == -1:
        return paragraph_xml, False

    placeholder_end = (
        position
        + len(placeholder)
    )

    # --------------------------------------------------------
    # Find every run touched by placeholder
    # --------------------------------------------------------

    touched_runs = []

    for item in run_ranges:

        if (
            item["end"] > position
            and item["start"] < placeholder_end
        ):

            touched_runs.append(
                item
            )

    if not touched_runs:
        return paragraph_xml, False

    # --------------------------------------------------------
    # First and last affected run
    # --------------------------------------------------------

    first_run = touched_runs[0]

    last_run = touched_runs[-1]

    first_node = first_run["node"]

    last_node = last_run["node"]

    first_text = first_node.group(2)

    last_text = last_node.group(2)

    # --------------------------------------------------------
    # Preserve text before placeholder
    # --------------------------------------------------------

    prefix_length = (
        position
        - first_run["start"]
    )

    prefix = first_text[
        :prefix_length
    ]

    # --------------------------------------------------------
    # Preserve text after placeholder
    # --------------------------------------------------------

    suffix_start = (
        placeholder_end
        - last_run["start"]
    )

    suffix = last_text[
        suffix_start:
    ]

    # --------------------------------------------------------
    # New text
    # --------------------------------------------------------

    new_content = (
        prefix
        + str(replacement)
        + suffix
    )

    new_content = escape_xml(
        new_content
    )

    # --------------------------------------------------------
    # Replace first affected run
    # --------------------------------------------------------

    replacements = [
        (
            first_node.start(),
            first_node.end(),
            (
                f"<w:t{first_node.group(1)}>"
                f"{new_content}"
                f"</w:t>"
            ),
        )
    ]

    # --------------------------------------------------------
    # Empty all remaining affected runs
    # --------------------------------------------------------

    for item in touched_runs[1:]:

        node = item["node"]

        replacements.append(
            (
                node.start(),
                node.end(),
                (
                    f"<w:t{node.group(1)}>"
                    f"</w:t>"
                ),
            )
        )

    # --------------------------------------------------------
    # Apply from end to beginning
    # --------------------------------------------------------

    for (
        start,
        end,
        replacement_xml,
    ) in reversed(
        replacements
    ):

        paragraph_xml = (
            paragraph_xml[:start]
            + replacement_xml
            + paragraph_xml[end:]
        )

    return paragraph_xml, True


# ============================================================
# REPLACE ALL ALLOWED PLACEHOLDERS
# ============================================================

def replace_all_placeholders(
    xml,
    data,
):
    """
    Searches every Word paragraph and replaces only the
    explicitly allowed {{...}} placeholders.

    Nothing else is intentionally replaced.
    """

    paragraphs = list(
        re.finditer(
            r"<w:p\b.*?</w:p>",
            xml,
            flags=re.IGNORECASE | re.DOTALL,
        )
    )

    # Work backwards so XML positions remain valid.
    for paragraph_match in reversed(
        paragraphs
    ):

        original_paragraph = (
            paragraph_match.group(0)
        )

        paragraph = (
            original_paragraph
        )

        # ----------------------------------------------------
        # Replace each allowed field
        # ----------------------------------------------------

        for (
            placeholder,
            data_key,
        ) in PLACEHOLDERS.items():

            while True:

                (
                    new_paragraph,
                    changed,
                ) = (
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
        # Put paragraph back
        # ----------------------------------------------------

        if (
            paragraph
            != original_paragraph
        ):

            xml = (
                xml[
                    :paragraph_match.start()
                ]
                + paragraph
                + xml[
                    paragraph_match.end():
                ]
            )

    return xml


# ============================================================
# FIND REMAINING PLACEHOLDERS
# ============================================================

def find_remaining_placeholders(
    xml,
):
    """
    Checks whether any {{PLACEHOLDER}} remains
    after replacement.
    """

    visible = get_visible_text(
        xml
    )

    found = re.findall(
        r"\{\{[A-Z0-9_]+\}\}",
        visible,
    )

    return sorted(
        set(found)
    )


# ============================================================
# VERIFY LOCKED FIELDS
# ============================================================

def verify_locked_fields(
    xml,
):
    """
    Checks that all locked template values are still present.

    Comparison is normalized so dash/spacing differences do not
    create false errors.

    The actual DOCX text is NOT changed.
    """

    visible = get_visible_text(
        xml
    )

    missing = []

    for fixed_value in FIXED_VALUES:

        expected = normalize_text(
            fixed_value
        )

        if expected not in visible:

            missing.append(
                fixed_value
            )

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
    Opens the existing DOCX template.

    Only {{...}} customer placeholders are replaced.

    The document is NOT rebuilt from scratch.
    """

    template_file = Path(
        template_file
    )

    # --------------------------------------------------------
    # Check template
    # --------------------------------------------------------

    if not template_file.exists():

        raise FileNotFoundError(
            f"Template not found: "
            f"{template_file}"
        )

    # --------------------------------------------------------
    # Read DOCX package
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
    # Check document.xml
    # --------------------------------------------------------

    if (
        "word/document.xml"
        not in files
    ):

        raise ValueError(
            "Invalid DOCX: "
            "word/document.xml not found."
        )

    xml = files[
        "word/document.xml"
    ].decode(
        "utf-8"
    )

    # --------------------------------------------------------
    # Check required input fields
    # --------------------------------------------------------

    required_fields = [
        "account_number",
        "customer_id",
        "name",
        "address",
        "pin_code",
    ]

    for field in required_fields:

        if field not in data:

            raise ValueError(
                f"Required data missing: "
                f"{field}"
            )

        value = data[field]

        if (
            value is None
            or str(value).strip() == ""
        ):

            raise ValueError(
                f"Required data is empty: "
                f"{field}"
            )

    # --------------------------------------------------------
    # Replace customer placeholders
    # --------------------------------------------------------

    xml = replace_all_placeholders(
        xml,
        data,
    )

    # --------------------------------------------------------
    # Make sure nothing is unmapped
    # --------------------------------------------------------

    remaining = (
        find_remaining_placeholders(
            xml
        )
    )

    if remaining:

        raise ValueError(
            "Unmapped placeholders remain: "
            + ", ".join(remaining)
        )

    # --------------------------------------------------------
    # Verify locked fields
    # --------------------------------------------------------

    missing_locked = (
        verify_locked_fields(
            xml
        )
    )

    if missing_locked:

        raise ValueError(
            "A locked field was changed "
            "or removed: "
            + ", ".join(missing_locked)
        )

    # --------------------------------------------------------
    # Save modified document.xml
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

            for (
                name,
                content,
            ) in files.items():

                destination.writestr(
                    name,
                    content,
                )

    else:

        output = Path(
            output
        )

        output.parent.mkdir(
            parents=True,
            exist_ok=True,
        )

        with zipfile.ZipFile(
            output,
            "w",
            zipfile.ZIP_DEFLATED,
        ) as destination:

            for (
                name,
                content,
            ) in files.items():

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
    Final safety check.

    The DOCX will only be considered successful if:

    1. All customer data is present.
    2. All locked fields are present.
    3. No {{...}} placeholder remains.
    """

    # --------------------------------------------------------
    # Open generated DOCX
    # --------------------------------------------------------

    with zipfile.ZipFile(
        io.BytesIO(docx_bytes),
        "r",
    ) as archive:

        if (
            "word/document.xml"
            not in archive.namelist()
        ):

            raise ValueError(
                "Generated DOCX is invalid."
            )

        xml = archive.read(
            "word/document.xml"
        ).decode(
            "utf-8"
        )

    # --------------------------------------------------------
    # Verify customer data
    # --------------------------------------------------------

    visible = get_visible_text(
        xml
    )

    customer_fields = [
        "account_number",
        "customer_id",
        "name",
        "address",
        "pin_code",
    ]

    for field in customer_fields:

        expected = normalize_text(
            data[field]
        )

        if expected not in visible:

            raise ValueError(
                "Final DOCX verification "
                "failed for: "
                + field
            )

    # --------------------------------------------------------
    # Verify locked fields
    # --------------------------------------------------------

    missing_locked = (
        verify_locked_fields(
            xml
        )
    )

    if missing_locked:

        raise ValueError(
            "Final DOCX verification failed. "
            "Locked field missing: "
            + ", ".join(missing_locked)
        )

    # --------------------------------------------------------
    # Verify no placeholders remain
    # --------------------------------------------------------

    remaining = (
        find_remaining_placeholders(
            xml
        )
    )

    if remaining:

        raise ValueError(
            "Final DOCX still contains "
            "placeholders: "
            + ", ".join(remaining)
        )

    # --------------------------------------------------------
    # SUCCESS
    # --------------------------------------------------------

    return True
