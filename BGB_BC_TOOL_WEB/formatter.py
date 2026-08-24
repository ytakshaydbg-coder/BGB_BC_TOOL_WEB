import io
import re
import zipfile
from pathlib import Path


# ============================================================
# CUSTOMER FIELDS — ONLY THESE CAN CHANGE
# ============================================================

PLACEHOLDERS = {
    "{{ACCOUNT_NO}}": "account_number",
    "{{CUSTOMER_ID}}": "customer_id",
    "{{NAME}}": "name",
    "{{ADDRESS}}": "address",
    "{{PIN_CODE}}": "pin_code",
}


# ============================================================
# LOCKED FIELDS — NEVER CHANGE
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
    return (
        str(value)
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
        .replace("'", "&apos;")
    )


# ============================================================
# NORMALIZE TEXT FOR VERIFICATION
# ============================================================

def normalize_text(text):
    """
    Word can split a visible line into many XML runs.
    It can also contain XML entities and unusual whitespace.

    This function normalizes all of that for comparison.
    """

    if not text:
        return ""

    text = (
        text
        .replace("&amp;", "&")
        .replace("&lt;", "<")
        .replace("&gt;", ">")
        .replace("&quot;", '"')
        .replace("&apos;", "'")
        .replace("\xa0", " ")
    )

    # Remove Word/XML line breaks for verification.
    text = re.sub(r"\s+", " ", text)

    return text.strip().upper()


# ============================================================
# GET ALL VISIBLE WORD TEXT
# ============================================================

def get_visible_text(xml):
    """
    Joins all <w:t> text nodes.

    This is important because Word may split:

        BRANCH - JORJA

    into several XML runs.
    """

    nodes = re.findall(
        r"<w:t\b[^>]*>(.*?)</w:t>",
        xml,
        flags=re.IGNORECASE | re.DOTALL,
    )

    return normalize_text("".join(nodes))


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

    visible = ""
    ranges = []

    for node in nodes:

        text = node.group(2)

        start = len(visible)

        visible += text

        end = len(visible)

        ranges.append(
            {
                "node": node,
                "start": start,
                "end": end,
            }
        )

    position = visible.find(placeholder)

    if position == -1:
        return paragraph_xml, False

    end_position = position + len(placeholder)

    touched = []

    for item in ranges:

        if (
            item["end"] > position
            and item["start"] < end_position
        ):
            touched.append(item)

    if not touched:
        return paragraph_xml, False

    first = touched[0]
    last = touched[-1]

    first_node = first["node"]
    last_node = last["node"]

    first_text = first_node.group(2)
    last_text = last_node.group(2)

    prefix_length = position - first["start"]

    suffix_start = end_position - last["start"]

    prefix = first_text[:prefix_length]

    suffix = last_text[suffix_start:]

    new_content = (
        prefix
        + str(replacement)
        + suffix
    )

    new_content = escape_xml(new_content)

    replacements = []

    replacements.append(
        (
            first_node.start(),
            first_node.end(),
            f"<w:t{first_node.group(1)}>"
            f"{new_content}"
            f"</w:t>",
        )
    )

    for item in touched[1:]:

        node = item["node"]

        replacements.append(
            (
                node.start(),
                node.end(),
                f"<w:t{node.group(1)}></w:t>",
            )
        )

    for start, end, replacement_xml in reversed(
        replacements
    ):

        paragraph_xml = (
            paragraph_xml[:start]
            + replacement_xml
            + paragraph_xml[end:]
        )

    return paragraph_xml, True


# ============================================================
# REPLACE ALL MAPPED FIELDS
# ============================================================

