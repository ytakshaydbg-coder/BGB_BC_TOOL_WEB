from extractor import extract_aof


def parse_pdf(pdf_bytes):
    return extract_aof(pdf_bytes)
