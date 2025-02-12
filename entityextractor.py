import streamlit as st
import fitz  # PyMuPDF
import spacy
import re
import json
from dateutil import parser
import pytesseract
from PIL import Image
import io

# Load spaCy's English model (ensure it's installed: python -m spacy download en_core_web_sm)
nlp = spacy.load("en_core_web_sm")

def extract_text_from_pdf(pdf_bytes):
    """
    Extract text from a PDF using PyMuPDF. If no text is found (e.g., scanned pages),
    OCR is applied using pytesseract.
    """
    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    full_text = ""
    for page in doc:
        text = page.get_text().strip()
        if not text:
            # Use OCR if the page contains images
            pix = page.get_pixmap()
            img_bytes = pix.tobytes("png")
            image = Image.open(io.BytesIO(img_bytes))
            text = pytesseract.image_to_string(image)
        full_text += text + "\n"
    return full_text

def convert_date(date_str):
    """
    Convert a date string to ISO format (YYYY-MM-DD) if possible.
    """
    try:
        dt = parser.parse(date_str)
        return dt.strftime("%Y-%m-%d")
    except Exception:
        return "unknown"

def extract_entities(text):
    """
    Extract entity data from text using spaCy and regex based on the WorldCat Person ontology.
    """
    data = {
        "givenName": "unknown",
        "surname": "unknown",
        "dateOfBirth": "unknown",
        "dateOfDeath": "unknown",
        "occupation": [],
        "educatedAt": "unknown",
        "placeOfBirth": "unknown",
        "placeOfDeath": "unknown",
        "residence": "unknown",
        "parent": [],
        "child": [],
        "sibling": [],
        "spouse": "unknown",
        "awardReceived": [],
        "employedBy": "unknown",
        "studentOf": [],
        "influencedBy": []
    }

    # Process text with spaCy
    doc = nlp(text)
    sentences = list(doc.sents)
    
    # Full Name, Date of Birth & Date of Death extraction
    if sentences:
        first_sentence = sentences[0].text.strip()
        # Extract full name (assumed to be before the first parenthesis)
        name_match = re.match(r"^(.*?)\s*\(", first_sentence)
        if name_match:
            full_name = name_match.group(1).strip()
            parts = full_name.split()
            if len(parts) >= 2:
                data["givenName"] = " ".join(parts[:-1])
                data["surname"] = parts[-1]
            else:
                data["givenName"] = full_name

        # Extract dates from within the parentheses (e.g., "9 November 1898 – 14 December 1997")
        paren_match = re.search(r"\(([^)]*)\)", first_sentence)
        if paren_match:
            paren_content = paren_match.group(1)
            dates = re.findall(r"(\d{1,2}\s+[A-Za-z]+\s+\d{4})", paren_content)
            if dates:
                data["dateOfBirth"] = convert_date(dates[0])
            if len(dates) >= 2:
                data["dateOfDeath"] = convert_date(dates[1])
    
    # Occupation extraction
    occ_match = re.search(r"was (?:an|a)\s+([\w\s,]+?)[\.,;]", first_sentence, re.IGNORECASE)
    if occ_match:
        occ_text = occ_match.group(1).strip()
        data["occupation"] = [o.strip() for o in occ_text.split(",") if o.strip()]

    # Education / Alma Mater extraction
    edu_match = re.search(r"(?:educated at|attended)\s+([^.,;]+)", text, re.IGNORECASE)
    if edu_match:
        data["educatedAt"] = edu_match.group(1).strip()

    # Place of Birth extraction
    pob_match = re.search(r"born in\s+([^.,;]+)", text, re.IGNORECASE)
    if pob_match:
        data["placeOfBirth"] = pob_match.group(1).strip()

    # Place of Death extraction
    pod_match = re.search(r"died in\s+([^.,;]+)", text, re.IGNORECASE)
    if pod_match:
        data["placeOfDeath"] = pod_match.group(1).strip()

    # Residence extraction
    residence_match = re.search(r"residence:\s*([^.;\n]+)", text, re.IGNORECASE)
    if residence_match:
        data["residence"] = residence_match.group(1).strip()

    # Spouse extraction
    spouse_match = re.search(r"(?:spouse|married to)\s+([A-Z][a-zA-Z\s]+)", text)
    if spouse_match:
        data["spouse"] = spouse_match.group(1).strip()

    # Children extraction
    children_match = re.search(r"children?:\s*([^.;\n]+)", text, re.IGNORECASE)
    if children_match:
        children = [child.strip() for child in children_match.group(1).split(",") if child.strip()]
        data["child"] = children

    # Siblings extraction
    sibling_match = re.search(r"siblings?:\s*([^.;\n]+)", text, re.IGNORECASE)
    if sibling_match:
        siblings = [sib.strip() for sib in sibling_match.group(1).split(",") if sib.strip()]
        data["sibling"] = siblings

    # Parents extraction
    parent_matches = re.findall(r"(?:father|mother|parent)[’']?s?\s*[:\-]?\s*([A-Z][a-zA-Z\s]+)", text)
    if parent_matches:
        data["parent"] = list(set(p.strip() for p in parent_matches if p.strip()))

    # Awards/Honors extraction
    awards_match = re.search(r"(?:award|honor)[s]?:?\s*([^.;\n]+)", text, re.IGNORECASE)
    if awards_match:
        awards = [award.strip() for award in awards_match.group(1).split(",") if award.strip()]
        data["awardReceived"] = awards

    # Employer extraction
    emp_match = re.search(r"employed by\s+([^.,;]+)", text, re.IGNORECASE)
    if emp_match:
        data["employedBy"] = emp_match.group(1).strip()

    # Students and Influences extraction
    student_match = re.search(r"student of\s+([^.,;]+)", text, re.IGNORECASE)
    if student_match:
        data["studentOf"] = [s.strip() for s in student_match.group(1).split(",") if s.strip()]

    influenced_match = re.search(r"influenced by\s+([^.,;]+)", text, re.IGNORECASE)
    if influenced_match:
        data["influencedBy"] = [s.strip() for s in influenced_match.group(1).split(",") if s.strip()]

    return data

