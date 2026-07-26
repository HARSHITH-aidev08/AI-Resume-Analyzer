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


def analyze_resume(resume, job_role):

    if resume is None:
        return "❌ Please upload a resume."

    # Read uploaded PDF
    try:
        reader = PdfReader(resume.name)
        resume_text = ""
        for page in reader.pages:
            text = page.extract_text()
            if text:
                resume_text += text + "\n"
    except Exception as e:
        return f"## ❌ Error reading PDF\n\n{e}"

    if not resume_text.strip():
        return "❌ Could not extract any text from this PDF. It may be a scanned/image-based file."

    if job_role.strip() == "":
        job_role = "Infer the best role from the resume."

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
"""

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
            return f"## ❌ API Error\n\nStatus Code: **{response.status_code}**\n\n{response.text}"

        result = response.json()
        report = result.get("response", "No analysis returned.")

        # Extract ATS Score
        score = "N/A"
        match = re.search(r'ATS Score[:\s]*\**(\d+/\d+)', report)
        if match:
            score = match.group(1)

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
        return "## ❌ Error\n\nThe request timed out. Please try again."
    except Exception as e:
        return f"## ❌ Error\n\n{e}"


# ---- Gradio UI ----
with gr.Blocks(title="Resume Ascent AI") as demo:
    gr.Markdown("# 🚀 Resume Ascent AI\nUpload your resume and get an ATS-style analysis.")

    with gr.Row():
        resume_input = gr.File(label="Upload Resume (PDF)", file_types=[".pdf"])
        job_role_input = gr.Textbox(label="Target Job Role (optional)", placeholder="e.g. Data Scientist")

    analyze_btn = gr.Button("Analyze Resume", variant="primary")
    output = gr.Markdown()

    analyze_btn.click(
        fn=analyze_resume,
        inputs=[resume_input, job_role_input],
        outputs=output
    )
if __name__ == "__main__":
    demo.launch(server_name="0.0.0.0", server_port=int(os.environ.get("PORT", 7860)))