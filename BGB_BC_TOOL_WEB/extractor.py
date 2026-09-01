import io
import re
import pdfplumber


# ============================================================
# BASIC CLEANING
# ============================================================

def clean(value):
    """
    Normalize repeated whitespace without changing
    the actual content.
    """
    return re.sub(r"\s+", " ", value or "").strip()


# ============================================================
# READ TEXT FROM PDF
# ============================================================

def lines_from_pdf(pdf_bytes):
    """
    Extract selectable text from all PDF pages.
    """

    with pdfplumber.open(
        io.BytesIO(pdf_bytes)
    ) as pdf:

        pages = [
            page.extract_text() or ""
            for page in pdf.pages
        ]

    return "\n".join(pages)


# ============================================================
# EXTRACT VALUE AFTER LABEL
# ============================================================

def after_label(
    lines,
    labels,
    value_pattern,
):
    """
    Finds a label and searches the following few lines
    for the required value.
    """

    labels = [
        re.sub(
            r"\s+",
            "",
            x
        ).lower()
        for x in labels
    ]

    for i, raw in enumerate(lines):

        compact = re.sub(
            r"\s+",
            "",
            raw
        ).lower()

        if any(
            label in compact
            for label in labels
        ):

            for j in range(
                i + 1,
                min(
                    i + 4,
                    len(lines)
                ),
            ):

                candidate = clean(
                    lines[j]
                )

                if not candidate:
                    continue

                # Skip other labels
                if re.match(
                    r"^(sex|account\s*no|customer\s*id|aadhaar\s*no|mobile\s*no)$",
                    candidate,
                    re.I,
                ):
                    continue

                match = re.search(
                    value_pattern,
                    candidate,
                    re.I,
                )

                if match:
                    return clean(
                        match.group(1)
                    )

    return ""


# ============================================================
# REMOVE ONLY THE UNWANTED AOF CODE
# ============================================================

def clean_address(address):
    """
    Removes ONLY the unwanted sequence:

        01716, 195

    from the extracted address.

    Nothing else in the address is intentionally removed.
    """

    if not address:
        return ""

    address = str(address)

    # Remove exactly:
    # 01716, 195
    #
    # Allows different spacing around comma.
    address = re.sub(
        r"\b01716\s*,\s*195\b",
        "",
        address,
        flags=re.IGNORECASE,
    )

    # Remove duplicate spaces created by deletion.
    address = re.sub(
        r"[ \t]{2,}",
        " ",
        address,
    )

    # Clean comma spacing.
    address = re.sub(
        r"\s*,\s*",
        ", ",
        address,
    )

    # Remove comma immediately before another comma.
    address = re.sub(
        r",\s*,+",
        ", ",
        address,
    )

    # Remove comma before end of address.
    address = re.sub(
        r",\s*$",
        "",
        address,
    )

    return address.strip(" ,")


# ============================================================
# MAIN AOF EXTRACTION
# ============================================================

def extract_aof(pdf_bytes):

    text = lines_from_pdf(
        pdf_bytes
    )

    lines = [
        x.strip()
        for x in text.splitlines()
        if x.strip()
    ]

    # ========================================================
    # BASIC AOF FIELDS
    # ========================================================

    name = after_label(
        lines,
        ["Customer Name"],
        r"^(.+)$",
    )

    account = after_label(
        lines,
        ["Account No"],
        r"^(\d{8,20})$",
    )

    customer_id = after_label(
        lines,
        [
            "Customer ID",
            "Customer IDss",
        ],
        r"^([A-Z0-9]{6,30})$",
    )

    dob = after_label(
        lines,
        ["Date of Birth"],
        r"^(\d{4}-\d{2}-\d{2})$",
    )

    aadhaar = after_label(
        lines,
        ["Aadhaar No"],
        r"^([Xx\d]{4,20})$",
    )

    mobile = after_label(
        lines,
        ["Mobile No"],
        r"^(\d{10})$",
    )

    # ========================================================
    # ADDRESS EXTRACTION
    # ========================================================

    address_parts = []

    compact_lines = [
        re.sub(
            r"\s+",
            "",
            x
        ).lower()
        for x in lines
    ]

    for i, compact in enumerate(
        compact_lines
    ):

        # ----------------------------------------------------
        # Flat / Building
        # ----------------------------------------------------

        if compact.startswith(
            "flatno./bldg.name"
        ):

            if i + 1 < len(lines):

                address_parts.append(
                    lines[i + 1]
                )

        # ----------------------------------------------------
        # Street / Road / Locality
        # ----------------------------------------------------

        elif compact.startswith(
            "street/road/locality"
        ):

            if i + 1 < len(lines):

                address_parts.append(
                    lines[i + 1]
                )

        # ----------------------------------------------------
        # City / District / State / PIN
        # ----------------------------------------------------

        elif compact.startswith(
            "city/district/statewithpincode"
        ):

            if i + 1 < len(lines):

                address_parts.append(
                    lines[i + 1]
                )

    # ========================================================
    # FALLBACK ADDRESS FORMAT
    # ========================================================

    if not address_parts:

        for i, line in enumerate(
            lines
        ):

            if re.match(
                r"^(D/O|S/O|W/O|C/O)\b",
                line,
                re.I,
            ):

                address_parts = lines[
                    i:i + 3
                ]

                break

    # ========================================================
    # JOIN ADDRESS
    # ========================================================

    address = clean(
        " ".join(
            address_parts
        )
    )

    # ========================================================
    # REMOVE ONLY 01716, 195
    # ========================================================

    address = clean_address(
        address
    )

    # ========================================================
    # PIN CODE
    # ========================================================

    pin_match = re.search(
        r"\b(\d{6})\b\s*$",
        address,
    )

    pin = (
        pin_match.group(1)
        if pin_match
        else ""
    )

    # ========================================================
    # REQUIRED DATA
    # ========================================================

    required = {
        "name": name,
        "account_number": account,
        "customer_id": customer_id,
        "address": address,
        "pin_code": pin,
    }

    # ========================================================
    # VALIDATION
    # ========================================================

    checks = {
        "all_required": all(
            bool(v)
            for v in required.values()
        ),

        "account_format": bool(
            re.fullmatch(
                r"\d{8,20}",
                account,
            )
        ),

        "customer_id_format": bool(
            re.fullmatch(
                r"[A-Z0-9]{6,30}",
                customer_id,
            )
        ),

        "pin_format": bool(
            re.fullmatch(
                r"\d{6}",
                pin,
            )
        ),

        "mobile": mobile,
        "dob": dob,
        "aadhaar": aadhaar,
    }

    # ========================================================
    # REQUIRED FIELD CHECK
    # ========================================================

    if not checks[
        "all_required"
    ]:

        missing = [
            k
            for k, v
            in required.items()
            if not v
        ]

        raise ValueError(
            "Required data missing: "
            + ", ".join(
                missing
            )
        )

    # ========================================================
    # ACCOUNT VALIDATION
    # ========================================================

    if not checks[
        "account_format"
    ]:

        raise ValueError(
            "Account Number validation failed."
        )

    # ========================================================
    # CUSTOMER ID VALIDATION
    # ========================================================

    if not checks[
        "customer_id_format"
    ]:

        raise ValueError(
            "Customer ID validation failed."
        )

    # ========================================================
    # PIN VALIDATION
    # ========================================================

    if not checks[
        "pin_format"
    ]:

        raise ValueError(
            "PIN Code validation failed."
        )

    # ========================================================
    # RETURN
    # ========================================================

    return (
        required,
        checks,
    )
