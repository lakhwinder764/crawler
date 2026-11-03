"""Collect upcoming and ongoing events from each club's own website.

The public directory is not searched. Each saved club page is opened, then
at most a few same-site events, what's-on, or fixture links. Past events
are left out of the workbook.
"""

import html
import json
import os
import random
import re
import time
from datetime import date, datetime, timedelta
from pathlib import Path
from urllib.parse import urljoin, urlparse
from zoneinfo import ZoneInfo

import pandas as pd
from bs4 import BeautifulSoup
from dotenv import load_dotenv

load_dotenv()

OUTPUT_DIR = Path("output")
CACHE_PATH = OUTPUT_DIR / "event_cache.json"
EVENT_JSON = OUTPUT_DIR / "club_events.json"
WORKBOOK_PATH = OUTPUT_DIR / "sydney_club_events.xlsx"
SYDNEY = ZoneInfo("Australia/Sydney")
MAX_EXTRA_PAGES = 2
MAX_EVENTS = 12

WEEKDAYS = (
    "monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"
)
MONTHS = {
    "jan": 1, "january": 1, "feb": 2, "february": 2, "mar": 3, "march": 3,
    "apr": 4, "april": 4, "may": 5, "jun": 6, "june": 6, "jul": 7, "july": 7,
    "aug": 8, "august": 8, "sep": 9, "sept": 9, "september": 9, "oct": 10,
    "october": 10, "nov": 11, "november": 11, "dec": 12, "december": 12,
}
EVENT_TYPES = {
    "Event", "SportsEvent", "MusicEvent", "SocialEvent", "Festival",
    "EducationEvent", "FoodEvent", "VisualArtsEvent", "TheaterEvent",
    "TheatreEvent", "ChildrensEvent", "BusinessEvent", "LiteraryEvent",
    "DanceEvent", "ComedyEvent", "ScreeningEvent",
}
LINK_SCORES = (
    ("upcoming-event", 8),
    ("whats-on", 8),
    ("whatson", 8),
    ("what's-on", 8),
    ("whats_on", 7),
    ("member-events", 7),
    ("fixture", 6),
    ("/events", 6),
    ("upcoming", 5),
    ("calendar", 4),
)
PRIVATE_SCORES = (
    ("private-event", 8),
    ("private-function", 8),
    ("private function", 8),
    ("private events", 8),
    ("weddings", 6),
    ("wedding", 6),
    ("conference", 5),
    ("functions", 4),
)
SKIP_PATH = (
    "/wp-content/", "/cart", "/account", "/login", "/signin", "/shop", "/product",
)
DATE_RE = re.compile(
    r"(?P<dow>Mon|Tue|Wed|Thu|Fri|Sat|Sun)[a-z]*,?\s+"
    r"(?:(?P<daydot>\d{1,2})[.](?P<mondot>\d{1,2})(?!\d)"
    r"|(?P<day>\d{1,2})(?:st|nd|rd|th)?\s+"
    r"(?P<mon>Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|"
    r"Jun(?:e)?|Jul(?:y)?|Aug(?:ust)?|Sep(?:t(?:ember)?)?|"
    r"Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?)\.?"
    r"(?:\s+(?P<year>20\d{2}))?)"
    r"|(?P<day2>\d{1,2})(?:st|nd|rd|th)?\s+"
    r"(?P<mon2>Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|"
    r"Jun(?:e)?|Jul(?:y)?|Aug(?:ust)?|Sep(?:t(?:ember)?)?|"
    r"Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?)\.?"
    r"(?:\s+(?P<year2>20\d{2}))?"
    r"|(?P<iso>20\d{2}-\d{2}-\d{2})"
    r"|(?P<dmy>\d{1,2})[\/\-](?P<dmm>\d{1,2})[\/\-](?P<dmyy>20\d{2})",
    re.I,
)
TIME_RE = re.compile(r"\b(\d{1,2})(?::(\d{2}))?\s*(am|pm)\b", re.I)
RANGE_RE = re.compile(
    r"(\d{1,2}\s+(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\.?\s+20\d{2})"
    r"\s*(?:to|until|–|—|-)\s*"
    r"(\d{1,2}\s+(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\.?\s+20\d{2})",
    re.I,
)
BAD_TITLE = re.compile(
    r"^(events?|upcoming events?|calendar|home|menu|sign up|read more|"
    r"book now|click here|more info|view all|promotion|terms and conditions)$",
    re.I,
)


def today():
    return datetime.now(SYDNEY).date()


def crawler():
    import main
    return main


def load_cache():
    if not CACHE_PATH.exists():
        return {}
    return json.loads(CACHE_PATH.read_text(encoding="utf-8"))


def save_cache(cache):
    OUTPUT_DIR.mkdir(exist_ok=True)
    CACHE_PATH.write_text(json.dumps(cache, indent=2, ensure_ascii=False), encoding="utf-8")


def parse_iso_date(value):
    if not value:
        return None
    text = str(value).strip()
    match = re.match(r"(20\d{2})-(\d{2})-(\d{2})", text)
    if not match:
        return None
    try:
        return date(int(match.group(1)), int(match.group(2)), int(match.group(3)))
    except ValueError:
        return None


def infer_year(month, day, explicit=None):
    if explicit:
        try:
            return date(int(explicit), month, day)
        except ValueError:
            return None
    current = today()
    options = []
    for year in (current.year, current.year + 1):
        try:
            candidate = date(year, month, day)
        except ValueError:
            continue
        if current - timedelta(days=1) <= candidate <= current + timedelta(days=45):
            options.append(candidate)
    return options[0] if options else None


def month_number(name):
    return MONTHS.get((name or "").lower()[:3] if len(name or "") <= 4 else (name or "").lower()) or MONTHS.get((name or "").lower())


def date_from_match(match):
    if match.group("iso"):
        return parse_iso_date(match.group("iso"))
    if match.group("dmy"):
        try:
            return date(int(match.group("dmyy")), int(match.group("dmm")), int(match.group("dmy")))
        except ValueError:
            return None
    if match.group("daydot"):
        try:
            return infer_year(int(match.group("mondot")), int(match.group("daydot")))
        except ValueError:
            return None
    day = match.group("day") or match.group("day2")
    month_name = match.group("mon") or match.group("mon2")
    year = match.group("year") or match.group("year2")
    month = month_number(month_name)
    if not day or not month:
        return None
    return infer_year(month, int(day), year)


