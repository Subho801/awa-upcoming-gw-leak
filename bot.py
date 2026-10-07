import os
import re
import json
import requests
from datetime import datetime
from bs4 import BeautifulSoup
from difflib import SequenceMatcher
from urllib.parse import quote_plus

AWA_URL = "https://na.alienwarearena.com/forums/board/443/demo-items-remember-to-change-before-publish"

MIN_ID = 2174000
SEEN_FILE = "seen.json"

WEBHOOK_URL = os.getenv("DISCORD_WEBHOOK")

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/154.0.0.0 Safari/537.36"
    )
}


# =========================================================
# SEEN
# =========================================================

def load_seen():
    if os.path.exists(SEEN_FILE):
        with open(SEEN_FILE, "r", encoding="utf-8") as f:
            return set(json.load(f))

    return set()


def save_seen(seen):
    with open(SEEN_FILE, "w", encoding="utf-8") as f:
        json.dump(sorted(list(seen)), f, indent=2)


# =========================================================
# TEXT CLEANING
# =========================================================

def clean_game_title(title):
    """
    Convert AWA giveaway title into something Steam Search
    can understand better.
    """

    title = title.strip()

    # Remove common giveaway suffixes
    patterns = [
        r"\s+Steam\s+Game\s+Key\s+Giveaway$",
        r"\s+Steam\s+Key\s+Giveaway$",
        r"\s+Game\s+Key\s+Giveaway$",
        r"\s+Key\s+Giveaway$",
        r"\s+Giveaway$",
    ]

    for pattern in patterns:
        title = re.sub(pattern, "", title, flags=re.I)

    # Remove common AWA wording
    title = re.sub(
        r"\b(Campaign|Demo|Beta|Closed Beta|Playtest)\b",
        "",
        title,
        flags=re.I
    )

    # Clean extra whitespace
    title = re.sub(r"\s+", " ", title).strip()

    return title


# =========================================================
# STEAM SEARCH
# =========================================================

