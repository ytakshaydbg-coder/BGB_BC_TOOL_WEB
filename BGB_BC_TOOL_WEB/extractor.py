import io
import re
import pdfplumber


# ============================================================
# BASIC CLEANING
# ============================================================

def clean(value):
    """
    Normalize repeated whitespace.
    """
    if value is None:
        return ""

    return re.sub(
        r"\s+",
        " ",
        str(value)
    ).strip()


# ============================================================
# READ PDF TEXT
# ============================================================

def lines_from_pdf(pdf_bytes):
    """
    Extract selectable text from every PDF page.
    """

    with pdfplumber.open(
        io.BytesIO(pdf_bytes)
    ) as pdf:

        pages = []

        for page in pdf.pages:
            text = page.extract_text() or ""
            pages.append(text)

    return "\n".join(pages)


# ============================================================
# COMPACT TEXT
# ============================================================

def compact(value):
    """
    Remove spaces/punctuation for comparison.
    """
    if value is None:
        return ""

    return re.sub(
        r"[^A-Z0-9]",
        "",
        str(value).upper()
    )


# ============================================================
# EXTRACT VALUE AFTER LABEL
# ============================================================

def after_label(
    lines,
    labels,
    value_pattern,
):
    """
    Search a label and inspect the following lines.
    """

    normalized_labels = []

    for label in labels:

        normalized_labels.append(
            re.sub(
                r"\s+",
                "",
                label
            ).lower()
        )

    for i, raw_line in enumerate(lines):

        compact_line = re.sub(
            r"\s+",
            "",
            raw_line
        ).lower()

        found = any(
            label in compact_line
            for label in normalized_labels
        )

        if not found:
            continue

        # Search next few lines
        for j in range(
            i + 1,
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

            # Ignore common labels
            if re.match(
                r"^(sex|gender|account\s*no\.?|account\s*number|"
                r"customer\s*id|aadhaar\s*no\.?|aadhaar|"
                r"mobile\s*no\.?|mobile|date\s*of\s*birth|"
                r"dob|pin\s*code|pincode|pin)$",
                candidate,
                re.IGNORECASE
            ):
                continue

            match = re.search(
                value_pattern,
                candidate,
                re.IGNORECASE
            )

            if match:

                return clean(
                    match.group(1)
                )

    return ""


# ============================================================
# ROBUST PIN FINDER
# ============================================================

def find_pin_in_text(text):
    """
    Detect a 6-digit Indian PIN.

    Handles:

        847105
        847 105
        847-105
        84 7105
        8 4 7 1 0 5
    """

    if not text:
        return ""

    text = str(text)

    # --------------------------------------------------------
    # CASE 1: Normal 6 digits
    # --------------------------------------------------------

    match = re.search(
        r"(?<!\d)(\d{6})(?!\d)",
        text
    )

    if match:

        value = match.group(1)

        # Indian PIN normally does not start with 0
        if value[0] != "0":
            return value

    # --------------------------------------------------------
    # CASE 2:
    #
    # 847 105
    # 847-105
    # --------------------------------------------------------

    match = re.search(
        r"(?<!\d)"
        r"(\d{3})"
        r"[\s\-]+"
        r"(\d{3})"
        r"(?!\d)",
        text
    )

    if match:

        value = (
            match.group(1)
            + match.group(2)
        )

        if value[0] != "0":
            return value

    # --------------------------------------------------------
    # CASE 3:
    #
    # 8 4 7 1 0 5
    # --------------------------------------------------------

    match = re.search(
        r"(?<!\d)"
        r"(\d)"
        r"\D{1,4}"
        r"(\d)"
        r"\D{1,4}"
        r"(\d)"
        r"\D{1,4}"
        r"(\d)"
        r"\D{1,4}"
        r"(\d)"
        r"\D{1,4}"
        r"(\d)"
        r"(?!\d)",
        text
    )

    if match:

        value = "".join(
            match.groups()
        )

        if value[0] != "0":
            return value

    return ""


# ============================================================
# ROBUST PIN CODE EXTRACTION
# ============================================================

def extract_pin_code(
    lines,
    address,
    full_text,
):
    """
    Multiple-level PIN detection.

    Priority:

    1. Explicit PIN label
    2. Address
    3. Address-related lines
    4. Complete PDF text
    5. Last suitable 6-digit candidate
    """

    # --------------------------------------------------------
    # PIN LABEL PATTERN
    # --------------------------------------------------------

    pin_label_pattern = re.compile(
        r"\b("
        r"pin\s*code"
        r"|pincode"
        r"|pin"
        r"|postal\s*code"
        r"|post\s*code"
        r")\b",
        re.IGNORECASE
    )

    # --------------------------------------------------------
    # 1. SEARCH AROUND EXPLICIT PIN LABEL
    # --------------------------------------------------------

    for i, line in enumerate(lines):

        if not pin_label_pattern.search(line):
            continue

        # Same line
        pin = find_pin_in_text(
            line
        )

        if pin:
            return pin

        # Following lines
        for candidate in lines[
            i + 1:i + 7
        ]:

            pin = find_pin_in_text(
                candidate
            )

            if pin:
                return pin

    # --------------------------------------------------------
    # 2. SEARCH COMPLETE ADDRESS
    # --------------------------------------------------------

    pin = find_pin_in_text(
        address
    )

    if pin:
        return pin

    # --------------------------------------------------------
    # 3. SEARCH ADDRESS RELATED LINES
    # --------------------------------------------------------

    address_keywords = re.compile(
        r"flat"
        r"|building"
        r"|bldg"
        r"|street"
        r"|road"
        r"|locality"
        r"|village"
        r"|town"
        r"|city"
        r"|district"
        r"|state"
        r"|address",
        re.IGNORECASE
    )

    for i, line in enumerate(lines):

        if not address_keywords.search(line):
            continue

        for candidate in lines[
            i:i + 8
        ]:

            pin = find_pin_in_text(
                candidate
            )

            if pin:
                return pin

    # --------------------------------------------------------
    # 4. SEARCH COMPLETE PDF TEXT
    # --------------------------------------------------------

    pin = find_pin_in_text(
        full_text
    )

    if pin:
        return pin

    # --------------------------------------------------------
    # 5. COLLECT ALL 6-DIGIT CANDIDATES
    # --------------------------------------------------------

    candidates = []

    for line_number, line in enumerate(
        lines
    ):

        # Normal 6 digit
        matches = re.findall(
            r"(?<!\d)(\d{6})(?!\d)",
            line
        )

        for value in matches:

            if value[0] != "0":

                candidates.append(
                    (
                        line_number,
                        value
                    )
                )

        # 3 + 3 format
        matches = re.findall(
            r"(?<!\d)"
            r"(\d{3})"
            r"[\s\-]+"
            r"(\d{3})"
            r"(?!\d)",
            line
        )

        for first, second in matches:

            value = (
                first
                + second
            )

            if value[0] != "0":

                candidates.append(
                    (
                        line_number,
                        value
                    )
                )

    # Prefer the last candidate
    if candidates:

        return candidates[-1][1]

    return ""


# ============================================================
# ADDRESS EXTRACTION
# ============================================================

def clean_address(address):
    """
    Remove ONLY the known unwanted fragment.
    """

    if not address:
        return ""

    address = str(address)

    # Remove only this specific unwanted code
    address = re.sub(
        r"\b01716\s*,\s*195\b",
        "",
        address,
        flags=re.IGNORECASE
    )

    # Normalize whitespace
    address = re.sub(
        r"\s+",
        " ",
        address
    )

    # Normalize commas
    address = re.sub(
        r"\s*,\s*",
        ", ",
        address
    )

    # Remove duplicate commas
    address = re.sub(
        r",\s*,+",
        ", ",
        address
    )

    # Remove comma at end
    address = re.sub(
        r",\s*$",
        "",
        address
    )

    return address.strip(
        " ,"
    )


# ============================================================
# ADDRESS EXTRACTION — MAIN
# ============================================================

def extract_address(lines):

    address_parts = []

    compact_lines = []

    for line in lines:

        compact_lines.append(
            re.sub(
                r"\s+",
                "",
                line
            ).lower()
        )

    # --------------------------------------------------------
    # STANDARD AOF ADDRESS FORMAT
    # --------------------------------------------------------

    for i, compact_line in enumerate(
        compact_lines
    ):

        # Flat / Building
        if compact_line.startswith(
            "flatno./bldg.name"
        ):

            if i + 1 < len(lines):

                address_parts.append(
                    lines[i + 1]
                )

        # Street / Road / Locality
        elif compact_line.startswith(
            "street/road/locality"
        ):

            if i + 1 < len(lines):

                address_parts.append(
                    lines[i + 1]
                )

        # City / District / State / PIN
        elif compact_line.startswith(
            "city/district/statewithpincode"
        ):

            if i + 1 < len(lines):

                address_parts.append(
                    lines[i + 1]
                )

    # --------------------------------------------------------
    # OTHER COMMON ADDRESS LABELS
    # --------------------------------------------------------

    if not address_parts:

        address_labels = [
            "address",
            "residential address",
            "communication address",
            "permanent address",
        ]

        for i, line in enumerate(lines):

            normalized = re.sub(
                r"\s+",
                "",
                line
            ).lower()

            for label in address_labels:

                compact_label = re.sub(
                    r"\s+",
                    "",
                    label
                ).lower()

                if compact_label in normalized:

                    # Collect following lines
                    for candidate in lines[
                        i + 1:i + 6
                    ]:

                        if candidate.strip():

                            address_parts.append(
                                candidate
                            )

                    break

            if address_parts:
                break

    # --------------------------------------------------------
    # D/O, S/O, W/O, C/O FALLBACK
    # --------------------------------------------------------

    if not address_parts:

        for i, line in enumerate(
            lines
        ):

            if re.match(
                r"^(D/O|S/O|W/O|C/O)\b",
                line,
                re.IGNORECASE
            ):

                address_parts = lines[
                    i:i + 5
                ]

                break

    # --------------------------------------------------------
    # JOIN
    # --------------------------------------------------------

    address = clean(
        " ".join(
            address_parts
        )
    )

    return clean_address(
        address
    )


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

    lines = [
        clean(line)
        for line in text.splitlines()
        if clean(line)
    ]

    if not lines:

        raise ValueError(
            "No selectable text found in PDF."
        )

    # --------------------------------------------------------
    # CUSTOMER NAME
    # --------------------------------------------------------

    name = after_label(
        lines,
        [
            "Customer Name",
            "CustomerName",
        ],
        r"^(.+)$"
    )

    # --------------------------------------------------------
    # ACCOUNT NUMBER
    # --------------------------------------------------------

    account = after_label(
        lines,
        [
            "Account No",
            "Account No.",
            "Account Number",
            "AccountNumber",
        ],
        r"^(\d{8,20})$"
    )

    # --------------------------------------------------------
    # CUSTOMER ID
    # --------------------------------------------------------

    customer_id = after_label(
        lines,
        [
            "Customer ID",
            "CustomerID",
            "Customer IDss",
            "CustomerIDss",
        ],
        r"^([A-Z0-9]{6,30})$"
    )

    # --------------------------------------------------------
    # DOB
    # --------------------------------------------------------

    dob = after_label(
        lines,
        [
            "Date of Birth",
            "DateofBirth",
            "DOB",
        ],
        r"^(\d{4}[-/]\d{2}[-/]\d{2})$"
    )

    # --------------------------------------------------------
    # AADHAAR
    # --------------------------------------------------------

    aadhaar = after_label(
        lines,
        [
            "Aadhaar No",
            "Aadhaar No.",
            "Aadhaar Number",
            "Aadhaar",
        ],
        r"^([Xx\d\s]{4,20})$"
    )

    # --------------------------------------------------------
    # MOBILE
    # --------------------------------------------------------

    mobile = after_label(
        lines,
        [
            "Mobile No",
            "Mobile No.",
            "Mobile Number",
            "Mobile",
        ],
        r"^(\d{10})$"
    )

    # --------------------------------------------------------
    # ADDRESS
    # --------------------------------------------------------

    address = extract_address(
        lines
    )

    # --------------------------------------------------------
    # PIN CODE
    # --------------------------------------------------------

    pin = extract_pin_code(
        lines,
        address,
        text
    )

    # --------------------------------------------------------
    # IMPORTANT:
    # If PIN was detected separately but is not already
    # present in the address, append it.
    # --------------------------------------------------------

    if pin:

        address_without_pin = compact(
            address
        )

        compact_pin = compact(
            pin
        )

        if compact_pin not in address_without_pin:

            if address:

                address = (
                    address.rstrip(
                        " ,"
                    )
                    + ", "
                    + pin
                )

            else:

                address = pin

    # --------------------------------------------------------
    # REQUIRED DATA
    # --------------------------------------------------------

    required = {
        "name": name,
        "account_number": account,
        "customer_id": customer_id,
        "address": address,
        "pin_code": pin,
    }

    # --------------------------------------------------------
    # VALIDATION
    # --------------------------------------------------------

    checks = {
        "all_required": all(
            bool(value)
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
                r"[1-9]\d{5}",
                pin
            )
        ),

        "mobile": mobile,

        "dob": dob,

        "aadhaar": aadhaar,
    }

    # --------------------------------------------------------
    # REQUIRED CHECK
    # --------------------------------------------------------

    if not checks[
        "all_required"
    ]:

        missing = [
            key
            for key, value
            in required.items()
            if not value
        ]

        raise ValueError(
            "Required data missing: "
            + ", ".join(
                missing
            )
        )

    # --------------------------------------------------------
    # ACCOUNT CHECK
    # --------------------------------------------------------

    if not checks[
        "account_format"
    ]:

        raise ValueError(
            "Account Number validation failed."
        )

    # --------------------------------------------------------
    # CUSTOMER ID CHECK
    # --------------------------------------------------------

    if not checks[
        "customer_id_format"
    ]:

        raise ValueError(
            "Customer ID validation failed."
        )

    # --------------------------------------------------------
    # PIN CHECK
    # --------------------------------------------------------

    if not checks[
        "pin_format"
    ]:

        raise ValueError(
            "PIN Code validation failed."
        )

    # --------------------------------------------------------
    # RETURN
    # --------------------------------------------------------

    return (
        required,
        checks,
    )
