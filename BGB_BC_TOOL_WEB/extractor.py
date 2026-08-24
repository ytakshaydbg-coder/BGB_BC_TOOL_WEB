import re
import pdfplumber


def clean(value):
    return re.sub(r"\s+", " ", value or "").strip()


def lines_from_pdf(pdf_bytes):
    with pdfplumber.open(__import__("io").BytesIO(pdf_bytes)) as pdf:
        pages = [page.extract_text() or "" for page in pdf.pages]
    return "\n".join(pages)


def after_label(lines, labels, value_pattern):
    labels = [re.sub(r"\s+", "", x).lower() for x in labels]

    for i, raw in enumerate(lines):
        compact = re.sub(r"\s+", "", raw).lower()

        if any(label in compact for label in labels):
            # Most fields in this AOF have the value on the next line.
            for j in range(i + 1, min(i + 4, len(lines))):
                candidate = clean(lines[j])
                if candidate and not re.match(
                    r"^(sex|account\s*no|customer\s*id|aadhaar\s*no|mobile\s*no)$",
                    candidate,
                    re.I,
                ):
                    m = re.search(value_pattern, candidate, re.I)
                    if m:
                        return clean(m.group(1))
    return ""


def extract_aof(pdf_bytes):
    text = lines_from_pdf(pdf_bytes)
    lines = [x.strip() for x in text.splitlines() if x.strip()]

    # This AOF layout has labels followed by their values.
    name = after_label(lines, ["Customer Name"], r"^(.+)$")
    account = after_label(lines, ["Account No"], r"^(\d{8,20})$")
    customer_id = after_label(lines, ["Customer ID", "Customer IDss"], r"^([A-Z0-9]{6,30})$")
    dob = after_label(lines, ["Date of Birth"], r"^(\d{4}-\d{2}-\d{2})$")
    aadhaar = after_label(lines, ["Aadhaar No"], r"^([Xx\d]{4,20})$")
    mobile = after_label(lines, ["Mobile No"], r"^(\d{10})$")

    # Address: take the actual value lines after the three address labels.
    address_parts = []
    compact_lines = [re.sub(r"\s+", "", x).lower() for x in lines]

    for i, compact in enumerate(compact_lines):
        if compact.startswith("flatno./bldg.name"):
            if i + 1 < len(lines):
                address_parts.append(lines[i + 1])
        elif compact.startswith("street/road/locality"):
            if i + 1 < len(lines):
                address_parts.append(lines[i + 1])
        elif compact.startswith("city/district/statewithpincode"):
            if i + 1 < len(lines):
                address_parts.append(lines[i + 1])

    # Fallback for the common AOF D/O/S/O/W/O address layout.
    if not address_parts:
        for i, line in enumerate(lines):
            if re.match(r"^(D/O|S/O|W/O|C/O)\b", line, re.I):
                address_parts = lines[i:i + 3]
                break

    address = clean(" ".join(address_parts))

    # In this AOF the PIN is the 6-digit value at the end of the address.
    pin_match = re.search(r"\b(\d{6})\b\s*$", address)
    pin = pin_match.group(1) if pin_match else ""

    required = {
        "name": name,
        "account_number": account,
        "customer_id": customer_id,
        "address": address,
        "pin_code": pin,
    }

    checks = {
        "all_required": all(bool(v) for v in required.values()),
        "account_format": bool(re.fullmatch(r"\d{8,20}", account)),
        "customer_id_format": bool(re.fullmatch(r"[A-Z0-9]{6,30}", customer_id)),
        "pin_format": bool(re.fullmatch(r"\d{6}", pin)),
        "mobile": mobile,
        "dob": dob,
        "aadhaar": aadhaar,
    }

    if not checks["all_required"]:
        missing = [k for k, v in required.items() if not v]
        raise ValueError("Required data missing: " + ", ".join(missing))

    if not checks["account_format"]:
        raise ValueError("Account Number validation failed.")
    if not checks["customer_id_format"]:
        raise ValueError("Customer ID validation failed.")
    if not checks["pin_format"]:
        raise ValueError("PIN Code validation failed.")

    return required, checks