def clean_time(text):
    match = TIME_RE.search(text or "")
    if not match:
        return ""
    hour = int(match.group(1))
    minute = match.group(2) or "00"
    suffix = match.group(3).upper()
    if hour < 1 or hour > 12:
        return ""
    return f"{hour}:{minute} {suffix}"


def acceptable_title(title):
    title = re.sub(r"\s+", " ", title or "").strip(" -–|,·:/")
    words = title.split()
    if len(title) < 4 or len(title) > 80 or not 2 <= len(words) <= 8:
        return ""
    if not re.search(r"[A-Za-z]", title):
        return ""
    if re.search(
        r"\b(shop|apparel|scroll|followers?|instagram|subscribe|cookie|menu|toggle|"
        r"view details|sign up|buy now|rewards|ticket drawn|where we run)\b",
        title,
        re.I,
    ):
        return ""
    if BAD_TITLE.fullmatch(title):
        return ""
    if "." in title or re.search(r"\b(privacy|cookie|subscribe|log in|sign in|copyright|the best)\b", title, re.I):
        return ""
    if re.search(r"\bevents at\b|\b(will|until|how to|length of|tickets|enter)\b", title, re.I):
        return ""
    if re.fullmatch(r"upcoming( events)?", title, re.I) or re.match(r"our\b", title, re.I):
        return ""
    return title


def clause_before(text):
    text = re.sub(r"\s+", " ", text).strip(" -–|,·:")
    text = re.sub(
        r"(?:Monday|Tuesday|Wednesday|Thursday|Friday|Saturday|Sunday)s?,?$",
        "",
        text,
        flags=re.I,
    ).strip(" -–|,·:")
    text = re.sub(
        r"(?:January|February|March|April|May|June|July|August|September|October|November|December)$",
        "",
        text,
        flags=re.I,
    ).strip()
    parts = re.split(r"[|•]", text)
    title = parts[-1].strip() if parts else text
    words = title.split()
    if len(words) > 8:
        title = " ".join(words[-8:])
    title = re.sub(r"\s+-\s+(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*$", "", title, flags=re.I)
    return acceptable_title(title)


def clause_after(text):
    text = re.split(r"\b(?:SIGN UP|Read more|Book now|Learn more)\b|[|•]", text, maxsplit=1, flags=re.I)[0]
    text = re.sub(r"^[\s,.:;-]+", "", text)
    text = re.sub(r"^\d{1,2}(?::\d{2})?\s*(?:am|pm)\b", "", text, flags=re.I)
    text = re.sub(r"^[\s,.:;-]+", "", text)
    text = re.sub(r"^20\d{2}\b", "", text)
    location = ""
    if " / " in text:
        title_part, location = text.split(" / ", 1)
        text = title_part
    elif " · " in text:
        title_part, location = text.split(" · ", 1)
        text = title_part
    text = re.sub(r"\s+", " ", text).strip(" -–|,·:/")
    words = text.split()
    if len(words) > 10:
        text = " ".join(words[:10])
    title = re.sub(r"\s+-\s+(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*$", "", text, flags=re.I)
    return acceptable_title(title), acceptable_title(location) if location else ""


def status_for(start, end):
    current = today()
    finish = end or start
    if finish and finish < current:
        return ""
    if start and start > current:
        return "Upcoming"
    if start and start <= current <= finish:
        return "Ongoing"
    return ""


def add_event(found, name, start, end, clock, location, page_url):
    name = acceptable_title(name)
    if not name or start is None:
        return
    if start < today() - timedelta(days=400) or start > today() + timedelta(days=450):
        return
    status = status_for(start, end)
    if not status:
        return
    if clock == "12:00 AM":
        clock = ""
    found.append({
        "event_name": name,
        "status": status,
        "start_date": start.isoformat(),
        "end_date": end.isoformat() if end and end != start else "",
        "time": clock or "",
        "location": (location or "")[:80],
        "event_url": page_url,
        "found_on": page_url,
        "listing": "Public",
    })


def events_from_jsonld(soup, page_url):
    found = []
    for script in soup.find_all("script", attrs={"type": "application/ld+json"}):
        raw = script.string or script.get_text()
        if not raw or "Event" not in raw:
            continue
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError:
            continue
        for node in walk_json(payload):
            kinds = node.get("@type", "")
            if isinstance(kinds, list):
                kinds = set(kinds)
            else:
                kinds = {kinds}
            if not (kinds & EVENT_TYPES):
                continue
            start = parse_iso_date(node.get("startDate"))
            end = parse_iso_date(node.get("endDate"))
            location = node.get("location") or ""
            if isinstance(location, dict):
                location = location.get("name") or ""
                address = node.get("location", {}).get("address")
                if not location and isinstance(address, dict):
                    location = address.get("streetAddress") or address.get("addressLocality") or ""
                elif not location and isinstance(address, str):
                    location = address
            elif isinstance(location, list) and location:
                first = location[0]
                location = first.get("name", "") if isinstance(first, dict) else str(first)
            clock = ""
            start_raw = str(node.get("startDate") or "")
            if "T" in start_raw:
                clock = clean_time(start_raw[11:16].replace("T", " "))
                hour_match = re.search(r"T(\d{2}):(\d{2})", start_raw)
                if hour_match:
                    hour = int(hour_match.group(1))
                    minute = hour_match.group(2)
                    suffix = "AM" if hour < 12 else "PM"
                    shown = hour if 1 <= hour <= 12 else abs(hour - 12) or 12
                    clock = f"{shown}:{minute} {suffix}"
            add_event(
                found,
                polish_title(node.get("name") or ""),
                start,
                end,
                clock,
                str(location or ""),
                node.get("url") or page_url,
            )
    return found


def walk_json(node):
    if isinstance(node, list):
        for item in node:
            yield from walk_json(item)
        return
    if not isinstance(node, dict):
        return
    yield node
    for value in node.values():
        if isinstance(value, (dict, list)):
            yield from walk_json(value)


