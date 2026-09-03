import os
import re
import requests
import gradio as gr
from dotenv import load_dotenv
from pypdf import PdfReader

load_dotenv()

API_KEY = os.getenv("LYZR_API_KEY")
AGENT_ID = os.getenv("AGENT_ID")

URL = "https://agent-prod.studio.lyzr.ai/v3/inference/chat/"


# ---------------------------------------------------------
# 1. EXTRACT PDF TEXT
# ---------------------------------------------------------

def extract_pdf_text(resume):

    try:
        reader = PdfReader(resume.name)

        resume_text = ""

        for page in reader.pages:
            text = page.extract_text()

            if text:
                resume_text += text + "\n"

        return resume_text.strip()

    except Exception as e:
        raise Exception(f"Error reading PDF: {e}")


# ---------------------------------------------------------
# 2. CHECK FOR SENSITIVE / NON-RESUME DOCUMENTS
# ---------------------------------------------------------

def detect_invalid_document(text):

    text_lower = text.lower()

    # -----------------------------------------
    # Aadhaar / Government ID indicators
    # -----------------------------------------

    aadhaar_keywords = [
        "aadhaar",
        "uidai",
        "unique identification authority",
        "government of india",
        "my aadhaar",
        "enrolment number",
        "enrollment number",
        "vid number",
        "date of birth",
        "dob",
        "male",
        "female"
    ]

    aadhaar_matches = sum(
        1 for keyword in aadhaar_keywords
        if keyword in text_lower
    )

    if aadhaar_matches >= 2:
        return (
            False,
            "This document appears to be an Aadhaar or government identity document. "
            "Please upload a resume instead."
        )

    # -----------------------------------------
    # Assignment / academic document indicators
    # -----------------------------------------

    assignment_keywords = [
        "assignment",
        "question paper",
        "question bank",
        "department of",
        "submitted to",
        "submitted by",
        "roll number",
        "register number",
        "semester",
        "internal assessment",
        "unit test",
        "laboratory",
        "experiment",
        "problem statement",
        "marks",
        "course code"
    ]

    assignment_matches = sum(
        1 for keyword in assignment_keywords
        if keyword in text_lower
    )

    if assignment_matches >= 3:
        return (
            False,
            "This document appears to be an academic assignment or college document, "
            "not a resume."
        )

    # -----------------------------------------
    # Certificate indicators
    # -----------------------------------------

    certificate_keywords = [
        "certificate of completion",
        "certificate of participation",
        "this is to certify",
        "certificate",
        "has successfully completed",
        "has successfully participated"
    ]

    certificate_matches = sum(
        1 for keyword in certificate_keywords
        if keyword in text_lower
    )

    if certificate_matches >= 2:
        return (
            False,
            "This document appears to be a certificate rather than a resume."
        )

    # -----------------------------------------
    # Invoice / financial document indicators
    # -----------------------------------------

    financial_keywords = [
        "invoice",
        "tax invoice",
        "gstin",
        "total amount",
        "amount payable",
        "bill number",
        "invoice number",
        "bank statement",
        "account number"
    ]

    financial_matches = sum(
        1 for keyword in financial_keywords
        if keyword in text_lower
    )

    if financial_matches >= 2:
        return (
            False,
            "This document appears to be a financial or billing document, "
            "not a resume."
        )

    return True, ""


# ---------------------------------------------------------
# 3. CHECK WHETHER DOCUMENT LOOKS LIKE A RESUME
# ---------------------------------------------------------

def validate_resume_structure(text):

    text_lower = text.lower()

    resume_sections = [
        "education",
        "experience",
        "skills",
        "projects",
        "certifications",
        "summary",
        "objective",
        "work experience",
        "professional experience",
        "technical skills",
        "achievements",
        "internship",
        "internships",
        "contact"
    ]

    matched_sections = [
        section
        for section in resume_sections
        if section in text_lower
    ]

    # A reasonable resume should contain at least 3
    # resume-related sections.

    if len(matched_sections) < 3:

        return (
            False,
            "The document does not contain enough resume-related sections "
            "such as Education, Skills, Experience, Projects, or Certifications."
        )

    # -----------------------------------------
    # Check for contact information
    # -----------------------------------------

    email_exists = re.search(
        r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b',
        text
    )

    phone_exists = re.search(
        r'(\+91[\s-]?)?[6-9]\d{9}',
        text
    )

    if not email_exists and not phone_exists:

        return (
            False,
            "The document does not appear to contain normal resume contact "
            "information such as an email address or phone number."
        )

    return True, ""


# ---------------------------------------------------------
# 4. MAIN ANALYSIS FUNCTION
# ---------------------------------------------------------

