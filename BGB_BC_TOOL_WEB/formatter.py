import io
import re
import zipfile
from pathlib import Path


# ============================================================
# ALLOWED CUSTOMER FIELDS
# ============================================================

PLACEHOLDERS = {
    "{{ACCOUNT_NO}}": "account_number",
    "{{CUSTOMER_ID}}": "customer_id",
    "{{NAME}}": "name",
    "{{ADDRESS}}": "address",
    "{{PIN_CODE}}": "pin_code",
}


# ============================================================
# LOCKED TEMPLATE VALUES
# THESE MUST NEVER CHANGE
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
    if value is None:
        value = ""

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

    # Normalize different dash characters
    for dash in "‐-‒–—―−﹘﹣－":
        text = text.replace(dash, "-")

    # Normalize whitespace
    text = re.sub(r"\s+", " ", text)

    return text.strip().upper()


# ============================================================
# COMPACT TEXT
#
# Used for IDs / account numbers / PIN.
# Removes spaces and punctuation ONLY for verification.
# It does NOT modify the actual DOCX value.
# ============================================================

def compact_text(value):
    if value is None:
        return ""

    return re.sub(
        r"[^A-Z0-9]",
        "",
        str(value).upper(),
    )


# ============================================================
# GET WORD TEXT NODES
# ============================================================

TEXT_NODE_RE = re.compile(
    r"<w:t\b([^>]*)>(.*?)</w:t>",
    flags=re.IGNORECASE | re.DOTALL,
)


def get_text_nodes(xml):
    return list(
        TEXT_NODE_RE.finditer(xml)
    )


# ============================================================
# GET VISIBLE TEXT
# ============================================================

def get_visible_text(xml):
    parts = []

    for node in get_text_nodes(xml):
        parts.append(node.group(2))

    return normalize_text(
        "".join(parts)
    )


# ============================================================
# PLACEHOLDER PATTERN
#
# Handles:
#
# {{CUSTOMER_ID}}
# {{ CUSTOMER_ID }}
# {{CUSTOMER ID}}
# {{ CUSTOMER ID }}
#
# ============================================================

