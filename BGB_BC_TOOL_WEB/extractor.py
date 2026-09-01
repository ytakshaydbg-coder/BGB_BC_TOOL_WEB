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
        str(value),
    ).strip()


# ============================================================
# NORMALIZE LABEL
# ============================================================

def compact(value):
    """
    Remove spaces and punctuation for label comparison.
    """

    if value is None:
        return ""

    return re.sub(
        r"[^a-z0-9]",
        "",
        str(value).lower(),
    )


# ============================================================
# READ PDF TEXT
# ============================================================

def lines_from_pdf(pdf_bytes):
    """
    Extract selectable text from every PDF page.
    """

    if not pdf_bytes:
        raise ValueError(
            "PDF file is empty."
        )

    with pdfplumber.open(
        io.BytesIO(pdf_bytes)
    ) as pdf:

        if not pdf.pages:
            raise ValueError(
                "PDF contains no pages."
            )

        pages = []

        for page in pdf.pages:

            text = page.extract_text(
                x_tolerance=2,
                y_tolerance=3,
            ) or ""

            pages.append(text)

    return "\n".join(pages)


# ============================================================
# CLEAN AOF ADDRESS
# ============================================================

def clean_address(address):
    """
    Clean address without damaging the actual address.

    Removes unwanted communication/STD fragments such as:

        01719, 195
        01716, 195
        Tel.No/FaxNo.(withSTDcode)Email

    Keeps the actual customer PIN.
    """

    if not address:
        return ""

    address = str(address)

    # --------------------------------------------------------
    # Remove common STD-code fragments.
    #
    # Examples:
    # 01719, 195
    # 01716, 195
    # 06272, 195
    # --------------------------------------------------------

    address = re.sub(
        r"\b0\d{4}\s*,\s*\d{3}\b",
        "",
        address,
        flags=re.IGNORECASE,
    )

    # --------------------------------------------------------
    # Remove telephone/fax/email labels and everything after
    # them on the same extracted address section.
    # --------------------------------------------------------

    address = re.sub(
        r"\bTel\.?\s*No\.?.*$",
        "",
        address,
        flags=re.IGNORECASE,
    )

    address = re.sub(
        r"\bFax\.?\s*No\.?.*$",
        "",
        address,
        flags=re.IGNORECASE,
    )

    address = re.sub(
        r"\bEmail\b.*$",
        "",
        address,
        flags=re.IGNORECASE,
    )

    # --------------------------------------------------------
    # Remove explicit STD-code wording.
    # --------------------------------------------------------

    address = re.sub(
        r"\(?\s*with\s*STD\s*code\s*\)?",
        "",
        address,
        flags=re.IGNORECASE,
    )

    # --------------------------------------------------------
    # Normalize whitespace.
    # --------------------------------------------------------

    address = re.sub(
        r"\s+",
        " ",
        address,
    )

    # --------------------------------------------------------
    # Normalize comma spacing.
    # --------------------------------------------------------

    address = re.sub(
        r"\s*,\s*",
        ", ",
        address,
    )

    # --------------------------------------------------------
    # Remove duplicate commas.
    # --------------------------------------------------------

    address = re.sub(
        r",\s*,+",
        ", ",
        address,
    )

    # --------------------------------------------------------
    # Remove comma before end.
    # --------------------------------------------------------

    address = re.sub(
        r",\s*$",
        "",
        address,
    )

    return address.strip(
        " ,"
    )


# ============================================================
# FIND VALUE AFTER LABEL
# ============================================================

