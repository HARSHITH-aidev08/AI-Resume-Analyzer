import os
import re
import requests
import gradio as gr

from dotenv import load_dotenv
from pypdf import PdfReader


# =========================================================
# ENVIRONMENT CONFIGURATION
# =========================================================

load_dotenv()

API_KEY = os.getenv("LYZR_API_KEY")
AGENT_ID = os.getenv("AGENT_ID")

URL = "https://agent-prod.studio.lyzr.ai/v3/inference/chat/"

# Maximum amount of resume text sent to the AI.
# This prevents extremely large PDFs from creating huge prompts.
MAX_RESUME_CHARS = 30000


# =========================================================
# PDF TEXT EXTRACTION
# =========================================================

def extract_pdf_text(resume):
    """
    Extract readable text from the uploaded PDF.
    """

    try:
        reader = PdfReader(resume.name)

        # Check for encrypted PDF
        if reader.is_encrypted:
            try:
                reader.decrypt("")
            except Exception:
                raise Exception(
                    "This PDF is password-protected. "
                    "Please upload an unlocked resume PDF."
                )

        if len(reader.pages) == 0:
            raise Exception("The PDF does not contain any pages.")

        resume_text = []

        for page in reader.pages:

            try:
                text = page.extract_text()

                if text:
                    resume_text.append(text)

            except Exception:
                # Skip a problematic page instead of crashing
                continue

        final_text = "\n".join(resume_text)

        # Clean excessive whitespace
        final_text = re.sub(r"[ \t]+", " ", final_text)
        final_text = re.sub(r"\n\s*\n+", "\n\n", final_text)

        return final_text.strip()

    except Exception as e:

        raise Exception(
            f"Unable to read the PDF. {str(e)}"
        )


# =========================================================
# DOCUMENT VALIDATION
# =========================================================

def validate_document(text):
    """
    Determine whether the uploaded document reasonably
    resembles a resume.

    IMPORTANT:
    This intentionally avoids generic words such as:
    - DOB
    - Male/Female
    - Semester
    - Marks
    - Department

    because these can legitimately appear in student resumes.
    """

    text_lower = text.lower()

    # -----------------------------------------------------
    # STRONG AADHAAR / GOVERNMENT ID INDICATORS
    # -----------------------------------------------------

    aadhaar_keywords = [
        "aadhaar",
        "uidai",
        "my aadhaar",
        "aadhaar number",
        "aadhaar no",
        "aadhaar no.",
        "unique identification authority of india",
        "enrolment no",
        "enrolment number",
        "enrollment no",
        "enrollment number",
        "virtual id",
        "virtual identification number"
    ]

    aadhaar_matches = [
        word for word in aadhaar_keywords
        if word in text_lower
    ]

    # -----------------------------------------------------
    # STRONG ACADEMIC DOCUMENT INDICATORS
    # -----------------------------------------------------

    assignment_keywords = [
        "question paper",
        "question bank",
        "assignment question",
        "problem statement",
        "internal assessment",
        "model question paper",
        "end semester examination",
        "end semester exam",
        "mid semester examination",
        "mid semester exam",
        "unit test question",
        "laboratory manual",
        "lab manual",
        "experiment no",
        "experiment number",
        "experiment-1",
        "experiment 1"
    ]

    assignment_matches = [
        word for word in assignment_keywords
        if word in text_lower
    ]

    # -----------------------------------------------------
    # CERTIFICATE INDICATORS
    # -----------------------------------------------------

    certificate_keywords = [
        "certificate of completion",
        "certificate of participation",
        "certificate of achievement",
        "certificate of appreciation",
        "this is to certify that",
        "has successfully completed",
        "has successfully participated"
    ]

    certificate_matches = [
        word for word in certificate_keywords
        if word in text_lower
    ]

    # -----------------------------------------------------
    # FINANCIAL DOCUMENT INDICATORS
    # -----------------------------------------------------

    financial_keywords = [
        "tax invoice",
        "gst invoice",
        "invoice number",
        "invoice no",
        "amount payable",
        "bank statement",
        "account statement",
        "transaction statement"
    ]

    financial_matches = [
        word for word in financial_keywords
        if word in text_lower
    ]

    # -----------------------------------------------------
    # RESUME INDICATORS
    # -----------------------------------------------------

    resume_keywords = [
        "education",
        "skills",
        "technical skills",
        "technical expertise",
        "projects",
        "experience",
        "work experience",
        "professional experience",
        "internship",
        "internships",
        "certifications",
        "achievements",
        "career objective",
        "professional summary",
        "profile summary",
        "summary",
        "objective",
        "linkedin",
        "github",
        "portfolio",
        "programming languages",
        "work history",
        "responsibilities",
        "publications",
        "technical skills",
        "soft skills"
    ]

    resume_matches = [
        word for word in resume_keywords
        if word in text_lower
    ]

    resume_score = len(resume_matches)

    # -----------------------------------------------------
    # CONTACT INFORMATION
    # -----------------------------------------------------

    email_exists = bool(
        re.search(
            r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b",
            text
        )
    )

    phone_exists = bool(
        re.search(
            r"(?:\+91[\s-]?)?[6-9]\d{9}",
            text
        )
    )

    linkedin_exists = (
        "linkedin.com" in text_lower
        or "linkedin" in text_lower
    )

    github_exists = (
        "github.com" in text_lower
        or "github" in text_lower
    )

    contact_score = sum([
        email_exists,
        phone_exists,
        linkedin_exists,
        github_exists
    ])

    # -----------------------------------------------------
    # DOCUMENT LENGTH
    # -----------------------------------------------------

    # Extremely short PDFs are unlikely to be resumes.
    word_count = len(text.split())

    # -----------------------------------------------------
    # PRIORITY 1:
    # Strong evidence of NON-RESUME
    # -----------------------------------------------------

    if len(aadhaar_matches) >= 2 and resume_score < 3:

        return False, (
            "The uploaded document appears to be an "
            "Aadhaar or government identity document."
        )

    if len(assignment_matches) >= 2 and resume_score < 3:

        return False, (
            "The uploaded document appears to be an "
            "academic assignment, examination paper, "
            "question paper, or college document."
        )

    if len(certificate_matches) >= 2 and resume_score < 3:

        return False, (
            "The uploaded document appears to be a "
            "certificate rather than a resume."
        )

    if len(financial_matches) >= 2 and resume_score < 3:

        return False, (
            "The uploaded document appears to be an "
            "invoice, bank statement, or financial document."
        )

    # -----------------------------------------------------
    # PRIORITY 2:
    # STRONG RESUME EVIDENCE
    # -----------------------------------------------------

    # 3 or more resume sections = likely resume
    if resume_score >= 3:
        return True, ""

    # 2 sections + contact information
    if resume_score >= 2 and contact_score >= 1:
        return True, ""

    # 1 section + multiple contact indicators
    if resume_score >= 1 and contact_score >= 2:
        return True, ""

    # -----------------------------------------------------
    # PRIORITY 3:
    # VERY SHORT DOCUMENT
    # -----------------------------------------------------

    if word_count < 40:

        return False, (
            "The uploaded PDF contains very little text "
            "and does not appear to be a complete resume."
        )

    # -----------------------------------------------------
    # FINAL REJECTION
    # -----------------------------------------------------

    return False, (
        "The document does not contain enough resume-related "
        "information such as Education, Skills, Projects, "
        "Experience, Internships, Certifications, or a "
        "professional summary."
    )


