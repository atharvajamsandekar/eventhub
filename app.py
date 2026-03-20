from flask import Flask, render_template, request, redirect, jsonify, session, send_file
import os
import sqlite3
import requests
from google import genai

app = Flask(__name__)
app.secret_key = "secret123"

UPLOAD_FOLDER = "static/uploads"
app.config["UPLOAD_FOLDER"] = UPLOAD_FOLDER
DATABASE = "event.db"

SENDER_EMAIL = os.environ.get("SENDER_EMAIL")
SENDGRID_API_KEY = os.environ.get("SENDGRID_API_KEY")

# ✅ Gemini Client (NEW WAY)
client = genai.Client(api_key=os.environ.get("GEMINI_API_KEY"))


# ---------------- DB ----------------
def get_db_connection():
    conn = sqlite3.connect(DATABASE)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT,
            email TEXT UNIQUE,
            password TEXT
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT,
            description TEXT,
            date TEXT,
            image TEXT,
            category TEXT DEFAULT 'General'
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS registrations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            event_id INTEGER,
            name TEXT,
            email TEXT
        )
    """)

    conn.commit()
    conn.close()


# ---------------- EMAIL ----------------
def send_confirmation_email(student_email, student_name, event_name, event_date):
    try:
        if not SENDER_EMAIL or not SENDGRID_API_KEY:
            return False

        url = "https://api.sendgrid.com/v3/mail/send"

        headers = {
            "Authorization": f"Bearer {SENDGRID_API_KEY}",
            "Content-Type": "application/json"
        }

        data = {
            "personalizations": [
                {
                    "to": [{"email": student_email}],
                    "subject": f"Registration Confirmed - {event_name}"
                }
            ],
            "from": {"email": SENDER_EMAIL},
            "content": [
                {
                    "type": "text/plain",
                    "value": f"""Hello {student_name},

You have successfully registered for {event_name}.
Date: {event_date}

Regards,
EventHub Team
"""
                }
            ]
        }

        response = requests.post(url, headers=headers, json=data)
        return response.status_code == 202

    except:
        return False


# ---------------- ROUTES ----------------

@app.route("/")
def home():
    conn = get_db_connection()

    total_events = conn.execute("SELECT COUNT(*) FROM events").fetchone()[0]
    total_registrations = conn.execute("SELECT COUNT(*) FROM registrations").fetchone()[0]
    total_users = conn.execute("SELECT COUNT(*) FROM users").fetchone()[0]

    events = conn.execute("SELECT * FROM events ORDER BY date ASC LIMIT 3").fetchall()
    conn.close()

    return render_template("index.html",
                           total_events=total_events,
                           total_registrations=total_registrations,
                           total_users=total_users,
                           upcoming_events=events)


@app.route("/events")
def events_page():
    conn = get_db_connection()
    events = conn.execute("SELECT * FROM events").fetchall()
    conn.close()
    return render_template("events.html", events=events)


@app.route("/admin", methods=["GET", "POST"])
def admin():
    if "admin" not in session:
        return redirect("/login")

    conn = get_db_connection()

    if request.method == "POST":
        name = request.form["name"]
        description = request.form["description"]
        date = request.form["date"]
        category = request.form["category"]

        image = request.files["image"]
        image_name = image.filename

        image.save(os.path.join(app.config["UPLOAD_FOLDER"], image_name))

        conn.execute(
            "INSERT INTO events (name, description, date, image, category) VALUES (?, ?, ?, ?, ?)",
            (name, description, date, image_name, category)
        )
        conn.commit()

    events = conn.execute("SELECT * FROM events").fetchall()
    registrations = conn.execute("SELECT * FROM registrations").fetchall()
    conn.close()

    return render_template("admin.html", events=events, registrations=registrations)


@app.route("/register/<int:event_id>", methods=["POST"])
def register(event_id):
    conn = get_db_connection()

    name = request.form["name"]
    email = request.form["email"]

    event = conn.execute("SELECT * FROM events WHERE id=?", (event_id,)).fetchone()

    conn.execute(
        "INSERT INTO registrations (event_id, name, email) VALUES (?, ?, ?)",
        (event_id, name, email)
    )
    conn.commit()
    conn.close()

    send_confirmation_email(email, name, event["name"], event["date"])

    return redirect("/events")


# ---------------- CHATBOT (AI) ----------------
@app.route("/chatbot", methods=["POST"])
def chatbot():
    user_message = request.json["message"]

    try:
        response = client.models.generate_content(
            model="gemini-2.0-flash",
            contents=user_message
        )
        reply = response.text
    except Exception as e:
        print("AI ERROR:", e)
        reply = "AI temporarily unavailable."

    return jsonify({"reply": reply})


# ---------------- LOGIN ----------------
@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        if request.form["username"] == "admin" and request.form["password"] == "admin123":
            session["admin"] = True
            return redirect("/admin")
    return render_template("login.html")


@app.route("/logout")
def logout():
    session.clear()
    return redirect("/")


# ---------------- RUN ----------------
if not os.path.exists("static/uploads"):
    os.makedirs("static/uploads")

init_db()

if __name__ == "__main__":
    app.run(debug=True)
