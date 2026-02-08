# =====================================================
# app.py — AI Bank Statement Bookkeeper (FIXED & SAFE)
# =====================================================

import os, time, json, threading, csv
from flask import Flask, render_template, request, send_file
from openai import OpenAI
import pytesseract
from PIL import Image
import fitz  # PyMuPDF
from fpdf import FPDF

# ---------------- CONFIG ----------------
UPLOAD_DIR = "storage"
DELETE_AFTER = 300  # seconds (5 minutes)

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY") or "YOUR_OPENAI_API_KEY"

os.makedirs(UPLOAD_DIR, exist_ok=True)

app = Flask(__name__)
client = OpenAI(api_key=OPENAI_API_KEY)

# ---------------- AUTO DELETE ----------------
def auto_delete(path):
    time.sleep(DELETE_AFTER)
    if os.path.exists(path):
        os.remove(path)

def schedule_delete(path):
    threading.Thread(
        target=auto_delete,
        args=(path,),
        daemon=True
    ).start()

# ---------------- TEXT EXTRACTION ----------------
def extract_text(path):
    ext = path.split(".")[-1].lower()

    if ext == "txt":
        with open(path, "r", encoding="utf-8", errors="ignore") as f:
            return f.read()

    if ext == "pdf":
        doc = fitz.open(path)
        return "\n".join(page.get_text() for page in doc)

    if ext in ["jpg", "jpeg", "png"]:
        return pytesseract.image_to_string(Image.open(path))

    return ""

# ---------------- AI PARSER (BANK-GRADE) ----------------
def parse_with_ai(text):
    prompt = f"""
You are a senior BANK STATEMENT ACCOUNTANT.

Extract ALL financial transactions from the text below.

STRICT RULES (DO NOT BREAK):
1. Every row MUST have a transaction_id
   - Use bank reference numbers if present
   - Otherwise generate a realistic bank-style ID (alphanumeric)
2. transaction must be ONLY:
   - Income (for Credit / Deposit / CR)
   - Expense (for Debit / Withdrawal / DR)
3. Ignore running balance columns completely
4. Amount must be numeric (no commas, no currency symbols)
5. Date must be YYYY-MM-DD
6. card = payment method or channel:
   Cash / Bank / Card / ATM / Bkash / Nagad / Online
7. name = counterparty or source
8. note = cleaned narration
9. DO NOT invent fake transactions
10. DO NOT explain anything

Return ONLY valid JSON array in this exact format:

[
  {{
    "transaction_id": "",
    "name": "",
    "date": "",
    "transaction": "",
    "amount": 0,
    "note": "",
    "card": ""
  }}
]

BANK STATEMENT TEXT:
{text}
"""

    response = client.chat.completions.create(
        model="gpt-4.1-mini",
        temperature=0,
        messages=[
            {"role": "user", "content": prompt}
        ]
    )

    content = response.choices[0].message.content.strip()

    # -------- HARD JSON VALIDATION --------
    try:
        data = json.loads(content)
    except json.JSONDecodeError:
        raise ValueError("Invalid JSON returned by AI")

    required = {
        "transaction_id", "name", "date",
        "transaction", "amount", "note", "card"
    }

    for row in data:
        if not required.issubset(row):
            raise ValueError(f"Missing required fields: {row}")

    return data

# ---------------- CSV ----------------
def generate_csv(data, path):
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow([
            "Transaction ID", "Name", "Date",
            "Transaction", "Amount", "Note", "Card"
        ])
        for d in data:
            writer.writerow([
                d["transaction_id"],
                d["name"],
                d["date"],
                d["transaction"],
                d["amount"],
                d["note"],
                d["card"]
            ])

# ---------------- PDF ----------------
def generate_pdf(data, path):
    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Arial", size=9)

    pdf.cell(0, 8, "AI Generated Bank Statement", ln=True)

    for d in data:
        line = (
            f"ID: {d['transaction_id']} | "
            f"{d['date']} | {d['name']} | "
            f"{d['transaction']} | {d['amount']} | "
            f"{d['card']} | {d['note']}"
        )
        pdf.multi_cell(0, 7, line)

    pdf.output(path)

# ---------------- ROUTES ----------------
@app.route("/")
def index():
    return render_template("index.html")

@app.route("/upload", methods=["POST"])
def upload():
    file = request.files["file"]

    fname = f"{int(time.time())}_{file.filename}"
    path = os.path.join(UPLOAD_DIR, fname)
    file.save(path)

    schedule_delete(path)

    text = extract_text(path)
    data = parse_with_ai(text)

    csv_path = path + ".csv"
    pdf_path = path + ".pdf"

    generate_csv(data, csv_path)
    generate_pdf(data, pdf_path)

    schedule_delete(csv_path)
    schedule_delete(pdf_path)

    return render_template(
        "result.html",
        csv=csv_path,
        pdf=pdf_path
    )

@app.route("/download")
def download():
    file = request.args.get("file")
    return send_file(file, as_attachment=True)

if __name__ == "__main__":
    app.run(debug=True)