# =========================================================
# FORMAT ERROR MESSAGE
# =========================================================

def invalid_resume_message(reason):

    return f"""
# ❌ Invalid Resume

### Why was this document rejected?

**{reason}**

---

### 📄 Please upload a proper resume/CV

A resume normally contains information such as:

- 👤 Name
- 📧 Email
- 📱 Phone number
- 🎯 Career Objective / Summary
- 🎓 Education
- 💻 Technical Skills
- 🚀 Projects
- 💼 Experience / Internships
- 📜 Certifications
- 🏆 Achievements
- 🔗 LinkedIn / GitHub / Portfolio

### 🔒 Privacy

The uploaded document was rejected during local
document validation and was **not sent to the Lyzr
AI analyzer**.

Please upload your resume as a PDF.
"""


# =========================================================
# CHECK ENVIRONMENT
# =========================================================

def check_configuration():

    missing = []

    if not API_KEY:
        missing.append("LYZR_API_KEY")

    if not AGENT_ID:
        missing.append("AGENT_ID")

    if missing:

        return False, (
            "Missing environment variable(s): "
            + ", ".join(missing)
        )

    return True, ""


# =========================================================
# LYZR API CALL
# =========================================================

def call_lyzr(prompt):

    # -----------------------------------------------------
    # Check configuration
    # -----------------------------------------------------

    configured, error = check_configuration()

    if not configured:
        raise Exception(error)

    # -----------------------------------------------------
    # Headers
    # -----------------------------------------------------

    headers = {
        "Content-Type": "application/json",
        "x-api-key": API_KEY
    }

    # -----------------------------------------------------
    # Payload
    # -----------------------------------------------------

    payload = {
        "user_id": "resume-user",
        "agent_id": AGENT_ID,
        "session_id": "resume-session",
        "message": prompt
    }

    # -----------------------------------------------------
    # API REQUEST
    # -----------------------------------------------------

    try:

        response = requests.post(
            URL,
            headers=headers,
            json=payload,
            timeout=120
        )

    except requests.exceptions.Timeout:

        raise Exception(
            "The Lyzr request timed out. "
            "Please try again."
        )

    except requests.exceptions.ConnectionError:

        raise Exception(
            "Could not connect to the Lyzr API. "
            "Please check your internet connection "
            "and try again."
        )

    except requests.exceptions.RequestException as e:

        raise Exception(
            f"Network error while contacting Lyzr: {str(e)}"
        )

    # -----------------------------------------------------
    # HTTP STATUS HANDLING
    # -----------------------------------------------------

    if response.status_code == 401:

        raise Exception(
            "Lyzr authentication failed. "
            "Please check your LYZR_API_KEY."
        )

    if response.status_code == 403:

        raise Exception(
            "Lyzr rejected the request. "
            "Please check your API key and agent permissions."
        )

    if response.status_code == 404:

        raise Exception(
            "Lyzr agent or API endpoint was not found. "
            "Please check your AGENT_ID."
        )

    if response.status_code == 429:

        raise Exception(
            "Lyzr rate limit reached. "
            "Please wait a moment and try again."
        )

    if response.status_code >= 500:

        raise Exception(
            "Lyzr is currently experiencing a server-side "
            "problem. Please try again later."
        )

    if response.status_code != 200:

        # Don't expose the complete API response to the user.
        # It may contain implementation details.

        raise Exception(
            f"Lyzr returned HTTP status {response.status_code}."
        )

    # -----------------------------------------------------
    # PARSE JSON
    # -----------------------------------------------------

    try:

        result = response.json()

    except ValueError:

        raise Exception(
            "Lyzr returned an invalid response format."
        )

    # -----------------------------------------------------
    # EXTRACT RESPONSE
    # -----------------------------------------------------

    report = result.get("response")

    if report is None:

        # Some APIs may return a slightly different
        # structure. Handle common alternatives.

        if isinstance(result.get("message"), str):
            report = result["message"]

        elif isinstance(result.get("output"), str):
            report = result["output"]

        else:
            raise Exception(
                "Lyzr returned successfully, but no analysis "
                "was found in the response."
            )

    if not isinstance(report, str):

        report = str(report)

    if not report.strip():

        raise Exception(
            "Lyzr returned an empty analysis."
        )

    return report.strip()