def replace_all_placeholders(xml, data):

    paragraphs = list(
        re.finditer(
            r"<w:p\b.*?</w:p>",
            xml,
            flags=re.IGNORECASE | re.DOTALL,
        )
    )

    for paragraph_match in reversed(paragraphs):

        original = paragraph_match.group(0)

        paragraph = original

        for placeholder, field in PLACEHOLDERS.items():

            while True:

                new_paragraph, changed = (
                    replace_placeholder_in_paragraph(
                        paragraph,
                        placeholder,
                        data[field],
                    )
                )

                if not changed:
                    break

                paragraph = new_paragraph

        if paragraph != original:

            xml = (
                xml[:paragraph_match.start()]
                + paragraph
                + xml[paragraph_match.end():]
            )

    return xml


# ============================================================
# CHECK UNMAPPED PLACEHOLDERS
# ============================================================

def remaining_placeholders(xml):

    visible = get_visible_text(xml)

    found = re.findall(
        r"\{\{[A-Z0-9_]+\}\}",
        visible,
    )

    return sorted(set(found))


# ============================================================
# CHECK LOCKED FIELDS
# ============================================================

def verify_locked_fields(xml):

    visible = get_visible_text(xml)

    missing = []

    for fixed_value in FIXED_VALUES:

        fixed_normalized = normalize_text(
            fixed_value
        )

        if fixed_normalized not in visible:

            missing.append(fixed_value)

    return missing


# ============================================================
# BUILD DOCX
# ============================================================

def build_docx(
    template_file,
    output,
    data,
):

    template_file = Path(template_file)

    if not template_file.exists():

        raise FileNotFoundError(
            f"Template not found: {template_file}"
        )

    # --------------------------------------------------------
    # Read existing DOCX
    # --------------------------------------------------------

    with zipfile.ZipFile(
        template_file,
        "r",
    ) as source:

        files = {
            name: source.read(name)
            for name in source.namelist()
        }

    if "word/document.xml" not in files:

        raise ValueError(
            "Invalid DOCX: document.xml missing."
        )

    xml = files[
        "word/document.xml"
    ].decode(
        "utf-8"
    )

    # --------------------------------------------------------
    # Required data check
    # --------------------------------------------------------

    required = [
        "account_number",
        "customer_id",
        "name",
        "address",
        "pin_code",
    ]

    for field in required:

        value = data.get(field)

        if value is None:

            raise ValueError(
                f"Missing field: {field}"
            )

        if str(value).strip() == "":

            raise ValueError(
                f"Empty field: {field}"
            )

    # --------------------------------------------------------
    # Replace ONLY mapped placeholders
    # --------------------------------------------------------

    xml = replace_all_placeholders(
        xml,
        data,
    )

    # --------------------------------------------------------
    # No placeholder should remain
    # --------------------------------------------------------

    left = remaining_placeholders(xml)

    if left:

        raise ValueError(
            "Unmapped placeholders remain: "
            + ", ".join(left)
        )

    # --------------------------------------------------------
    # Verify locked fields
    # --------------------------------------------------------

    missing_locked = verify_locked_fields(
        xml
    )

    if missing_locked:

        raise ValueError(
            "A locked field was changed or removed: "
            + ", ".join(missing_locked)
        )

    # --------------------------------------------------------
    # Save modified XML
    # --------------------------------------------------------

    files[
        "word/document.xml"
    ] = xml.encode(
        "utf-8"
    )

    # --------------------------------------------------------
    # Create DOCX
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
# FINAL VERIFICATION
# ============================================================

def verify_result(
    docx_bytes,
    data,
):

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

    visible = get_visible_text(xml)

    # --------------------------------------------------------
    # Verify customer data
    # --------------------------------------------------------

    customer_fields = [
        "account_number",
        "customer_id",
        "name",
        "address",
        "pin_code",
    ]

    for field in customer_fields:

        value = normalize_text(
            data[field]
        )

        if value not in visible:

            raise ValueError(
                "Final DOCX verification failed: "
                + field
            )

    # --------------------------------------------------------
    # Verify locked fields
    # --------------------------------------------------------

    missing_locked = verify_locked_fields(
        xml
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

    left = remaining_placeholders(xml)

    if left:

        raise ValueError(
            "Final DOCX still contains placeholders: "
            + ", ".join(left)
        )

    return True
