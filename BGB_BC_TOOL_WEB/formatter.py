import io
import re
import zipfile
from pathlib import Path


# ============================================================
# ALLOWED TEMPLATE PLACEHOLDERS
# ============================================================

PLACEHOLDERS = {
    "{{FIELD_1}}": "field_1",
    "{{FIELD_2}}": "field_2",
    "{{FIELD_3}}": "field_3",
    "{{FIELD_4}}": "field_4",
    "{{FIELD_5}}": "field_5",
}


# ============================================================
# XML TEXT NODE REGEX
# ============================================================

TEXT_NODE_RE = re.compile(
    r"<w:t\b([^>]*)>(.*?)</w:t>",
    flags=re.IGNORECASE | re.DOTALL,
)


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
# XML UNESCAPE / NORMALIZE
# ============================================================

def normalize_text(value):
    if value is None:
        return ""

    text = str(value)

    text = (
        text
        .replace("&amp;", "&")
        .replace("&lt;", "<")
        .replace("&gt;", ">")
        .replace("&quot;", '"')
        .replace("&apos;", "'")
        .replace("\xa0", " ")
    )

    text = re.sub(r"\s+", " ", text)

    return text.strip()


# ============================================================
# GET TEXT NODES
# ============================================================

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
# ============================================================

def placeholder_pattern(placeholder):
    name = placeholder.strip()

    if name.startswith("{{") and name.endswith("}}"):
        name = name[2:-2]

    name = re.escape(name)

    # Permit spaces/underscores between words.
    name = name.replace(r"\_", r"[\s_]*")

    return re.compile(
        r"\{\{\s*"
        + name
        + r"\s*\}\}",
        flags=re.IGNORECASE,
    )


# ============================================================
# REPLACE ONE PLACEHOLDER
#
# Works even when Word splits the placeholder across
# multiple <w:r>/<w:t> nodes.
# ============================================================

def replace_placeholder(xml, placeholder, replacement):

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
            (
                node,
                start,
                end,
            )
        )

    pattern = placeholder_pattern(placeholder)

    match = pattern.search(visible)

    if not match:
        return xml, False

    start_pos = match.start()
    end_pos = match.end()

    affected = []

    for node, start, end in ranges:
        if end > start_pos and start < end_pos:
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

    prefix_length = start_pos - first_start

    prefix = first_text[:prefix_length]

    suffix_start = end_pos - last_start

    suffix = last_text[suffix_start:]

    replacement_text = (
        prefix
        + str(replacement)
        + suffix
    )

    replacement_text = escape_xml(
        replacement_text
    )

    changes = []

    changes.append(
        (
            first_node.start(),
            first_node.end(),
            (
                "<w:t"
                + first_node.group(1)
                + ">"
                + replacement_text
                + "</w:t>"
            ),
        )
    )

    for node, _, _ in affected[1:]:
        changes.append(
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

    for start, end, new_xml in reversed(changes):
        xml = (
            xml[:start]
            + new_xml
            + xml[end:]
        )

    return xml, True


# ============================================================
# REPLACE ALL ALLOWED PLACEHOLDERS
# ============================================================

def replace_all_placeholders(xml, data):

    for placeholder, field in PLACEHOLDERS.items():

        value = data.get(field, "")

        while True:

            new_xml, changed = replace_placeholder(
                xml,
                placeholder,
                value,
            )

            if not changed:
                break

            xml = new_xml

    return xml


# ============================================================
# FIND ANY REMAINING PLACEHOLDERS
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
# GET WORD XML PARTS
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
# COMBINE XML TEXT
# ============================================================

def combined_visible_text(xml_parts):

    return normalize_text(
        " ".join(
            get_visible_text(xml)
            for xml in xml_parts
        )
    )


# ============================================================
# VERIFY CUSTOMER/TEMPLATE DATA
# ============================================================

def verify_customer_fields(xml_parts, data):

    document_text = combined_visible_text(
        xml_parts
    )

    failed = []

    for field in PLACEHOLDERS.values():

        expected = normalize_text(
            data.get(field, "")
        )

        if not expected:
            failed.append(field)
            continue

        if expected not in document_text:
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

        return

    output_path = Path(output)

    output_path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    with zipfile.ZipFile(
        output_path,
        "w",
        zipfile.ZIP_DEFLATED,
    ) as destination:

        for name, content in files.items():
            destination.writestr(
                name,
                content,
            )


# ============================================================
# VALIDATE INPUT DATA
# ============================================================

def validate_data(data):

    if not isinstance(data, dict):
        raise ValueError(
            "Data must be a dictionary."
        )

    for field in PLACEHOLDERS.values():

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

    validate_data(data)

    # --------------------------------------------------------
    # Read DOCX ZIP
    # --------------------------------------------------------

    try:

        with zipfile.ZipFile(
            template_file,
            "r",
        ) as source:

            if (
                "word/document.xml"
                not in source.namelist()
            ):
                raise ValueError(
                    "Invalid DOCX: "
                    "word/document.xml not found."
                )

            files = {
                name: source.read(name)
                for name in source.namelist()
            }

    except zipfile.BadZipFile as exc:

        raise ValueError(
            "Template is not a valid DOCX file."
        ) from exc

    # --------------------------------------------------------
    # Find Word XML files
    # --------------------------------------------------------

    xml_names = get_word_xml_names(
        files
    )

    if not xml_names:
        raise ValueError(
            "No Word XML parts found."
        )

    # --------------------------------------------------------
    # Replace placeholders
    # --------------------------------------------------------

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

    xml_parts = []

    for name in xml_names:

        xml_parts.append(
            files[name].decode(
                "utf-8"
            )
        )

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
            + ", ".join(remaining)
        )

    # --------------------------------------------------------
    # Verify inserted data
    # --------------------------------------------------------

    failed = verify_customer_fields(
        xml_parts,
        data,
    )

    if failed:
        raise ValueError(
            "Document verification failed: "
            + ", ".join(failed)
        )

    # --------------------------------------------------------
    # Write final DOCX
    # --------------------------------------------------------

    write_docx(
        files,
        output,
    )

    return True


# ============================================================
# FINAL DOCX VERIFICATION
# ============================================================

def verify_result(
    docx_bytes,
    data,
):

    if not docx_bytes:
        raise ValueError(
            "Empty DOCX data."
        )

    try:

        with zipfile.ZipFile(
            io.BytesIO(docx_bytes),
            "r",
        ) as archive:

            names = archive.namelist()

            if "word/document.xml" not in names:
                raise ValueError(
                    "Final DOCX is invalid: "
                    "word/document.xml missing."
                )

            xml_parts = []

            for name in names:

                if (
                    name.startswith("word/")
                    and name.endswith(".xml")
                ):

                    try:
                        xml = archive.read(
                            name
                        ).decode(
                            "utf-8"
                        )
                    except UnicodeDecodeError as exc:
                        raise ValueError(
                            "Unable to decode final XML: "
                            + name
                        ) from exc

                    xml_parts.append(xml)

    except zipfile.BadZipFile as exc:

        raise ValueError(
            "Generated file is not a valid DOCX."
        ) from exc

    # --------------------------------------------------------
    # Check placeholders
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
            + ", ".join(remaining)
        )

    # --------------------------------------------------------
    # Check inserted values
    # --------------------------------------------------------

    failed = verify_customer_fields(
        xml_parts,
        data,
    )

    if failed:
        raise ValueError(
            "Final DOCX verification failed: "
            + ", ".join(failed)
        )

    return True