# =========================================================
# EXTRACT ATS SCORE
# =========================================================

def extract_ats_score(report):

    patterns = [

        # ATS Score: 85/100
        r"ATS\s*Score\s*[:\-]?\s*\**\s*(\d{1,3})\s*/\s*100",

        # ATS Score - 85
        r"ATS\s*Score\s*[:\-]?\s*\**\s*(\d{1,3})",

        # Score: 85/100
        r"Score\s*[:\-]?\s*\**\s*(\d{1,3})\s*/\s*100"

    ]

    for pattern in patterns:

        match = re.search(
            pattern,
            report,
            re.IGNORECASE
        )

        if match:

            score = int(match.group(1))

            # Keep score within valid range
            if 0 <= score <= 100:
                return f"{score}/100"

    return "N/A"


# =========================================================
# MAIN RESUME ANALYSIS
# =========================================================

def analyze_resume(resume, job_role):

    # -----------------------------------------------------
    # STEP 1: Check upload
    # -----------------------------------------------------

    if resume is None:

        return """
# ⚠️ No Resume Uploaded

Please upload your resume in **PDF format**.
"""

    # -----------------------------------------------------
    # STEP 2: Validate file extension
    # -----------------------------------------------------

    filename = getattr(
        resume,
        "name",
        ""
    )

    if not filename.lower().endswith(".pdf"):

        return """
# ❌ Invalid File

Please upload your resume as a **PDF file**.
"""

    # -----------------------------------------------------
    # STEP 3: Extract PDF text
    # -----------------------------------------------------

    try:

        resume_text = extract_pdf_text(resume)

    except Exception as e:

        return f"""
# ❌ Unable to Read PDF

### Error

{str(e)}

### Please try

- Uploading another PDF
- Removing the PDF password
- Exporting your resume again as PDF
"""

    # -----------------------------------------------------
    # STEP 4: Check extracted text
    # -----------------------------------------------------

    if not resume_text:

        return """
# ❌ Invalid Resume

### Why?

No readable text could be extracted from this PDF.

The PDF may be:

- 🖼️ Image-only
- 📷 Scanned
- 🔒 Password-protected
- 📄 Empty
- ❌ Corrupted

Please upload a **text-based PDF resume**.

If your resume is an image/scanned PDF, OCR support
would be required to read it.
"""

    # -----------------------------------------------------
    # STEP 5: Validate document
    # -----------------------------------------------------

    valid_resume, reason = validate_document(
        resume_text
    )

    if not valid_resume:

        return invalid_resume_message(reason)

    # -----------------------------------------------------
    # STEP 6: Limit resume size
    # -----------------------------------------------------

    if len(resume_text) > MAX_RESUME_CHARS:

        resume_text = resume_text[:MAX_RESUME_CHARS]

        resume_text += (
            "\n\n[Resume text truncated because the "
            "document was extremely large.]"
        )

    # -----------------------------------------------------
    # STEP 7: Target role
    # -----------------------------------------------------

    if not job_role or not job_role.strip():

        job_role = (
            "Infer the most suitable job role from "
            "the resume."
        )

    else:

        job_role = job_role.strip()

    # -----------------------------------------------------
    # STEP 8: Create Lyzr prompt
    # -----------------------------------------------------

    prompt = f"""
You are an expert ATS recruiter, resume reviewer,
and career coach.

TARGET JOB ROLE:
{job_role}

RESUME:
{resume_text}

=========================================================
TASK
=========================================================

Analyze the resume specifically for the target job role.

If the target job role is:
"Infer the most suitable job role from the resume."

then first identify the most suitable role based on
the candidate's education, skills, projects, experience,
and overall profile.

=========================================================
OUTPUT FORMAT
=========================================================

Provide the following sections:

# ATS Score
Give a score from 0 to 100.

# Candidate Summary
Give a concise professional summary.

# Strengths
List the strongest parts of the resume.

# Weaknesses
Identify important weaknesses.

# Missing Skills
Identify skills that are missing for the target role.

# ATS Improvements
Give practical changes that would improve ATS performance.

# Suggested Projects
Suggest projects that would strengthen the candidate's
profile for the target role.

# Recommended Certifications
Suggest relevant certifications.

# Interview Questions
Give relevant technical and HR interview questions.

# Final Recommendation
Clearly state whether the resume is:
- Strongly aligned
- Moderately aligned
- Weakly aligned

Also explain the most important next steps.

=========================================================
IMPORTANT RULES
=========================================================

1. Analyze ONLY information present in the resume.
2. Do not invent experience, skills, degrees, projects,
   certifications, or achievements.
3. Clearly distinguish between existing skills and
   recommended skills.
4. Keep the analysis practical for a student/job seeker.
5. The ATS score must be between 0 and 100.
6. Use Markdown headings and bullet points.
"""

    # -----------------------------------------------------
    # STEP 9: Call Lyzr
    # -----------------------------------------------------

    try:

        report = call_lyzr(prompt)

    except Exception as e:

        return f"""
# ❌ Resume Analysis Failed

### What happened?

{str(e)}

### What you can try

1. Check your internet connection.
2. Check your Lyzr API key.
3. Check your Agent ID.
4. Try again after a few seconds.

Your resume passed local document validation.
"""

    # -----------------------------------------------------
    # STEP 10: Extract ATS score
    # -----------------------------------------------------

    score = extract_ats_score(report)

    # -----------------------------------------------------
    # STEP 11: Display result
    # -----------------------------------------------------

    formatted = f"""
# 🚀 Resume Ascent AI

---

# 🎯 ATS SCORE

## **{score}**

---

{report}

---

### ✅ Analysis Complete

Your resume was successfully validated and analyzed
for the selected job role.
"""

    return formatted


