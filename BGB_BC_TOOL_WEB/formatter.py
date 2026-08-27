import io
import re
import zipfile
from pathlib import Path


# ============================================================
# ONLY THESE FIELDS CAN CHANGE
# ============================================================

PLACEHOLDERS = {
    "{{ACCOUNT_NO}}": "account_number",
    "{{CUSTOMER_ID}}": "customer_id",
    "{{NAME}}": "name",
    "{{ADDRESS}}": "address",
    "{{PIN_CODE}}": "pin_code",
}


# ============================================================
# THESE FIELDS ARE LOCKED
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
# NORMALIZE TEXT
# ============================================================

def normalize_text(text):

    if text is None:
        return ""

    text = str(text)

    # XML entities
    text = (
        text
        .replace("&amp;", "&")
        .replace("&lt;", "<")
        .replace("&gt;", ">")
        .replace("&quot;", '"')
        .replace("&apos;", "'")
        .replace("\xa0", " ")
    )

    # Normalize all common dash characters
    for dash in "‐-‒–—―−﹘﹣－":
        text = text.replace(dash, "-")

    # Normalize whitespace
    text = re.sub(r"\s+", " ", text)

    return text.strip().upper()


# ============================================================
# GET VISIBLE TEXT FROM XML
# ============================================================

def get_visible_text(xml):

    nodes = re.findall(
        r"<w:t\b[^>]*>(.*?)</w:t>",
        xml,
        flags=re.IGNORECASE | re.DOTALL,
    )

    return normalize_text(
        "".join(nodes)
    )


# ============================================================
# GET ALL TEXT-RUN NODES
# ============================================================

def get_text_nodes(xml):

    return list(
        re.finditer(
            r"<w:t\b([^>]*)>(.*?)</w:t>",
            xml,
            flags=re.IGNORECASE | re.DOTALL,
        )
    )


# ============================================================
# REPLACE PLACEHOLDER ACROSS WORD RUNS
# ============================================================

def replace_placeholder(
    xml,
    placeholder,
    replacement,
):

    nodes = get_text_nodes(xml)

    if not nodes:
        return xml, False

    # --------------------------------------------------------
    # Build complete visible text
    # --------------------------------------------------------

    visible = ""

    ranges = []

    for node in nodes:

        text = node.group(2)

        start = len(visible)

        visible += text

        end = len(visible)

        ranges.append(
            (
                node,
                start,
                end,
            )
        )

    # --------------------------------------------------------
    # Find placeholder
    # --------------------------------------------------------

    position = visible.find(
        placeholder
    )

    if position == -1:
        return xml, False

    end_position = (
        position
        + len(placeholder)
    )

    # --------------------------------------------------------
    # Find affected XML text runs
    # --------------------------------------------------------

    affected = []

    for node, start, end in ranges:

        if (
            end > position
            and start < end_position
        ):

            affected.append(
                (
                    node,
                    start,
                    end,
                )
            )

    if not affected:
        return xml, False

    first_node, first_start, _ = affected[0]

    last_node, last_start, _ = affected[-1]

    first_text = first_node.group(2)

    last_text = last_node.group(2)

    # --------------------------------------------------------
    # Preserve text before placeholder
    # --------------------------------------------------------

    prefix_length = (
        position
        - first_start
    )

    prefix = first_text[
        :prefix_length
    ]

    # --------------------------------------------------------
    # Preserve text after placeholder
    # --------------------------------------------------------

    suffix_start = (
        end_position
        - last_start
    )

    suffix = last_text[
        suffix_start:
    ]

    # --------------------------------------------------------
    # New content
    # --------------------------------------------------------

    new_content = (
        prefix
        + str(replacement)
        + suffix
    )

    new_content = escape_xml(
        new_content
    )

    replacements = []

    # --------------------------------------------------------
    # First run gets replacement
    # --------------------------------------------------------

    replacements.append(
        (
            first_node.start(),
            first_node.end(),
            (
                f"<w:t{first_node.group(1)}>"
                f"{new_content}"
                f"</w:t>"
            ),
        )
    )

    # --------------------------------------------------------
    # Other affected runs become empty
    # --------------------------------------------------------

    for node, _, _ in affected[1:]:

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
    # Apply backwards
    # --------------------------------------------------------

    for start, end, new_xml in reversed(
        replacements
    ):

        xml = (
            xml[:start]
            + new_xml
            + xml[end:]
        )

    return xml, True


# ============================================================
# REPLACE ALL PLACEHOLDERS IN ONE XML PART
# ============================================================

def replace_all_placeholders(
    xml,
    data,
):

    for placeholder, field in PLACEHOLDERS.items():

        # Keep replacing until this placeholder no longer exists.
        while True:

            new_xml, changed = (
                replace_placeholder(
                    xml,
                    placeholder,
                    data[field],
                )
            )

            if not changed:
                break

            xml = new_xml

    return xml


# ============================================================
# FIND REMAINING PLACEHOLDERS
# ============================================================

def find_remaining_placeholders(
    xml,
):

    visible = get_visible_text(
        xml
    )

    return sorted(
        set(
            re.findall(
                r"\{\{[A-Z0-9_]+\}\}",
                visible,
            )
        )
    )


