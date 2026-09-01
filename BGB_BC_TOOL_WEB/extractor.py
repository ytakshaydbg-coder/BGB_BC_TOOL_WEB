import io
import re
import pdfplumber


# ============================================================
# BASIC CLEANING
# ============================================================

def clean(value):
    """
    Normalize whitespace while preserving actual content.
    """
    if value is None:
        return ""

    return re.sub(r"\s+", " ", str(value)).strip()


# ============================================================
# NORMALIZE FOR COMPARISON
# ============================================================

def normalize_for_match(value):
    """
    Used only for matching labels.
    """
    if value is None:
        return ""

    value = str(value)
    value = value.replace("\xa0", " ")

    return re.sub(
        r"\s+",
        "",
        value
    ).lower()


# ============================================================
# READ TEXT FROM PDF
# ============================================================

def lines_from_pdf(pdf_bytes):
    """
    Extract selectable text from every page of the PDF.
    """

    if not pdf_bytes:
        raise ValueError("Empty PDF file.")

    try:
        with pdfplumber.open(
            io.BytesIO(pdf_bytes)
        ) as pdf:

            pages = []

            for page in pdf.pages:
                text = page.extract_text(
                    x_tolerance=2,
                    y_tolerance=3
                ) or ""

                pages.append(text)

    except Exception as exc:
        raise ValueError(
            "Unable to read PDF: " + str(exc)
        )

    return "\n".join(pages)


# ============================================================
# GET CLEAN LINES
# ============================================================

def get_lines(text):
    """
    Convert extracted PDF text into clean non-empty lines.
    """

    return [
        clean(line)
        for line in text.splitlines()
        if clean(line)
    ]


# ============================================================
# FIND VALUE AFTER LABEL
# ============================================================

def after_label(
    lines,
    labels,
    value_pattern,
):
    """
    Find a field label and search nearby lines for its value.

    Works when:
        Label
        Value

    and also when:
        Label: Value
    """

    label_patterns = []

    for label in labels:

        compact = normalize_for_match(label)

        label_patterns.append(
            compact
        )

    regex = re.compile(
        value_pattern,
        re.IGNORECASE
    )

    for i, raw_line in enumerate(lines):

        line = clean(raw_line)

        compact_line = normalize_for_match(
            line
        )

        matched_label = any(
            label in compact_line
            for label in label_patterns
        )

        if not matched_label:
            continue

        # ----------------------------------------------------
        # First check value on same line
        # ----------------------------------------------------

        for label in labels:

            escaped_label = re.escape(
                label
            )

            same_line_pattern = re.compile(
                escaped_label
                + r"\s*:?\s*(.+)$",
                re.IGNORECASE
            )

            same_match = same_line_pattern.search(
                line
            )

            if same_match:

                candidate = clean(
                    same_match.group(1)
                )

                if candidate:

                    value_match = regex.search(
                        candidate
                    )

                    if value_match:
                        return clean(
                            value_match.group(1)
                        )

        # ----------------------------------------------------
        # Then search next few lines
        # ----------------------------------------------------

        for j in range(
            i + 1,
            min(
                i + 7,
                len(lines)
            )
        ):

            candidate = clean(
                lines[j]
            )

            if not candidate:
                continue

            # Skip obvious labels.
            compact_candidate = normalize_for_match(
                candidate
            )

            if any(
                normalize_for_match(label)
                == compact_candidate
                for label in [
                    "Sex",
                    "Account No",
                    "Customer ID",
                    "Customer IDss",
                    "Aadhaar No",
                    "Mobile No",
                    "Date of Birth",
                    "Customer Name",
                ]
            ):
                continue

            match = regex.search(
                candidate
            )

            if match:

                return clean(
                    match.group(1)
                )

    return ""


# ============================================================
# EXTRACT ACCOUNT NUMBER
# ============================================================

def extract_account_number(lines):

    # Normal form
    value = after_label(
        lines,
        [
            "Account No",
            "Account Number",
            "A/C No",
            "A/C Number",
            "AccountNo",
            "AccountNumber",
        ],
        r"^(\d{8,20})$",
    )

    if value:
        return value

    # Fallback:
    # Search lines near account-related labels.
    account_label_re = re.compile(
        r"account\s*(?:no|number)"
        r"|a/?c\s*(?:no|number)",
        re.IGNORECASE
    )

    for i, line in enumerate(lines):

        if not account_label_re.search(line):
            continue

        for candidate in lines[
            i:i + 5
        ]:

            numbers = re.findall(
                r"\b\d{8,20}\b",
                candidate
            )

            if numbers:
                return numbers[0]

    return ""


# ============================================================
# EXTRACT CUSTOMER ID
# ============================================================