# =========================================================
# GRADIO UI
# =========================================================

with gr.Blocks(
    title="Resume Ascent AI"
) as demo:

    gr.Markdown(
        """
# 🚀 Resume Ascent AI

### AI-Powered ATS Resume Analyzer

Upload your **resume/CV in PDF format** and receive
an ATS-style analysis.

---

### 📋 The analyzer checks

- Resume validity
- Resume structure
- Skills
- Education
- Projects
- Experience
- Certifications
- ATS compatibility
- Missing skills
- Interview preparation

### 🔒 Privacy

Please **do not upload Aadhaar cards, identity documents,
bank statements, or other sensitive documents**.
"""
    )

    with gr.Row():

        resume_input = gr.File(
            label="📄 Upload Resume (PDF)",
            file_types=[".pdf"],
            type="filepath"
        )

        job_role_input = gr.Textbox(
            label="🎯 Target Job Role (Optional)",
            placeholder="Example: Data Scientist",
            lines=1
        )

    analyze_btn = gr.Button(
        "🚀 Analyze Resume",
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


# =========================================================
# APPLICATION START
# =========================================================

if __name__ == "__main__":

    port = int(
        os.environ.get("PORT", 7860)
    )

    demo.launch(
        server_name="0.0.0.0",
        server_port=port
    )