def placeholder_pattern(name):

    name = name.replace(
        "_",
        r"[\s_]*",
    )

    return re.compile(
        r"\{\{\s*"
        + name
        + r"\s*\}\}",
        flags=re.IGNORECASE,
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
    # Build visible text
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

    pattern = placeholder_pattern(
        placeholder.strip("{} ")
    )

    match = pattern.search(
        visible
    )

    if not match:
        return xml, False

    position = match.start()

    end_position = match.end()

    # --------------------------------------------------------
    # Find affected Word runs
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

    first_node = affected[0][0]
    first_start = affected[0][1]

    last_node = affected[-1][0]
    last_start = affected[-1][1]

    first_text = first_node.group(2)
    last_text = last_node.group(2)

    # --------------------------------------------------------
    # Text before placeholder
    # --------------------------------------------------------

    prefix_length = (
        position
        - first_start
    )

    prefix = first_text[
        :prefix_length
    ]

    # --------------------------------------------------------
    # Text after placeholder
    # --------------------------------------------------------

    suffix_start = (
        end_position
        - last_start
    )

    suffix = last_text[
        suffix_start:
    ]

    # --------------------------------------------------------
    # Replacement content
    # --------------------------------------------------------

    new_text = (
        prefix
        + str(replacement)
        + suffix
    )

    new_text = escape_xml(
        new_text
    )

    replacements = []

    # --------------------------------------------------------
    # First affected run
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
# REPLACE ALL PLACEHOLDERS
# ============================================================

def replace_all_placeholders(
    xml,
    data,
):

    for placeholder, field in PLACEHOLDERS.items():

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

    matches = re.findall(
        r"\{\{\s*[A-Z0-9_ ]+\s*\}\}",
        visible,
        flags=re.IGNORECASE,
    )

    return sorted(
        set(matches)
    )


# ============================================================
# CLEAN ADDRESS
# ============================================================

def clean_address(address):

    if address is None:
        return ""

    address = str(address)

    # Remove ONLY the unwanted AOF fragment
    address = re.sub(
        r"\b01716\s*,\s*195\b",
        "",
        address,
        flags=re.IGNORECASE,
    )

    # Clean spaces
    address = re.sub(
        r"[ \t]{2,}",
        " ",
        address,
    )

    # Clean comma spacing
    address = re.sub(
        r"\s*,\s*",
        ", ",
        address,
    )

    address = re.sub(
        r",\s*,+",
        ", ",
        address,
    )

    address = re.sub(
        r",\s*$",
        "",
        address,
    )

    return address.strip()


# ============================================================
# CLEAN DATA
# ============================================================

def clean_data(data):

    result = dict(data)

    for key in [
        "account_number",
        "customer_id",
        "name",
        "address",
        "pin_code",
    ]:

        value = result.get(
            key,
            "",
        )

        if value is None:
            value = ""

        value = str(value).strip()

        if key == "address":
            value = clean_address(
                value
            )

        result[key] = value

    return result


# ============================================================
# GET ALL WORD XML FILES
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

def combined_visible_text(
    xml_parts,
):

    return normalize_text(
        " ".join(
            get_visible_text(xml)
            for xml in xml_parts
        )
    )


# ============================================================
# VERIFY LOCKED FIELDS
# ============================================================

def verify_locked_fields(
    xml_parts,
):

    complete_text = (
        combined_visible_text(
            xml_parts
        )
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
#
# IMPORTANT:
# Customer ID is checked using compact comparison.
# This fixes Word run/spacing issues.
# ============================================================

def verify_customer_fields(
    xml_parts,
    data,
):

    complete_text = (
        combined_visible_text(
            xml_parts
        )
    )

    compact_document = compact_text(
        complete_text
    )

    failed = []

    # --------------------------------------------------------
    # ACCOUNT NUMBER
    # --------------------------------------------------------

    expected_account = compact_text(
        data.get(
            "account_number",
            "",
        )
    )

    if (
        not expected_account
        or expected_account
        not in compact_document
    ):

        failed.append(
            "account_number"
        )

    # --------------------------------------------------------
    # CUSTOMER ID
    # --------------------------------------------------------

    expected_customer_id = compact_text(
        data.get(
            "customer_id",
            "",
        )
    )

    if (
        not expected_customer_id
        or expected_customer_id
        not in compact_document
    ):

        failed.append(
            "customer_id"
        )

    # --------------------------------------------------------
    # NAME
    # --------------------------------------------------------

    expected_name = normalize_text(
        data.get(
            "name",
            "",
        )
    )

    if (
        not expected_name
        or expected_name
        not in complete_text
    ):

        failed.append(
            "name"
        )

    # --------------------------------------------------------
    # ADDRESS
    # --------------------------------------------------------

    expected_address = normalize_text(
        clean_address(
            data.get(
                "address",
                "",
            )
        )
    )

    if (
        not expected_address
        or expected_address
        not in complete_text
    ):

        failed.append(
            "address"
        )

    # --------------------------------------------------------
    # PIN CODE
    # --------------------------------------------------------

    expected_pin = compact_text(
        data.get(
            "pin_code",
            "",
        )
    )

    if (
        not expected_pin
        or expected_pin
        not in compact_document
    ):

        failed.append(
            "pin_code"
        )

    return failed


# ============================================================
# WRITE DOCX
# ============================================================

def write_docx(
    files,
    output,
):

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

def build_docx(
    template_file,
    output,
    data,
):

    template_file = Path(
        template_file
    )

    # --------------------------------------------------------
    # Template exists?
    # --------------------------------------------------------

    if not template_file.exists():

        raise FileNotFoundError(
            "Template not found: "
            + str(template_file)
        )

    # --------------------------------------------------------
    # Clean input data
    # --------------------------------------------------------

    data = clean_data(
        data
    )

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

        if not str(
            data[field]
        ).strip():

            raise ValueError(
                "Empty required field: "
                + field
            )

    # --------------------------------------------------------
    # Account number validation
    # --------------------------------------------------------

    if not re.fullmatch(
        r"\d{8,20}",
        data["account_number"],
    ):

        raise ValueError(
            "Account Number validation failed."
        )

    # --------------------------------------------------------
    # Customer ID validation
    # --------------------------------------------------------

    if not re.fullmatch(
        r"[A-Z0-9]{6,30}",
        data["customer_id"],
        flags=re.IGNORECASE,
    ):

        raise ValueError(
            "Customer ID validation failed."
        )

    # --------------------------------------------------------
    # PIN validation
    # --------------------------------------------------------

    if not re.fullmatch(
        r"\d{6}",
        data["pin_code"],
    ):

        raise ValueError(
            "PIN Code validation failed."
        )

    # --------------------------------------------------------
    # Open template
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
    # DOCX validation
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
    # Find Word XML parts
    # --------------------------------------------------------

    xml_names = (
        get_word_xml_names(
            files
        )
    )

    if not xml_names:

        raise ValueError(
            "No Word XML parts found."
        )

    # --------------------------------------------------------
    # Replace only allowed placeholders
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

    xml_parts = [
        files[name].decode(
            "utf-8"
        )
        for name in xml_names
    ]

    # --------------------------------------------------------
    # Check remaining placeholders
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
            "Unmapped placeholders remain: "
            + ", ".join(
                remaining
            )
        )

    # --------------------------------------------------------
    # LOCKED FIELD CHECK
    # --------------------------------------------------------

    missing_locked = (
        verify_locked_fields(
            xml_parts
        )
    )

    if missing_locked:

        raise ValueError(
            "A locked field was changed "
            "or removed: "
            + ", ".join(
                missing_locked
            )
        )

    # --------------------------------------------------------
    # CUSTOMER DATA CHECK
    # --------------------------------------------------------

    failed_customer_fields = (
        verify_customer_fields(
            xml_parts,
            data,
        )
    )

    if failed_customer_fields:

        raise ValueError(
            "Customer data verification failed: "
            + ", ".join(
                failed_customer_fields
            )
