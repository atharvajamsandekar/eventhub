from flask import Flask, render_template, request, redirect, jsonify, session, send_file
import os
import csv
import io
import requests
import psycopg2
from psycopg2.extras import RealDictCursor
from google import genai

app = Flask(__name__)
app.secret_key = "secret123"

UPLOAD_FOLDER = "static/uploads"
app.config["UPLOAD_FOLDER"] = UPLOAD_FOLDER

DATABASE_URL = os.environ.get("DATABASE_URL")
SENDER_EMAIL = os.environ.get("SENDER_EMAIL")
SENDGRID_API_KEY = os.environ.get("SENDGRID_API_KEY")
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")

# Gemini client
client = None
if GEMINI_API_KEY:
    try:
        client = genai.Client(api_key=GEMINI_API_KEY)
    except Exception as e:
        print("Gemini client init error:", e)
        client = None


# -----------------------------
# DATABASE
# -----------------------------
def get_db_connection():
    if not DATABASE_URL:
        raise ValueError("DATABASE_URL is not set in environment variables.")
    return psycopg2.connect(DATABASE_URL, cursor_factory=RealDictCursor)


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
            event_id INTEGER NOT NULL REFERENCES events(id) ON DELETE CASCADE,
            name TEXT NOT NULL,
            email TEXT NOT NULL
        )
    """)

    conn.commit()
    conn.close()


# -----------------------------
# EMAIL
# -----------------------------
def send_confirmation_email(student_email, student_name, event_name, event_date):
    try:
        if not SENDER_EMAIL or not SENDGRID_API_KEY:
            print("SendGrid credentials missing.")
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

Your registration for "{event_name}" has been confirmed.

Event Date: {event_date}

Thank you for registering.

Regards,
EventHub Team
"""
                }
            ]
        }

        response = requests.post(url, headers=headers, json=data, timeout=20)
        print("SendGrid status:", response.status_code)
        print("SendGrid response:", response.text)
        return response.status_code == 202

    except Exception as e:
        print("SendGrid email error:", e)
        return False


# -----------------------------
# HOME
# -----------------------------
@app.route("/")
def home():
    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute("SELECT COUNT(*) AS count FROM events")
    total_events = cursor.fetchone()["count"]

    cursor.execute("SELECT COUNT(*) AS count FROM registrations")
    total_registrations = cursor.fetchone()["count"]

    cursor.execute("SELECT COUNT(*) AS count FROM users")
    total_users = cursor.fetchone()["count"]

    cursor.execute("SELECT * FROM events ORDER BY date ASC, id DESC LIMIT 3")
    upcoming_events = cursor.fetchall()

    conn.close()

    return render_template(
        "index.html",
        total_events=total_events,
        total_registrations=total_registrations,
        total_users=total_users,
        upcoming_events=upcoming_events
    )


# -----------------------------
# EVENTS / GALLERY
# -----------------------------
@app.route("/events")
def events_page():
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM events ORDER BY date ASC, id DESC")
    events = cursor.fetchall()
    conn.close()
    return render_template("events.html", events=events)


@app.route("/gallery")
def gallery():
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM events ORDER BY id DESC")
    events = cursor.fetchall()
    conn.close()
    return render_template("gallery.html", events=events)


# -----------------------------
# SIGNUP / USER LOGIN
# -----------------------------
@app.route("/signup", methods=["GET", "POST"])
def signup():
    if request.method == "POST":
        name = request.form["name"].strip()
        email = request.form["email"].strip().lower()
        password = request.form["password"].strip()

        conn = get_db_connection()
        cursor = conn.cursor()

        cursor.execute("SELECT * FROM users WHERE email = %s", (email,))
        existing_user = cursor.fetchone()

        if existing_user:
            conn.close()
            return "Email already registered. Please login."

        cursor.execute(
            "INSERT INTO users (name, email, password) VALUES (%s, %s, %s)",
            (name, email, password)
        )
        conn.commit()
        conn.close()

        return redirect("/user_login")

    return render_template("signup.html")


@app.route("/user_login", methods=["GET", "POST"])
def user_login():
    if request.method == "POST":
        email = request.form["email"].strip().lower()
        password = request.form["password"].strip()

        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute(
            "SELECT * FROM users WHERE email = %s AND password = %s",
            (email, password)
        )
        user = cursor.fetchone()
        conn.close()

        if user:
            session["user"] = email
            return redirect("/events")

        return "Invalid Login. Check your email and password."

    return render_template("user_login.html")


