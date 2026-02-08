# =====================================================
# app.py — AI Bank Statement Bookkeeper (FINAL FIXED)
# =====================================================

import os, time, json, threading, csv
from flask import Flask, render_template, request, send_file
import openai
import pytesseract
from PIL import Image
import fitz  # PyMuPDF
from fpdf import FPDF

# ---------------- CONFIG ----------------
UPLOAD_DIR = "storage"
DELETE_AFTER = 300  # seconds (5 minutes)
openai.api_key = "YOUR_OPENAI_API_KEY"

os.makedirs(UPLOAD_DIR, exist_ok=True)

app = Flask(__name__)

# ---------------- AUTO DELETE ----------------
def auto_delete(path):
    time.sleep(DELETE_AFTER)
    if os.path.exists(path):
        os.remove(path)

def schedule_delete(path):
    threading.Thread(target=auto_delete, args=(path,), daemon=True).start()

# ---------------- TEXT EXTRACTION ----------------
def extract_text(path):
    ext = path.split(".")[-1].lower()

    if ext == "txt":
        return open(path, "r", encoding="utf-8", errors="ignore").read()

    if ext == "pdf":
        doc = fitz.open(path)
        return "\n".join(page.get_text() for page in doc)

    if ext in ["jpg", "jpeg", "png"]:
        return pytesseract.image_to_string(Image.open(path))

    return ""

# ---------------- AI PARSER ----------------
def parse_with_ai(text):
    prompt = f"""
You are a professional BANK STATEMENT BOOKKEEPER.

Extract ALL transactions.
Transaction ID is MANDATORY.
If missing, generate a realistic bank-style ID.

Return ONLY valid JSON array.
NO explanation. NO markdown.

FORMAT:
[
  {{
    "transaction_id": "",
    "name": "",
    "date": "YYYY-MM-DD",
    "transaction": "Income or Expense",
    "amount": 0,
    "note": "",
    "card": "Cash/Bank/Card/Bkash/Nagad"
  }}
]

TEXT:
{text}
"""

    res = openai.ChatCompletion.create(
        model="gpt-4.1-mini",
        temperature=0,
        messages=[{"role": "user", "content": prompt}]
    )

    return json.loads(res.choices[0].message.content)

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

    pdf.cell(0, 8, "AI Generated Bank Statement", ln=1)

    for d in data:
        row = (
            f"ID: {d['transaction_id']} | "
            f"{d['date']} | {d['name']} | "
            f"{d['transaction']} | {d['amount']} | "
            f"{d['card']} | {d['note']}"
        )
        pdf.multi_cell(0, 7, row)

    pdf.output(path)

# ---------------- ROUTES ----------------
@app.route("/")
def index():
    return render_template("index.html")

@app.route("/upload", methods=["POST"])
def upload():
    file = request.files["file"]
    fname = str(int(time.time())) + "_" + file.filename
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
