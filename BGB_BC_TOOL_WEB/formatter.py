import io
import re
import zipfile
from pathlib import Path


# ============================================================
# FIELDS WHICH ARE ALLOWED TO CHANGE
# ============================================================

PLACEHOLDER_FIELDS = {
    "ACCOUNT_NO": "account_number",
    "ACCOUNT NUMBER": "account_number",

    "CUSTOMER_ID": "customer_id",
    "CUSTOMER ID": "customer_id",

    "NAME": "name",

    "ADDRESS": "address",

    "PIN_CODE": "pin_code",
    "PIN CODE": "pin_code",
}


# ============================================================
# LOCKED / FIXED TEMPLATE VALUES
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
    value = "" if value is None else str(value)

    return (
        value
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

    # Normalize dash characters
    for dash in "‐-‒–—―−﹘﹣－":
        text = text.replace(dash, "-")

    # Normalize whitespace
    text = re.sub(r"\s+", " ", text)

    return text.strip().upper()


# ============================================================
# CLEAN CUSTOMER DATA
# ============================================================

def clean_customer_data(data):
    cleaned = dict(data)

    for key in [
        "account_number",
        "customer_id",
        "name",
        "address",
        "pin_code",
    ]:
        value = cleaned.get(key, "")

        if value is None:
            value = ""

        value = str(value).strip()

        # Remove unwanted address fragment specifically requested.
        if key == "address":
            value = re.sub(
                r"\s*,?\s*01716\s*,?\s*195\b",
                "",
                value,
                flags=re.IGNORECASE,
            )

            value = re.sub(
                r"\s{2,}",
                " ",
                value,
            )

            value = re.sub(
                r"\s+,",
                ",",
                value,
            )

            value = re.sub(
                r",\s*,",
                ",",
                value,
            )

            value = value.strip(" ,")

        cleaned[key] = value

    return cleaned


# ============================================================
# WORD XML TEXT NODES
# ============================================================

TEXT_NODE_RE = re.compile(
    r"<w:t\b([^>]*)>(.*?)</w:t>",
    flags=re.IGNORECASE | re.DOTALL,
)


def get_text_nodes(xml):
    return list(TEXT_NODE_RE.finditer(xml))


# ============================================================
# GET VISIBLE WORD TEXT
# ============================================================

def get_visible_text(xml):
    parts = []

    for node in get_text_nodes(xml):
        parts.append(node.group(2))

    return normalize_text("".join(parts))


# ============================================================
# PLACEHOLDER REGEX
#
# Handles:
# {{CUSTOMER_ID}}
# {{ CUSTOMER_ID }}
# {{CUSTOMER ID}}
# {{ CUSTOMER ID }}
# ============================================================

def placeholder_regex(field_name):
    field_name = field_name.replace("_", r"[\s_]*")

    return re.compile(
        r"\{\{\s*"
        + field_name
        + r"\s*\}\}",
        flags=re.IGNORECASE,
    )


# ============================================================
# REPLACE PLACEHOLDER
#
# Works even when Word has split the placeholder over
# multiple <w:t> runs.
# ============================================================

def replace_placeholder(xml, field_name, replacement):
    nodes = get_text_nodes(xml)

    if not nodes:
        return xml, False

    # --------------------------------------------------------
    # Build visible text from all runs
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

    pattern = placeholder_regex(field_name)

    match = pattern.search(visible)

    if not match:
        return xml, False

    position = match.start()
    end_position = match.end()

    # --------------------------------------------------------
    # Find all runs affected by placeholder
    # --------------------------------------------------------

    affected = []

    for node, start, end in ranges:
        if end > position and start < end_position:
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

    prefix_length = position - first_start

    prefix = first_text[:prefix_length]

    # --------------------------------------------------------
    # Preserve text after placeholder
    # --------------------------------------------------------

    suffix_start = end_position - last_start

    suffix = last_text[suffix_start:]

    # --------------------------------------------------------
    # New text
    # --------------------------------------------------------

    new_text = (
        prefix
        + str(replacement)
        + suffix
    )

    new_text = escape_xml(new_text)

    replacements = []

    # --------------------------------------------------------
    # Put replacement into first affected run
    # --------------------------------------------------------

    replacements.append(
        (
            first_node.start(),
            first_node.end(),
            (
                "<w:t"
                + first_node.group(1)
                + ">"
                + new_text
                + "</w:t>"
            ),
        )
    )

    # --------------------------------------------------------
    # Clear remaining affected runs
    # --------------------------------------------------------

    for node, _, _ in affected[1:]:
        replacements.append(
            (
                node.start(),
                node.end(),
                (
                    "<w:t"
                    + node.group(1)
                    + "></w:t>"
                ),
            )
        )

    # --------------------------------------------------------
    # Apply replacements backwards
    # --------------------------------------------------------

    for start, end, replacement_xml in reversed(
        replacements
    ):
        xml = (
            xml[:start]
            + replacement_xml
            + xml[end:]
        )

    return xml, True


# ============================================================
# REPLACE ALL SUPPORTED PLACEHOLDERS
# ============================================================

def replace_all_placeholders(xml, data):
    changed_any = False

    for field_name, data_key in PLACEHOLDER_FIELDS.items():

        # Continue until no matching placeholder remains.
        while True:

            new_xml, changed = replace_placeholder(
                xml,
                field_name,
                data[data_key],
            )

            if not changed:
                break

            xml = new_xml
            changed_any = True

    return xml, changed_any


# ============================================================
# FIND REMAINING PLACEHOLDERS
# ============================================================

def find_remaining_placeholders(xml):
    visible = get_visible_text(xml)

    matches = re.findall(
        r"\{\{\s*[A-Z0-9_ ]+\s*\}\}",
        visible,
        flags=re.IGNORECASE,
    )

    return sorted(
        set(
            normalize_text(x)
            for x in matches
        )
    )


# ============================================================
# COLLECT ALL WORD XML PARTS
# ============================================================

def get_word_xml_names(files):
    return [
        name
        for name in files
        if (
            name.startswith("word/")
            and name.endswith(".xml")
        )
    ]


# ============================================================
# COMBINE VISIBLE TEXT
# ============================================================

def combined_visible_text(xml_parts):
    return normalize_text(
        " ".join(
            get_visible_text(xml)
            for xml in xml_parts
        )
    )


# ============================================================
# VERIFY LOCKED FIELDS
# ============================================================

def verify_locked_fields(xml_parts):
    complete_text = combined_visible_text(
        xml_parts
    )

    missing = []

    for fixed in FIXED_VALUES:

        expected = normalize_text(fixed)

        if expected not in complete_text:
            missing.append(fixed)

    return missing


# ============================================================
# VERIFY CUSTOMER FIELDS
# ============================================================

def verify_customer_fields(xml_parts, data):
    complete_text = combined_visible_text(
        xml_parts
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
            data.get(field, "")
        )

        if not expected:
            failed.append(field)
            continue

        if expected not in complete_text:
            failed.append(field)

    return failed


# ============================================================
# WRITE DOCX
# ============================================================

def write_docx(files, output):
    if hasattr(output, "write"):

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
# BUILD DOCX
# ============================================================

def build_docx(template_file, output, data):

    template_file = Path(template_file)

    if not template_file.exists():
        raise FileNotFoundError(
            "Template not found: "
            + str(template_file)
        )

    # --------------------------------------------------------
    # Clean data first
    # --------------------------------------------------------

    data = clean_customer_data(data)

    # --------------------------------------------------------
    # Required fields
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

        if not str(data[field]).strip():
            raise ValueError(
                "Empty required field: "
                + field
            )

    # --------------------------------------------------------
    # Basic validation
    # --------------------------------------------------------

    if not re.fullmatch(
        r"\d{8,20}",
        str(data["account_number"]).strip(),
    ):
        raise ValueError(
            "Account Number validation failed."
        )

    if not re.fullmatch(
        r"[A-Z0-9]{6,30}",
        str(data["customer_id"]).strip(),
        flags=re.IGNORECASE,
    ):
        raise ValueError(
            "Customer ID validation failed."
        )

    if not re.fullmatch(
        r"\d{6}",
        str(data["pin_code"]).strip(),
    ):
        raise ValueError(
            "PIN Code validation failed."
        )

    # --------------------------------------------------------
    # Open original DOCX
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

    if "word/document.xml" not in files:
        raise ValueError(
            "Invalid DOCX: word/document.xml not found."
        )

    # --------------------------------------------------------
    # Process Word XML parts
    # --------------------------------------------------------

    xml_names = get_word_xml_names(files)

    if not xml_names:
        raise ValueError(
            "No Word XML document parts found."
        )

    for name in xml_names:

        try:
            xml = files[name].decode(
                "utf-8"
            )
        except UnicodeDecodeError as exc:
            raise ValueError(
                "Unable to decode Word XML: "
                + name
            ) from exc

        xml, _ = replace_all_placeholders(
            xml,
            data,
        )

        files[name] = xml.encode(
            "utf-8"
        )

    # --------------------------------------------------------
    # Collect processed XML
    # --------------------------------------------------------

    xml_parts = [
        files[name].decode("utf-8")
        for name in xml_names
    ]

    # --------------------------------------------------------
    # Remaining placeholders
    # --------------------------------------------------------

    remaining = []

    for xml in xml_parts:
        remaining.extend(
            find_remaining_placeholders(xml)
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
    # Locked field verification
    # --------------------------------------------------------

    missing_locked = verify_locked_fields(
        xml_parts
    )

    if missing_locked:
        raise ValueError(
            "A locked field was changed or removed: "
            + ", ".join(missing_locked)
        )

    # --------------------------------------------------------
    # Customer field verification
    # --------------------------------------------------------

    failed_customer_fields = verify_customer_fields(
        xml_parts,
        data,
    )

    if failed_customer_fields:
        raise ValueError(
            "Customer data verification failed: "
            + ", ".join(failed_customer_fields)
        )

    # --------------------------------------------------------
    # Write final DOCX
    # --------------------------------------------------------

    write_docx(
        files,
        output,
    )


# ============================================================
# FINAL DOCX VERIFICATION
# ============================================================

def verify_result(docx_bytes, data):

    data = clean_customer_data(data)

    try:

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

                    try:
                        xml_parts.append(
                            archive.read(
                                name
                            ).decode(
                                "utf-8"
                            )
                        )

                    except UnicodeDecodeError:
                        continue

    except zipfile.BadZipFile as exc:

        raise ValueError(
            "Generated DOCX is not a valid ZIP/DOCX file."
        ) from exc

    if not xml_parts:
        raise ValueError(
            "Final DOCX contains no Word XML parts."
        )

    # --------------------------------------------------------
    # Verify customer data
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
    # Verify locked fields
    # --------------------------------------------------------

    missing_locked = verify_locked_fields(
        xml_parts
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

    remaining = []

    for xml in xml_parts:
        remaining.extend(
            find_remaining_placeholders(xml)
        )

    remaining = sorted(
        set(remaining)
    )

    if remaining:
        raise ValueError(
            "Final DOCX still contains placeholders: "
            + ", ".join(remaining)
        )

    return True
