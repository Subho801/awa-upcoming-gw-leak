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

BASE_URL = "https://na.alienwarearena.com"

headers = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/154.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "en-US,en;q=0.9",
}


def load_seen():
    if os.path.exists(SEEN_FILE):
        with open(SEEN_FILE, "r", encoding="utf-8") as f:
            return set(json.load(f))

    return set()


def save_seen(seen):
    with open(SEEN_FILE, "w", encoding="utf-8") as f:
        json.dump(sorted(list(seen)), f, indent=2)


def normalize_link(link):
    if link.startswith("/"):
        return BASE_URL + link

    return link


def fetch_post_details(link):
    """
    Open the individual AWA post and attempt to extract:

    - ARP Tier requirement
    - ARP / bid requirement
    - giveaway type
    - country restrictions

    Returns a dictionary.
    """

    result = {
        "tier": None,
        "arp": None,
        "giveaway_type": None,
        "country": None,
    }

    try:
        response = requests.get(
            link,
            headers=headers,
            timeout=20
        )

        response.raise_for_status()

    except requests.RequestException as e:
        print(f"Failed to fetch post {link}: {e}")
        return result

    soup = BeautifulSoup(response.text, "html.parser")

    # ---------------------------------------------------------
    # Convert page to clean text
    # ---------------------------------------------------------

    page_text = soup.get_text(
        " ",
        strip=True
    )

    # Collapse excessive whitespace
    page_text = re.sub(
        r"\s+",
        " ",
        page_text
    )

    # ---------------------------------------------------------
    # TIER REQUIREMENT
    #
    # Examples:
    #   Tier 1+
    #   Tier 2+
    #   Tier 3+
    #   ARP Tier 4
    # ---------------------------------------------------------

    tier_patterns = [
        r"\bTier\s*(\d+)\s*\+",
        r"\bARP\s*Tier\s*(\d+)\s*\+?",
        r"\bTier\s*(\d+)\b",
    ]

    for pattern in tier_patterns:
        match = re.search(
            pattern,
            page_text,
            re.IGNORECASE
        )

        if match:
            result["tier"] = f"Tier {match.group(1)}+"
            break

    # ---------------------------------------------------------
    # ARP / BLIND AUCTION
    #
    # We DON'T assume that every number followed by ARP
    # is an entry requirement.
    #
    # Look for wording around bids / requirements.
    # ---------------------------------------------------------

    arp_patterns = [
        # "ARP bid: 250"
        r"(?:ARP|Arp)\s*bid\s*[:\-]?\s*(\d[\d,]*)",

        # "bid of 250 ARP"
        r"bid\s*(?:of|:)?\s*(\d[\d,]*)\s*ARP",

        # "250 ARP bid"
        r"(\d[\d,]*)\s*ARP\s*bid",

        # "minimum bid: 250 ARP"
        r"minimum\s+bid\s*[:\-]?\s*(\d[\d,]*)\s*ARP",

        # "minimum 250 ARP"
        r"minimum\s+(\d[\d,]*)\s*ARP",
    ]

    for pattern in arp_patterns:
        match = re.search(
            pattern,
            page_text,
            re.IGNORECASE
        )

        if match:
            result["arp"] = f"{match.group(1)} ARP"
            break

    # ---------------------------------------------------------
    # GIVEAWAY TYPE
    # ---------------------------------------------------------

    if re.search(
        r"Blind Auction",
        page_text,
        re.IGNORECASE
    ):
        result["giveaway_type"] = "Blind Auction"

    elif re.search(
        r"Community Giveaway",
        page_text,
        re.IGNORECASE
    ):
        result["giveaway_type"] = "Community Giveaway"

    # ---------------------------------------------------------
    # COUNTRY RESTRICTION
    # ---------------------------------------------------------

    country_patterns = [
        r"Country Restrictions?\s*[:\-]?\s*(.{0,150})",
        r"Countries?\s*[:\-]?\s*(.{0,150})",
    ]

    for pattern in country_patterns:
        match = re.search(
            pattern,
            page_text,
            re.IGNORECASE
        )

        if match:
            country = match.group(1).strip()

            # Prevent the value from becoming enormous
            country = country[:150]

            result["country"] = country
            break

    print(
        f"DETAILS | Tier={result['tier']} | "
        f"ARP={result['arp']} | "
        f"Type={result['giveaway_type']}"
    )

    return result