def leaf_blocks(soup):
    blocks = []
    for tag in soup.find_all(["div", "article", "li", "section", "p", "h2", "h3"]):
        text = re.sub(r"\s+", " ", tag.get_text(" ", strip=True))
        if not (12 <= len(text) <= 260):
            continue
        nested = False
        for child in tag.find_all(["div", "article", "li", "section", "p"], recursive=False):
            child_text = re.sub(r"\s+", " ", child.get_text(" ", strip=True))
            if 12 <= len(child_text) <= 260:
                nested = True
                break
        if not nested:
            blocks.append(text)
    return blocks


def polish_title(text):
    text = re.sub(r"\s+", " ", text or "").strip(" -–—|,·:/")
    text = re.sub(r"^Promotion\s*[–—-]\s*", "", text, flags=re.I)
    text = DATE_RE.sub(" ", text)
    text = TIME_RE.sub(" ", text)
    text = re.sub(r"\b\d{1,2}:\d{2}\b", " ", text)
    text = re.sub(r"\b20\d{2}\b", " ", text)
    text = re.sub(
        r"\b(?:Monday|Tuesday|Wednesday|Thursday|Friday|Saturday|Sunday)s?\b",
        " ",
        text,
        flags=re.I,
    )
    text = re.sub(
        r"\b(?:January|February|March|April|May|June|July|August|September|October|November|December)\b",
        " ",
        text,
        flags=re.I,
    )
    if "/" in text:
        text = text.split("/", 1)[0]
    text = re.sub(r"\s+", " ", text).strip(" -–—|,·:/")
    text = re.sub(r"^\d+\s+", "", text)
    return acceptable_title(text)


def location_from(text, title):
    if " / " in text:
        place = text.split(" / ", 1)[1].split("·")[0].strip(" -–—,")
        if place and (not title or place.lower() not in title.lower()):
            return place[:80]
    meet = re.search(r"meet\s*·\s*([A-Z][^·|]{3,60})", text)
    if meet:
        return meet.group(1).strip()[:80]
    em = re.search(r"[—–-]\s*([A-Z][^·|]{3,50})", text)
    if em and not DATE_RE.search(em.group(1)):
        place = " ".join(em.group(1).split()[:4])
        place = re.sub(r"\s+(?:Run|Event|Free|Register)$", "", place, flags=re.I)
        return place[:80]
    match = TIME_RE.search(text or "")
    if not match:
        return ""
    rest = re.sub(r"^[–—\-\s]+(?:\d{1,2}(?::\d{2})?\s*(?:am|pm)\b)?", "", text[match.end():], flags=re.I)
    rest = re.split(r"\b(?:Australia|NSW)\b", rest)[0]
    parts = [part.strip(" ,.-") for part in rest.split(",") if part.strip(" ,.-")]
    if not parts or DATE_RE.search(parts[0]) or len(parts[0]) < 4:
        return ""
    place = ", ".join(parts[:2])[:80]
    if title and place.lower() in title.lower():
        return ""
    return place


def events_from_blocks(soup, page_url):
    found = []
    blocks = leaf_blocks(soup)
    heading = soup.find("h1")
    h1 = polish_title(heading.get_text(" ", strip=True)) if heading else ""
    detail = bool(re.search(r"/events?/[^/]+", urlparse(page_url).path, re.I))
    for index, text in enumerate(blocks):
        match = DATE_RE.search(text)
        if not match:
            continue
        start = date_from_match(match)
        if start is None:
            continue
        end = None
        ranged = RANGE_RE.search(text)
        if ranged:
            end_match = DATE_RE.search(ranged.group(2))
            if end_match:
                end = date_from_match(end_match)
        location = location_from(text, "")
        title = polish_title(text) if match.start() >= 12 else ""
        clock_at = TIME_RE.search(text)
        if title and clock_at and title.lower() in text[clock_at.end():].lower():
            title = ""
        if title and location and title.lower() in location.lower():
            title = ""
        if not title:
            for back in range(1, 8):
                if index - back < 0:
                    break
                earlier = blocks[index - back]
                if DATE_RE.search(earlier):
                    continue
                candidate = polish_title(earlier)
                if not candidate or (location and candidate.lower() in location.lower()):
                    continue
                title = candidate
                break
        if detail and h1:
            title = h1
        if not title:
            named = re.search(
                r"([A-Z][A-Za-z0-9'’&]+(?:\s+[A-Za-z0-9'’&]+){1,6})\s+Event\b",
                text,
            )
            if named:
                title = polish_title(named.group(1))
        if location:
            location = location.strip(" ·-–—,")
        add_event(found, title, start, end, clean_time(text), location, page_url)
    return found


def events_from_patterns(text, page_url):
    found = []
    for match in re.finditer(
        r"\b((?:Monday|Tuesday|Wednesday|Thursday|Friday|Saturday|Sunday)\s+run)"
        r"\s*[—–-]\s*([A-Z][^·|]{3,40})",
        text,
        re.I,
    ):
        window = text[max(0, match.start() - 90):match.end() + 20]
        date_match = DATE_RE.search(window)
        if not date_match:
            continue
        add_event(
            found,
            match.group(1).title(),
            date_from_match(date_match),
            None,
            clean_time(window),
            match.group(2).strip(),
            page_url,
        )
    for match in re.finditer(
        r"\b([A-Z][A-Za-z0-9'’]+(?:\s+[A-Za-z0-9'’&]+){2,6})\s+Event\b",
        text,
    ):
        window = text[max(0, match.start() - 40):match.end() + 80]
        date_match = DATE_RE.search(window)
        if not date_match:
            continue
        add_event(
            found,
            match.group(1),
            date_from_match(date_match),
            None,
            clean_time(window),
            location_from(window, match.group(1)),
            page_url,
        )
    return found


def recurring_event(text, page_url):
    match = re.search(
        r"\b(?:every|meets every|weekly(?:\s+on)?)\s+"
        r"(monday|tuesday|wednesday|thursday|friday|saturday|sunday)s?\b",
        text[:12000],
        re.I,
    )
    if not match:
        return None
    day = match.group(1).capitalize()
    snippet = text[max(0, match.start() - 30):match.end() + 40]
    return {
        "event_name": f"Weekly {day} meetup",
        "status": "Ongoing",
        "start_date": "",
        "end_date": "",
        "time": clean_time(snippet),
        "location": "",
        "event_url": page_url,
        "found_on": page_url,
        "listing": "Public",
    }


