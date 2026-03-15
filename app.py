from flask import Flask, render_template, request, redirect, jsonify, session, send_file
import os
import sqlite3
import requests

app = Flask(__name__)
app.secret_key = "secret123"

UPLOAD_FOLDER = "static/uploads"
app.config["UPLOAD_FOLDER"] = UPLOAD_FOLDER
DATABASE = "event.db"

SENDER_EMAIL = os.environ.get("SENDER_EMAIL")
SENDGRID_API_KEY = os.environ.get("SENDGRID_API_KEY")

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
            name TEXT NOT NULL,
            email TEXT NOT NULL UNIQUE,
            password TEXT NOT NULL
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            description TEXT NOT NULL,
            date TEXT NOT NULL,
            image TEXT NOT NULL
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS registrations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            event_id INTEGER NOT NULL,
            name TEXT NOT NULL,
            email TEXT NOT NULL,
            FOREIGN KEY (event_id) REFERENCES events (id)
        )
    """)

    columns = [row["name"] for row in cursor.execute("PRAGMA table_info(events)").fetchall()]
    if "category" not in columns:
        cursor.execute("ALTER TABLE events ADD COLUMN category TEXT DEFAULT 'General'")

    conn.commit()
    conn.close()


def send_confirmation_email(student_email, student_name, event_name, event_date):
    try:
        if not SENDER_EMAIL or not SENDGRID_API_KEY:
            print("SendGrid credentials are missing.")
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
            "from": {
                "email": SENDER_EMAIL
            },
            "content": [
                {
                    "type": "text/plain",
                    "value": f"""Hello {student_name},

Your registration for the event "{event_name}" has been confirmed.

Event Details:
Event Name: {event_name}
Event Date: {event_date}

Thank you for registering.
See you at the event!

