import os
import json
from fastapi import FastAPI, File, UploadFile
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

GROQ_API_KEY = os.environ.get("GROQ_API_KEY")
client = Groq(api_key=GROQ_API_KEY)

@app.get("/")
def health_check():
    return {"status": "Backend is live and secure"}

@app.post("/upload")
async def analyze_statement(file: UploadFile = File(...)):
    try:
        raw_text = ""
        with pdfplumber.open(file.file) as pdf:
            for page in pdf.pages:
                text = page.extract_text()
                if text:
                    raw_text += text + "\n"

        chat_completion = client.chat.completions.create(
            messages=[
                {
                    "role": "system",
                    "content": """You are an expert financial underwriter analyzing an Indian bank statement.
Return ONLY a valid JSON object with exactly these keys:
{"verified_monthly_salary": 0, "bounced_cheque_count": 0, "risk_score": 0, "total_emi": 0, "average_balance": 0, "summary": ""}
IMPORTANT: risk_score MUST be a single number between 1 and 10. Never more than 10."""
                },
                {
                    "role": "user",
                    "content": f"Analyze this bank statement:\n{raw_text[:10000]}"
                }
            ],
            model="llama-3.3-70b-versatile",
            response_format={"type": "json_object"},
            temperature=0.0,
        )

        result = json.loads(chat_completion.choices[0].message.content)

        if "risk_score" in result:
            score = int(result["risk_score"])
            if score > 10:
                score = score % 10 or 10
            result["risk_score"] = max(1, min(10, score))

        return result

    except Exception as e:
        return {"error": str(e)}
        