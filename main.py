import os
import json
import threading
import time
import requests
from fastapi import FastAPI, File, UploadFile, Form
from fastapi.middleware.cors import CORSMiddleware
import pdfplumber
from groq import Groq

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

def keep_alive():
    while True:
        time.sleep(840)
        try:
            requests.get("https://credilens-api.onrender.com/")
        except:
            pass

threading.Thread(target=keep_alive, daemon=True).start()

@app.get("/")
def health_check():
    return {"status": "Backend is live and secure, Groq is connected!"}

@app.post("/upload")
async def analyze_statement(file: UploadFile = File(...), password: str = Form(None)):
    try:
        GROQ_API_KEY = os.environ.get("GROQ_API_KEY")
        client = Groq(api_key=GROQ_API_KEY)

        file_bytes = await file.read()

        import io
        raw_text = ""

        # Try with password first, then without
        passwords_to_try = [password] if password else []
        passwords_to_try.append(None)

        extracted = False
        for pwd in passwords_to_try:
            try:
                with pdfplumber.open(io.BytesIO(file_bytes), password=pwd) as pdf:
                    for page in pdf.pages:
                        # Try multiple extraction methods
                        text = page.extract_text(x_tolerance=3, y_tolerance=3)
                        if not text:
                            text = page.extract_text()
                        if text:
                            raw_text += text + "\n"
                if raw_text.strip():
                    extracted = True
                    break
            except Exception as e:
                continue

        if not extracted or not raw_text.strip():
            return {
                "error": "Could not extract text from PDF. Please ensure the correct password was entered and the PDF contains selectable text (not a scanned image).",
                "verified_monthly_salary": 0,
                "bounced_cheque_count": 0,
                "risk_score": 5,
                "total_emi": 0,
                "average_balance": 0,
                "summary": "PDF extraction failed. Please try again with the correct password."
            }

        # Send ALL pages (up to 15000 chars to cover 3 pages)
        chat_completion = client.chat.completions.create(
            messages=[
                {"role": "system", "content": """You are an expert financial underwriter analyzing an Indian bank statement.
Extract real numbers from the statement — do NOT return zeros unless the actual value is zero.
Look carefully for:
- Salary credits (regular monthly deposits from employer)
- EMI debits (loan repayments, recurring fixed debits)
- Cheque bounces (return/bounce entries)
- Average balance (mentioned explicitly or calculate from entries)

Return ONLY a valid JSON object with exactly these keys:
{"verified_monthly_salary": 0, "bounced_cheque_count": 0, "risk_score": 0, "total_emi": 0, "average_balance": 0, "summary": ""}
risk_score MUST be between 1 and 10. Higher score = higher risk."""},
                {"role": "user", "content": f"Analyze this bank statement carefully and extract real values:\n\n{raw_text[:15000]}"}
            ],
            model="llama-3.3-70b-versatile",
            response_format={"type": "json_object"},
            temperature=0.0,
        )

        result = json.loads(chat_completion.choices[0].message.content)
        if "risk_score" in result:
            result["risk_score"] = max(1, min(10, int(result["risk_score"])))
        return result

    except Exception as e:
        return {"error": str(e)}
