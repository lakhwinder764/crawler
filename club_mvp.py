"""Map crawler records onto the MVP Phase 1 club profile."""

import json
import math
import re
import uuid
from pathlib import Path

import database

ROOT = Path(__file__).resolve().parent
SEED_PATH = ROOT / "output" / "top_100_clubs.json"
STORE_PATH = ROOT / "data" / "store.json"

CATEGORIES = [
    "Run",
    "Book Club",
    "Fitness",
    "Social",
    "Art",
    "Sports",
    "Bar Crawl",
    "Professional",
]

CATEGORY_SLUGS = {
    "Run": "run-clubs",
    "Book Club": "book-clubs",
    "Fitness": "fitness-clubs",
    "Social": "social-clubs",
    "Art": "art-clubs",
    "Sports": "sports-clubs",
    "Bar Crawl": "bar-crawl-clubs",
    "Professional": "professional-clubs",
}

SLUG_TO_CATEGORY = {slug: name for name, slug in CATEGORY_SLUGS.items()}

DAYS = [
    "Monday", "Tuesday", "Wednesday", "Thursday",
    "Friday", "Saturday", "Sunday",
]

SUBURB_COORDS = {
    "Sydney": (-33.8688, 151.2093),
    "Manly": (-33.7969, 151.2880),
    "Blacktown": (-33.7710, 150.9063),
    "Cronulla": (-34.0556, 151.1519),
    "North Sydney": (-33.8406, 151.2065),
    "Parramatta": (-33.8150, 151.0011),
    "Coogee": (-33.9200, 151.2553),
    "Sutherland": (-34.0310, 151.0576),
    "Maroubra": (-33.9500, 151.2431),
    "Dee Why": (-33.7514, 151.2890),
    "Dulwich Hill": (-33.9042, 151.1390),
    "Gladesville": (-33.8280, 151.1290),
    "Kensington": (-33.9078, 151.2220),
    "Hornsby": (-33.7042, 151.0986),
    "Leichhardt": (-33.8831, 151.1560),
    "Bankstown": (-33.9170, 151.0340),
    "Beecroft": (-33.7495, 151.0650),
    "Bonnyrigg": (-33.8878, 150.8836),
    "Greenwich": (-33.8390, 151.1830),
    "Northbridge": (-33.8130, 151.2160),
    "Camden": (-34.0544, 150.6958),
    "Belrose": (-33.7390, 151.2100),
    "Granville": (-33.8334, 151.0124),
    "Newington": (-33.8390, 151.0560),
    "Castle Hill": (-33.7310, 151.0070),
    "Hurstville": (-33.9670, 151.1020),
    "Stanmore": (-33.8940, 151.1640),
    "Concord": (-33.8610, 151.1030),
    "Campbelltown": (-34.0650, 150.8140),
    "Penrith": (-33.7507, 150.6940),
    "Dural": (-33.6830, 151.0250),
    "Prospect": (-33.8160, 150.9120),
    "Rockdale": (-33.9520, 151.1400),
    "Moorebank": (-33.9330, 150.9480),
    "Kyle Bay": (-33.9880, 151.1000),
    "Marrickville": (-33.9110, 151.1550),
    "Mosman": (-33.8290, 151.2440),
    "Sydney Olympic Park": (-33.8469, 151.0686),
    "North Bondi": (-33.8840, 151.2800),
    "Bronte": (-33.9034, 151.2638),
    "Clovelly": (-33.9120, 151.2620),
    "Freshwater": (-33.7790, 151.2870),
    "Palm Beach": (-33.5960, 151.3230),
    "Canterbury": (-33.9120, 151.1180),
    "Narrabeen": (-33.7230, 151.2970),
    "Tamarama": (-33.8980, 151.2700),
    "Caringbah": (-34.0350, 151.1220),
    "Curl Curl": (-33.7690, 151.2890),
    "Newtown": (-33.8986, 151.1794),
    "Bondi": (-33.8915, 151.2767),
    "Redfern": (-33.8929, 151.2043),
    "Surry Hills": (-33.8840, 151.2110),
}


def slugify(value):
    text = re.sub(r"[^a-z0-9]+", "-", (value or "").lower()).strip("-")
    return text or "club"