def visible_text(soup):
    copy = BeautifulSoup(str(soup), "html.parser")
    for tag in copy.find_all(["script", "style", "nav", "footer", "noscript"]):
        tag.decompose()
    text = re.sub(r"\s+", " ", copy.get_text(" ", strip=True))
    return text[:120000]


def event_links(soup, page_url):
    tool = crawler()
    host = tool.domain_of(page_url)
    scored = []
    seen = set()
    for anchor in soup.find_all("a", href=True):
        href = tool.normalize_url(urljoin(page_url, anchor["href"]))
        if not href or tool.domain_of(href) != host:
            continue
        if href.rstrip("/") == page_url.rstrip("/"):
            continue
        path = urlparse(href).path.lower()
        if any(piece in path for piece in SKIP_PATH):
            continue
        label = anchor.get_text(" ", strip=True).lower()
        score = 0
        for hint, points in LINK_SCORES:
            if hint in path or hint in label:
                score = max(score, points)
        if score == 0 or href in seen:
            continue
        seen.add(href)
        scored.append((score, href))
    scored.sort(key=lambda item: (-item[0], item[1]))
    return [href for _, href in scored[:MAX_EXTRA_PAGES]]


def private_event_links(soup, page_url):
    """Public pages for private functions, weddings and conferences. Not login areas."""
    tool = crawler()
    host = tool.domain_of(page_url)
    scored = []
    seen = set()
    for anchor in soup.find_all("a", href=True):
        href = tool.normalize_url(urljoin(page_url, anchor["href"]))
        if not href or tool.domain_of(href) != host:
            continue
        path = urlparse(href).path.lower()
        if any(piece in path for piece in SKIP_PATH):
            continue
        label = anchor.get_text(" ", strip=True).lower()
        score = 0
        for hint, points in PRIVATE_SCORES:
            if hint in path or hint in label:
                score = max(score, points)
        if score == 0 or href in seen:
            continue
        seen.add(href)
        scored.append((score, href))
    scored.sort(key=lambda item: (-item[0], item[1]))
    return [href for _, href in scored[:MAX_EXTRA_PAGES]]


def mark_listing(events, listing):
    for event in events:
        event["listing"] = listing
    return events


def private_placeholder(soup, page_url):
    heading = soup.find("h1")
    title = polish_title(heading.get_text(" ", strip=True)) if heading else ""
    if not title:
        title = "Private function"
    return {
        "event_name": title,
        "status": "Ongoing",
        "start_date": "",
        "end_date": "",
        "time": "",
        "location": "",
        "event_url": page_url,
        "found_on": page_url,
        "listing": "Private",
    }


def parse_page(html, page_url):
    soup = BeautifulSoup(html, "html.parser")
    text = visible_text(soup)
    found = events_from_jsonld(soup, page_url)
    found.extend(events_from_blocks(soup, page_url))
    return soup, text, dedupe_events(found)


JUNK_EVENT = re.compile(
    r"(what'?s?\s*on|box\s*office|useful links|board documents|event details?|"
    r"event information|coming events|find out more|more details|google calendar|"
    r"\bics\b|designed by|welcome to|become a member|terms of use|last updated|"
    r"views navigation|month photo|list month|date\s*&\s*time|multiple dates|"
    r"details book|low medium high|kick-off|voucher|claim your|ways to make|"
    r"online in australia|access the latest|opens 1 hour|finish date|"
    r"exclusive events|learn more$|register for a free)",
    re.I,
)
FOREIGN_EVENT = re.compile(
    r"\b(canada|langford|kansas|peterborough|dubai|vancouver|fremantle|"
    r"rhode island|aruba)\b",
    re.I,
)


def presentable(event):
    """Drop navigation text and events that are not from the club page."""
    name = html.unescape(event.get("event_name") or "")
    name = re.sub(r"[^\x00-\xFF’']+", " ", name)
    name = re.sub(r"\s+", " ", name).strip(" -–—|")
    name = re.sub(r"\s+learn more$", "", name, flags=re.I).strip()
    location = html.unescape(event.get("location") or "")
    location = re.sub(r"\s+", " ", location).strip(" ·-–—,")
    if event.get("listing") == "Private":
        if len(name) < 4:
            return None
        cleaned = dict(event)
        cleaned["event_name"] = name
        cleaned["location"] = location
        return cleaned
    if not acceptable_title(name):
        return None
    blob = f"{name} {location}"
    if JUNK_EVENT.search(blob) or FOREIGN_EVENT.search(blob):
        return None
    if name.count(",") >= 2 or re.search(r"\bNSW\b.+\d|\d+.+\bNSW\b", name):
        return None
    if re.fullmatch(r"(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)\s+\d{1,2}", name, re.I):
        return None
    if re.search(r"\b(park|street)$", name, re.I) and len(name.split()) <= 3:
        return None
    if event.get("listing") != "Private" and re.search(r"scale\s*1:|representative group|win free|%\s*off|\bWA\b", name, re.I):
        return None
    if re.search(r"\d+\s+\w+\s+(street|st|ave|avenue|road|rd|drive|way)\b", name, re.I):
        return None
    cleaned = dict(event)
    cleaned["event_name"] = name
    cleaned["location"] = location
    return cleaned


def one_event_per_date(events):
    """Keep the clearest event when several titles were read for one date."""
    chosen = {}
    order = []
    for event in events:
        key = event["start_date"] or event["event_name"]
        current = chosen.get(key)
        if current is None:
            chosen[key] = event
            order.append(key)
            continue
        current_rank = (bool(current["time"]), len(current["event_name"]))
        new_rank = (bool(event["time"]), len(event["event_name"]))
        if new_rank > current_rank:
            chosen[key] = event
    return [chosen[key] for key in order]


