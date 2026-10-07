import os
import re
import json
import requests
from datetime import datetime
from bs4 import BeautifulSoup

BOARD_URL = "https://na.alienwarearena.com/forums/board/443/demo-items-remember-to-change-before-publish"

MIN_ID = 2174000
SEEN_FILE = "seen.json"
WEBHOOK_URL = os.getenv("DISCORD_WEBHOOK")

headers = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                  "AppleWebKit/537.36 (KHTML, like Gecko) "
                  "Chrome/154.0.0.0 Safari/537.36"
}


def load_seen():
    if os.path.exists(SEEN_FILE):
        with open(SEEN_FILE, "r", encoding="utf-8") as f:
            return set(json.load(f))
    return set()


def save_seen(seen):
    with open(SEEN_FILE, "w", encoding="utf-8") as f:
        json.dump(sorted(list(seen)), f, indent=2)


def fetch_requirements(link):
    """
    Fetch the individual AWA giveaway page and extract
    ARP/Tier information from its HTML metadata.

    The visible page may say:
        YOU ARE NOT ALLOWED ACCESS TO THIS CONTENT

    but the HTML metadata can still contain the giveaway description.
    """

    try:
        r = requests.get(
            link,
            headers=headers,
            timeout=20,
            allow_redirects=True
        )

        print(f"  Details HTTP: {r.status_code}")
        print(f"  Final URL: {r.url}")

        soup = BeautifulSoup(r.text, "html.parser")

        # Collect descriptions from meta tags
        descriptions = []

        for meta in soup.find_all("meta"):
            content = meta.get("content", "")
            if not content:
                continue

            name = (meta.get("name") or "").lower()
            prop = (meta.get("property") or "").lower()

            if (
                name in ("description", "og:description")
                or prop == "og:description"
            ):
                descriptions.append(content)

        # Also check JSON-LD descriptions
        for script in soup.find_all(
            "script",
            {"type": "application/ld+json"}
        ):
            try:
                data = json.loads(script.string or script.get_text())

                if isinstance(data, dict):
                    desc = data.get("description")
                    if desc:
                        descriptions.append(str(desc))

            except Exception:
                pass

        # Remove duplicates while preserving order
        descriptions = list(dict.fromkeys(descriptions))

        combined_text = " ".join(descriptions)

        print("  Metadata:", combined_text[:500])

        # ---------------------------------------------------------
        # ARP
        # ---------------------------------------------------------

        arp = None

        arp_patterns = [
            r"requires\s+redeeming\s+([\d,]+)\s*ARP",
            r"redeeming\s+([\d,]+)\s*ARP",
            r"requires\s+([\d,]+)\s*ARP",
            r"([\d,]+)\s*ARP\s+to\s+claim",
        ]

        for pattern in arp_patterns:
            match = re.search(
                pattern,
                combined_text,
                re.IGNORECASE
            )

            if match:
                arp = int(match.group(1).replace(",", ""))
                break

        # ---------------------------------------------------------
        # TIER
        # ---------------------------------------------------------

        tier = None

        tier_patterns = [
            r"requires\s+(?:AWA\s+)?Tier\s*(\d+)\s*\+?",
            r"Tier\s*(\d+)\s*\+\s*required",
            r"Tier\s*Requirement\s*[:\-]?\s*(\d+)\s*\+?",
            r"minimum\s+Tier\s*(\d+)",
        ]

        for pattern in tier_patterns:
            match = re.search(
                pattern,
                combined_text,
                re.IGNORECASE
            )

            if match:
                tier = int(match.group(1))
                break

        # If no explicit Tier requirement was found,
        # don't confuse it with the user's own account tier.
        if tier is None:
            tier_display = "Not specified"
        else:
            tier_display = f"Tier {tier}+"

        if arp is None:
            arp_display = "Not specified"
        else:
            arp_display = f"{arp:,} ARP"

        print(f"  ARP: {arp_display}")
        print(f"  Tier: {tier_display}")

        return {
            "arp": arp_display,
            "tier": tier_display
        }

    except Exception as e:
        print(f"  Failed to fetch requirements: {e}")

        return {
            "arp": "Not specified",
            "tier": "Not specified"
        }


def send_discord(title, link, post_id, requirements):
    if not WEBHOOK_URL:
        print("DISCORD_WEBHOOK not set. Printing only.")
        return

    lower = title.lower()

    if "skin" in lower:
        color = 0xff4d6d
    elif "closed beta" in lower:
        color = 0x3498db
    elif "beta" in lower:
        color = 0x5865F2
    elif "key giveaway" in lower:
        color = 0xf1c40f
    else:
        color = 0x9b59b6

    payload = {
        "embeds": [{
            "title": title,
            "url": link,
            "description": "🛸 **New AWA Leak Detected**",
            "color": color,
            "thumbnail": {
                "url": "https://files.catbox.moe/fwq83q.jpg"
            },
            "fields": [
                {
                    "name": "🎟️ Tier Requirement",
                    "value": requirements["tier"],
                    "inline": True
                },
                {
                    "name": "💰 ARP Requirement",
                    "value": requirements["arp"],
                    "inline": True
                },
                {
                    "name": "Status",
                    "value": "Upcoming / Demo Board Leak",
                    "inline": False
                },
                {
                    "name": "Post ID",
                    "value": str(post_id),
                    "inline": True
                },
                {
                    "name": "Source",
                    "value": f"[Open AWA Post]({link})",
                    "inline": True
                }
            ],
            "footer": {
                "text": "Subho's AWA Upcoming GA Notifier",
                "icon_url": "https://files.catbox.moe/qttqpy.png"
            },
            "timestamp": datetime.utcnow().isoformat()
        }]
    }

    r = requests.post(
        WEBHOOK_URL,
        json=payload,
        timeout=20
    )

    r.raise_for_status()


def main():
    seen = load_seen()

    print("Fetching AWA Demo Board...")

    r = requests.get(
        BOARD_URL,
        headers=headers,
        timeout=20
    )

    r.raise_for_status()

    soup = BeautifulSoup(r.text, "html.parser")

    found_new = False

    for a in soup.find_all("a", href=True):

        text = a.get_text(" ", strip=True)
        link = a["href"]

        if "/ucf/show/" not in link:
            continue

        match = re.search(
            r"/ucf/show/(\d+)",
            link
        )

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

        print()
        print("=" * 60)
        print("NEW:", text)
        print("POST ID:", post_id)
        print("LINK:", link)

        # Fetch ARP/Tier from individual page metadata
        requirements = fetch_requirements(link)

        print("ARP:", requirements["arp"])
        print("TIER:", requirements["tier"])

        send_discord(
            text,
            link,
            post_id,
            requirements
        )

        seen.add(unique_key)
        found_new = True

    save_seen(seen)

    if not found_new:
        print("No new upcoming giveaways found.")


if __name__ == "__main__":
    main()
