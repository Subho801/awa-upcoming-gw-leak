import os
import re
import json
import requests
from datetime import datetime
from bs4 import BeautifulSoup

URL = "https://na.alienwarearena.com/forums/board/443/demo-items-remember-to-change-before-publish"
MIN_ID = 2174000
SEEN_FILE = "seen.json"
WEBHOOK_URL = os.getenv("DISCORD_WEBHOOK")

headers = {"User-Agent": "Mozilla/5.0"}


def load_seen():
    if os.path.exists(SEEN_FILE):
        with open(SEEN_FILE, "r", encoding="utf-8") as f:
            return set(json.load(f))
    return set()


def save_seen(seen):
    with open(SEEN_FILE, "w", encoding="utf-8") as f:
        json.dump(sorted(list(seen)), f, indent=2)


def send_discord(title, link, post_id):
    if not WEBHOOK_URL:
        print("DISCORD_WEBHOOK not set. Printing only.")
        return

    payload = {
    "embeds": [
        {
            "title": title,
            "url": link,
            "description": "👽 **AWA Upcoming Giveaway Detected**",
            "color": 10181046,
            "image": {
    "url": "https://shared.fastly.steamstatic.com/store_item_assets/steam/apps/3768760/header.jpg"
},
            "fields": [
                {"name": "Status", "value": "Upcoming / Demo Board Leak", "inline": False},
                {"name": "Post ID", "value": str(post_id), "inline": True},
                {"name": "Source", "value": "[Open AWA Post](" + link + ")", "inline": True},
            ],
            "footer": {
                "text": "Subho's AWA Upcoming GA Notifier",
                "icon_url": "https://files.catbox.moe/qttqpy.png"
            },
            "timestamp": datetime.utcnow().isoformat()
        }
    ]
}
    r = requests.post(WEBHOOK_URL, json=payload, timeout=20)
    r.raise_for_status()


def main():
    seen = load_seen()

    html = requests.get(URL, headers=headers, timeout=20).text
    soup = BeautifulSoup(html, "html.parser")

    found_new = False

    for a in soup.find_all("a", href=True):
        text = a.get_text(" ", strip=True)
        link = a["href"]

        if "/ucf/show/" not in link:
            continue

        match = re.search(r"/ucf/show/(\d+)", link)
        if not match:
            continue

        post_id = int(match.group(1))

        if post_id < MIN_ID:
            continue

        lower = text.lower()
        if "giveaway" not in lower and "key" not in lower:
            continue

        if link.startswith("/"):
            link = "https://na.alienwarearena.com" + link

        unique_key = f"{post_id}:{text}"

        if unique_key in seen:
            continue

        print("NEW:", text)
        print(link)

        send_discord(text, link, post_id)

        seen.add(unique_key)
        found_new = True

    save_seen(seen)

    if not found_new:
        print("No new upcoming giveaways found.")


if __name__ == "__main__":
    main()