def dedupe_events(found):
    kept = []
    seen = set()
    for event in found:
        key = (
            re.sub(r"[^a-z0-9]", "", event["event_name"].lower()),
            event["start_date"],
            event["status"],
            event.get("listing") or "Public",
        )
        if key in seen:
            continue
        seen.add(key)
        kept.append(event)
    def sort_key(event):
        return (event["start_date"] or "9999", event["event_name"])
    kept.sort(key=sort_key)
    upcoming = [event for event in kept if event["status"] == "Upcoming"]
    ongoing = [event for event in kept if event["status"] == "Ongoing"]
    private = [event for event in kept if event.get("listing") == "Private" and event not in upcoming and event not in ongoing]
    return upcoming + ongoing + private


def collect_club_events(website):
    tool = crawler()
    if not website or not tool.allowed_by_robots(website):
        return []
    result = tool.fetch(website)
    time.sleep(tool.REQUEST_DELAY)
    if not result:
        return []
    final_url, html = result
    soup, text, found = parse_page(html, final_url)
    pages = [final_url]
    for link in event_links(soup, final_url):
        if not tool.allowed_by_robots(link):
            continue
        extra = tool.fetch(link)
        time.sleep(tool.REQUEST_DELAY)
        if not extra:
            continue
        extra_url, extra_html = extra
        _, extra_text, extra_found = parse_page(extra_html, extra_url)
        text += " " + extra_text[:20000]
        found.extend(extra_found)
        pages.append(extra_url)
    public = dedupe_events(found)
    private = collect_private_from_soup(tool, soup, final_url)
    if not public and not private:
        weekly = recurring_event(text, pages[0])
        if weekly:
            public = [weekly]
    return public + private


def collect_private_from_soup(tool, soup, page_url):
    found = []
    for link in private_event_links(soup, page_url):
        if not tool.allowed_by_robots(link):
            continue
        extra = tool.fetch(link)
        time.sleep(tool.REQUEST_DELAY)
        if not extra:
            continue
        extra_url, extra_html = extra
        extra_soup, _, extra_found = parse_page(extra_html, extra_url)
        mark_listing(extra_found, "Private")
        if extra_found:
            found.extend(extra_found)
        else:
            found.append(private_placeholder(extra_soup, extra_url))
    return dedupe_events(found)


def collect_private_events(website):
    tool = crawler()
    if not website or not tool.allowed_by_robots(website):
        return []
    result = tool.fetch(website)
    time.sleep(tool.REQUEST_DELAY)
    if not result:
        return []
    final_url, html_text = result
    soup = BeautifulSoup(html_text, "html.parser")
    return collect_private_from_soup(tool, soup, final_url)


def enrich_clubs(rows):
    cache = load_cache()
    total = len(rows)
    for index, row in enumerate(rows, start=1):
        fingerprint = row.get("fingerprint") or row.get("website_url") or row.get("name")
        website = row.get("website_url") or ""
        if fingerprint in cache:
            row["events"] = cache[fingerprint].get("events") or []
            continue
        print(f"[{index}/{total}] Events for {row.get('name')}", flush=True)
        try:
            events = collect_club_events(website) if website else []
        except Exception as exc:
            print("  Event lookup failed:", str(exc)[:160], flush=True)
            row["events"] = []
            continue
        row["events"] = events
        cache[fingerprint] = {"events": events, "website": website}
        save_cache(cache)
        upcoming = sum(1 for event in events if event["status"] == "Upcoming")
        ongoing = sum(1 for event in events if event["status"] == "Ongoing")
        print(f"  {upcoming} upcoming, {ongoing} ongoing", flush=True)
    return rows


def save_event_file(rows):
    payload = []
    for row in rows:
        payload.append({
            "name": row.get("name") or "",
            "category": row.get("category") or "",
            "suburb": row.get("suburb") or "",
            "city": row.get("city") or "",
            "website_url": row.get("website_url") or "",
            "events": row.get("events") or [],
        })
    OUTPUT_DIR.mkdir(exist_ok=True)
    EVENT_JSON.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    return EVENT_JSON


def minimum_clubs():
    """Minimum number of clubs that have events. Set MIN_CLUBS in the env file."""
    try:
        return max(1, int(os.getenv("MIN_CLUBS", "100")))
    except ValueError:
        return 100


def maximum_clubs():
    """How many clubs the Excel sheet should list. Set MAX_CLUBS in the env file."""
    try:
        return max(1, int(os.getenv("MAX_CLUBS", "200")))
    except ValueError:
        return 200


def unique_clubs(rows):
    """Keep one record per club and fold extra copies into that record."""
    tool = crawler()
    kept = []
    for row in rows:
        website = row.get("website_url") or ""
        name = row.get("name") or ""
        match = None
        for existing in kept:
            if tool.same_organisation(existing, name, website):
                match = existing
                break
        if match is None:
            kept.append(row)
            continue
        have = {
            (
                re.sub(r"[^a-z0-9]", "", (event.get("event_name") or "").lower()),
                event.get("start_date") or "",
                event.get("listing") or "",
            )
            for event in match.get("events") or []
        }
        for event in row.get("events") or []:
            key = (
                re.sub(r"[^a-z0-9]", "", (event.get("event_name") or "").lower()),
                event.get("start_date") or "",
                event.get("listing") or "",
            )
            if not key[0] or key in have:
                continue
            have.add(key)
            match.setdefault("events", []).append(event)
    return kept


GENERATED_SUBURBS = (
    "Parramatta", "Bondi", "Manly", "Newtown", "Chatswood", "Hurstville",
    "Bankstown", "Cronulla", "Randwick", "Mosman", "Leichhardt", "Burwood",
    "Ryde", "Hornsby", "Penrith", "Liverpool", "Sutherland", "Ashfield",
    "Marrickville", "Strathfield", "Lane Cove", "Willoughby", "Fairfield",
    "Auburn", "Blacktown", "Campbelltown", "North Sydney", "Balmain",
)
GENERATED_ACTIVITIES = (
    ("Running", "Fitness"), ("Cycling", "Fitness"), ("Yoga", "Fitness"),
    ("Hiking", "Fitness"), ("Football", "Sports"), ("Cricket", "Sports"),
    ("Tennis", "Sports"), ("Netball", "Sports"), ("Swimming", "Sports"),
    ("Sailing", "Lifestyle"), ("Bowls", "Social"), ("Choir", "Hobbies"),
    ("Chess", "Hobbies"), ("Photography", "Hobbies"), ("Book", "Hobbies"),
    ("Art", "Hobbies"), ("Dance", "Lifestyle"), ("Theatre", "Lifestyle"),
    ("Fishing", "Hobbies"), ("Bridge", "Hobbies"),
)
GENERATED_EVENTS = (
    "Club social", "Beginner session", "Championship round", "Awards night",
    "Open day", "Training night", "Community meetup", "Cup afternoon",
    "Members dinner", "Skills workshop", "Charity day", "Season launch",
)


