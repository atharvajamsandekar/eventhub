function toggleChat() {
    let box = document.getElementById("chatbot-box");

    if (box.style.display === "none" || box.style.display === "") {
        box.style.display = "block";
    } else {
        box.style.display = "none";
    }
}

function handleEnter(event) {
    if (event.key === "Enter") {
        sendMessage();
    }
}

function sendMessage() {
    let input = document.getElementById("userInput");
    let message = input.value.trim();

    if (message === "") {
        return;
    }

    fetch("/chatbot", {
        method: "POST",
        headers: {
            "Content-Type": "application/json"
        },
        body: JSON.stringify({ message: message })
    })
    .then(res => res.json())
    .then(data => {
        let chat = document.getElementById("chat-messages");

        chat.innerHTML += "<div class='user-message'>" + message + "</div>";
        chat.innerHTML += "<div class='bot-message'>" + data.reply + "</div>";

        input.value = "";
        chat.scrollTop = chat.scrollHeight;
    });
}

function filterEvents() {
    let searchValue = document.getElementById("searchInput").value.toLowerCase().trim();
    let dateValue = document.getElementById("dateFilter").value;
    let categoryValue = document.getElementById("categoryFilter").value.toLowerCase();
    let events = document.querySelectorAll(".event-item");
    let visibleCount = 0;

    events.forEach(function(event) {
        let eventName = event.getAttribute("data-name");
        let eventDate = event.getAttribute("data-date");
        let eventCategory = event.getAttribute("data-category");

        let matchesSearch = eventName.includes(searchValue);
        let matchesDate = (dateValue === "" || eventDate === dateValue);
        let matchesCategory = (categoryValue === "" || eventCategory === categoryValue);

        if (matchesSearch && matchesDate && matchesCategory) {
            event.style.display = "block";
            visibleCount++;
        } else {
            event.style.display = "none";
        }
    });

    let noEventsMessage = document.getElementById("noEventsMessage");

    if (noEventsMessage) {
        if (visibleCount === 0) {
            noEventsMessage.style.display = "block";
        } else {
            noEventsMessage.style.display = "none";
        }
    }
}

document.addEventListener("DOMContentLoaded", function() {
    let searchInput = document.getElementById("searchInput");
    let dateFilter = document.getElementById("dateFilter");
    let categoryFilter = document.getElementById("categoryFilter");

    if (searchInput) {
        searchInput.addEventListener("keyup", filterEvents);
    }

    if (dateFilter) {
        dateFilter.addEventListener("change", filterEvents);
    }

    if (categoryFilter) {
        categoryFilter.addEventListener("change", filterEvents);
    }
});