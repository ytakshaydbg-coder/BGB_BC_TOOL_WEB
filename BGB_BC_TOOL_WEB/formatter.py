import io
import re
import zipfile
from pathlib import Path


# ============================================================
# DEMO DOCX FORMATTER
# ============================================================
# Supports placeholders such as:
# {{ACCOUNT_NO}}
# {{ ACCOUNT NO }}
# {{CUSTOMER_ID}}
# {{ CUSTOMER ID }}
# {{NAME}}
# {{ ADDRESS }}
# {{PIN_CODE}}
# {{ PIN CODE }}
#
# This version is intended for DEMO / TEST templates only.
# ============================================================


PLACEHOLDERS = {
    "ACCOUNT_NO": "account_number",
    "CUSTOMER_ID": "customer_id",
    "NAME": "name",
    "ADDRESS": "address",
    "PIN_CODE": "pin_code",
}


DEMO_MARKER = "DEMO — NOT A VALID BANK DOCUMENT"


# ============================================================
# TEXT HELPERS
# ============================================================

def normalize_text(value):
    if value is None:
        return ""

    value = str(value)

    value = (
        value
        .replace("&amp;", "&")
        .replace("&lt;", "<")
        .replace("&gt;", ">")
        .replace("&quot;", '"')
        .replace("&apos;", "'")
        .replace("\xa0", " ")
    )

    value = re.sub(r"\s+", " ", value)

    return value.strip().upper()


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


def clean_address(value):
    if value is None:
        return ""

    value = str(value)

    # Remove the unwanted fragment mentioned in your example.
    value = re.sub(
        r"\b01716\s*,\s*195\b",
        "",
        value,
        flags=re.IGNORECASE,
    )

    value = re.sub(r"\s+", " ", value)
    value = re.sub(r"\s*,\s*", ", ", value)
    value = re.sub(r",\s*,+", ", ", value)
    value = re.sub(r",\s*$", "", value)

    return value.strip()


def clean_data(data):
    result = {}

    for key in (
        "account_number",
        "customer_id",
        "name",
        "address",
        "pin_code",
    ):
        value = data.get(key, "")

        if value is None:
            value = ""

        value = str(value).strip()

        if key == "address":
            value = clean_address(value)

        result[key] = value

    return result


# ============================================================
# WORD XML
# ============================================================

TEXT_NODE_RE = re.compile(
    r"<w:t\b([^>]*)>(.*?)</w:t>",
    re.IGNORECASE | re.DOTALL,
)


def get_text_nodes(xml):
    return list(TEXT_NODE_RE.finditer(xml))


def get_visible_text(xml):
    return normalize_text(
        "".join(
            node.group(2)
            for node in get_text_nodes(xml)
        )
    )


# ============================================================
# PLACEHOLDER REGEX
# ============================================================

def make_placeholder_regex(name):
    """
    CUSTOMER_ID matches:

        {{CUSTOMER_ID}}
        {{ CUSTOMER_ID }}
        {{CUSTOMER ID}}
        {{ CUSTOMER ID }}
    """

    parts = name.split("_")

    body = r"[\s_]+".join(
        re.escape(part)
        for part in parts
    )

    return re.compile(
        r"\{\{\s*"
        + body
        + r"\s*\}\}",
        re.IGNORECASE,
    )


# ============================================================
# REPLACE PLACEHOLDER
# ============================================================

def replace_placeholder(xml, placeholder_name, replacement):

    nodes = get_text_nodes(xml)

    if not nodes:
        return xml, False

    visible = ""
    ranges = []

    for node in nodes:
        text = node.group(2)

        start = len(visible)
        visible += text
        end = len(visible)

        ranges.append(
            (node, start, end)
        )

    pattern = make_placeholder_regex(
        placeholder_name
    )

    match = pattern.search(visible)

    if not match:
        return xml, False

    start_pos = match.start()
    end_pos = match.end()

    affected = []

    for node, start, end in ranges:

        if (
            end > start_pos
            and start < end_pos
        ):
            affected.append(
                (node, start, end)
            )

    if not affected:
        return xml, False

    first_node = affected[0][0]
    first_start = affected[0][1]

    last_node = affected[-1][0]
    last_start = affected[-1][1]

    first_text = first_node.group(2)
    last_text = last_node.group(2)

    prefix_length = (
        start_pos - first_start
    )

    prefix = first_text[
        :prefix_length
    ]

    suffix_start = (
        end_pos - last_start
    )

    suffix = last_text[
        suffix_start:
    ]

    new_text = (
        prefix
        + str(replacement)
        + suffix
    )

    new_text = escape_xml(new_text)

    replacements = []

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
# REPLACE ALL CUSTOMER PLACEHOLDERS
# ============================================================