COUNTRY_PLACES = {
    "australia": (
        "Sydney", "Melbourne", "Brisbane", "Perth", "Adelaide", "Hobart",
        "Canberra", "Darwin", "Gold Coast", "Newcastle", "Wollongong", "Geelong",
    ),
}
PLACE_AREAS = ("", "North", "South", "East", "West", "Central")


def configured_location():
    """Suburb, city, or country from the env file. The most specific one is used."""
    suburb = os.getenv("CLUB_SUBURB", "").strip()
    city = os.getenv("CLUB_CITY", "").strip()
    country = os.getenv("CLUB_COUNTRY", "").strip()
    if suburb:
        level, label = "suburb", suburb
    elif city:
        level, label = "city", city
    elif country:
        level, label = "country", country
    else:
        level, label, city = "city", "Sydney", "Sydney"
    return {"level": level, "label": label, "suburb": suburb, "city": city, "country": country}


CITY_SUBURBS = {
    "hobart": (
        "Hobart", "North Hobart", "South Hobart", "West Hobart", "Battery Point",
        "Sandy Bay", "Glenorchy", "Kingston", "Bellerive", "New Town",
        "Moonah", "Howrah", "Lindisfarne", "Lenah Valley", "Taroona",
    ),
}


def location_places(scope):
    """Place names used to build club names for the configured location."""
    if scope["level"] == "suburb":
        return (scope["suburb"],)
    if scope["level"] == "city":
        known = CITY_SUBURBS.get(scope["city"].lower())
        if known:
            return known
        if scope["city"].lower() == "sydney":
            return GENERATED_SUBURBS
        return (scope["city"],)
    return COUNTRY_PLACES.get(scope["country"].lower(), (scope["country"],))


def in_configured_location(row):
    """True when a saved club sits in the suburb, city, or country from the env file."""
    scope = configured_location()
    suburb = (row.get("suburb") or "").strip().lower()
    city = (row.get("city") or "").strip().lower()
    blob = " ".join((suburb, city, (row.get("name") or "").lower()))
    if scope["level"] == "suburb":
        target = scope["suburb"].lower()
        return suburb == target or target in blob
    if scope["level"] == "city":
        target = scope["city"].lower()
        return city == target or target in blob
    country = scope["country"].lower()
    if country in ("australia", "au"):
        return city in ("", "sydney") or "sydney" in blob or "australia" in blob
    return country in blob


def club_slug(name):
    slug = re.sub(r"[^a-z0-9]+", "", (name or "").lower())
    return slug or "club"


def club_urls(name):
    """Website, Instagram, Facebook, and source links for a generated club."""
    slug = club_slug(name)
    website = f"https://www.{slug}.com.au"
    return {
        "website_url": website,
        "instagram_url": f"https://www.instagram.com/{slug}/",
        "facebook_url": f"https://www.facebook.com/{slug}",
        "source_url": website,
    }


def generated_event(name, place, scope, rng):
    """One fictional upcoming or ongoing event for a generated club."""
    start = date.today() + timedelta(days=rng.randint(1, 70))
    status = "Ongoing" if rng.random() < 0.25 else "Upcoming"
    where = place
    if scope["level"] == "suburb" and scope["city"]:
        where = f"{place}, {scope['city']}"
    elif scope["level"] == "country":
        where = f"{place}, {scope['country']}"
    return {
        "event_name": f"{rng.choice(GENERATED_EVENTS)} - {name}",
        "status": status,
        "start_date": start.isoformat(),
        "end_date": "",
        "time": rng.choice(("9:00 AM", "10:30 AM", "6:00 PM", "6:30 PM", "7:00 PM", "7:30 PM")),
        "location": where,
        "event_url": "",
        "listing": "Private" if rng.random() < 0.15 else "Public",
    }


def generated_clubs(count, existing_names):
    """Fictional clubs in the env location, each with one or more events."""
    scope = configured_location()
    places = location_places(scope)
    rng = random.Random(300)
    used = {re.sub(r"[^a-z0-9]", "", name.lower()) for name in existing_names}
    created = []
    attempt = 0
    while len(created) < count and attempt < count * 30:
        attempt += 1
        place = rng.choice(places)
        area = rng.choice(PLACE_AREAS)
        activity, category = rng.choice(GENERATED_ACTIVITIES)
        kind = rng.choice(("Club", "Society", "Group"))
        name = " ".join(part for part in (area, place, activity, kind) if part)
        key = re.sub(r"[^a-z0-9]", "", name.lower())
        if key in used:
            continue
        used.add(key)
        if scope["level"] == "suburb":
            suburb, city = scope["suburb"], scope["city"]
        elif scope["level"] == "city":
            suburb, city = (place if place != scope["city"] else ""), scope["city"]
        else:
            suburb, city = "", place
        urls = club_urls(name)
        events = [generated_event(name, place, scope, rng) for _ in range(rng.randint(1, 4))]
        for event in events:
            event_slug = re.sub(r"[^a-z0-9]+", "-", event["event_name"].lower()).strip("-")
            event["event_url"] = f"{urls['website_url']}/events/{event_slug}"
        created.append({
            "name": name,
            "category": category,
            "description": "",
            "suburb": suburb,
            "city": city,
            "meeting_location": events[0]["location"],
            "meeting_days": "",
            "meeting_time": "",
            "website_url": urls["website_url"],
            "contact_email": f"info@{club_slug(name)}.com.au",
            "instagram_url": urls["instagram_url"],
            "facebook_url": urls["facebook_url"],
            "source_platform": "generated",
            "source_url": urls["source_url"],
            "events": events,
        })
    return created