Regards,
EventHub Team
"""
                }
            ]
        }

        response = requests.post(url, headers=headers, json=data)

        print("SendGrid status:", response.status_code)
        print("SendGrid response:", response.text)

        return response.status_code == 202

    except Exception as e:
        print("SendGrid email error:", repr(e))
        return False


@app.route("/")
def home():
    conn = get_db_connection()

    total_events = conn.execute("SELECT COUNT(*) FROM events").fetchone()[0]
    total_registrations = conn.execute("SELECT COUNT(*) FROM registrations").fetchone()[0]
    total_users = conn.execute("SELECT COUNT(*) FROM users").fetchone()[0]

    upcoming_events = conn.execute(
        "SELECT * FROM events ORDER BY date ASC, id DESC LIMIT 3"
    ).fetchall()

    conn.close()

    return render_template(
        "index.html",
        total_events=total_events,
        total_registrations=total_registrations,
        total_users=total_users,
        upcoming_events=upcoming_events
    )


@app.route("/events")
def events_page():
    conn = get_db_connection()
    events = conn.execute("SELECT * FROM events ORDER BY date ASC, id DESC").fetchall()
    conn.close()
    return render_template("events.html", events=events)


@app.route("/gallery")
def gallery():
    conn = get_db_connection()
    events = conn.execute("SELECT * FROM events ORDER BY id DESC").fetchall()
    conn.close()
    return render_template("gallery.html", events=events)


@app.route("/signup", methods=["GET", "POST"])
def signup():
    if request.method == "POST":
        name = request.form["name"]
        email = request.form["email"]
        password = request.form["password"]

        conn = get_db_connection()
        existing_user = conn.execute(
            "SELECT * FROM users WHERE email = ?",
            (email,)
        ).fetchone()

        if existing_user:
            conn.close()
            return "Email already registered. Please login."

        conn.execute(
            "INSERT INTO users (name, email, password) VALUES (?, ?, ?)",
            (name, email, password)
        )
        conn.commit()
        conn.close()

        return redirect("/user_login")

    return render_template("signup.html")


@app.route("/user_login", methods=["GET", "POST"])
def user_login():
    if request.method == "POST":
        email = request.form["email"]
        password = request.form["password"]

        conn = get_db_connection()
        user = conn.execute(
            "SELECT * FROM users WHERE email = ? AND password = ?",
            (email, password)
        ).fetchone()
        conn.close()

        if user:
            session["user"] = email
            return redirect("/events")

        return "Invalid Login"

    return render_template("user_login.html")


@app.route("/user_logout")
def user_logout():
    session.pop("user", None)
    return redirect("/")


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form["username"]
        password = request.form["password"]

        if username == "admin" and password == "admin123":
            session["admin"] = True
            return redirect("/admin")
        else:
            return "Invalid Login"

    return render_template("login.html")


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

        image_path = os.path.join(app.config["UPLOAD_FOLDER"], image_name)
        image.save(image_path)

        conn.execute(
            "INSERT INTO events (name, description, date, image, category) VALUES (?, ?, ?, ?, ?)",
            (name, description, date, image_name, category)
        )
        conn.commit()

    events = conn.execute("SELECT * FROM events ORDER BY id DESC").fetchall()
    registrations = conn.execute("SELECT * FROM registrations ORDER BY id DESC").fetchall()

    category_rows = conn.execute("""
        SELECT category, COUNT(*) AS total
        FROM events
        GROUP BY category
        ORDER BY total DESC
    """).fetchall()

    total_users = conn.execute("SELECT COUNT(*) FROM users").fetchone()[0]

    conn.close()

    category_labels = [row["category"] for row in category_rows]
    category_totals = [row["total"] for row in category_rows]

    return render_template(
        "admin.html",
        events=events,
        registrations=registrations,
        total_users=total_users,
        category_labels=category_labels,
        category_totals=category_totals
    )


@app.route("/download_excel")
def download_excel():
    if "admin" not in session:
        return redirect("/login")

    conn = get_db_connection()
    rows = conn.execute("""
        SELECT registrations.id, registrations.name, registrations.email,
               events.name AS event_name, events.date, events.category
        FROM registrations
        JOIN events ON registrations.event_id = events.id
        ORDER BY registrations.id DESC
    """).fetchall()
    conn.close()

    file_path = "registrations.csv"

    with open(file_path, "w") as f:
        f.write("Registration ID,Student Name,Email,Event Name,Event Date,Category\n")

        for row in rows:
            f.write(f"{row['id']},{row['name']},{row['email']},{row['event_name']},{row['date']},{row['category']}\n")

    return send_file(file_path, as_attachment=True)


@app.route("/edit_event/<int:event_id>", methods=["GET", "POST"])
def edit_event(event_id):
    if "admin" not in session:
        return redirect("/login")

    conn = get_db_connection()
    event = conn.execute("SELECT * FROM events WHERE id = ?", (event_id,)).fetchone()

    if not event:
        conn.close()
        return "Event not found"

    if request.method == "POST":
        name = request.form["name"]
        description = request.form["description"]
        date = request.form["date"]
        category = request.form["category"]

        image = request.files["image"]

        if image and image.filename != "":
            image_name = image.filename
            image_path = os.path.join(app.config["UPLOAD_FOLDER"], image_name)
            image.save(image_path)

            conn.execute("""
                UPDATE events
                SET name = ?, description = ?, date = ?, image = ?, category = ?
                WHERE id = ?
            """, (name, description, date, image_name, category, event_id))
        else:
            conn.execute("""
                UPDATE events
                SET name = ?, description = ?, date = ?, category = ?
                WHERE id = ?
            """, (name, description, date, category, event_id))

        conn.commit()
        conn.close()
        return redirect("/admin")

    conn.close()
    return render_template("edit_event.html", event=event)


@app.route("/delete_event/<int:event_id>")
def delete_event(event_id):
    if "admin" not in session:
        return redirect("/login")

    conn = get_db_connection()
    conn.execute("DELETE FROM registrations WHERE event_id = ?", (event_id,))
    conn.execute("DELETE FROM events WHERE id = ?", (event_id,))
    conn.commit()
    conn.close()

    return redirect("/admin")


@app.route("/register/<int:event_id>", methods=["GET", "POST"])
def register(event_id):
    if "user" not in session:
        return redirect("/user_login")

    conn = get_db_connection()
    selected_event = conn.execute(
        "SELECT * FROM events WHERE id = ?",
        (event_id,)
    ).fetchone()

    if not selected_event:
        conn.close()
        return "Event not found"

    if request.method == "POST":
        name = request.form["name"]
        email = request.form["email"]

        already_registered = conn.execute(
            "SELECT * FROM registrations WHERE event_id = ? AND email = ?",
            (event_id, email)
        ).fetchone()

        if already_registered:
            conn.close()
            return "You have already registered for this event."

        conn.execute(
            "INSERT INTO registrations (event_id, name, email) VALUES (?, ?, ?)",
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


@app.route("/view_registrations/<int:event_id>")
def view_registrations(event_id):
    if "admin" not in session:
        return redirect("/login")

    conn = get_db_connection()
    registrations = conn.execute(
        "SELECT * FROM registrations WHERE event_id = ? ORDER BY id DESC",
        (event_id,)
    ).fetchall()
    conn.close()

    return render_template("registrations.html", registrations=registrations)


@app.route("/my_events")
def my_events():
    if "user" not in session:
        return redirect("/user_login")

    user_email = session["user"]

    conn = get_db_connection()
    events = conn.execute("""
        SELECT DISTINCT events.*
        FROM events
        JOIN registrations ON events.id = registrations.event_id
        WHERE registrations.email = ?
        ORDER BY events.date ASC, events.id DESC
    """, (user_email,)).fetchall()
    conn.close()

    return render_template("my_events.html", events=events)


@app.route("/chatbot", methods=["POST"])
def chatbot():
    message = request.json["message"].lower().strip()

    conn = get_db_connection()
    events = conn.execute("SELECT * FROM events ORDER BY date ASC").fetchall()
    conn.close()

    if "hello" in message or "hi" in message or "hey" in message:
        reply = "Hello! I am your Event Assistant. Ask me about events, dates, categories, or registration."

    elif "register" in message and "how" in message:
        reply = "To register, first login as a student, open the Events page, choose an event, and click Register Now."

    elif "category" in message or "categories" in message:
        categories = sorted(list(set([event["category"] for event in events if event["category"]])))
        if categories:
            reply = "Available categories are: " + ", ".join(categories)
        else:
            reply = "No event categories are available right now."

    elif "sports" in message or "tech" in message or "cultural" in message or "general" in message:
        matched = []
        for event in events:
            if event["category"] and event["category"].lower() in message:
                matched.append(event["name"])
        if matched:
            reply = "Events in this category: " + ", ".join(matched)
        else:
            reply = "I could not find events in that category right now."

    elif "event" in message or "events" in message:
        if len(events) == 0:
            reply = "No events are available right now."
        else:
            names = [event["name"] for event in events]
            reply = "Available events: " + ", ".join(names)

    else:
        event_found = None
        for event in events:
            if event["name"].lower() in message:
                event_found = event
                break

        if event_found:
            reply = (
                f"{event_found['name']} is a {event_found['category']} event scheduled on "
                f"{event_found['date']}. Description: {event_found['description']}"
            )
        else:
            reply = "I can help with event names, dates, categories, and how to register."

    return jsonify({"reply": reply})


@app.route("/logout")
def logout():
    session.pop("admin", None)
    return redirect("/")


# -----------------------------
# Render / Production Setup
# -----------------------------
if not os.path.exists("static/uploads"):
    os.makedirs("static/uploads")

init_db()


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)