def load_store():
    if not STORE_PATH.exists():
        return {"hidden": [], "overrides": {}, "submissions": [], "reviews": {}}
    return json.loads(STORE_PATH.read_text(encoding="utf-8"))


def save_store(store):
    STORE_PATH.parent.mkdir(exist_ok=True)
    STORE_PATH.write_text(
        json.dumps(store, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )


def infer_suburb(name, suburb):
    if suburb:
        return suburb
    blob = (name or "").lower()
    for candidate in sorted(SUBURB_COORDS, key=len, reverse=True):
        if candidate == "Sydney":
            continue
        if re.search(rf"(?<![a-z]){re.escape(candidate.lower())}(?![a-z])", blob):
            return candidate
    return ""


def classify(name, description, current):
    blob = f"{name} {description} {current}".lower()
    if re.search(r"\b(book club|reading group)\b", blob):
        return "Book Club", "Reading"
    if re.search(r"\bbar crawl\b", blob):
        return "Bar Crawl", "Nightlife"
    if re.search(r"\b(run club|running club|runners)\b", blob):
        return "Run", "Running"
    if re.search(r"\b(art|choir|orchestra|opera|dramatic|theatre|theater|mozart|organ)\b", blob):
        return "Art", "Creative"
    if re.search(r"\b(business|professional|networking)\b", blob):
        return "Professional", "Networking"
    if re.search(r"\b(cycling|cycle|triathlon|fitness|yoga)\b", blob):
        return "Fitness", "Training"
    if re.search(r"\b(rsl|rotary|probus|leagues|bowling)\b", blob):
        return "Social", "Community club"
    if current == "Social":
        return "Social", "Community"
    if current == "Lifestyle":
        return "Social", "Lifestyle"
    if current == "Hobbies":
        return "Art", "Hobby"
    sport = "Club sport"
    for label, words in (
        ("Football", ("football", "fc", "soccer")),
        ("Futsal", ("futsal",)),
        ("Surf Life Saving", ("surf", "slsc", "lifesaving")),
        ("Swimming", ("swim",)),
        ("Sailing", ("yacht", "sailing")),
        ("Golf", ("golf",)),
        ("Chess", ("chess",)),
    ):
        if any(re.search(rf"\b{word}\b", blob) for word in words):
            sport = label
            break
    return "Sports", sport


def infer_flags(name, description):
    blob = f"{name} {description}".lower()
    beginner = None
    if re.search(r"\b(all levels|beginner|new runners welcome|no experience)\b", blob):
        beginner = True
    age = ""
    if re.search(r"\b(junior|youth|under \d+)\b", blob):
        age = "Juniors"
    elif re.search(r"\b(probus|senior|over 50|over 55)\b", blob):
        age = "Seniors"
    elif re.search(r"\b(all ages|all levels)\b", blob):
        age = "All ages"
    elif re.search(r"\badult\b", blob):
        age = "Adults"
    audience = ""
    if re.search(r"\b(women'?s|women only|ladies)\b", blob):
        audience = "Women-only"
    elif re.search(r"\b(men'?s only|men only)\b", blob):
        audience = "Men-only"
    price = ""
    if re.search(r"\b(free|no cost|no charge)\b", blob):
        price = "Free"
    elif re.search(r"\b(membership fee|paid membership|ticketed)\b", blob):
        price = "Paid"
    return beginner, age, audience, price


def coords_for(suburb):
    return SUBURB_COORDS.get(suburb)


def enrich_record(row, verified=True):
    name = (row.get("name") or "").strip()
    description = (row.get("description") or "").strip()
    suburb = infer_suburb(name, (row.get("suburb") or "").strip())
    category, subcategory = classify(name, description, row.get("category") or "")
    if row.get("subcategory"):
        subcategory = row["subcategory"]
    if row.get("mvp_category"):
        category = row["mvp_category"]
    beginner, age, audience, price = infer_flags(name, description)
    if row.get("audience"):
        audience = row["audience"]
    if row.get("age_group"):
        age = row["age_group"]
    if row.get("price"):
        price = row["price"]
    if row.get("beginner_friendly") is not None and "beginner_friendly" in row and row.get("mvp_category"):
        beginner = row["beginner_friendly"]

    photos = list(row.get("photos") or [])
    image = (row.get("image_url") or "").strip()
    if image and image not in photos:
        photos.insert(0, image)

    days = (row.get("meeting_days") or "").strip()
    meeting_time = (row.get("meeting_time") or "").strip()
    meeting_location = (row.get("meeting_location") or "").strip()
    if not meeting_location and suburb:
        meeting_location = f"{suburb}, Sydney"
    events = list(row.get("events") or [])
    if not events and days:
        events = [{
            "id": slugify(name) + "-weekly",
            "title": f"Weekly {category.lower()} meetup",
            "day": days,
            "time": meeting_time,
            "location": meeting_location,
        }]

    point = coords_for(suburb)
    slug = row.get("id") or slugify(name)
    record = {
        "id": slug,
        "name": name,
        "category": category,
        "subcategory": subcategory or "",
        "description": description,
        "suburb": suburb,
        "city": (row.get("city") or "Sydney").strip() or "Sydney",
        "meeting_location": meeting_location,
        "lat": point[0] if point else None,
        "lng": point[1] if point else None,
        "meeting_days": days,
        "meeting_time": meeting_time,
        "photos": photos,
        "website_url": (row.get("website_url") or "").strip(),
        "instagram_url": (row.get("instagram_url") or "").strip(),
        "facebook_url": (row.get("facebook_url") or "").strip(),
        "contact_email": (row.get("contact_email") or "").strip(),
        "whatsapp": (row.get("whatsapp") or "").strip(),
        "price": price,
        "beginner_friendly": beginner,
        "age_group": age,
        "audience": audience,
        "events": events,
        "verified": bool(row.get("verified", verified)),
        "status": row.get("status") or "published",
        "source_url": row.get("source_url") or "",
        "source_platform": row.get("source_platform") or "",
    }
    return record


def load_seed():
    if not SEED_PATH.exists():
        return []
    rows = json.loads(SEED_PATH.read_text(encoding="utf-8"))
    used = set()
    clubs = []
    for row in rows:
        club = enrich_record(row, verified=True)
        base = club["id"]
        slug = base
        number = 2
        while slug in used:
            slug = f"{base}-{number}"
            number += 1
        club["id"] = slug
        used.add(slug)
        clubs.append(club)
    return clubs


_CRAWLED_EVENTS = None


def crawled_event_index():
    """Events collected from club websites, including private functions."""
    global _CRAWLED_EVENTS
    if _CRAWLED_EVENTS is not None:
        return _CRAWLED_EVENTS
    path = ROOT / "output" / "club_events.json"
    by_domain = {}
    by_name = {}
    if path.exists():
        for club in json.loads(path.read_text(encoding="utf-8")):
            events = club.get("events") or []
            host = re.sub(r"^www\.", "", re.sub(r"^https?://", "", (club.get("website_url") or "").lower()).split("/")[0])
            if host:
                by_domain[host] = events
            by_name[re.sub(r"[^a-z0-9]", "", (club.get("name") or "").lower())] = events
    _CRAWLED_EVENTS = (by_domain, by_name)
    return _CRAWLED_EVENTS


def site_events_for(row):
    by_domain, by_name = crawled_event_index()
    host = re.sub(r"^www\.", "", re.sub(r"^https?://", "", (row.get("website_url") or "").lower()).split("/")[0])
    found = by_domain.get(host) or by_name.get(re.sub(r"[^a-z0-9]", "", (row.get("name") or "").lower())) or []
    events = []
    for index, event in enumerate(found):
        start = event.get("start_date") or ""
        end = event.get("end_date") or ""
        when = start
        if start and end:
            when = f"{start} to {end}"
        events.append({
            "id": f"{row.get('id') or 'club'}-event-{index}",
            "title": event.get("event_name") or "Event",
            "day": when,
            "time": event.get("time") or "",
            "location": event.get("location") or "",
            "status": event.get("status") or "",
            "listing": event.get("listing") or "Public",
        })
    return events


def as_public_club(row):
    """Turn a database row into the profile the website renders."""
    if row["lat"] is None:
        point = coords_for(row.get("suburb") or "")
        if point:
            row["lat"], row["lng"] = point
    photos = [row["image_url"]] if row.get("image_url") else []
    events = site_events_for(row)
    if not events and row.get("meeting_days"):
        events.append({
            "id": row["id"] + "-weekly",
            "title": f"Weekly {row.get('category') or 'club'} meetup",
            "day": row.get("meeting_days") or "",
            "time": row.get("meeting_time") or "",
            "location": row.get("meeting_location") or "",
            "status": "Ongoing",
            "listing": "Public",
        })
    beginner = row.get("beginner_friendly")
    return {
        "id": row["id"],
        "name": row.get("name") or "",
        "category": row.get("category") or "",
        "subcategory": row.get("subcategory") or "",
        "description": row.get("description") or "",
        "suburb": row.get("suburb") or "",
        "city": row.get("city") or "",
        "meeting_location": row.get("meeting_location") or "",
        "lat": row.get("lat"),
        "lng": row.get("lng"),
        "meeting_days": row.get("meeting_days") or "",
        "meeting_time": row.get("meeting_time") or "",
        "photos": photos,
        "website_url": row.get("website_url") or "",
        "instagram_url": row.get("instagram_url") or "",
        "facebook_url": row.get("facebook_url") or "",
        "contact_email": row.get("contact_email") or "",
        "whatsapp": row.get("whatsapp") or "",
        "price": row.get("price") or "",
        "beginner_friendly": None if beginner is None else bool(beginner),
        "age_group": row.get("age_group") or "",
        "audience": row.get("audience") or "",
        "events": events,
        "verified": bool(row.get("verified")),
        "status": row.get("status") or "",
        "source_url": row.get("source_url") or "",
        "source_platform": row.get("source_platform") or "",
        "fingerprint": row.get("fingerprint") or "",
    }


def all_clubs():
    """Published clubs from the database. The site does not crawl on search."""
    if database.count_clubs() == 0 and SEED_PATH.exists():
        database.import_records([
            {
                **club,
                "image_url": (club.get("photos") or [""])[0],
                "status": "published",
                "verified": True,
            }
            for club in load_seed()
        ])
    return [as_public_club(row) for row in database.list_clubs("published")]


def pending_submissions():
    return [as_public_club(row) for row in database.list_clubs("pending")]


def get_club(slug):
    row = database.get_club_row(slug)
    if row is None or row.get("status") != "published":
        return None
    return as_public_club(row)


def haversine(lat1, lng1, lat2, lng2):
    radius = 6371
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dlat = math.radians(lat2 - lat1)
    dlng = math.radians(lng2 - lng1)
    a = math.sin(dlat / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dlng / 2) ** 2
    return 2 * radius * math.asin(math.sqrt(a))


def filter_clubs(clubs, args):
    keyword = (args.get("q") or "").strip().lower()
    category = (args.get("category") or "").strip()
    suburb = (args.get("suburb") or "").strip().lower()
    city = (args.get("city") or "").strip().lower()
    day = (args.get("day") or "").strip()
    price = (args.get("price") or "").strip()
    beginner = (args.get("beginner") or "").strip()
    age = (args.get("age") or "").strip()
    audience = (args.get("audience") or "").strip()
    distance = (args.get("distance") or "").strip()
    lat = args.get("lat")
    lng = args.get("lng")

    selected = []
    for club in clubs:
        blob = " ".join((
            club["name"], club["description"], club["category"],
            club["subcategory"], club["suburb"], club["city"],
        )).lower()
        if keyword and keyword not in blob:
            continue
        if category and club["category"] != category:
            continue
        if suburb and suburb not in club["suburb"].lower():
            continue
        if city and city not in club["city"].lower():
            continue
        if day and day.lower() not in club["meeting_days"].lower():
            continue
        if price and club["price"] != price:
            continue
        if beginner == "yes" and club["beginner_friendly"] is not True:
            continue
        if age and club["age_group"] != age:
            continue
        if audience and club["audience"] != audience:
            continue
        if distance and lat not in (None, "") and lng not in (None, ""):
            if club["lat"] is None:
                continue
            kilometres = haversine(float(lat), float(lng), club["lat"], club["lng"])
            if kilometres > float(distance):
                continue
            club = dict(club)
            club["distance_km"] = round(kilometres, 1)
        selected.append(club)
    return selected


def add_submission(form):
    name = (form.get("name") or "").strip()
    if not name:
        return None, "A club name is required."
    record = enrich_record({
        "id": slugify(name) + "-" + uuid.uuid4().hex[:6],
        "name": name,
        "mvp_category": form.get("category") or "Social",
        "subcategory": (form.get("subcategory") or "").strip(),
        "description": (form.get("description") or "").strip(),
        "suburb": (form.get("suburb") or "").strip(),
        "city": (form.get("city") or "Sydney").strip(),
        "meeting_location": (form.get("meeting_location") or "").strip(),
        "meeting_days": (form.get("meeting_days") or "").strip(),
        "meeting_time": (form.get("meeting_time") or "").strip(),
        "website_url": (form.get("website_url") or "").strip(),
        "instagram_url": (form.get("instagram_url") or "").strip(),
        "facebook_url": (form.get("facebook_url") or "").strip(),
        "contact_email": (form.get("contact_email") or "").strip(),
        "whatsapp": (form.get("whatsapp") or "").strip(),
        "image_url": (form.get("image_url") or "").strip(),
        "price": form.get("price") or "",
        "age_group": form.get("age_group") or "",
        "audience": form.get("audience") or "",
        "beginner_friendly": form.get("beginner_friendly") == "yes",
        "verified": False,
        "status": "pending",
        "source_platform": "Club submission",
        "source_url": "",
    }, verified=False)
    record["status"] = "pending"
    record["verified"] = False
    record["image_url"] = (record.get("photos") or [""])[0]
    record["fingerprint"] = database.fingerprint_for(
        record["name"], record.get("website_url") or "", record["id"]
    )
    database.save_club(record)
    return record, ""


def approve_submission(slug):
    row = database.get_club_row(slug)
    if row is None or row["status"] != "pending":
        return False
    return database.set_status(slug, "published", verified=True)


def hide_club(slug):
    return database.set_status(slug, "hidden")


def update_club(slug, form):
    club = get_club(slug)
    if club is None:
        return False
    club.update({
        "name": (form.get("name") or club["name"]).strip(),
        "mvp_category": form.get("category") or club["category"],
        "category": form.get("category") or club["category"],
        "subcategory": (form.get("subcategory") or "").strip(),
        "description": (form.get("description") or "").strip(),
        "suburb": (form.get("suburb") or "").strip(),
        "city": (form.get("city") or "").strip(),
        "meeting_location": (form.get("meeting_location") or "").strip(),
        "meeting_days": (form.get("meeting_days") or "").strip(),
        "meeting_time": (form.get("meeting_time") or "").strip(),
        "contact_email": (form.get("contact_email") or "").strip(),
        "website_url": (form.get("website_url") or "").strip(),
        "instagram_url": (form.get("instagram_url") or "").strip(),
        "facebook_url": (form.get("facebook_url") or "").strip(),
        "whatsapp": (form.get("whatsapp") or "").strip(),
        "price": form.get("price") or "",
        "age_group": form.get("age_group") or "",
        "audience": form.get("audience") or "",
        "beginner_friendly": form.get("beginner_friendly") == "yes",
        "verified": form.get("verified") == "yes",
    })
    point = coords_for(club["suburb"])
    club["lat"] = point[0] if point else None
    club["lng"] = point[1] if point else None
    club["image_url"] = (club.get("photos") or [""])[0]
    database.save_club(club)
    return True


def add_review(slug, form, photo_path=""):
    club = get_club(slug)
    if club is None:
        return False
    try:
        stars = int(form.get("stars") or 0)
    except ValueError:
        stars = 0
    if stars < 1 or stars > 5:
        return False
    text = (form.get("text") or "").strip()
    if not text:
        return False
    store = load_store()
    reviews = store.setdefault("reviews", {})
    reviews.setdefault(slug, []).append({
        "id": uuid.uuid4().hex[:8],
        "stars": stars,
        "text": text[:600],
        "photo": photo_path,
        "author": (form.get("author") or "Member").strip()[:40] or "Member",
    })
    save_store(store)
    return True


def reviews_for(slug):
    return load_store().get("reviews", {}).get(slug, [])


def analytics(clubs):
    counts = {category: 0 for category in CATEGORIES}
    for club in clubs:
        counts[club["category"]] = counts.get(club["category"], 0) + 1
    store = load_store()
    review_count = sum(len(items) for items in (store.get("reviews") or {}).values())
    return {
        "published": len(clubs),
        "pending": len(pending_submissions()),
        "reviews": review_count,
        "with_map": sum(1 for club in clubs if club["lat"] is not None),
        "categories": counts,
    }