def after_label(
    lines,
    labels,
    value_pattern,
    max_lines=5,
):
    """
    Find a label and extract its value.

    Supports:
        LABEL
        VALUE

    and:
        LABEL : VALUE
    """

    normalized_labels = [
        compact(label)
        for label in labels
    ]

    for i, raw in enumerate(lines):

        raw_clean = clean(raw)

        raw_compact = compact(
            raw_clean
        )

        matched_label = None

        for label in normalized_labels:

            if label and label in raw_compact:
                matched_label = label
                break

        if matched_label is None:
            continue

        # ----------------------------------------------------
        # Case 1:
        # Label and value are on the same line.
        #
        # Example:
        # PIN CODE : 847101
        # ----------------------------------------------------

        same_line = raw_clean

        # Remove the label from the line.
        for original_label in labels:

            pattern = re.compile(
                re.escape(
                    original_label
                ),
                re.IGNORECASE,
            )

            if pattern.search(
                same_line
            ):

                remainder = pattern.sub(
                    "",
                    same_line,
                    count=1,
                )

                remainder = re.sub(
                    r"^[\s:：\-–—]+",
                    "",
                    remainder,
                )

                remainder = clean(
                    remainder
                )

                if remainder:

                    match = re.search(
                        value_pattern,
                        remainder,
                        re.IGNORECASE,
                    )

                    if match:

                        return clean(
                            match.group(1)
                        )

                break

        # ----------------------------------------------------
        # Case 2:
        # Value is on one of the next lines.
        # ----------------------------------------------------

        for j in range(
            i + 1,
            min(
                i + 1 + max_lines,
                len(lines),
            ),
        ):

            candidate = clean(
                lines[j]
            )

            if not candidate:
                continue

            candidate_compact = compact(
                candidate
            )

            # ------------------------------------------------
            # Do not accidentally take another field label.
            # ------------------------------------------------

            field_labels = [
                "sex",
                "accountno",
                "accountnumber",
                "customerid",
                "customeridss",
                "aadhaarno",
                "aadharno",
                "mobileno",
                "dateofbirth",
                "dob",
                "pincode",
                "pincode",
                "name",
                "customername",
            ]

            if candidate_compact in field_labels:
                continue

            match = re.search(
                value_pattern,
                candidate,
                re.IGNORECASE,
            )

            if match:

                return clean(
                    match.group(1)
                )

    return ""


# ============================================================
# EXTRACT PIN CODE
# ============================================================

def extract_pin_code(
    lines,
    address="",
):
    """
    Robust PIN extraction.

    Priority:

    1. Explicit PIN CODE / PINCODE / PIN label
    2. PIN at end of address
    3. Six-digit number in address
    4. Six-digit number near address section

    Important:
    The fixed KO Location PIN 847105 is ignored.
    """

    # ========================================================
    # FIXED TEMPLATE PIN(S) TO IGNORE
    # ========================================================

    ignored_pins = {
        "847105",
    }

    # ========================================================
    # 1. EXPLICIT PIN LABEL
    # ========================================================

    pin_label_patterns = [
        r"\bPIN\s*CODE\b",
        r"\bPINCODE\b",
        r"\bPIN\b",
        r"\bPOSTAL\s*CODE\b",
        r"\bZIP\s*CODE\b",
    ]

    for i, line in enumerate(lines):

        current = clean(line)

        # ----------------------------------------------------
        # Same line:
        #
        # PIN CODE : 847101
        # ----------------------------------------------------

        for label_pattern in pin_label_patterns:

            match_label = re.search(
                label_pattern,
                current,
                re.IGNORECASE,
            )

            if not match_label:
                continue

            remainder = current[
                match_label.end():
            ]

            remainder = re.sub(
                r"^[\s:：\-–—]+",
                "",
                remainder,
            )

            pin_match = re.search(
                r"(?<!\d)(\d{6})(?!\d)",
                remainder,
            )

            if pin_match:

                candidate = (
                    pin_match.group(1)
                )

                if candidate not in ignored_pins:

                    return candidate

            # ------------------------------------------------
            # Label on one line, value on next line.
            # ------------------------------------------------

            for j in range(
                i + 1,
                min(
                    i + 4,
                    len(lines),
                ),
            ):

                next_line = clean(
                    lines[j]
                )

                pin_match = re.search(
                    r"(?<!\d)(\d{6})(?!\d)",
                    next_line,
                )

                if pin_match:

                    candidate = (
                        pin_match.group(1)
                    )

                    if candidate not in ignored_pins:

                        return candidate

    # ========================================================
    # 2. PIN AT END OF CLEANED ADDRESS
    # ========================================================

    cleaned_address = clean_address(
        address
    )

    pin_match = re.search(
        r"(?<!\d)(\d{6})(?!\d)\s*$",
        cleaned_address,
    )

    if pin_match:

        candidate = pin_match.group(1)

        if candidate not in ignored_pins:

            return candidate

    # ========================================================
    # 3. ANY SIX-DIGIT NUMBER IN ADDRESS
    # ========================================================

    address_candidates = re.findall(
        r"(?<!\d)(\d{6})(?!\d)",
        cleaned_address,
    )

    for candidate in reversed(
        address_candidates
    ):

        if candidate not in ignored_pins:

            return candidate

    # ========================================================
    # 4. LOOK FOR SIX-DIGIT NUMBER IN ADDRESS AREA
    # ========================================================

    address_start = None

    address_labels = [
        "flatno./bldg.name",
        "street/road/locality",
        "city/district/statewithpincode",
        "address",
        "residentialaddress",
    ]

    compact_lines = [
        compact(line)
        for line in lines
    ]

    for i, line_compact in enumerate(
        compact_lines
    ):

        for label in address_labels:

            if label in line_compact:

                address_start = i
                break

        if address_start is not None:
            break

    if address_start is not None:

        for line in lines[
            address_start:
        ]:

            line = clean(
                line
            )

            candidates = re.findall(
                r"(?<!\d)(\d{6})(?!\d)",
                line,
            )

            for candidate in candidates:

                if candidate not in ignored_pins:

                    return candidate

    # ========================================================
    # 5. LAST RESORT
    #
    # Search complete PDF text.
    # But ignore fixed KO Location PIN.
    # ========================================================

    for line in reversed(lines):

        candidates = re.findall(
            r"(?<!\d)(\d{6})(?!\d)",
            line,
        )

        for candidate in candidates:

            if candidate not in ignored_pins:

                return candidate

    return ""