def send_discord(
    title,
    link,
    post_id,
    details
):

    if not WEBHOOK_URL:
        print(
            "DISCORD_WEBHOOK not set. Printing only."
        )
        return

    lower = title.lower()

    # ---------------------------------------------------------
    # Embed colour
    # ---------------------------------------------------------

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

    # ---------------------------------------------------------
    # Requirements
    # ---------------------------------------------------------

    tier = details.get("tier") or "Not specified"

    arp = details.get("arp") or "Not specified"

    giveaway_type = (
        details.get("giveaway_type")
        or "Not specified"
    )

    # ---------------------------------------------------------
    # Discord payload
    # ---------------------------------------------------------

    payload = {
        "embeds": [
            {
                "title": title,
                "url": link,

                "description": (
                    "🛸 **New AWA Leak Detected**"
                ),

                "color": color,

                "thumbnail": {
                    "url": (
                        "https://files.catbox.moe/fwq83q.jpg"
                    )
                },

                "fields": [

                    {
                        "name": "Status",
                        "value": (
                            "Upcoming / Demo Board Leak"
                        ),
                        "inline": False
                    },

                    {
                        "name": "Tier Requirement",
                        "value": f"🏆 {tier}",
                        "inline": True
                    },

                    {
                        "name": "ARP / Bid",
                        "value": f"💰 {arp}",
                        "inline": True
                    },

                    {
                        "name": "Giveaway Type",
                        "value": f"🎁 {giveaway_type}",
                        "inline": True
                    },

                    {
                        "name": "Post ID",
                        "value": str(post_id),
                        "inline": True
                    },

                    {
                        "name": "Source",
                        "value": (
                            "[Open AWA Post]("
                            + link
                            + ")"
                        ),
                        "inline": True
                    },
                ],

                "footer": {
                    "text": (
                        "Subho's AWA Upcoming GA Notifier"
                    ),
                    "icon_url": (
                        "https://files.catbox.moe/qttqpy.png"
                    )
                },

                "timestamp": (
                    datetime.utcnow().isoformat()
                )
            }
        ]
    }

    try:
        r = requests.post(
            WEBHOOK_URL,
            json=payload,
            timeout=20
        )

        r.raise_for_status()

    except requests.RequestException as e:
        print(
            f"Discord webhook failed: {e}"
        )


def main():

    seen = load_seen()

    # ---------------------------------------------------------
    # Fetch demo board
    # ---------------------------------------------------------

    try:
        response = requests.get(
            URL,
            headers=headers,
            timeout=20
        )

        response.raise_for_status()

    except requests.RequestException as e:
        print(
            f"Failed to fetch AWA demo board: {e}"
        )
        return

    html = response.text

    soup = BeautifulSoup(
        html,
        "html.parser"
    )

    found_new = False

    # ---------------------------------------------------------
    # Find posts
    # ---------------------------------------------------------

    for a in soup.find_all(
        "a",
        href=True
    ):

        text = a.get_text(
            " ",
            strip=True
        )

        link = a["href"]

        if "/ucf/show/" not in link:
            continue

        match = re.search(
            r"/ucf/show/(\d+)",
            link
        )

        if not match:
            continue

        post_id = int(
            match.group(1)
        )

        if post_id < MIN_ID:
            continue

        lower = text.lower()

        if (
            "giveaway" not in lower
            and "key" not in lower
        ):
            continue

        link = normalize_link(link)

        unique_key = (
            f"{post_id}:{text}"
        )

        if unique_key in seen:
            continue

        # -----------------------------------------------------
        # New post detected
        # -----------------------------------------------------

        print()
        print("=" * 60)
        print("NEW AWA LEAK")
        print("Title:", text)
        print("Post ID:", post_id)
        print("Link:", link)
        print("=" * 60)

        # -----------------------------------------------------
        # Fetch individual giveaway details
        # -----------------------------------------------------

        details = fetch_post_details(
            link
        )

        print(
            "Tier:",
            details["tier"]
        )

        print(
            "ARP:",
            details["arp"]
        )

        print(
            "Type:",
            details["giveaway_type"]
        )

        # -----------------------------------------------------
        # Discord
        # -----------------------------------------------------

        send_discord(
            text,
            link,
            post_id,
            details
        )

        # -----------------------------------------------------
        # Mark as seen
        # -----------------------------------------------------

        seen.add(
            unique_key
        )

        found_new = True

    save_seen(seen)

    if not found_new:
        print(
            "No new upcoming giveaways found."
        )


if __name__ == "__main__":
    main()