def extract_customer_id(lines):

    value = after_label(
        lines,
        [
            "Customer ID",
            "Customer IDss",
            "CustomerID",
            "Customer Id",
        ],
        r"^([A-Z0-9]{6,30})$",
    )

    if value:
        return value.upper()

    # --------------------------------------------------------
    # More tolerant fallback
    # --------------------------------------------------------

    label_re = re.compile(
        r"customer\s*id",
        re.IGNORECASE
    )

    for i, line in enumerate(lines):

        if not label_re.search(line):
            continue

        # Same line
        candidate = re.sub(
            r"^.*?customer\s*id\s*:?\s*",
            "",
            line,
            flags=re.IGNORECASE
        ).strip()

        if re.fullmatch(
            r"[A-Z0-9]{6,30}",
            candidate,
            re.IGNORECASE
        ):
            return candidate.upper()

        # Next lines
        for next_line in lines[
            i + 1:i + 6
        ]:

            candidate = clean(
                next_line
            )

            if re.fullmatch(
                r"[A-Z0-9]{6,30}",
                candidate,
                re.IGNORECASE
            ):
                return candidate.upper()

    return ""


# ============================================================
# EXTRACT CUSTOMER NAME
# ============================================================

def extract_name(lines):

    value = after_label(
        lines,
        [
            "Customer Name",
            "CustomerName",
            "Name of Customer",
            "Name",
        ],
        r"^(.+)$",
    )

    if value:
        return value

    return ""


# ============================================================
# EXTRACT DOB
# ============================================================

def extract_dob(lines):

    value = after_label(
        lines,
        [
            "Date of Birth",
            "Date Of Birth",
            "DOB",
        ],
        r"^(\d{4}-\d{2}-\d{2})$",
    )

    if value:
        return value

    # Additional common date formats
    date_re = re.compile(
        r"\b("
        r"\d{4}-\d{2}-\d{2}"
        r"|"
        r"\d{2}-\d{2}-\d{4}"
        r"|"
        r"\d{2}/\d{2}/\d{4}"
        r")\b"
    )

    for i, line in enumerate(lines):

        if re.search(
            r"date\s*of\s*birth|dob",
            line,
            re.IGNORECASE
        ):

            for candidate in lines[
                i:i + 5
            ]:

                match = date_re.search(
                    candidate
                )

                if match:
                    return match.group(1)

    return ""


# ============================================================
# EXTRACT AADHAAR
# ============================================================

def extract_aadhaar(lines):

    value = after_label(
        lines,
        [
            "Aadhaar No",
            "Aadhaar Number",
            "Aadhar No",
            "Aadhar Number",
        ],
        r"^([Xx\d\s-]{4,25})$",
    )

    if value:
        return clean(value)

    return ""


# ============================================================
# EXTRACT MOBILE
# ============================================================

def extract_mobile(lines):

    value = after_label(
        lines,
        [
            "Mobile No",
            "Mobile Number",
            "MobileNo",
            "Mobile",
        ],
        r"^(\d{10})$",
    )

    if value:
        return value

    return ""


# ============================================================
# REMOVE UNWANTED AOF FRAGMENT
# ============================================================

def clean_address(address):

    if not address:
        return ""

    address = str(address)

    # --------------------------------------------------------
    # Remove unwanted fragment:
    #
    # 01716, 195
    # 01719, 195
    # --------------------------------------------------------
    #
    # The AOF can contain slightly different 017xx codes.
    # We remove only this specific pattern.
    # --------------------------------------------------------

    address = re.sub(
        r"\b017\d{2}\s*,\s*195\b",
        "",
        address,
        flags=re.IGNORECASE
    )

    # Also support spaces around the comma.
    address = re.sub(
        r"\b017\d{2}\s*,\s*195\b",
        "",
        address,
        flags=re.IGNORECASE
    )

    # --------------------------------------------------------
    # Normalize spaces
    # --------------------------------------------------------

    address = re.sub(
        r"\s+",
        " ",
        address
    )

    # --------------------------------------------------------
    # Normalize comma spacing
    # --------------------------------------------------------

    address = re.sub(
        r"\s*,\s*",
        ", ",
        address
    )

    # --------------------------------------------------------
    # Remove duplicate commas
    # --------------------------------------------------------

    address = re.sub(
        r",\s*,+",
        ", ",
        address
    )

    # --------------------------------------------------------
    # Remove comma before end
    # --------------------------------------------------------

    address = re.sub(
        r",\s*$",
        "",
        address
    )

    return address.strip(" ,")


# ============================================================
# EXTRACT PIN FROM A STRING
# ============================================================