@app.route("/user_logout")
def user_logout():
    session.pop("user", None)
    return redirect("/")


# -----------------------------
# ADMIN LOGIN
# -----------------------------
@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form["username"].strip()
        password = request.form["password"].strip()

        if username == "admin" and password == "admin123":
            session["admin"] = True
            return redirect("/admin")

        return "Invalid Login"

    return render_template("login.html")


@app.route("/logout")
def logout():
    session.pop("admin", None)
    return redirect("/")


# -----------------------------
# ADMIN PANEL
# -----------------------------
@app.route("/admin", methods=["GET", "POST"])
def admin():
    if "admin" not in session:
        return redirect("/login")

    conn = get_db_connection()
    cursor = conn.cursor()

    if request.method == "POST":
        name = request.form["name"].strip()
        description = request.form["description"].strip()
        date = request.form["date"].strip()
        category = request.form["category"].strip()

        image = request.files["image"]
        if not image or image.filename == "":
            conn.close()
            return "Please select an image."

        image_name = image.filename
        image_path = os.path.join(app.config["UPLOAD_FOLDER"], image_name)
        image.save(image_path)

        cursor.execute("""
            INSERT INTO events (name, description, date, image, category)
            VALUES (%s, %s, %s, %s, %s)
        """, (name, description, date, image_name, category))
        conn.commit()

    cursor.execute("SELECT * FROM events ORDER BY id DESC")
    events = cursor.fetchall()

    cursor.execute("SELECT * FROM users ORDER BY id DESC")
    users = cursor.fetchall()

    cursor.execute("""
        SELECT registrations.id,
               registrations.name,
               registrations.email,
               registrations.event_id,
               events.name AS event_name,
               events.date AS event_date,
               events.category AS event_category
        FROM registrations
        JOIN events ON registrations.event_id = events.id
        ORDER BY registrations.id DESC
    """)
    registrations = cursor.fetchall()

    total_events = len(events)
    total_users = len(users)
    total_registrations = len(registrations)

    conn.close()

    return render_template(
        "admin.html",
        events=events,
        users=users,
        registrations=registrations,
        total_events=total_events,
        total_users=total_users,
        total_registrations=total_registrations
    )


# -----------------------------
# EDIT EVENT
# -----------------------------
@app.route("/edit_event/<int:event_id>", methods=["GET", "POST"])
def edit_event(event_id):
    if "admin" not in session:
        return redirect("/login")

    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute("SELECT * FROM events WHERE id = %s", (event_id,))
    event = cursor.fetchone()

    if not event:
        conn.close()
        return "Event not found"

    if request.method == "POST":
        name = request.form["name"].strip()
        description = request.form["description"].strip()
        date = request.form["date"].strip()
        category = request.form["category"].strip()

        image = request.files.get("image")

        if image and image.filename != "":
            image_name = image.filename
            image_path = os.path.join(app.config["UPLOAD_FOLDER"], image_name)
            image.save(image_path)

            cursor.execute("""
                UPDATE events
                SET name = %s, description = %s, date = %s, image = %s, category = %s
                WHERE id = %s
            """, (name, description, date, image_name, category, event_id))
        else:
            cursor.execute("""
                UPDATE events
                SET name = %s, description = %s, date = %s, category = %s
                WHERE id = %s
            """, (name, description, date, category, event_id))

        conn.commit()
        conn.close()
        return redirect("/admin")

    conn.close()
    return render_template("edit_event.html", event=event)


# -----------------------------
# DELETE EVENT
# -----------------------------
@app.route("/delete_event/<int:event_id>")
def delete_event(event_id):
    if "admin" not in session:
        return redirect("/login")

    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute("DELETE FROM registrations WHERE event_id = %s", (event_id,))
    cursor.execute("DELETE FROM events WHERE id = %s", (event_id,))

    conn.commit()
    conn.close()

    return redirect("/admin")