def extract_data_from_pdf(person_pdf_bytes, ontology_pdf_bytes=None):
    """
    Extract entity data from the biography PDF and output a JSON-LD structure 
    following the WorldCat Person ontology.
    """
    text = extract_text_from_pdf(person_pdf_bytes)
    extracted = extract_entities(text)
    json_ld = {
        "@context": "https://id.oclc.org/worldcat/ontology/",
        "@type": "Person",
        "givenName": extracted["givenName"],
        "surname": extracted["surname"],
        "dateOfBirth": extracted["dateOfBirth"],
        "dateOfDeath": extracted["dateOfDeath"],
        "occupation": extracted["occupation"],
        "educatedAt": extracted["educatedAt"],
        "placeOfBirth": extracted["placeOfBirth"],
        "placeOfDeath": extracted["placeOfDeath"],
        "residence": extracted["residence"],
        "parent": extracted["parent"],
        "child": extracted["child"],
        "sibling": extracted["sibling"],
        "spouse": extracted["spouse"],
        "awardReceived": extracted["awardReceived"],
        "employedBy": extracted["employedBy"],
        "studentOf": extracted["studentOf"],
        "influencedBy": extracted["influencedBy"]
    }
    return json_ld

def main():
    st.title("PDF Biography Entity Extractor")
    st.write("Upload a PDF containing biographical information (e.g., a Wikipedia article).")
    
    person_pdf_file = st.file_uploader("Upload Biography PDF", type=["pdf"])
    ontology_pdf_file = st.file_uploader("Upload Ontology PDF (optional)", type=["pdf"])
    
    if person_pdf_file is not None:
        person_pdf_bytes = person_pdf_file.read()
        ontology_pdf_bytes = ontology_pdf_file.read() if ontology_pdf_file is not None else None

        with st.spinner("Extracting data, please wait..."):
            result = extract_data_from_pdf(person_pdf_bytes, ontology_pdf_bytes)
        st.success("Extraction complete!")
        st.json(result)

if __name__ == "__main__":
    main()