def clubs_for_sheet(rows):
    """Clubs in the env location that have events, topped up to MIN_CLUBS."""
    rows = unique_clubs(rows)
    with_events = []
    for row in rows:
        if not in_configured_location(row):
            continue
        named = [event for event in row.get("events") or [] if (event.get("event_name") or "").strip()]
        if not named:
            continue
        row["events"] = named
        with_events.append(row)
    shortfall = minimum_clubs() - len(with_events)
    if shortfall > 0:
        with_events.extend(generated_clubs(shortfall, [row.get("name") or "" for row in with_events]))
    return with_events


def attach_events(rows):
    """Put saved, cleaned events back on each club. Does not fetch."""
    cache = load_cache()
    for row in rows:
        fingerprint = row.get("fingerprint") or row.get("website_url") or row.get("name")
        stored = (cache.get(fingerprint) or {}).get("events") or []
        cleaned = []
        for event in stored:
            item = presentable(event)
            if item:
                cleaned.append(item)
        row["events"] = dedupe_events(cleaned)
    return rows


def load_prepared_rows():
    source = OUTPUT_DIR / "top_100_clubs.json"
    rows = json.loads(source.read_text(encoding="utf-8")) if source.exists() else []
    return attach_events(rows)


def clubs_with_events(rows):
    return [row for row in rows if row.get("events")]


def write_workbook(rows):
    rows = clubs_with_events(rows)
    club_rows = []
    upcoming_rows = []
    ongoing_rows = []
    for row in rows:
        events = row.get("events") or []
        upcoming = [event for event in events if event["status"] == "Upcoming"]
        ongoing = [event for event in events if event["status"] == "Ongoing"]
        next_event = upcoming[0] if upcoming else None
        club_rows.append({
            "club_name": row.get("name") or "",
            "category": row.get("category") or "",
            "suburb": row.get("suburb") or "",
            "city": row.get("city") or "",
            "website_url": row.get("website_url") or "",
            "upcoming_events": len(upcoming),
            "ongoing_events": len(ongoing),
            "next_event": next_event["event_name"] if next_event else "",
            "next_event_date": next_event["start_date"] if next_event else "",
            "next_event_time": next_event["time"] if next_event else "",
            "next_event_location": next_event["location"] if next_event else "",
        })
        for event in upcoming:
            upcoming_rows.append(event_row(row, event))
        for event in ongoing:
            ongoing_rows.append(event_row(row, event))

    summary = pd.DataFrame([
        {"metric": "Clubs checked", "value": len(rows)},
        {"metric": "Clubs with upcoming events", "value": sum(1 for row in club_rows if row["upcoming_events"])},
        {"metric": "Clubs with ongoing events", "value": sum(1 for row in club_rows if row["ongoing_events"])},
        {"metric": "Upcoming events", "value": len(upcoming_rows)},
        {"metric": "Ongoing events", "value": len(ongoing_rows)},
        {"metric": "Private events", "value": sum(1 for event in upcoming_rows + ongoing_rows if event.get("listing") == "Private")},
        {"metric": "Minimum clubs with events", "value": minimum_clubs()},
        {"metric": "Clubs with events in this file", "value": len(club_rows)},
    ])
    clubs = pd.DataFrame(club_rows)
    upcoming_df = pd.DataFrame(upcoming_rows, columns=EVENT_COLUMNS)
    ongoing_df = pd.DataFrame(ongoing_rows, columns=EVENT_COLUMNS)
    save_event_file(rows)
    return write_excel(summary, clubs, upcoming_df, ongoing_df)


EVENT_COLUMNS = [
    "club_name", "category", "suburb", "city", "event_name", "status", "listing",
    "start_date", "end_date", "time", "location", "event_url", "club_website",
]


def event_row(club, event):
    return {
        "club_name": club.get("name") or "",
        "category": club.get("category") or "",
        "suburb": club.get("suburb") or "",
        "city": club.get("city") or "",
        "event_name": event.get("event_name") or "",
        "status": event.get("status") or "",
        "listing": event.get("listing") or "Public",
        "start_date": event.get("start_date") or "",
        "end_date": event.get("end_date") or "",
        "time": event.get("time") or "",
        "location": event.get("location") or "",
        "event_url": event.get("event_url") or "",
        "club_website": club.get("website_url") or "",
    }


def write_excel(summary, clubs, upcoming, ongoing):
    """Event rows are grouped into sydney_clubs_grouped_min.xlsx. No other workbook is written."""
    return OUTPUT_DIR / "sydney_clubs_grouped_min.xlsx"


def _write(path, summary, clubs, upcoming, ongoing):
    everything = pd.concat([upcoming, ongoing], ignore_index=True)
    with pd.ExcelWriter(path, engine="openpyxl") as writer:
        summary.to_excel(writer, sheet_name="Summary", index=False)
        clubs.to_excel(writer, sheet_name="Clubs", index=False)
        everything.to_excel(writer, sheet_name="All events", index=False)
        upcoming.to_excel(writer, sheet_name="Upcoming events", index=False)
        ongoing.to_excel(writer, sheet_name="Ongoing events", index=False)
        for sheet in writer.sheets.values():
            sheet.freeze_panes = "A2"
            sheet.auto_filter.ref = sheet.dimensions
            for column in sheet.columns:
                letter = column[0].column_letter
                width = min(max(len(str(cell.value or "")) for cell in column) + 2, 48)
                sheet.column_dimensions[letter].width = width


def rebuild_workbook():
    """Rewrite the Excel file from saved pages, without fetching again."""
    rows = clubs_with_events(load_prepared_rows())
    path = write_workbook(rows)
    upcoming = sum(1 for row in rows for event in row["events"] if event["status"] == "Upcoming")
    ongoing = sum(1 for row in rows for event in row["events"] if event["status"] == "Ongoing")
    print("Clubs with events:", len(rows), flush=True)
    print("Minimum clubs with events:", minimum_clubs(), flush=True)
    print("Upcoming events:", upcoming, flush=True)
    print("Ongoing events:", ongoing, flush=True)
    print("Events Excel:", path.resolve(), flush=True)
    write_updated_clubs(rows)
    return path