def extract_pin_from_text(text):

    if not text:
        return ""

    text = str(text)

    # --------------------------------------------------------
    # First: explicit PIN-related labels
    # --------------------------------------------------------

    patterns = [
        r"(?:pin\s*code|pincode|pin)\s*[:\-]?\s*(\d{6})\b",
        r"(?:with\s*pincode|pincode)\s*[:\-]?\s*(\d{6})\b",
    ]

    for pattern in patterns:

        match = re.search(
            pattern,
            text,
            re.IGNORECASE
        )

        if match:
            return match.group(1)

    # --------------------------------------------------------
    # Second: any standalone 6-digit PIN
    # --------------------------------------------------------

    matches = re.findall(
        r"(?<!\d)(\d{6})(?!\d)",
        text
    )

    # Return the last 6-digit number.
    #
    # In these AOF address layouts, PIN is normally
    # near the end of the address.
    if matches:

        return matches[-1]

    return ""


# ============================================================
# EXTRACT ADDRESS
# ============================================================

def extract_address(lines):

    address_parts = []

    compact_lines = [
        normalize_for_match(line)
        for line in lines
    ]

    # --------------------------------------------------------
    # Known AOF address labels
    # --------------------------------------------------------

    address_label_patterns = [
        "flatno./bldg.name",
        "flatno./bldgname",
        "flatno/bldg.name",
        "flatno/bldgname",
        "street/road/locality",
        "street/road/locality",
        "city/district/statewithpincode",
        "city/district/statewithpin",
        "city/district/state",
    ]

    found_address_label = False

    for i, compact in enumerate(
        compact_lines
    ):

        matched = False

        for label in address_label_patterns:

            if compact.startswith(
                normalize_for_match(label)
            ):

                matched = True
                found_address_label = True

                # ------------------------------------------------
                # Same line may contain value after colon.
                # ------------------------------------------------

                current_line = lines[i]

                parts = re.split(
                    r":\s*",
                    current_line,
                    maxsplit=1
                )

                if (
                    len(parts) == 2
                    and clean(parts[1])
                ):

                    address_parts.append(
                        clean(parts[1])
                    )

                # ------------------------------------------------
                # Otherwise next 1-2 lines
                # ------------------------------------------------

                else:

                    for j in range(
                        i + 1,
                        min(
                            i + 3,
                            len(lines)
                        )
                    ):

                        candidate = clean(
                            lines[j]
                        )

                        if not candidate:
                            continue

                        # Stop if next field label begins.
                        if re.match(
                            r"^(account|customer\s*id|"
                            r"customer\s*name|sex|"
                            r"mobile|aadhaar|date\s*of\s*birth|"
                            r"pin\s*code)\b",
                            candidate,
                            re.IGNORECASE
                        ):
                            break

                        address_parts.append(
                            candidate
                        )

                break

        if matched:
            continue

    # --------------------------------------------------------
    # Fallback: D/O, S/O, W/O, C/O format
    # --------------------------------------------------------

    if not address_parts:

        relation_re = re.compile(
            r"^(D/O|S/O|W/O|C/O)\b",
            re.IGNORECASE
        )

        for i, line in enumerate(lines):

            if relation_re.search(line):

                # Collect several consecutive lines.
                for j in range(
                    i,
                    min(
                        i + 6,
                        len(lines)
                    )
                ):

                    candidate = clean(
                        lines[j]
                    )

                    if not candidate:
                        continue

                    # Stop at obvious unrelated fields.
                    if (
                        j > i
                        and re.match(
                            r"^(account|customer\s*id|"
                            r"customer\s*name|mobile|"
                            r"aadhaar|date\s*of\s*birth)\b",
                            candidate,
                            re.IGNORECASE
                        )
                    ):
                        break

                    address_parts.append(
                        candidate
                    )

                break

    # --------------------------------------------------------
    # Last fallback:
    #
    # Search lines containing a 6-digit PIN.
    # --------------------------------------------------------

    if not address_parts:

        for line in lines:

            if re.search(
                r"(?<!\d)\d{6}(?!\d)",
                line
            ):

                address_parts.append(
                    line
                )

    # --------------------------------------------------------
    # Join address
    # --------------------------------------------------------

    address = clean(
        " ".join(
            address_parts
        )
    )

    address = clean_address(
        address
    )

    return address


# ============================================================
# EXTRACT PIN CODE
# ============================================================