def normalize(text):
    text = text.lower()
    text = re.sub(r"[^a-z0-9]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def similarity(a, b):
    return SequenceMatcher(
        None,
        normalize(a),
        normalize(b)
    ).ratio()


def find_steam_image(title):
    """
    Search Steam Store and return:
        (steam_title, image_url)

    Returns:
        (None, None) if no suitable match is found.
    """

    cleaned = clean_game_title(title)

    # Try cleaned title first, then original title.
    queries = []

    if cleaned:
        queries.append(cleaned)

    if title not in queries:
        queries.append(title)

    for query in queries:

        print(f"STEAM SEARCH: {query}")

        url = (
            "https://store.steampowered.com/search/"
            "?term=" + quote_plus(query)
        )

        try:
            response = requests.get(
                url,
                headers=HEADERS,
                timeout=20
            )

            response.raise_for_status()

        except Exception as e:
            print(f"Steam search failed: {e}")
            continue

        soup = BeautifulSoup(response.text, "html.parser")

        results = soup.select("a.search_result_row")

        if not results:
            print("No Steam results.")
            continue

        best_result = None
        best_score = 0

        for result in results[:10]:

            steam_title = result.get_text(" ", strip=True)

            if not steam_title:
                continue

            # Steam sometimes includes extra text like
            # release date / price, so get the title element.
            title_element = result.select_one(".title")

            if title_element:
                steam_title = title_element.get_text(
                    " ",
                    strip=True
                )

            score = similarity(cleaned, steam_title)

            print(
                f"  Steam candidate: {steam_title} "
                f"(score={score:.2f})"
            )

            if score > best_score:
                best_score = score
                best_result = result

        if not best_result:
            continue

        steam_title_element = best_result.select_one(".title")

        if steam_title_element:
            steam_title = steam_title_element.get_text(
                " ",
                strip=True
            )
        else:
            steam_title = best_result.get_text(
                " ",
                strip=True
            )

        appid = best_result.get("data-ds-appid")

        # Steam can sometimes contain multiple IDs
        if appid:
            appid = appid.split(",")[0].strip()

        if not appid:
            # Try extracting from the URL
            href = best_result.get("href", "")

            match = re.search(
                r"/app/(\d+)",
                href
            )

            if match:
                appid = match.group(1)

        if not appid:
            print("Steam result found but no AppID.")
            continue

        # Don't accept completely unrelated games.
        # 0.35 gives some flexibility for DLC/campaign names.
        if best_score < 0.35:
            print(
                f"Steam match too weak: "
                f"{steam_title} ({best_score:.2f})"
            )
            continue

        image_url = (
            f"https://cdn.akamai.steamstatic.com/"
            f"steam/apps/{appid}/header.jpg"
        )

        print(
            f"STEAM MATCH: {steam_title} "
            f"(AppID {appid})"
        )

        print(f"STEAM IMAGE: {image_url}")

        return steam_title, image_url

    return None, None


# =========================================================
# AWA METADATA
# =========================================================

def extract_metadata(url):

    try:
        response = requests.get(
            url,
            headers=HEADERS,
            timeout=20,
            allow_redirects=True
        )

        print(
            f"AWA METADATA HTTP: "
            f"{response.status_code}"
        )

        print(
            f"AWA FINAL URL: "
            f"{response.url}"
        )

    except Exception as e:

        print(
            f"Failed to fetch AWA page: {e}"
        )

        return "", ""


    soup = BeautifulSoup(
        response.text,
        "html.parser"
    )

    descriptions = []

    # Meta description
    meta = soup.find(
        "meta",
        attrs={"name": "description"}
    )

    if meta and meta.get("content"):
        descriptions.append(
            meta["content"]
        )

    # OpenGraph description
    og = soup.find(
        "meta",
        attrs={"property": "og:description"}
    )

    if og and og.get("content"):
        descriptions.append(
            og["content"]
        )

    # JSON-LD
    for script in soup.find_all(
        "script",
        type="application/ld+json"
    ):

        try:
            data = json.loads(
                script.string or script.get_text()
            )

            items = data

            if not isinstance(items, list):
                items = [items]

            for item in items:

                if isinstance(item, dict):

                    description = item.get(
                        "description"
                    )

                    if description:
                        descriptions.append(
                            str(description)
                        )

        except Exception:
            pass


    combined = " ".join(descriptions)

    combined = (
        combined
        .replace("&nbsp;", " ")
        .replace("\xa0", " ")
    )

    print(
        f"AWA METADATA: {combined[:500]}"
    )

    return combined


# =========================================================
# ARP
# =========================================================

def extract_arp(text):

    patterns = [

        r"requires\s+redeeming\s+([\d,]+)\s*ARP",

        r"redeeming\s+([\d,]+)\s*ARP",

        r"requires\s+([\d,]+)\s*ARP",

        r"([\d,]+)\s*ARP\s+to\s+claim",

        r"([\d,]+)\s*ARP\s+to\s+redeem",

    ]

    for pattern in patterns:

        match = re.search(
            pattern,
            text,
            flags=re.I
        )

        if match:

            amount = match.group(1)

            amount = amount.replace(",", "")

            return f"{int(amount):,} ARP"

    # Nothing mentioned = free / no ARP requirement
    return "0 ARP"


# =========================================================
# TIER
# =========================================================

def extract_tier(text):

    patterns = [

        r"requires\s+(?:AWA\s+)?Tier\s+(\d+)\s*\+?",

        r"Tier\s+(\d+)\s*\+\s*required",

        r"Tier\s+Requirement\s*[:\-]?\s*(\d+)\s*\+?",

        r"minimum\s+Tier\s+(\d+)",

        r"Tier\s+(\d+)\s+required",

    ]

    for pattern in patterns:

        match = re.search(
            pattern,
            text,
            flags=re.I
        )

        if match:

            tier = match.group(1)

            return f"Tier {tier}+"

    # If no tier requirement is mentioned,
    # treat it as Tier 1+
    return "Tier 1+"


# =========================================================
# DISCORD
# =========================================================

def send_discord(
    title,
    link,
    post_id,
    tier,
    arp
):

    if not WEBHOOK_URL:

        print(
            "DISCORD_WEBHOOK not set. "
            "Printing only."
        )

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


    # =====================================================
    # STEAM IMAGE
    # =====================================================

    steam_title, steam_image = find_steam_image(title)


    fields = [

        {
            "name": "🎟️ Tier Requirement",
            "value": tier,
            "inline": True
        },

        {
            "name": "💰 ARP Requirement",
            "value": arp,
            "inline": True
        },

        {
            "name": "Status",
            "value": "Upcoming / Demo Board Leak",
            "inline": False
        },

    ]


    embed = {

        "title": title,

        "url": link,

        "description":
            "🛸 **New AWA Leak Detected**",

        "color": color,

        "fields": fields,

        "footer": {
            "text":
                "Subho's AWA Upcoming GA Notifier",

            "icon_url":
                "https://files.catbox.moe/qttqpy.png"
        },

        "timestamp":
            datetime.utcnow().isoformat()

    }


    # Add Steam image if found
    if steam_image:

        embed["image"] = {
            "url": steam_image
        }

        print(
            f"Using Steam image for: "
            f"{steam_title}"
        )

    else:

        print(
            f"No Steam image found for: "
            f"{title}"
        )


    payload = {
        "embeds": [embed]
    }


    try:

        r = requests.post(
            WEBHOOK_URL,
            json=payload,
            timeout=20
        )

        r.raise_for_status()

        print(
            "Discord notification sent."
        )

    except Exception as e:

        print(
            f"Discord error: {e}"
        )


# =========================================================
# MAIN
# =========================================================

def main():

    seen = load_seen()

    try:

        response = requests.get(
            AWA_URL,
            headers=HEADERS,
            timeout=20
        )

        response.raise_for_status()

    except Exception as e:

        print(
            f"Failed to fetch AWA Demo Board: {e}"
        )

        return


    soup = BeautifulSoup(
        response.text,
        "html.parser"
    )

    found_new = False


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


        if link.startswith("/"):

            link = (
                "https://na.alienwarearena.com"
                + link
            )


        unique_key = (
            f"{post_id}:{text}"
        )


        if unique_key in seen:

            continue


        print()
        print("=" * 60)
        print("NEW:", text)
        print("LINK:", link)
        print("=" * 60)


        # ---------------------------------------------
        # Fetch metadata
        # ---------------------------------------------

        metadata = extract_metadata(
            link
        )


        # ---------------------------------------------
        # Requirements
        # ---------------------------------------------

        arp = extract_arp(
            metadata
        )

        tier = extract_tier(
            metadata
        )


        print(
            f"Tier: {tier}"
        )

        print(
            f"ARP: {arp}"
        )


        # ---------------------------------------------
        # Discord
        # ---------------------------------------------

        send_discord(
            title=text,
            link=link,
            post_id=post_id,
            tier=tier,
            arp=arp
        )


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