# ============================================================
# VERIFY LOCKED FIELDS
# ============================================================

def verify_locked_fields(
    all_xml_parts,
):

    complete_text = ""

    for xml in all_xml_parts:

        complete_text += " "

        complete_text += get_visible_text(
            xml
        )

    complete_text = normalize_text(
        complete_text
    )

    missing = []

    for fixed in FIXED_VALUES:

        expected = normalize_text(
            fixed
        )

        if expected not in complete_text:

            missing.append(
                fixed
            )

    return missing


# ============================================================
# VERIFY CUSTOMER FIELDS
# ============================================================

def verify_customer_fields(
    all_xml_parts,
    data,
):

    complete_text = ""

    for xml in all_xml_parts:

        complete_text += " "

        complete_text += get_visible_text(
            xml
        )

    complete_text = normalize_text(
        complete_text
    )

    failed = []

    for field in [
        "account_number",
        "customer_id",
        "name",
        "address",
        "pin_code",
    ]:

        expected = normalize_text(
            data[field]
        )

        if expected not in complete_text:

            failed.append(
                field
            )

    return failed


# ============================================================
# BUILD DOCX
# ============================================================

def build_docx(
    template_file,
    output,
    data,
):

    template_file = Path(
        template_file
    )

    if not template_file.exists():

        raise FileNotFoundError(
            "Template not found: "
            + str(template_file)
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
    # Validate DOCX
    # --------------------------------------------------------

    if (
        "word/document.xml"
        not in files
    ):

        raise ValueError(
            "Invalid DOCX: "
            "word/document.xml not found."
        )

    # --------------------------------------------------------
    # Validate input
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
                "Missing required field: "
                + field
            )

        if (
            data[field] is None
            or str(data[field]).strip() == ""
        ):

            raise ValueError(
                "Empty required field: "
                + field
            )

    # --------------------------------------------------------
    # Process ALL Word XML parts
    #
    # This includes:
    # document.xml
    # headers
    # footers
    # etc.
    # --------------------------------------------------------

    xml_names = []

    for name in files:

        if (
            name.startswith("word/")
            and name.endswith(".xml")
        ):

            xml_names.append(
                name
            )

    # --------------------------------------------------------
    # Replace placeholders
    # --------------------------------------------------------

    for name in xml_names:

        xml = files[name].decode(
            "utf-8"
        )

        xml = replace_all_placeholders(
            xml,
            data,
        )

        files[name] = xml.encode(
            "utf-8"
        )

    # --------------------------------------------------------
    # Collect processed XML
    # --------------------------------------------------------

    all_xml_parts = []

    for name in xml_names:

        xml = files[name].decode(
            "utf-8"
        )

        all_xml_parts.append(
            xml
        )

    # --------------------------------------------------------
    # Check remaining placeholders
    # --------------------------------------------------------

    remaining = []

    for xml in all_xml_parts:

        remaining.extend(
            find_remaining_placeholders(
                xml
            )
        )

    remaining = sorted(
        set(remaining)
    )

    if remaining:

        raise ValueError(
            "Unmapped placeholders remain: "
            + ", ".join(remaining)
        )

    # --------------------------------------------------------
    # Check locked fields
    # --------------------------------------------------------

    missing_locked = (
        verify_locked_fields(
            all_xml_parts
        )
    )

    if missing_locked:

        raise ValueError(
            "A locked field was changed "
            "or removed: "
            + ", ".join(missing_locked)
        )

    # --------------------------------------------------------
    # Check customer fields
    # --------------------------------------------------------

    failed_customer_fields = (
        verify_customer_fields(
            all_xml_parts,
            data,
        )
    )

    if failed_customer_fields:

        raise ValueError(
            "Customer data verification failed: "
            + ", ".join(
                failed_customer_fields
            )
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

        output = Path(
            output
        )

        output.parent.mkdir(
            parents=True,
            exist_ok=True
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

        xml_parts = []

        for name in archive.namelist():

            if (
                name.startswith("word/")
                and name.endswith(".xml")
            ):

                xml_parts.append(
                    archive.read(
                        name
                    ).decode(
                        "utf-8"
                    )
                )

    # --------------------------------------------------------
    # Customer verification
    # --------------------------------------------------------

    failed = verify_customer_fields(
        xml_parts,
        data,
    )

    if failed:

        raise ValueError(
            "Final DOCX verification failed for: "
            + ", ".join(failed)
        )

    # --------------------------------------------------------
    # Locked-field verification
    # --------------------------------------------------------

    missing_locked = (
        verify_locked_fields(
            xml_parts
        )
    )

    if missing_locked:

        raise ValueError(
            "Final DOCX verification failed. "
            "Locked field missing: "
            + ", ".join(
                missing_locked
            )
        )

    # --------------------------------------------------------
    # Placeholder verification
    # --------------------------------------------------------

    remaining = []

    for xml in xml_parts:

        remaining.extend(
            find_remaining_placeholders(
                xml
            )
        )

    remaining = sorted(
        set(remaining)
    )

    if remaining:

        raise ValueError(
            "Final DOCX still contains placeholders: "
            + ", ".join(
                remaining
            )
        )

    return True