def extract_pin_code(
    lines,
    address,
):

    # --------------------------------------------------------
    # 1. Search explicit PIN labels in complete PDF
    # --------------------------------------------------------

    full_text = "\n".join(
        lines
    )

    pin = extract_pin_from_text(
        full_text
    )

    if pin:
        return pin

    # --------------------------------------------------------
    # 2. Search address
    # --------------------------------------------------------

    pin = extract_pin_from_text(
        address
    )

    if pin:
        return pin

    # --------------------------------------------------------
    # 3. Search lines near address labels
    # --------------------------------------------------------

    address_label_re = re.compile(
        r"flat\s*no"
        r"|bldg"
        r"|street"
        r"|road"
        r"|locality"
        r"|city"
        r"|district"
        r"|state"
        r"|pincode"
        r"|pin\s*code",
        re.IGNORECASE
    )

    for i, line in enumerate(lines):

        if not address_label_re.search(
            line
        ):
            continue

        for candidate in lines[
            i:i + 6
        ]:

            matches = re.findall(
                r"(?<!\d)(\d{6})(?!\d)",
                candidate
            )

            if matches:
                return matches[-1]

    # --------------------------------------------------------
    # 4. Final fallback:
    #
    # Search from bottom of PDF upward.
    #
    # This is useful when the AOF places PIN at the
    # end of the address but changes the exact label.
    # --------------------------------------------------------

    for line in reversed(lines):

        matches = re.findall(
            r"(?<!\d)(\d{6})(?!\d)",
            line
        )

        if matches:

            # Ignore obvious dates such as 2026xx etc.
            # A PIN must be exactly six digits.
            return matches[-1]

    return ""


# ============================================================
# MAIN EXTRACTION
# ============================================================

def extract_aof(pdf_bytes):

    # --------------------------------------------------------
    # Read PDF
    # --------------------------------------------------------

    text = lines_from_pdf(
        pdf_bytes
    )

    lines = get_lines(
        text
    )

    if not lines:

        raise ValueError(
            "No selectable text found in PDF."
        )

    # --------------------------------------------------------
    # Extract fields
    # --------------------------------------------------------

    name = extract_name(
        lines
    )

    account = extract_account_number(
        lines
    )

    customer_id = extract_customer_id(
        lines
    )

    dob = extract_dob(
        lines
    )

    aadhaar = extract_aadhaar(
        lines
    )

    mobile = extract_mobile(
        lines
    )

    # --------------------------------------------------------
    # Address
    # --------------------------------------------------------

    address = extract_address(
        lines
    )

    address = clean_address(
        address
    )

    # --------------------------------------------------------
    # PIN
    # --------------------------------------------------------

    pin = extract_pin_code(
        lines,
        address
    )

    # --------------------------------------------------------
    # If PIN was found separately but is not present in
    # address, append it only when the address has no PIN.
    #
    # This makes final DOCX verification reliable.
    # --------------------------------------------------------

    if (
        pin
        and not re.search(
            r"(?<!\d)"
            + re.escape(pin)
            + r"(?!\d)",
            address
        )
    ):

        if address:
            address = (
                address.rstrip(" ,")
                + ", "
                + pin
            )
        else:
            address = pin

    # --------------------------------------------------------
    # Clean address one final time
    # --------------------------------------------------------

    address = clean_address(
        address
    )

    # --------------------------------------------------------
    # Required fields
    # --------------------------------------------------------

    required = {
        "name": name,
        "account_number": account,
        "customer_id": customer_id,
        "address": address,
        "pin_code": pin,
    }

    # --------------------------------------------------------
    # Validation
    # --------------------------------------------------------

    checks = {
        "all_required": all(
            bool(
                str(value).strip()
            )
            for value in required.values()
        ),

        "account_format": bool(
            re.fullmatch(
                r"\d{8,20}",
                account
            )
        ),

        "customer_id_format": bool(
            re.fullmatch(
                r"[A-Z0-9]{6,30}",
                customer_id,
                flags=re.IGNORECASE
            )
        ),

        "pin_format": bool(
            re.fullmatch(
                r"\d{6}",
                pin
            )
        ),

        "mobile": mobile,
        "dob": dob,
        "aadhaar": aadhaar,
    }

    # --------------------------------------------------------
    # Required data check
    # --------------------------------------------------------

    if not checks[
        "all_required"
    ]:

        missing = [
            key
            for key, value
            in required.items()
            if not str(
                value
            ).strip()
        ]

        raise ValueError(
            "Required data missing: "
            + ", ".join(
                missing
            )
        )

    # --------------------------------------------------------
    # Account validation
    # --------------------------------------------------------

    if not checks[
        "account_format"
    ]:

        raise ValueError(
            "Account Number validation failed."
        )

    # --------------------------------------------------------
    # Customer ID validation
    # --------------------------------------------------------

    if not checks[
        "customer_id_format"
    ]:

        raise ValueError(
            "Customer ID validation failed."
        )

    # --------------------------------------------------------
    # PIN validation
    # --------------------------------------------------------

    if not checks[
        "pin_format"
    ]:

        raise ValueError(
            "PIN Code validation failed."
        )

    # --------------------------------------------------------
    # Return
    # --------------------------------------------------------

    return (
        required,
        checks
    )
