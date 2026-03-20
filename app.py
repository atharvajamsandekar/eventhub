from flask import Flask, render_template, request, redirect, jsonify, session, send_file
import os
import psycopg2
import requests
from google import genai

app = Flask(__name__)
app.secret_key = "secret123"

UPLOAD_FOLDER = "static/uploads"
app.config["UPLOAD_FOLDER"] = UPLOAD_FOLDER

# -----------------------------
# DATABASE (PostgreSQL)
# -----------------------------
DATABASE_URL = os.environ.get("DATABASE_URL")

def get_db_connection():
    return psycopg2.connect(DATABASE_URL)

# -----------------------------
# GEMINI AI (FIXED VERSION)
# -----------------------------
client = genai.Client(api_key=os.environ.get("GEMINI_API_KEY"))

# -----------------------------
# EMAIL CONFIG
# -----------------------------
SENDER_EMAIL = os.environ.get("SENDER_EMAIL")
SENDGRID_API_KEY = os.environ.get("SENDGRID_API_KEY")

# -----------------------------
# INIT DATABASE
# -----------------------------
def init_db():
    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id SERIAL PRIMARY KEY,
            name TEXT NOT NULL,
            email TEXT UNIQUE NOT NULL,
            password TEXT NOT NULL
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS events (
            id SERIAL PRIMARY KEY,
            name TEXT NOT NULL,
            description TEXT NOT NULL,
            date TEXT NOT NULL,
            image TEXT NOT NULL,
            category TEXT DEFAULT 'General'
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS registrations (
            id SERIAL PRIMARY KEY,
            event_id INTEGER REFERENCES events(id),
            name TEXT NOT NULL,
            email TEXT NOT NULL
        )
    """)

    conn.commit()
    conn.close()

# -----------------------------
# EMAIL FUNCTION
# -----------------------------
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
            "personalizations": [{
                "to": [{"email": student_email}],
                "subject": f"Registration Confirmed - {event_name}"
            }],
            "from": {"email": SENDER_EMAIL},
            "content": [{
                "type": "text/plain",
                "value": f"Hello {student_name}, Your registration for {event_name} is confirmed."
            }]
        }

        response = requests.post(url, headers=headers, json=data)
        return response.status_code == 202

    except:
        return False

# -----------------------------
# ROUTES
# -----------------------------
@app.route("/")
def home():
    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute("SELECT COUNT(*) FROM events")
    total_events = cursor.fetchone()[0]

    cursor.execute("SELECT COUNT(*) FROM registrations")
    total_registrations = cursor.fetchone()[0]

    cursor.execute("SELECT COUNT(*) FROM users")
    total_users = cursor.fetchone()[0]

    cursor.execute("SELECT * FROM events ORDER BY date ASC LIMIT 3")
    upcoming_events = cursor.fetchall()

    conn.close()

    return render_template("index.html",
        total_events=total_events,
        total_registrations=total_registrations,
        total_users=total_users,
        upcoming_events=upcoming_events
    )

@app.route("/events")
def events_page():
    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute("SELECT * FROM events ORDER BY date ASC")
    events = cursor.fetchall()

    conn.close()
    return render_template("events.html", events=events)

@app.route("/signup", methods=["POST"])
def signup():
    name = request.form["name"]
    email = request.form["email"]
    password = request.form["password"]

    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute("INSERT INTO users (name, email, password) VALUES (%s, %s, %s)",
                   (name, email, password))
    conn.commit()
    conn.close()

    return redirect("/user_login")

@app.route("/chatbot", methods=["POST"])
def chatbot():
    user_message = request.json["message"]

    try:
        response = client.models.generate_content(
            model="gemini-2.0-flash",
            contents=user_message
        )
        reply = response.text if response else "No response"
    except Exception as e:
        print("AI ERROR:", e)
        reply = "AI temporarily unavailable."

    return jsonify({"reply": reply})

# -----------------------------
# START
# -----------------------------
if not os.path.exists("static/uploads"):
    os.makedirs("static/uploads")

init_db()

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