# ============================================================
# EXTRACT ADDRESS
# ============================================================

def extract_address(lines):
    """
    Extract address from multiple known AOF layouts.
    """

    address_parts = []

    compact_lines = [
        compact(line)
        for line in lines
    ]

    # ========================================================
    # FORMAT 1
    #
    # Flat No./Bldg. Name
    # VALUE
    #
    # Street/Road/Locality
    # VALUE
    #
    # City/District/State with Pincode
    # VALUE
    # ========================================================

    for i, line_compact in enumerate(
        compact_lines
    ):

        if line_compact.startswith(
            "flatno./bldg.name"
        ):

            if i + 1 < len(lines):

                value = clean(
                    lines[i + 1]
                )

                if value:
                    address_parts.append(
                        value
                    )

        elif line_compact.startswith(
            "street/road/locality"
        ):

            if i + 1 < len(lines):

                value = clean(
                    lines[i + 1]
                )

                if value:
                    address_parts.append(
                        value
                    )

        elif line_compact.startswith(
            "city/district/statewithpincode"
        ):

            if i + 1 < len(lines):

                value = clean(
                    lines[i + 1]
                )

                if value:
                    address_parts.append(
                        value
                    )

    # ========================================================
    # FORMAT 2
    #
    # ADDRESS : VALUE
    # ========================================================

    if not address_parts:

        for i, line in enumerate(
            lines
        ):

            if re.match(
                r"^\s*ADDRESS\s*[:\-]",
                line,
                re.IGNORECASE,
            ):

                remainder = re.sub(
                    r"^\s*ADDRESS\s*[:\-]\s*",
                    "",
                    line,
                    flags=re.IGNORECASE,
                )

                remainder = clean(
                    remainder
                )

                if remainder:
                    address_parts.append(
                        remainder
                    )

                # ------------------------------------------------
                # Some PDFs continue address on next lines.
                # ------------------------------------------------

                for j in range(
                    i + 1,
                    min(
                        i + 5,
                        len(lines),
                    ),
                ):

                    candidate = clean(
                        lines[j]
                    )

                    if not candidate:
                        continue

                    candidate_compact = compact(
                        candidate
                    )

                    # Stop at next known field.
                    if candidate_compact in {
                        "pincode",
                        "pincode",
                        "customerid",
                        "accountno",
                        "accountnumber",
                        "name",
                        "ifscode",
                        "accounttype",
                        "koname",
                        "kolocation",
                    }:

                        break

                    # Stop if explicit next field appears.
                    if re.match(
                        r"^(PIN\s*CODE|CUSTOMER\s*ID|ACCOUNT\s*NO|NAME|IFSC|KO\s*NAME|KO\s*LOCATION)",
                        candidate,
                        re.IGNORECASE,
                    ):

                        break

                    address_parts.append(
                        candidate
                    )

                    # Stop after a PIN.
                    if re.search(
                        r"(?<!\d)\d{6}(?!\d)",
                        candidate,
                    ):

                        break

                break

    # ========================================================
    # FORMAT 3
    #
    # D/O, S/O, W/O, C/O address
    #
    # Example:
    #
    # W/O: Samsul Ansari, Laxmipur, Jurja,
    # Laxmipur, Jorja, 01719, 195, BH,
    # 847101 Tel.No/FaxNo.(withSTDcode)Email
    # ========================================================

    if not address_parts:

        for i, line in enumerate(
            lines
        ):

            if re.match(
                r"^(D/O|S/O|W/O|C/O)\b",
                line,
                re.IGNORECASE,
            ):

                collected = []

                for candidate in lines[i:]:

                    candidate = clean(
                        candidate
                    )

                    if not candidate:
                        continue

                    # --------------------------------------------
                    # Stop before telephone/fax/email section.
                    # --------------------------------------------

                    if re.search(
                        r"\bTel\.?\s*No\.?|"
                        r"\bFax\.?\s*No\.?|"
                        r"\bEmail\b",
                        candidate,
                        re.IGNORECASE,
                    ):

                        # Keep only the part before
                        # telephone/fax/email.
                        candidate = re.split(
                            r"\bTel\.?\s*No\.?|"
                            r"\bFax\.?\s*No\.?|"
                            r"\bEmail\b",
                            candidate,
                            flags=re.IGNORECASE,
                        )[0]

                        candidate = clean(
                            candidate
                        )

                        if candidate:
                            collected.append(
                                candidate
                            )

                        break

                    collected.append(
                        candidate
                    )

                    # --------------------------------------------
                    # Stop when customer PIN is found.
                    # --------------------------------------------

                    if re.search(
                        r"(?<!\d)\d{6}(?!\d)",
                        candidate,
                    ):

                        break

                address_parts = collected
                break

    # ========================================================
    # FORMAT 4
    #
    # Generic fallback:
    # Search for D/O/S/O/W/O/C/O anywhere in line.
    # ========================================================

    if not address_parts:

        for i, line in enumerate(
            lines
        ):

            match = re.search(
                r"\b(D/O|S/O|W/O|C/O)\s*[:\-]?",
                line,
                re.IGNORECASE,
            )

            if not match:
                continue

            collected = []

            for candidate in lines[i:]:

                candidate = clean(
                    candidate
                )

                if not candidate:
                    continue

                # Remove communication fields.
                communication_match = re.search(
                    r"\bTel\.?\s*No\.?|"
                    r"\bFax\.?\s*No\.?|"
                    r"\bEmail\b",
                    candidate,
                    re.IGNORECASE,
                )

                if communication_match:

                    candidate = candidate[
                        :communication_match.start()
                    ]

                    candidate = clean(
                        candidate
                    )

                    if candidate:
                        collected.append(
                            candidate
                        )

                    break

                collected.append(
                    candidate
                )

                if re.search(
                    r"(?<!\d)\d{6}(?!\d)",
                    candidate,
                ):

                    break

            address_parts = collected
            break

    # ========================================================
    # JOIN
    # ========================================================

    address = clean(
        " ".join(
            address_parts
        )
    )

    # ========================================================
    # CLEAN FINAL ADDRESS
    # ========================================================

    address = clean_address(
        address
    )

    return address


