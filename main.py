import os
import json
import threading
import time
import requests
import io
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
        raw_text = ""

        # Try every possible password combination
        passwords_to_try = []
        if password and password.strip():
            passwords_to_try.append(password.strip())
        passwords_to_try.append("")      # no password
        passwords_to_try.append(None)    # also no password

        extracted = False
        last_error = ""

        for pwd in passwords_to_try:
            try:
                open_kwargs = {"file_like": io.BytesIO(file_bytes)}
                if pwd:
                    open_kwargs["password"] = pwd

                with pdfplumber.open(io.BytesIO(file_bytes), password=pwd or "") as pdf:
                    page_texts = []
                    for page in pdf.pages:
                        # Try multiple extraction strategies per page
                        text = None

                        # Strategy 1: default
                        try:
                            text = page.extract_text()
                        except:
                            pass

                        # Strategy 2: with tolerances
                        if not text:
                            try:
                                text = page.extract_text(x_tolerance=3, y_tolerance=3)
                            except:
                                pass

                        # Strategy 3: extract words and join
                        if not text:
                            try:
                                words = page.extract_words()
                                if words:
                                    text = " ".join(w["text"] for w in words)
                            except:
                                pass

                        # Strategy 4: extract tables and flatten
                        if not text:
                            try:
                                tables = page.extract_tables()
                                if tables:
                                    rows = []
                                    for table in tables:
                                        for row in table:
                                            rows.append(" | ".join(str(c) for c in row if c))
                                    text = "\n".join(rows)
                            except:
                                pass

                        if text and text.strip():
                            page_texts.append(text.strip())

                    if page_texts:
                        raw_text = "\n\n".join(page_texts)
                        extracted = True
                        break

            except Exception as e:
                last_error = str(e)
                continue

        if not extracted or not raw_text.strip():
            return {
                "error": f"Could not extract text from PDF. Error: {last_error}. The PDF may be scanned/image-based or password is incorrect.",
                "verified_monthly_salary": 0,
                "bounced_cheque_count": 0,
                "risk_score": 5,
                "total_emi": 0,
                "average_balance": 0,
                "summary": "PDF extraction failed. If password protected, please enter the correct password. Common passwords: date of birth (DDMMYYYY), PAN number, or mobile number."
            }

        # Truncate to 15000 chars to cover 3+ pages
        text_for_ai = raw_text[:15000]

        chat_completion = client.chat.completions.create(
            messages=[
                {
                    "role": "system",
                    "content": """You are an expert financial underwriter analyzing Indian bank statements.
Your job is to extract REAL numbers — never return 0 unless the actual value is truly zero.

Look carefully for:
- SALARY: Regular monthly credits from employer (look for words like salary, sal, credited by, NEFT from company names)
- EMI: Fixed monthly debits for loans (look for EMI, loan, housing loan, car loan, personal loan)
- BOUNCED CHEQUES: Any return/bounce/dishonour entries
- AVERAGE BALANCE: Explicitly stated or calculate from closing balances across pages
- RISK SCORE: 1=very low risk, 10=very high risk. Base on: salary regularity, bounce count, EMI burden ratio, balance maintenance

Return ONLY a valid JSON object with exactly these keys, no extra text:
{
  "verified_monthly_salary": <number in rupees>,
  "bounced_cheque_count": <integer>,
  "risk_score": <integer 1-10>,
  "total_emi": <number in rupees>,
  "average_balance": <number in rupees>,
  "summary": "<2-3 sentence financial summary>"
}"""
                },
                {
                    "role": "user",
                    "content": f"Analyze this bank statement and extract all real financial values:\n\n{text_for_ai}"
                }
            ],
            model="llama-3.3-70b-versatile",
            response_format={"type": "json_object"},
            temperature=0.0,
        )

        result = json.loads(chat_completion.choices[0].message.content)

        # Sanitize risk score
        if "risk_score" in result:
            result["risk_score"] = max(1, min(10, int(result["risk_score"])))

        # Add raw text length for debugging
        result["_debug_chars_extracted"] = len(raw_text)

        return result

    except Exception as e:
        return {"error": str(e)}