def replace_all_placeholders(xml, data):

    for placeholder_name, field in PLACEHOLDERS.items():

        replacement = data.get(field, "")

        # Replace repeatedly in case the same
        # placeholder appears multiple times.
        while True:

            xml, changed = replace_placeholder(
                xml,
                placeholder_name,
                replacement,
            )

            if not changed:
                break

    return xml


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

    return sorted(set(matches))


# ============================================================
# WORD XML FILES
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


def get_xml_parts(files):

    names = get_word_xml_names(files)

    return [
        files[name].decode("utf-8")
        for name in names
    ]


def combined_visible_text(xml_parts):

    return normalize_text(
        " ".join(
            get_visible_text(xml)
            for xml in xml_parts
        )
    )


# ============================================================
# CUSTOMER VERIFICATION
# ============================================================

def verify_customer_fields(xml_parts, data):

    complete_text = combined_visible_text(
        xml_parts
    )

    failed = []

    fields = (
        "account_number",
        "customer_id",
        "name",
        "address",
        "pin_code",
    )

    for field in fields:

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
        ) as archive:

            for name, content in files.items():

                archive.writestr(
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
        ) as archive:

            for name, content in files.items():

                archive.writestr(
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

    data = clean_data(data)

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

    # Basic demo-data validation.
    if not re.fullmatch(
        r"\d{8,20}",
        data["account_number"],
    ):
        raise ValueError(
            "Account Number validation failed."
        )

    if not re.fullmatch(
        r"[A-Z0-9]{6,30}",
        data["customer_id"],
        flags=re.IGNORECASE,
    ):
        raise ValueError(
            "Customer ID validation failed."
        )

    if not re.fullmatch(
        r"\d{6}",
        data["pin_code"],
    ):
        raise ValueError(
            "PIN Code validation failed."
        )

    # --------------------------------------------------------
    # Read template
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
            "Invalid DOCX: "
            "word/document.xml not found."
        )

    xml_names = get_word_xml_names(files)

    if not xml_names:

        raise ValueError(
            "No Word XML parts found."
        )

    # --------------------------------------------------------
    # Replace placeholders
    # --------------------------------------------------------

    for name in xml_names:

        xml = files[name].decode("utf-8")

        xml = replace_all_placeholders(
            xml,
            data,
        )

        files[name] = xml.encode("utf-8")

    # --------------------------------------------------------
    # Check placeholders
    # --------------------------------------------------------

    xml_parts = get_xml_parts(files)

    remaining = []

    for xml in xml_parts:

        remaining.extend(
            find_remaining_placeholders(xml)
        )

    remaining = sorted(set(remaining))

    if remaining:

        raise ValueError(
            "Unmapped placeholders remain: "
            + ", ".join(remaining)
        )

    # --------------------------------------------------------
    # Customer-data verification
    # --------------------------------------------------------

    failed = verify_customer_fields(
        xml_parts,
        data,
    )

    if failed:

        raise ValueError(
            "Customer data verification failed: "
            + ", ".join(failed)
        )

    # --------------------------------------------------------
    # Add DEMO marker to document text.
    # --------------------------------------------------------

    document_xml = files[
        "word/document.xml"
    ].decode("utf-8")

    marker_xml = (
        '<w:p>'
        '<w:r>'
        '<w:rPr><w:b/></w:rPr>'
        '<w:t>'
        + escape_xml(DEMO_MARKER)
        + '</w:t>'
        '</w:r>'
        '</w:p>'
    )

    document_xml = document_xml.replace(
        "</w:body>",
        marker_xml + "</w:body>",
        1,
    )

    files[
        "word/document.xml"
    ] = document_xml.encode("utf-8")

    # --------------------------------------------------------
    # Write output
    # --------------------------------------------------------

    write_docx(
        files,
        output,
    )


# ============================================================
# FINAL VERIFICATION
# ============================================================

def verify_result(docx_bytes, data):

    data = clean_data(data)

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
                    archive.read(name).decode(
                        "utf-8"
                    )
                )

    # --------------------------------------------------------
    # Placeholder check
    # --------------------------------------------------------

    remaining = []

    for xml in xml_parts:

        remaining.extend(
            find_remaining_placeholders(xml)
        )

    remaining = sorted(set(remaining))

    if remaining:

        raise ValueError(
            "Final DOCX still contains placeholders: "
            + ", ".join(remaining)
        )

    # --------------------------------------------------------
    # Customer-data check
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
    # DEMO marker check
    # --------------------------------------------------------

    complete_text = combined_visible_text(
        xml_parts
    )

    if normalize_text(DEMO_MARKER) not in complete_text:

        raise ValueError(
            "Demo safety marker is missing."
        )

    return True
