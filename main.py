import os
import json
from fastapi import FastAPI, File, UploadFile
from fastapi.middleware.cors import CORSMiddleware
import pdfplumber
from groq import Groq

app = FastAPI()

# SECURITY UPDATE: Added "*" to allow origins during debugging 
# and added your specific Vercel URL without the trailing slash.
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000", 
        "https://credilens-frontend.vercel.app",
        "https://credilens-frontend-git-main-sehnawajisgenius-projects.vercel.app"
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Pulling the key from Environment Variables
GROQ_API_KEY = os.environ.get("GROQ_API_KEY")
client = Groq(api_key=GROQ_API_KEY)

@app.get("/")
def health_check():
    return {"status": "Backend is live and secure"}

@app.post("/upload")
async def analyze_statement(file: UploadFile = File(...)):
    try:
        raw_text = ""
        # Improved PDF reading logic
        with pdfplumber.open(file.file) as pdf:
            for page in pdf.pages:
                extracted = page.extract_text()
                if extracted:
                    raw_text += extracted + "\n"

        if not raw_text.strip():
            return {"error": "Could not extract text from the PDF. Is it a scanned image?"}

        system_prompt = """
        You are an expert financial underwriter analyzing an Indian bank statement. 
        Calculate the average verified monthly salary.
        Count the exact number of bounced cheques (look for return fees, bounce charges, or inward return).
        You must output ONLY a valid JSON object. No intro, no explanation, no markdown tags.
        Format EXACTLY like this: {"verified_monthly_salary": 45000, "bounced_cheque_count": 1, "risk_score": 8, "total_emi": 0, "average_balance": 45000, "summary": "Stable income."}
        """

        chat_completion = client.chat.completions.create(
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": f"Raw Document Text:\n{raw_text[:12000]}"} 
            ],
            model="llama3-8b-8192",
            response_format={"type": "json_object"},
            temperature=0.0,
        )

        response_text = chat_completion.choices[0].message.content
        return json.loads(response_text)

    except Exception as e:
        print(f"Error occurred: {str(e)}") # This will show up in Render Logs
        return {"error": str(e)}
        