import sqlite3


def get_events():

    conn = sqlite3.connect("event.db")
    cursor = conn.cursor()

    cursor.execute("SELECT name,description,date FROM events")

    events = cursor.fetchall()

    conn.close()

    return events


def chatbot_response(message):

    message = message.lower()

    if "hello" in message or "hi" in message:
        return "Hello! Welcome to the Event Management System."

    if "events" in message:

        events = get_events()

        if not events:
            return "No events available right now."

        names = [e[0] for e in events]

        return "Available events: " + ", ".join(names)

    events = get_events()

    for event in events:

        name,desc,date = event

        if name.lower() in message:

            return f"{name} is on {date}. {desc}"

    return "Ask me about available events."