# ============================================================
# NORMALIZE CUSTOMER ID
# ============================================================

def normalize_customer_id(value):
    """
    Remove accidental spaces around Customer ID.

    Example:
        R19753279
        R19753279
        R 19753279

    becomes:
        R19753279
    """

    if not value:
        return ""

    value = clean(
        value
    )

    value = re.sub(
        r"\s+",
        "",
        value,
    )

    return value.upper()


# ============================================================
# NORMALIZE ACCOUNT NUMBER
# ============================================================

def normalize_account(value):
    if not value:
        return ""

    value = clean(
        value
    )

    return re.sub(
        r"\D",
        "",
        value,
    )


# ============================================================
# MAIN EXTRACTION
# ============================================================

def extract_aof(pdf_bytes):

    # ========================================================
    # READ PDF
    # ========================================================

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

    # ========================================================
    # CUSTOMER NAME
    # ========================================================

    name = after_label(
        lines,
        [
            "Customer Name",
            "CustomerName",
            "Name",
        ],
        r"^(.+)$",
        max_lines=5,
    )

    # ========================================================
    # ACCOUNT NUMBER
    # ========================================================

    account = after_label(
        lines,
        [
            "Account No",
            "Account No.",
            "Account Number",
            "AccountNumber",
        ],
        r"^(\d{8,20})$",
        max_lines=5,
    )

    # Fallback: account number may be on same line
    if not account:

        for line in lines:

            match = re.search(
                r"\bAccount\s*(?:No\.?|Number)\s*[:\-]?\s*(\d{8,20})\b",
                line,
                re.IGNORECASE,
            )

            if match:

                account = match.group(1)
                break

    account = normalize_account(
        account
    )

    # ========================================================
    # CUSTOMER ID
    # ========================================================

    customer_id = after_label(
        lines,
        [
            "Customer ID",
            "Customer IDss",
            "CustomerID",
            "Customer Id",
        ],
        r"^([A-Z0-9]{6,30})$",
        max_lines=5,
    )

    # Fallback: same line
    if not customer_id:

        for line in lines:

            match = re.search(
                r"\bCustomer\s*ID(?:ss)?\s*[:\-]?\s*([A-Z0-9]{6,30})\b",
                line,
                re.IGNORECASE,
            )

            if match:

                customer_id = match.group(1)
                break

    customer_id = normalize_customer_id(
        customer_id
    )

    # ========================================================
    # DATE OF BIRTH
    # ========================================================

    dob = after_label(
        lines,
        [
            "Date of Birth",
            "DateofBirth",
            "DOB",
        ],
        r"^(\d{4}[-/]\d{2}[-/]\d{2})$",
        max_lines=5,
    )

    # ========================================================
    # AADHAAR
    # ========================================================

    aadhaar = after_label(
        lines,
        [
            "Aadhaar No",
            "Aadhar No",
            "Aadhaar Number",
            "Aadhar Number",
        ],
        r"^([Xx\d\s]{4,24})$",
        max_lines=5,
    )

    aadhaar = clean(
        aadhaar
    )

    # ========================================================
    # MOBILE
    # ========================================================

    mobile = after_label(
        lines,
        [
            "Mobile No",
            "Mobile Number",
            "MobileNo",
        ],
        r"^(\d{10})$",
        max_lines=5,
    )

    # Fallback mobile
    if not mobile:

        for line in lines:

            match = re.search(
                r"\b(?:Mobile\s*(?:No\.?|Number)?)\s*[:\-]?\s*(\d{10})\b",
                line,
                re.IGNORECASE,
            )

            if match:

                mobile = match.group(1)
                break

    # ========================================================
    # ADDRESS
    # ========================================================

    address = extract_address(
        lines
    )

    # ========================================================
    # PIN CODE
    #
    # IMPORTANT:
    # Do this AFTER address extraction.
    # It can detect PIN even when address parser fails.
    # ========================================================

    pin = extract_pin_code(
        lines,
        address,
    )

    # ========================================================
    # If PIN found, ensure it is present in address when
    # address exists but does not contain it.
    #
    # This is useful for AOF layouts where PIN is shown
    # separately as:
    #
    # ADDRESS : ...
    # PIN CODE : 847101
    # ========================================================

    if (
        address
        and pin
        and not re.search(
            rf"(?<!\d){re.escape(pin)}(?!\d)",
            address,
        )
    ):

        # Only append PIN when address does not already
        # contain it. This keeps address useful for the
        # DOCX template and verification.
        address = clean(
            address
            + ", "
            + pin
        )

    # ========================================================
    # FINAL ADDRESS CLEANING
    # ========================================================

    address = clean_address(
        address
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
            bool(
                str(value).strip()
            )
            for value in required.values()
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
                re.IGNORECASE,
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
