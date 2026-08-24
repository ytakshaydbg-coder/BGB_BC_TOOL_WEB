import io
import re
import zipfile
from pathlib import Path


# These values identify the customer-data positions in the supplied template.
# Fixed fields are intentionally absent from the replacement map.
TEMPLATE_MAP = {
    "account_number": "44530700004612",
    "customer_id": "R19580151",
    "name": "NEMO SAH",
    "pin_code": "847105",
}

FIXED_VALUES = {
    "branch": "BRANCH - JORJA",
    "ifsc": "PUNB0MBGB06",
    "ko_name": "RAVISH KUMAR SAH",
    "ko_location": "PAGHARI CHOWK, 847105",
}


def replace_text(xml, old, new):
    if not old or not new:
        return xml
    return xml.replace(old, new)


def replace_textbox_address(xml, address):
    # The supplied DOCX stores the passbook inside a VML textbox.
    # Its address is split across two paragraphs. We keep the paragraph/run
    # structure and replace only the visible address text.
    parts = re.split(r"(?<=,)\s+", address)
    if len(parts) < 2:
        line1, line2 = address, ""
    else:
        best = 1
        best_score = 10**9
        for i in range(1, len(parts)):
            left = " ".join(parts[:i])
            right = " ".join(parts[i:])
            score = abs(len(left) - len(right))
            if score < best_score:
                best_score = score
                best = i
        line1 = " ".join(parts[:best])
        line2 = " ".join(parts[best:])

    # Locate the paragraph that contains the existing first address line.
    p_matches = list(re.finditer(
        r"<w:p\b.*?</w:p>", xml, re.I | re.S
    ))

    address_index = None
    for i, m in enumerate(p_matches):
        p = m.group(0)
        if "W/O Rajeev" in p or "W/O Rajeev" in p.replace("&amp;", "&"):
            address_index = i
            break

    if address_index is None or address_index + 1 >= len(p_matches):
        raise ValueError("ADDRESS mapping target not found in template.")

    targets = [
        (p_matches[address_index], line1),
        (p_matches[address_index + 1], line2),
    ]

    # Work backwards to preserve XML offsets.
    for pm, new_line in reversed(targets):
        para = pm.group(0)

        nodes = list(re.finditer(
            r"<w:t([^>]*)>(.*?)</w:t>", para, re.I | re.S
        ))
        if not nodes:
            raise ValueError("Address text run not found in template.")

        # Preserve the first run's formatting/properties.
        first = nodes[0]
        new_first = (
            f"<w:t{first.group(1)}>{escape_xml(new_line)}</w:t>"
        )
        para = para[:first.start()] + new_first + para[first.end():]

        # Clear other visible text runs in that address paragraph.
        nodes2 = list(re.finditer(
            r"<w:t([^>]*)>(.*?)</w:t>", para, re.I | re.S
        ))
        for node in reversed(nodes2[1:]):
            blank = f"<w:t{node.group(1)}></w:t>"
            para = para[:node.start()] + blank + para[node.end():]

        xml = xml[:pm.start()] + para + xml[pm.end():]

    return xml

def escape_xml(value):
    return (
        str(value)
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
        .replace("'", "&apos;")
    )


def build_docx(template_file, output, data):
    template_file = Path(template_file)

    with zipfile.ZipFile(template_file, "r") as zin:
        files = {name: zin.read(name) for name in zin.namelist()}

    xml = files["word/document.xml"].decode("utf-8")

    # Only customer fields are replaced.
    for key in ("account_number", "customer_id", "name", "pin_code"):
        xml = replace_text(xml, TEMPLATE_MAP[key], data[key])

    xml = replace_textbox_address(xml, data["address"])

    # Explicit fixed-field safety check.
    for fixed in FIXED_VALUES.values():
        if fixed not in xml:
            raise ValueError(f"Fixed template value was altered or lost: {fixed}")

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

    expected = [
        data["account_number"],
        data["customer_id"],
        data["name"],
        data["pin_code"],
        FIXED_VALUES["branch"],
        FIXED_VALUES["ifsc"],
        FIXED_VALUES["ko_name"],
        FIXED_VALUES["ko_location"],
    ]

    missing = [x for x in expected if x not in xml]
    if missing:
        raise ValueError("Final DOCX verification failed: " + ", ".join(missing))

    return True