# -----------------------------
# REGISTER FOR EVENT
# -----------------------------
@app.route("/register/<int:event_id>", methods=["GET", "POST"])
def register(event_id):
    if "user" not in session:
        return redirect("/user_login")

    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute("SELECT * FROM events WHERE id = %s", (event_id,))
    selected_event = cursor.fetchone()

    if not selected_event:
        conn.close()
        return "Event not found"

    if request.method == "POST":
        name = request.form["name"].strip()
        email = request.form["email"].strip().lower()

        cursor.execute(
            "SELECT * FROM registrations WHERE event_id = %s AND email = %s",
            (event_id, email)
        )
        already_registered = cursor.fetchone()

        if already_registered:
            conn.close()
            return "You have already registered for this event."

        cursor.execute(
            "INSERT INTO registrations (event_id, name, email) VALUES (%s, %s, %s)",
            (event_id, name, email)
        )
        conn.commit()
        conn.close()

        email_sent = send_confirmation_email(
            student_email=email,
            student_name=name,
            event_name=selected_event["name"],
            event_date=selected_event["date"]
        )

        return render_template(
            "registration_success.html",
            student_name=name,
            event_name=selected_event["name"],
            event_date=selected_event["date"],
            email=email,
            email_sent=email_sent
        )

    conn.close()
    return render_template("register.html", event_id=event_id)


# -----------------------------
# VIEW REGISTRATIONS
# -----------------------------
@app.route("/view_registrations/<int:event_id>")
def view_registrations(event_id):
    if "admin" not in session:
        return redirect("/login")

    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT id, name, email
        FROM registrations
        WHERE event_id = %s
        ORDER BY id DESC
    """, (event_id,))
    registrations = cursor.fetchall()

    conn.close()
    return render_template("registrations.html", registrations=registrations)


# -----------------------------
# MY EVENTS
# -----------------------------
@app.route("/my_events")
def my_events():
    if "user" not in session:
        return redirect("/user_login")

    user_email = session["user"]

    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT DISTINCT events.*
        FROM events
        JOIN registrations ON events.id = registrations.event_id
        WHERE registrations.email = %s
        ORDER BY events.date ASC, events.id DESC
    """, (user_email,))
    events = cursor.fetchall()

    conn.close()
    return render_template("my_events.html", events=events)


# -----------------------------
# DOWNLOAD CSV
# -----------------------------
@app.route("/download_excel")
def download_excel():
    if "admin" not in session:
        return redirect("/login")

    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT registrations.id,
               registrations.name,
               registrations.email,
               events.name AS event_name,
               events.date,
               events.category
        FROM registrations
        JOIN events ON registrations.event_id = events.id
        ORDER BY registrations.id DESC
    """)
    rows = cursor.fetchall()
    conn.close()

    output = io.StringIO()
    writer = csv.writer(output)

    writer.writerow([
        "Registration ID",
        "Student Name",
        "Email",
        "Event Name",
        "Event Date",
        "Category"
    ])

    for row in rows:
        writer.writerow([
            row["id"],
            row["name"],
            row["email"],
            row["event_name"],
            row["date"],
            row["category"]
        ])

    mem = io.BytesIO()
    mem.write(output.getvalue().encode("utf-8"))
    mem.seek(0)
    output.close()

    return send_file(
        mem,
        as_attachment=True,
        download_name="registrations.csv",
        mimetype="text/csv"
    )


# -----------------------------
# CHATBOT
# -----------------------------
@app.route("/chatbot", methods=["POST"])
def chatbot():
    user_message = request.json.get("message", "").strip()

    if not user_message:
        return jsonify({"reply": "Please type a message."})

    try:
        # Cheap fallback first for event list questions
        lower_msg = user_message.lower()
        if "events" in lower_msg or "upcoming" in lower_msg:
            conn = get_db_connection()
            cursor = conn.cursor()
            cursor.execute("SELECT name, date, category FROM events ORDER BY date ASC LIMIT 5")
            events = cursor.fetchall()
            conn.close()

            if events:
                reply = "Upcoming events are: " + ", ".join(
                    [f"{e['name']} on {e['date']}" for e in events]
                )
                return jsonify({"reply": reply})

        if client is None:
            return jsonify({"reply": "AI temporarily unavailable."})

        response = client.models.generate_content(
            model="gemini-2.0-flash",
            contents=user_message
        )
        reply = response.text if response and hasattr(response, "text") else "No response from AI."

    except Exception as e:
        print("AI ERROR:", e)
        reply = "AI temporarily unavailable."

    return jsonify({"reply": reply})


# -----------------------------
# STARTUP
# -----------------------------
if not os.path.exists("static/uploads"):
    os.makedirs("static/uploads")

init_db()

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)