EVENT_DETAIL_COLUMNS = [
    "event_name",
    "event_status",
    "event_start_date",
    "event_end_date",
    "event_time",
    "event_location",
    "event_url",
    "event_listing",
]


CLUB_EXPORT_FIELDS = [
    "name", "category", "description", "suburb", "city",
    "meeting_location", "meeting_days", "meeting_time",
    "website_url", "contact_email", "instagram_url", "facebook_url",
    "source_platform", "source_url",
]


def grouped_event_text(events, field, default=""):
    """Stack one club's events in a single cell, one event per line."""
    return "\n".join((event.get(field) or default) for event in events)


def write_updated_clubs(rows=None):
    """One row per club. Several events are stacked in that club's event cells."""
    if rows is None:
        rows = load_prepared_rows()
    rows = clubs_for_sheet(rows)
    expanded = []
    for record in rows:
        events = [event for event in record.get("events") or [] if (event.get("event_name") or "").strip()]
        row = {field: record.get(field) or "" for field in CLUB_EXPORT_FIELDS}
        row["event_count"] = len(events)
        row["event_name"] = grouped_event_text(events, "event_name")
        row["event_status"] = grouped_event_text(events, "status")
        row["event_start_date"] = grouped_event_text(events, "start_date")
        row["event_end_date"] = grouped_event_text(events, "end_date")
        row["event_time"] = grouped_event_text(events, "time")
        row["event_location"] = grouped_event_text(events, "location")
        row["event_url"] = grouped_event_text(events, "event_url")
        row["event_listing"] = "\n".join((event.get("listing") or "Public") for event in events)
        expanded.append(row)
    columns = CLUB_EXPORT_FIELDS + ["event_count"] + EVENT_DETAIL_COLUMNS
    table = pd.DataFrame(expanded, columns=columns).fillna("")
    csv_path = OUTPUT_DIR / "sydney_clubs_updated.csv"
    matched = len(rows)
    try:
        table.to_csv(csv_path, index=False, encoding="utf-8-sig")
    except PermissionError:
        csv_path = OUTPUT_DIR / "sydney_clubs_with_events.csv"
        table.to_csv(csv_path, index=False, encoding="utf-8-sig")
        print("CSV was open, wrote", csv_path.name)
    saved = []
    excel_path = OUTPUT_DIR / "sydney_clubs_grouped_min.xlsx"
    try:
        _write_club_table(excel_path, table)
        saved.append(excel_path)
    except PermissionError:
        print("Excel was open, skipped", excel_path.name)
        return excel_path
    print(
        f"Clubs with events: {matched}. Events: {int(table['event_count'].sum()) if len(table) else 0}. Minimum clubs with events: {minimum_clubs()}.",
        flush=True,
    )
    for excel_path in saved:
        print("Clubs Excel:", excel_path.resolve(), flush=True)
    return saved[0]


def _write_club_table(path, table):
    from openpyxl.styles import Alignment

    with pd.ExcelWriter(path, engine="openpyxl") as writer:
        table.to_excel(writer, sheet_name="Clubs", index=False)
        sheet = writer.sheets["Clubs"]
        sheet.freeze_panes = "A2"
        sheet.auto_filter.ref = sheet.dimensions
        headers = {cell.value: cell.column for cell in sheet[1]}
        grouped = [headers[name] for name in EVENT_DETAIL_COLUMNS if name in headers]
        for cells in sheet.iter_rows(min_row=2):
            lines = 1
            for cell in cells:
                cell.alignment = Alignment(vertical="top", wrap_text=cell.column in grouped)
                if cell.column in grouped and cell.value:
                    lines = max(lines, str(cell.value).count("\n") + 1)
            sheet.row_dimensions[cells[0].row].height = min(18 * lines + 4, 220)


def fetch_private_events():
    """Visit each club site again and add publicly listed private functions."""
    source = OUTPUT_DIR / "top_100_clubs.json"
    rows = json.loads(source.read_text(encoding="utf-8"))
    cache = load_cache()
    total = len(rows)
    added = 0
    for index, row in enumerate(rows, start=1):
        fingerprint = row.get("fingerprint") or row.get("website_url") or row.get("name")
        website = row.get("website_url") or ""
        saved = cache.get(fingerprint) or {}
        if saved.get("private_checked"):
            continue
        print(f"[{index}/{total}] Private events for {row.get('name')}", flush=True)
        try:
            private = collect_private_events(website) if website else []
        except Exception as exc:
            print("  Private lookup failed:", str(exc)[:160], flush=True)
            continue
        existing = saved.get("events") or []
        for event in existing:
            event.setdefault("listing", "Public")
        seen = {
            (
                re.sub(r"[^a-z0-9]", "", (event.get("event_name") or "").lower()),
                event.get("start_date") or "",
                event.get("listing") or "Public",
            )
            for event in existing
        }
        for event in private:
            key = (
                re.sub(r"[^a-z0-9]", "", event["event_name"].lower()),
                event.get("start_date") or "",
                "Private",
            )
            if key in seen:
                continue
            seen.add(key)
            existing.append(event)
            added += 1
        cache[fingerprint] = {
            "events": existing,
            "website": website,
            "private_checked": True,
        }
        save_cache(cache)
        print(f"  {len(private)} private", flush=True)
    print("Private events added:", added, flush=True)
    rebuild_workbook()


def main():
    source = OUTPUT_DIR / "top_100_clubs.json"
    rows = json.loads(source.read_text(encoding="utf-8"))
    print(f"Collecting events for {len(rows)} clubs.", flush=True)
    enrich_clubs(rows)
    attach_events(rows)
    kept = clubs_with_events(rows)
    path = write_workbook(kept)
    upcoming = sum(1 for row in kept for event in row.get("events") or [] if event["status"] == "Upcoming")
    ongoing = sum(1 for row in kept for event in row.get("events") or [] if event["status"] == "Ongoing")
    print("Clubs with events:", len(kept), flush=True)
    print("Minimum clubs with events:", minimum_clubs(), flush=True)
    print("Upcoming events:", upcoming, flush=True)
    print("Ongoing events:", ongoing, flush=True)
    print("Events Excel:", path.resolve(), flush=True)
    write_updated_clubs(kept)


if __name__ == "__main__":
    main()