def analyze_resume(resume, job_role):

    if resume is None:
        return "❌ **Please upload a resume in PDF format.**"

    # -----------------------------------------
    # Extract PDF
    # -----------------------------------------

    try:
        resume_text = extract_pdf_text(resume)

    except Exception as e:
        return f"""
# ❌ Invalid PDF

{e}
"""

    if not resume_text:

        return """
# ❌ Invalid Resume

**Reason:** No readable text could be extracted from this PDF.

The file may be:
- A scanned document
- An image-only PDF
- An empty PDF
- A corrupted PDF

Please upload a text-based resume PDF.
"""

    # -----------------------------------------
    # STEP 1: Detect obviously wrong documents
    # -----------------------------------------

    valid_document, reason = detect_invalid_document(resume_text)

    if not valid_document:

        return f"""
# ❌ Invalid Resume

### Why is this document invalid?

{reason}

### Please upload

A professional resume containing information such as:

- Name
- Contact information
- Career objective/summary
- Education
- Skills
- Projects
- Internships
- Work experience
- Certifications
- Achievements

**Your document was rejected before being sent for resume analysis.**
"""

    # -----------------------------------------
    # STEP 2: Check resume structure
    # -----------------------------------------

    valid_resume, reason = validate_resume_structure(resume_text)

    if not valid_resume:

        return f"""
# ❌ Invalid Resume

### Why is this document invalid?

{reason}

The uploaded file does not appear to be a resume.

Please upload a proper resume/CV PDF.
"""

    # -----------------------------------------
    # STEP 3: Target role
    # -----------------------------------------

    if not job_role or job_role.strip() == "":
        job_role = "Infer the best role from the resume."

    # -----------------------------------------
    # STEP 4: Create AI prompt
    # -----------------------------------------

    prompt = f"""
You are an expert ATS recruiter and career coach.

Target Job Role:
{job_role}

Resume:
{resume_text}

Instructions:

If the target role is not provided,
first infer the most suitable role.

Then provide:

1. ATS Score (/100)
2. Candidate Summary
3. Strengths
4. Weaknesses
5. Missing Skills
6. ATS Improvements
7. Suggested Projects
8. Recommended Certifications
9. Interview Questions
10. Final Recommendation

Important:
Analyze only the resume.
Do not assume information that is not present.
"""

    # -----------------------------------------
    # STEP 5: Lyzr API
    # -----------------------------------------

    headers = {
        "Content-Type": "application/json",
        "x-api-key": API_KEY
    }

    payload = {
        "user_id": "resume-user",
        "agent_id": AGENT_ID,
        "session_id": "resume-session",
        "message": prompt
    }

    try:

        response = requests.post(
            URL,
            headers=headers,
            json=payload,
            timeout=120
        )

        if response.status_code != 200:

            return f"""
# ❌ API Error

**Status Code:** {response.status_code}

Please try again later.
"""

        result = response.json()

        report = result.get(
            "response",
            "No analysis returned."
        )

        # -----------------------------------------
        # Extract ATS score
        # -----------------------------------------

        score = "N/A"

        match = re.search(
            r'ATS Score[:\s]*\**\s*(\d+)\s*/\s*100',
            report,
            re.IGNORECASE
        )

        if match:
            score = f"{match.group(1)}/100"

        formatted = f"""
# 🚀 Resume Ascent AI

---

# 🎯 ATS SCORE

## **{score}**

---

{report}
"""

        return formatted

    except requests.exceptions.Timeout:

        return """
# ❌ Error

The AI analysis request timed out.

Please try again.
"""

    except Exception as e:

        return f"""
# ❌ Error

{e}
"""


# ---------------------------------------------------------
# GRADIO UI
# ---------------------------------------------------------

with gr.Blocks(title="Resume Ascent AI") as demo:

    gr.Markdown(
        """
# 🚀 Resume Ascent AI

Upload your **resume/CV in PDF format** and get an ATS-style analysis.

⚠️ Please do not upload Aadhaar cards, identity documents,
college assignments, certificates, or other sensitive documents.
"""
    )

    with gr.Row():

        resume_input = gr.File(
            label="Upload Resume (PDF)",
            file_types=[".pdf"]
        )

        job_role_input = gr.Textbox(
            label="Target Job Role (optional)",
            placeholder="e.g. Data Scientist"
        )

    analyze_btn = gr.Button(
        "Analyze Resume",
        variant="primary"
    )

    output = gr.Markdown()

    analyze_btn.click(
        fn=analyze_resume,
        inputs=[
            resume_input,
            job_role_input
        ],
        outputs=output
    )


if __name__ == "__main__":

    demo.launch(
        server_name="0.0.0.0",
        server_port=int(
            os.environ.get("PORT", 7860)
        )
    )
