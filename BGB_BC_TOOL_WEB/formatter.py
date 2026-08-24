import io
import re
import zipfile
from pathlib import Path

# Only these placeholders are allowed to change.
PLACEHOLDERS = {
    "{{ACCOUNT_NO}}": "account_number",
    "{{CUSTOMER_ID}}": "customer_id",
    "{{NAME}}": "name",
    "{{ADDRESS}}": "address",
    "{{PIN_CODE}}": "pin_code",
}

# These fields are locked and must remain exactly as in the template.
FIXED_VALUES = {
    "BRANCH - JORJA",
    "PUNB0MBGB06",
    "RAVISH KUMAR SAH",
    "PAGHARI CHOWK, 847105",
}


def _escape_xml(value):
    return (
        str(value)
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
        .replace("'", "&apos;")
    )


def _replace_placeholder_in_paragraph(paragraph_xml, token, value):
    """Replace a token even when Word split it across multiple text runs."""
    nodes = list(re.finditer(
        r"<w:t([^>]*)>(.*?)</w:t>",
        paragraph_xml,
        re.I | re.S
    ))
    if not nodes:
        return paragraph_xml, False

    visible = ""
    spans = []
    for node in nodes:
        content = re.sub(r"<[^>]+>", "", node.group(2))
        start = len(visible)
        visible += content
        spans.append((start, len(visible), node))

    pos = visible.find(token)
    if pos < 0:
        return paragraph_xml, False

    end = pos + len(token)
    touched = [
        node for start, stop, node in spans
        if stop > pos and start < end
    ]
    if not touched:
        return paragraph_xml, False

    first = touched[0]
    last = touched[-1]

    first_start = next(
        start for start, stop, node in spans if node is first
    )
    last_stop = next(
        stop for start, stop, node in spans if node is last
    )

    replacement = (
        visible[first_start:pos]
        + str(value)
        + visible[end:last_stop]
    )

    first_xml = (
        f"<w:t{first.group(1)}>{_escape_xml(replacement)}</w:t>"
    )

    replacements = []
    for node in touched:
        if node is first:
            replacements.append((node.start(), node.end(), first_xml))
        else:
            replacements.append((
                node.start(),
                node.end(),
                f"<w:t{node.group(1)}></w:t>"
            ))

    for start, stop, repl in reversed(replacements):
        paragraph_xml = paragraph_xml[:start] + repl + paragraph_xml[stop:]

    return paragraph_xml, True


def _replace_all_placeholders(xml, data):
    paragraphs = list(re.finditer(
        r"<w:p\b.*?</w:p>",
        xml,
        re.I | re.S
    ))

    for pm in reversed(paragraphs):
        paragraph = pm.group(0)

        for token, key in PLACEHOLDERS.items():
            while token in paragraph:
                new_paragraph, changed = _replace_placeholder_in_paragraph(
                    paragraph, token, data[key]
                )
                if not changed:
                    break
                paragraph = new_paragraph

        if paragraph != pm.group(0):
            xml = xml[:pm.start()] + paragraph + xml[pm.end():]

    return xml


def _remaining_placeholders(xml):
    return sorted(set(re.findall(r"\{\{[A-Z0-9_]+\}\}", xml)))


def build_docx(template_file, output, data):
    template_file = Path(template_file)

    if not template_file.exists():
        raise FileNotFoundError(f"Template not found: {template_file}")

    with zipfile.ZipFile(template_file, "r") as zin:
        files = {name: zin.read(name) for name in zin.namelist()}

    xml = files["word/document.xml"].decode("utf-8")

    # Make sure the template really has the mapping the tool expects.
    missing = [token for token in PLACEHOLDERS if token not in xml]
    if missing:
        raise ValueError(
            "Template mapping missing: " + ", ".join(missing)
        )

    # Replace ONLY {{...}} fields.
    xml = _replace_all_placeholders(xml, data)

    remaining = _remaining_placeholders(xml)
    if remaining:
        raise ValueError(
            "Unmapped placeholders remain: " + ", ".join(remaining)
        )

    # Safety lock: fixed fields must still be present.
    for fixed in FIXED_VALUES:
        if fixed not in xml:
            raise ValueError(
                f"Fixed field was changed or removed: {fixed}"
            )

    files["word/document.xml"] = xml.encode("utf-8")

    if hasattr(output, "write"):
        with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as zout:
            for name, content in files.items():
                zout.writestr(name, content)
    else:
        output = Path(output)
        output.parent.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as zout:
            for name, content in files.items():
                zout.writestr(name, content)


def verify_result(docx_bytes, data):
    with zipfile.ZipFile(io.BytesIO(docx_bytes), "r") as z:
        xml = z.read("word/document.xml").decode("utf-8")

    for value in (
        data["account_number"],
        data["customer_id"],
        data["name"],
        data["address"],
        data["pin_code"],
    ):
        if value not in xml:
            raise ValueError("Final DOCX verification failed.")

    for fixed in FIXED_VALUES:
        if fixed not in xml:
            raise ValueError(
                f"Final DOCX verification failed: fixed field missing: {fixed}"
            )

    if _remaining_placeholders(xml):
        raise ValueError("Final DOCX still contains an unmapped placeholder.")

    return True
