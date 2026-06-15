from flask import Flask, request, jsonify, send_file, render_template, redirect, url_for
from flask_login import LoginManager, UserMixin, login_user, logout_user, login_required, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from fpdf import FPDF
from datetime import datetime
from dotenv import load_dotenv
import sqlite3, os, uuid

load_dotenv()

app = Flask(__name__)
app.secret_key = os.getenv("SECRET_KEY", "fallback-secret")

login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = "login_page"
login_manager.login_message = ""

DB = "database.db"
INVOICE_DIR = "invoices"
os.makedirs(INVOICE_DIR, exist_ok=True)


class User(UserMixin):
    def __init__(self, id, name, email):
        self.id = id
        self.name = name
        self.email = email


@login_manager.user_loader
def load_user(user_id):
    conn = sqlite3.connect(DB)
    row = conn.execute("SELECT id, name, email FROM users WHERE id=?", (user_id,)).fetchone()
    conn.close()
    return User(*row) if row else None


def init_db():
    conn = sqlite3.connect(DB)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id TEXT PRIMARY KEY,
            name TEXT,
            email TEXT UNIQUE,
            password TEXT
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS invoices (
            id TEXT PRIMARY KEY,
            user_id TEXT,
            client_name TEXT,
            client_email TEXT,
            amount REAL,
            created_at TEXT,
            FOREIGN KEY(user_id) REFERENCES users(id)
        )
    """)
    conn.commit()
    conn.close()


@app.route("/register", methods=["GET"])
def register_page():
    return render_template("register.html")


@app.route("/register", methods=["POST"])
def register():
    data = request.json
    user_id = str(uuid.uuid4())
    hashed = generate_password_hash(data["password"])
    try:
        conn = sqlite3.connect(DB)
        conn.execute("INSERT INTO users VALUES (?,?,?,?)",
                     (user_id, data["name"], data["email"], hashed))
        conn.commit()
        conn.close()
        return jsonify({"ok": True})
    except sqlite3.IntegrityError:
        return jsonify({"ok": False, "error": "Email already registered"}), 400


@app.route("/login", methods=["GET"])
def login_page():
    return render_template("login.html")


@app.route("/login", methods=["POST"])
def login():
    data = request.json
    conn = sqlite3.connect(DB)
    row = conn.execute("SELECT id, name, email, password FROM users WHERE email=?",
                       (data["email"],)).fetchone()
    conn.close()
    if row and check_password_hash(row[3], data["password"]):
        login_user(User(row[0], row[1], row[2]))
        return jsonify({"ok": True})
    return jsonify({"ok": False, "error": "Invalid email or password"}), 401


@app.route("/logout")
@login_required
def logout():
    logout_user()
    return redirect(url_for("login_page"))


@app.route("/")
def index():
    return render_template("invoice_form.html")


@app.route("/generate", methods=["POST"])
def generate():
    data = request.json
    invoice_id = "INV-" + str(uuid.uuid4())[:8].upper()
    total = sum(i["qty"] * i["rate"] for i in data["items"])
    currency = data.get("currency", "Rs.")

    invoice = {
        "id": invoice_id,
        "your_name": data["your_name"],
        "your_email": data["your_email"],
        "client_name": data["client_name"],
        "client_email": data.get("client_email", ""),
        "items": data["items"],
        "date": datetime.today().strftime("%d %B %Y"),
        "due_date": data["due_date"],
        "currency": currency,
        "total": total
    }

    pdf_path = f"{INVOICE_DIR}/{invoice_id}.pdf"
    pdf = FPDF()
    pdf.add_page()
    pdf.set_margins(15, 15, 15)

    pdf.set_fill_color(79, 70, 229)
    pdf.rect(0, 0, 210, 45, 'F')

    pdf.set_xy(0, 12)
    pdf.set_font("Helvetica", "B", 28)
    pdf.set_text_color(255, 255, 255)
    pdf.cell(0, 12, "INVOICE", align="R", ln=True)

    pdf.set_xy(15, 26)
    pdf.set_font("Helvetica", "", 10)
    pdf.set_text_color(200, 200, 255)
    pdf.cell(0, 6, "Invoice ID: " + invoice["id"], align="R", ln=True)

    pdf.set_xy(15, 55)
    pdf.set_font("Helvetica", "B", 9)
    pdf.set_text_color(150, 150, 150)
    pdf.cell(90, 6, "FROM", ln=False)
    pdf.cell(0, 6, "BILL TO", ln=True)

    pdf.set_xy(15, 62)
    pdf.set_font("Helvetica", "B", 11)
    pdf.set_text_color(30, 30, 30)
    pdf.cell(90, 6, invoice["your_name"], ln=False)
    pdf.cell(0, 6, invoice["client_name"], ln=True)

    pdf.set_xy(15, 69)
    pdf.set_font("Helvetica", "", 9)
    pdf.set_text_color(100, 100, 100)
    pdf.cell(90, 5, invoice["your_email"], ln=False)
    pdf.cell(0, 5, invoice["client_email"], ln=True)

    pdf.set_xy(15, 85)
    pdf.set_font("Helvetica", "B", 9)
    pdf.set_text_color(150, 150, 150)
    pdf.cell(60, 5, "INVOICE DATE", ln=False)
    pdf.cell(60, 5, "DUE DATE", ln=False)
    pdf.cell(0, 5, "AMOUNT DUE", ln=True)

    pdf.set_xy(15, 91)
    pdf.set_font("Helvetica", "B", 11)
    pdf.set_text_color(30, 30, 30)
    pdf.cell(60, 6, invoice["date"], ln=False)
    pdf.cell(60, 6, invoice["due_date"], ln=False)
    pdf.set_text_color(79, 70, 229)
    pdf.cell(0, 6, currency + str("{:,.0f}".format(invoice["total"])), ln=True)

    pdf.set_xy(15, 103)
    pdf.set_draw_color(220, 220, 220)
    pdf.set_line_width(0.3)
    pdf.line(15, 103, 195, 103)

    pdf.set_xy(15, 108)
    pdf.set_fill_color(245, 245, 250)
    pdf.set_font("Helvetica", "B", 9)
    pdf.set_text_color(100, 100, 100)
    pdf.cell(85, 8, "DESCRIPTION", fill=True, ln=False)
    pdf.cell(25, 8, "QTY", align="C", fill=True, ln=False)
    pdf.cell(35, 8, "RATE", align="R", fill=True, ln=False)
    pdf.cell(35, 8, "AMOUNT", align="R", fill=True, ln=True)

    pdf.set_font("Helvetica", "", 10)
    pdf.set_text_color(30, 30, 30)
    fill = False
    for item in invoice["items"]:
        if fill:
            pdf.set_fill_color(250, 250, 255)
        else:
            pdf.set_fill_color(255, 255, 255)
        pdf.set_x(15)
        pdf.cell(85, 9, str(item["desc"]), fill=True, ln=False)
        pdf.cell(25, 9, str(item["qty"]), align="C", fill=True, ln=False)
        pdf.cell(35, 9, currency + str("{:,.0f}".format(item["rate"])), align="R", fill=True, ln=False)
        pdf.cell(35, 9, currency + str("{:,.0f}".format(item["qty"] * item["rate"])), align="R", fill=True, ln=True)
        fill = not fill

    pdf.ln(4)
    pdf.set_x(120)
    pdf.set_draw_color(220, 220, 220)
    pdf.set_line_width(0.3)
    pdf.line(120, pdf.get_y(), 195, pdf.get_y())
    pdf.ln(3)
    pdf.set_x(120)
    pdf.set_font("Helvetica", "", 10)
    pdf.set_text_color(100, 100, 100)
    pdf.cell(40, 7, "Subtotal", ln=False)
    pdf.cell(0, 7, currency + str("{:,.0f}".format(invoice["total"])), align="R", ln=True)

    pdf.set_x(120)
    pdf.set_font("Helvetica", "B", 11)
    pdf.set_text_color(79, 70, 229)
    pdf.set_fill_color(240, 238, 255)
    pdf.cell(40, 9, "TOTAL", fill=True, ln=False)
    pdf.cell(0, 9, currency + str("{:,.0f}".format(invoice["total"])), align="R", fill=True, ln=True)

    pdf.set_xy(15, 265)
    pdf.set_font("Helvetica", "", 8)
    pdf.set_text_color(180, 180, 180)
    pdf.cell(0, 5, "Generated by InvoiceApp", align="C", ln=True)
    pdf.set_fill_color(79, 70, 229)
    pdf.rect(0, 275, 210, 22, 'F')

    pdf.output(pdf_path)

    conn = sqlite3.connect(DB)
    conn.execute("INSERT INTO invoices VALUES (?,?,?,?,?,?)", (
        invoice_id, data["your_email"], data["client_name"],
        data.get("client_email", ""), invoice["total"], invoice["date"]
    ))
    conn.commit()
    conn.close()

    return jsonify({
        "invoice_id": invoice_id,
        "download_url": "/download/" + invoice_id,
        "email_sent": False
    })


@app.route("/download/<invoice_id>")
def download(invoice_id):
    path = f"{INVOICE_DIR}/{invoice_id}.pdf"
    if not os.path.exists(path):
        return "Not found", 404
    return send_file(path, as_attachment=True,
                     download_name=f"{invoice_id}.pdf")


if __name__ == "__main__":
    init_db()
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False)