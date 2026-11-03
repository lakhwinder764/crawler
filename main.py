import hashlib
import json
import os
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urldefrag, urljoin, urlparse

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

import pandas as pd
import requests
from bs4 import BeautifulSoup
from ddgs import DDGS
from dotenv import load_dotenv
from urllib.robotparser import RobotFileParser

load_dotenv()

MAX_CLUBS = int(os.getenv("MAX_CLUBS", "100"))
MIN_CLUBS = int(os.getenv("MIN_CLUBS", "100"))
REQUEST_DELAY = float(os.getenv("REQUEST_DELAY", "2"))
OUTPUT_DIR = Path("output")
OUTPUT_DIR.mkdir(exist_ok=True)

HEADERS = {
    "User-Agent": (
        "SydneyClubResearchBot/1.0 "
        "(public business directory research)"
    )
}

FOOTBALL_DIRECTORY = "https://footballnsw.com.au/clubs-directory/"

# Queries are Sydney-focused so the first dataset matches the handover.
SEARCH_QUERIES = [
    ("Sydney football club official website", "Sports"),
    ("Sydney cricket club official website", "Sports"),
    ("Sydney rugby club official website", "Sports"),
    ("Sydney netball club official website", "Sports"),
    ("Sydney tennis club official website", "Sports"),
    ("Sydney golf club official website", "Sports"),
    ("Sydney hockey club official website", "Sports"),
    ("Sydney basketball club official website", "Sports"),
    ("Sydney swimming club official website", "Sports"),
    ("Sydney AFL club official website", "Sports"),
    ("Sydney surf lifesaving club official website", "Sports"),
    ("Sydney running club official website", "Fitness"),
    ("Sydney cycling club official website", "Fitness"),
    ("Sydney triathlon club official website", "Fitness"),
    ("Sydney hiking club official website", "Fitness"),
    ("Sydney bushwalking club official website", "Fitness"),
    ("Sydney photography club official website", "Hobbies"),
    ("Sydney book club official website", "Hobbies"),
    ("Sydney chess club official website", "Hobbies"),
    ("Sydney art society official website", "Hobbies"),
    ("Sydney choir official website", "Hobbies"),
    ("Sydney RSL club official website", "Social"),
    ("Sydney leagues club official website", "Social"),
    ("Sydney community club official website", "Social"),
    ("Sydney Probus club official website", "Social"),
    ("Sydney Rotary club official website", "Social"),
    ("Sydney yacht club official website", "Lifestyle"),
    ("Sydney cultural association official website", "Lifestyle"),
    ("Sydney dance club official website", "Lifestyle"),
    ("Sydney business networking group official website", "Professional"),
    ("Sydney professional association official website", "Professional"),
    ("Sydney chamber of commerce official website", "Professional"),
    ("Sydney bowling club official website", "Social"),
    ("Bondi surf club official website", "Sports"),
    ("Manly surf club official website", "Sports"),
    ("Cronulla surf club official website", "Sports"),
    ("Sydney rugby league club official website", "Sports"),
    ("Randwick rugby club official website", "Sports"),
    ("Sydney little athletics club official website", "Fitness"),
    ("Sydney bushwalkers club official website", "Fitness"),
    ("Sydney bridge club official website", "Hobbies"),
    ("Sydney fishing club official website", "Hobbies"),
    ("Sydney music society official website", "Hobbies"),
    ("Sydney theatre society official website", "Lifestyle"),
    ("Sydney sailing club official website", "Lifestyle"),
    ("Parramatta RSL club official website", "Social"),
    ("North Sydney club official website", "Social"),
    ("Sydney business club official website", "Professional"),
    ("Sydney women in business association official website", "Professional"),
]

EXTRA_QUERIES = [
    ("Bronte surf club official website", "Sports"),
    ("Maroubra surf club official website", "Sports"),
    ("Clovelly surf club official website", "Sports"),
    ("Freshwater surf club official website", "Sports"),
    ("Dee Why surf club official website", "Sports"),
    ("Palm Beach surf club official website", "Sports"),
    ("Newport surf club official website", "Sports"),
    ("Coogee surf club official website", "Sports"),
    ("Elouera surf club official website", "Sports"),
    ("North Curl Curl surf club official website", "Sports"),
    ("Wanda surf club Cronulla official website", "Sports"),
    ("Easts rugby club Sydney official website", "Sports"),
    ("Gordon rugby club Sydney official website", "Sports"),
    ("Warringah rugby club Sydney official website", "Sports"),
    ("Sydney University Football Club official website", "Sports"),
    ("Concord golf club Sydney official website", "Sports"),
    ("Bonnie Doon golf club Sydney official website", "Sports"),
    ("Moore Park golf club Sydney official website", "Sports"),
    ("Petersham cricket club Sydney official website", "Sports"),
    ("Gordon cricket club Sydney official website", "Sports"),
    ("Hornsby RSL club official website", "Social"),
    ("Dee Why RSL club official website", "Social"),
    ("Blacktown RSL club official website", "Social"),
    ("Manly RSL club official website", "Social"),
    ("Cronulla RSL club official website", "Social"),
    ("Canterbury leagues club Sydney official website", "Social"),
    ("Mounties club Sydney official website", "Social"),
    ("Dooleys Lidcombe club official website", "Social"),
    ("South Curl Curl surf club official website", "Sports"),
    ("Queenscliff surf club Sydney official website", "Sports"),
    ("Avalon Beach surf club official website", "Sports"),
    ("North Steyne surf club Manly official website", "Sports"),
    ("Collaroy surf club official website", "Sports"),
    ("Long Reef surf club Sydney official website", "Sports"),
    ("Bilgola surf club official website", "Sports"),
    ("Whale Beach surf club official website", "Sports"),
    ("Mona Vale surf club official website", "Sports"),
    ("North Narrabeen surf club official website", "Sports"),
    ("Tamarama surf club official website", "Sports"),
    ("Bondi Icebergs club official website", "Social"),
]

FILL_QUERIES = [
    ("Coogee surf life saving club official website", "Sports"),
    ("Tamarama surf life saving club official website", "Sports"),
    ("Garie surf life saving club official website", "Sports"),
    ("South Curl Curl surf life saving club official website", "Sports"),
    ("North Steyne surf life saving club Manly official website", "Sports"),
    ("Queenscliff surf life saving club Sydney official website", "Sports"),
    ("Collaroy surf life saving club official website", "Sports"),
    ("Long Reef surf life saving club official website", "Sports"),
    ("Bilgola surf life saving club official website", "Sports"),
    ("Mona Vale surf life saving club official website", "Sports"),
    ("Bondi Surf Bathers Life Saving Club official website", "Sports"),
    ("North Curl Curl surf life saving club official website", "Sports"),
]

GROWTH_QUERIES = [
    ("Sydney rowing club official website", "Sports"),
    ("Sydney baseball club official website", "Sports"),
    ("Sydney softball club official website", "Sports"),
    ("Sydney netball association club official website", "Sports"),
    ("Sydney hockey association club official website", "Sports"),
    ("Sydney badminton club official website", "Sports"),
    ("Sydney squash club official website", "Sports"),
    ("Sydney table tennis club official website", "Sports"),
    ("Sydney volleyball club official website", "Sports"),
    ("Sydney athletics club official website", "Fitness"),
    ("Sydney dragon boat club official website", "Sports"),
    ("Sydney kayak club official website", "Lifestyle"),
    ("Sydney outrigger canoe club official website", "Sports"),
    ("Sydney fencing club official website", "Sports"),
    ("Sydney judo club official website", "Fitness"),
    ("Sydney karate club official website", "Fitness"),
    ("Sydney climbing club official website", "Fitness"),
    ("Sydney orienteering club official website", "Fitness"),
    ("Sydney bushwalking club official website", "Fitness"),
    ("Sydney garden club official website", "Hobbies"),
    ("Sydney camera club official website", "Hobbies"),
    ("Sydney film society official website", "Hobbies"),
    ("Sydney historical society official website", "Hobbies"),
    ("Sydney bridge club official website", "Hobbies"),
    ("Sydney chess club official website", "Hobbies"),
    ("Sydney men's shed official website", "Social"),
    ("Sydney Lions club official website", "Social"),
    ("Sydney Rotary club official website", "Social"),
    ("Sydney Probus club official website", "Social"),
    ("Parramatta football club official website", "Sports"),
    ("Penrith football club official website", "Sports"),
    ("Liverpool football club Sydney official website", "Sports"),
    ("Campbelltown football club official website", "Sports"),
    ("Sutherland football club official website", "Sports"),
    ("Hornsby football club official website", "Sports"),
    ("Ryde football club official website", "Sports"),
    ("Bankstown football club official website", "Sports"),
    ("Auburn football club official website", "Sports"),
    ("Fairfield football club official website", "Sports"),
    ("Canterbury football club official website", "Sports"),
    ("Eastern Suburbs cricket club Sydney official website", "Sports"),
    ("Western Suburbs cricket club Sydney official website", "Sports"),
    ("Northern Suburbs rugby club Sydney official website", "Sports"),
    ("Southern Districts rugby club Sydney official website", "Sports"),
    ("Sydney University rugby club official website", "Sports"),
    ("Macquarie University sport club official website", "Sports"),
    ("UNSW sports club official website", "Sports"),
    ("UTS sport club Sydney official website", "Sports"),
    ("Sydney bowls club official website", "Social"),
    ("Sydney RSL sub branch club official website", "Social"),
    ("Chatswood RSL club official website", "Social"),
    ("Epping RSL club official website", "Social"),
    ("Castle Hill RSL club official website", "Social"),
    ("Rooty Hill RSL club official website", "Social"),
    ("Revesby Workers club official website", "Social"),
    ("Club Marconi Sydney official website", "Social"),
    ("Western Suburbs leagues club Sydney official website", "Social"),
    ("North Sydney leagues club official website", "Social"),
    ("Sydney dance society official website", "Lifestyle"),
    ("Sydney bushwalkers club official website", "Fitness"),
]

CATEGORIES = (
    "Fitness", "Social", "Sports", "Hobbies", "Lifestyle", "Professional",
)

CATEGORY_KEYWORDS = {
    "Fitness": (
        "running", "runners", "cycling", "cycle", "triathlon", "yoga",
        "pilates", "crossfit", "fitness", "hiking", "bushwalk", "parkrun",
        "athletic", "athletics",
    ),
    "Sports": (
        "football", "soccer", "cricket", "rugby", "netball", "tennis",
        "golf", "hockey", "swimming", "swim", "surf", "lifesaving", "slsc",
        "afl", "basketball", "baseball", "softball", "rowing", "fc",
    ),
    "Hobbies": (
        "photography", "photo club", "book club", "chess", "art society",
        "art club", "choir", "orchestra", "garden club", "craft", "stamp",
        "radio club", "film society",
    ),
    "Lifestyle": (
        "yacht", "sailing", "wine", "cultural", "dance", "theatre",
        "theater", "lifestyle",
    ),
    "Professional": (
        "networking", "professional", "business association", "chamber",
        "institute", "women in business", "industry association",
    ),
    "Social": (
        "rsl", "leagues club", "social club", "community club", "rotary",
        "lions club", "probus", "mens shed", "men's shed", "bowling",
    ),
}

EXCLUDED_DOMAINS = {
    "facebook.com", "instagram.com", "linkedin.com", "youtube.com",
    "tiktok.com", "x.com", "twitter.com", "google.com", "wikipedia.org",
    "reddit.com", "pinterest.com", "yelp.com", "tripadvisor.com",
    "eventbrite.com", "meetup.com", "cloudinary.com", "claimsgateway.com",
    "gowgates.com.au", "gmail.com", "outlook.com", "live.com",
    "office.com", "microsoft.com", "apple.com", "amazon.com",
    "smh.com.au", "abc.net.au", "theguardian.com", "news.com.au",
    "bbc.com", "bbc.co.uk", "dailytelegraph.com.au", "9news.com.au",
    "7news.com.au", "sbs.com.au", "espn.com", "foxsports.com.au",
    "timeout.com", "broadsheet.com.au", "yellowpages.com.au",
    "truelocal.com.au", "whitepages.com.au", "localsearch.com.au",
    "hotfrog.com.au", "playfootball.com.au", "nplnsw.com.au",
    "findglocal.com", "afl.com.au", "bing.com", "nrl.com",
    "writingtipsoasis.com", "clubsandpubsnearme.com.au",
    "myabf.com.au", "esplanadeevents.com.au", "devave.website",
    "sydneycommunitycollege.edu.au", "rslsouthqueensland.org",
    "manlylotarsl.com.au", "palmspringssurfclub.com",
    "weeblyte.com", "mopstar.com.au", "clovellynews.com.au",
    "cityofsydneydirect.com", "rslnsw.org.au",
    "australia247.info", "sutherlandshireaustralia.com.au",
    "surflifesaving.net.au", "sportkin.com", "whereis.com",
    "eventfinda.com.au", "teamapp.com",
    "footballaustralia.com.au", "sportnsw.com.au", "beachsafe.org.au",
    "surflifesaving.com.au", "beachsafetyhub.org.au",
    "playsport.com", "bowlsclubsdirectory.com", "judoshop.com",
    "worldplaces.me", "onlysydney.com.au",
}

DIRECTORY_HOSTS = {
    "ra.co", "footballnsw.com.au", "sls.sydney", "sydney.com",
    "clubsnsw.com.au", "visitnsw.com", "nsw.gov.au",
}

FREE_EMAIL_DOMAINS = {
    "gmail.com", "yahoo.com", "yahoo.com.au", "hotmail.com",
    "outlook.com", "live.com", "bigpond.com", "bigpond.net.au",
    "y7mail.com", "icloud.com", "me.com",
}

JUNK_NAMES = {
    "visit website", "click here", "read more", "learn more", "home",
    "contact", "contact us", "login", "log in", "official website",
    "website", "insurance", "injury insurance", "injury claim form",
    "top-up cover", "serious injury report", "play football",
    "find a club", "download", "more info", "book now",
}

CLUB_TOKEN = re.compile(
    r"\b(club|clubs|fc|afc|sc|slsc|rsl|association|society|community|"
    r"league|leagues|golf|bowling|cricket|rugby|netball|tennis|hockey|"
    r"swimming|swim|surf|lifesaving|cycling|cycle|runners|running|"
    r"yoga|photography|chess|choir|orchestra|rotary|lions|yacht|"
    r"sailing|basketball|afl|soccer|football|hiking|bushwalking|"
    r"triathlon|athletic|athletics|probus|wanderers)\b",
    re.I,
)

REJECT_NAME = re.compile(
    r"\b(insurance|claim|coverage|broker|wikipedia|directory|jobs|"
    r"nightclub|login|signin|download)\b",
    re.I,
)

OTHER_CITY = re.compile(
    r"\b(melbourne|brisbane|perth|adelaide|hobart|darwin|canberra|"
    r"newcastle|wollongong|geelong|gold coast)\b",
    re.I,
)

EMAIL_RE = re.compile(
    r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b",
    re.I,
)

SYDNEY_SUBURBS = (
    "north sydney", "circular quay", "circular quay west", "st marys",
    "st ives", "castle hill", "baulkham hills", "rouse hill", "quakers hill",
    "glenmore park", "mount druitt", "rooty hill", "seven hills",
    "wentworthville", "olympic park", "eastwood", "macquarie park",
    "north ryde", "west ryde", "lane cove", "crows nest", "neutral bay",
    "cremorne", "double bay", "bellevue hill", "rose bay", "watsons bay",
    "bondi beach", "bondi junction", "north bondi", "tamarama", "bronte",
    "coogee", "maroubra", "little bay", "la perouse",
    "caringbah", "cronulla", "woolooware", "gymea", "sutherland",
    "engadine", "menai", "jannali", "miranda", "sylvania", "oatley",
    "hurstville", "kogarah", "rockdale", "bexley", "kingsgrove",
    "earlwood", "canterbury", "campsie", "lakemba", "punchbowl",
    "bankstown", "revesby", "padstow", "riverwood", "narwee",
    "liverpool", "casula", "moorebank", "chipping norton", "warwick farm",
    "cabramatta", "fairfield", "wetherill park", "smithfield", "guildford",
    "granville", "auburn", "lidcombe", "strathfield", "burwood",
    "ashfield", "summer hill", "petersham", "stanmore", "newtown",
    "enmore", "erskineville", "marrickville", "dulwich hill", "leichhardt",
    "annandale", "glebe", "ultimo", "pyrmont", "balmain", "rozelle",
    "drummoyne", "five dock", "abbotsford", "chatswood", "willoughby",
    "artarmon", "hornsby", "wahroonga", "turramurra", "pymble", "ryde",
    "gladesville", "hunters hill", "mosman", "manly", "dee why",
    "brookvale", "freshwater", "collaroy", "narrabeen", "mona vale",
    "newport", "avalon", "palm beach", "frenchs forest", "forestville",
    "parramatta", "harris park", "westmead", "merrylands", "greystanes",
    "toongabbie", "blacktown", "doonside", "penrith", "kingswood",
    "werrington", "emu plains", "campbelltown", "camden", "narellan",
    "leumeah", "minto", "ingleburn", "oran park", "leppington",
    "windsor", "richmond", "kellyville", "bella vista", "dural",
    "epping", "carlingford", "dundas", "ermington", "melrose park",
    "rhodes", "concord", "cabarita", "breakfast point", "mortlake",
    "randwick", "kensington", "kingsford", "pagewood", "mascot",
    "botany", "eastlakes", "rosebery", "zetland", "waterloo", "redfern",
    "alexandria", "surry hills", "darlinghurst", "potts point",
    "woolloomooloo", "paddington", "woollahra", "bondi", "vaucluse",
    "dover heights", "queens park", "waverley", "clovelly",
    "malabar", "matraville", "hillsdale", "eastgardens",
    "allawah", "carlton", "beverly hills", "mortdale", "penshurst",
    "peakhurst", "lugarno", "illawong", "alfords point", "bangor",
    "kirrawee", "como", "bonnet bay", "yowie bay", "gymea bay",
    "grays point", "loftus", "yarrawarrah", "barden ridge", "kirribilli",
    "milsons point", "lavender bay", "waverton", "wollstonecraft",
    "naremburn", "castlecrag", "northbridge", "cammeray", "cremorne point",
    "seaforth", "balgowlah", "fairlight", "curl curl", "narraweena",
    "warriewood", "elanora heights", "bilgola", "whale beach",
    "terry hills", "belrose", "davidson", "st ives chase", "asquith",
    "waitara", "normanhurst", "thornleigh", "pennant hills", "cheltenham",
    "beecroft", "cherrybrook", "west pennant hills", "castle cove",
    "middle cove", "longueville", "woolwich", "greenwich", "linley point",
    "huntleys point", "gladesville", "putney", "meadowbank", "denistone",
    "marsfield", "north rocks", "winston hills", "old toongabbie",
    "pendle hill", "girraween", "prospect", "greystanes", "yennora",
    "villawood", "chester hill", "sefton", "regents park", "birrong",
    "potts hill", "chullora", "greenacre", "mount lewis", "roselands",
    "narwee", "beverly hills", "kingsgrove", "clemton park", "earlwood",
    "hurlstone park", "canterbury", "ashbury", "croydon", "croydon park",
    "enfield", "strathfield south", "homebush", "homebush west",
    "flemington", "sydney olympic park", "wentworth point", "newington",
    "silverwater", "granville", "harris park", "holroyd", "merrylands west",
    "guildford west", "smithfield", "bossley park", "prairiewood",
    "abbotsbury", "edensor park", "bonnyrigg", "green valley", "heckenberg",
    "busby", "miller", "sadleir", "cartwright", "ashcroft", "liverpool",
    "casula", "lurnea", "prestons", "horningsea park", "hoxton park",
    "west hoxton", "austral", "kemps creek", "badgerys creek", "bringelly",
    "cobbitty", "harrington park", "narellan vale", "mount annan",
    "spring farm", "elderslie", "camden south", "grasmere", "ellis lane",
    "bradbury", "rosemeadow", "st helens park", "ambarvale",
    "airds", "ruse", "leumeah", "woodbine", "eagle vale", "eschol park",
    "claymore", "blairmount", "kearns", "raby", "varroville", "denham court",
    "ingleburn", "minto", "macquarie fields", "glenfield",
    "casula", "hammondville", "moorebank", "wattle grove", "holsworthy",
    "menai", "bangor", "alfords point", "illawong", "barden ridge",
    "lucas heights", "engadine", "heathcote", "waterfall", "woronora",
    "bonnet bay", "como", "oatley", "mortdale", "penshurst", "hurstville",
    "south hurstville", "blakehurst", "carss park", "connells point",
    "kyle bay", "kogarah bay", "sans souci", "ramsgate", "brighton-le-sands",
    "monterey", "kyeemagh", "arncliffe", "turrella", "bardwell park",
    "bardwell valley", "bexley north", "kingsgrove", "beverly hills",
    "narwee", "riverwood", "peakhurst", "peakhurst heights", "lugarno",
    "oatley", "kangaroo point", "sylvania waters", "taren point",
    "caringbah south", "woolooware", "cronulla", "kurnell",     "bundeena",
    "grays point", "gymea bay", "lilli pilli",
    "port hacking", "burraneer", "caringbah",
    "miranda", "sylvania", "kirrawee", "jannali", "como", "bonnet bay",
)

SUBURBS_SORTED = tuple(sorted(set(SYDNEY_SUBURBS), key=len, reverse=True))

FIELDS = [
    "name", "description", "suburb", "city", "category", "raw_categories",
    "website_url", "contact_email", "instagram_url", "image_url",
    "meeting_location", "meeting_days", "meeting_time",
    "source_url", "source_platform", "source_type",
    "member_count", "fingerprint", "created_at",
]

session = requests.Session()
session.headers.update(HEADERS)
robots_cache = {}
CREATED_AT = datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def normalize_url(url):
    """Normalize a URL and remove fragments."""
    if not url:
        return ""

    url = url.strip()
    if url.startswith("//"):
        url = "https:" + url
    elif url.startswith(("mailto:", "tel:", "javascript:")):
        return ""
    elif not url.startswith(("http://", "https://")):
        url = "https://" + url

    url = urldefrag(url)[0].rstrip("/")
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https") or not parsed.netloc:
        return ""
    return url


def domain_of(url):
    host = urlparse(url).netloc.lower().split(":")[0]
    if host.startswith("www."):
        host = host[4:]
    return host


def host_matches(host, domains):
    return any(host == domain or host.endswith("." + domain) for domain in domains)


def clean_name(name):
    name = re.sub(r"\s+", " ", name or "").strip()
    name = name.strip(" -|•")
    name = re.sub(
        r"\b(official website|official site|homepage|home page)\b",
        "",
        name,
        flags=re.I,
    )
    return re.sub(r"\s+", " ", name).strip(" -|•")


def name_key(name):
    return re.sub(r"[^a-z0-9]", "", (name or "").lower())


def is_junk_name(name):
    lowered = re.sub(r"\s+", " ", (name or "").strip().lower())
    if len(lowered) < 3 or lowered in JUNK_NAMES:
        return True
    if EMAIL_RE.fullmatch(lowered):
        return True
    if re.fullmatch(r"[\d\s()+.-]{6,}", lowered):
        return True
    if REJECT_NAME.search(lowered):
        return True
    return False


NON_SYDNEY_NAME = re.compile(
    r"\b(wollongong|newcastle|central coast|canberra|melbourne|brisbane|"
    r"perth|adelaide|hobart|darwin|geelong|gold coast|gosford|"
    r"queensland|brisbane|lota|palm springs)\b",
    re.I,
)
ARTICLE_NAME = re.compile(
    r"\b(best|top \d+|\d+ top|to join|guide to|things to do|how to|weekly|"
    r"schedule|calendar|fixtures|running the streets|list of|directory of|"
    r"contact details|updates|updated|profile|menu|archives|room)\b",
    re.I,
)
COMMERCIAL_NAME = re.compile(
    r"\b(store|shop|hire|for sale|tickets)\b",
    re.I,
)
GENERIC_NAME = re.compile(
    r"^(the club|surf club|clubs?|sailing club|chess club|club contacts|"
    r"club finder|fan club|afl|football|hockey|netball nsw|rsl nsw|"
    r"tennis nsw|nsw leagues club)$",
    re.I,
)
ORG_NAME = re.compile(
    r"\b(club|clubs|fc|afc|sc|slsc|rsl|association|society|squadron|"
    r"rotary|probus|choir|group)\b",
    re.I,
)
HOST_PLATFORMS = {
    "wildapricot.org", "blogspot.com", "wordpress.com", "wixsite.com",
    "square.site", "weebly.com",
}


def acceptable_name(name, source_type):
    """Keep organisation names and drop articles, shops, and directories."""
    if not name or is_junk_name(name):
        return False
    if NON_SYDNEY_NAME.search(name) or ARTICLE_NAME.search(name):
        return False
    if COMMERCIAL_NAME.search(name) or GENERIC_NAME.search(name.strip()):
        return False
    if len(name.split()) > 8 or name.endswith(":"):
        return False
    if re.match(r"^(home of|welcome to|official |join the)\b", name, re.I):
        return False
    if re.search(r"\b(policy|listed|clubs in|near me)\b", name, re.I):
        return False
    if source_type == "directory":
        return True
    return bool(ORG_NAME.search(name))


def pick_club_name(raw):
    raw = clean_name(raw)
    parts = [
        clean_name(part)
        for part in re.split(r"\s+[\|\-–—:]\s+", raw)
        if clean_name(part)
    ]
    for part in parts:
        if CLUB_TOKEN.search(part) and not is_junk_name(part):
            return part
    for part in parts:
        if not is_junk_name(part):
            return part
    return ""


def is_excluded(url):
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https"):
        return True
    host = domain_of(url)
    if host.endswith((".uk", ".nz", ".us", ".ca", ".za")):
        return True
    if not host or host_matches(host, EXCLUDED_DOMAINS):
        return True
    if host_matches(host, DIRECTORY_HOSTS):
        return True
    path = parsed.path.lower()
    if path.endswith((
        ".pdf", ".jpg", ".jpeg", ".png", ".webp", ".gif",
        ".zip", ".doc", ".docx",
    )):
        return True
    return False


def fetch(url):
    """Fetch a page politely; return None on errors."""
    try:
        response = session.get(url, timeout=15, allow_redirects=True)
        if response.status_code >= 400:
            print("HTTP", response.status_code, url)
            return None

        content_type = response.headers.get("Content-Type", "")
        if "text/html" not in content_type.lower():
            return None

        return response.url, response.text
    except requests.RequestException as exc:
        print("Fetch failed:", url, str(exc)[:120])
        return None


def allowed_by_robots(url):
    """Check robots.txt before crawling a website."""
    parsed = urlparse(url)
    origin = f"{parsed.scheme}://{parsed.netloc}"

    if origin not in robots_cache:
        robots_url = urljoin(origin, "/robots.txt")
        parser = RobotFileParser()
        parser.set_url(robots_url)

        try:
            response = session.get(robots_url, timeout=10)
            if response.status_code == 200:
                parser.parse(response.text.splitlines())
                robots_cache[origin] = parser
            elif response.status_code in (404, 410):
                robots_cache[origin] = None
            else:
                robots_cache[origin] = "unknown"
        except requests.RequestException:
            robots_cache[origin] = "unknown"

    parser = robots_cache[origin]
    if parser == "unknown":
        return False
    if parser is None:
        return True
    return parser.can_fetch(HEADERS["User-Agent"], url)


def valid_emails(values):
    cleaned = []
    for email in values:
        email = email.strip().strip(".").lower()
        if not EMAIL_RE.fullmatch(email):
            continue
        if email.endswith((".png", ".jpg", ".jpeg", ".webp", ".gif")):
            continue
        if email.endswith((
            "example.com", "sentry.io", "wixpress.com", "schema.org",
        )):
            continue
        if email.split("@", 1)[0] in {"noreply", "no-reply", "donotreply"}:
            continue
        cleaned.append(email)
    return sorted(set(cleaned))


def choose_email(emails, website):
    emails = valid_emails(emails)
    if not emails:
        return ""
    site_domain = domain_of(website)
    for email in emails:
        host = email.split("@", 1)[1]
        if site_domain and (host == site_domain or host.endswith("." + site_domain)):
            return email
    for email in emails:
        if email.split("@", 1)[1] not in FREE_EMAIL_DOMAINS:
            return email
    return emails[0]


def find_suburb(*texts):
    blob = " ".join(text or "" for text in texts).lower()
    for suburb in SUBURBS_SORTED:
        if re.search(rf"(?<![a-z]){re.escape(suburb)}(?![a-z])", blob):
            return " ".join(part.capitalize() for part in suburb.split())
    return ""


def sydney_related(*texts):
    blob = " ".join(text or "" for text in texts)
    if find_suburb(blob):
        return True
    return bool(re.search(r"\bsydney\b", blob, re.I))


def classify(name, description, raw_categories, hint):
    blob_name = (name or "").lower()
    blob_raw = " ".join(raw_categories).lower()
    blob_desc = (description or "").lower()
    scores = {category: 0 for category in CATEGORIES}
    for category, keywords in CATEGORY_KEYWORDS.items():
        for keyword in keywords:
            if keyword in blob_name:
                scores[category] += 3
            if keyword in blob_raw:
                scores[category] += 2
            if keyword in blob_desc:
                scores[category] += 1
    best = max(scores, key=scores.get)
    if scores[best] == 0:
        return hint if hint in CATEGORIES else "Social"
    return best


def extract_instagram(soup, page_url):
    for anchor in soup.find_all("a", href=True):
        href = urljoin(page_url, anchor["href"])
        host = domain_of(href)
        if host != "instagram.com":
            continue
        parts = [part for part in urlparse(href).path.split("/") if part]
        if not parts:
            continue
        handle = parts[0].lower()
        if handle in {
            "p", "reel", "reels", "explore", "stories", "share",
            "accounts", "about", "developer",
        }:
            continue
        if not re.fullmatch(r"[a-z0-9._]+", handle):
            continue
        return f"https://www.instagram.com/{handle}/"
    return ""


def extract_image(soup, page_url):
    tag = soup.find("meta", property="og:image")
    if tag is None:
        tag = soup.find("meta", attrs={"name": "twitter:image"})
    if tag is None:
        return ""
    image = normalize_url(urljoin(page_url, tag.get("content", "")))
    if not image or is_excluded(image):
        host = domain_of(image) if image else ""
        if not image or not host:
            return ""
    return image


def extract_meeting(text):
    window = text[:12000]
    day_match = re.search(
        r"\b(?:every|meets|meeting|training|train)\b.{0,50}\b"
        r"(monday|tuesday|wednesday|thursday|friday|saturday|sunday)s?\b",
        window,
        re.I,
    )
    if not day_match:
        return "", ""
    day = day_match.group(1).capitalize()
    snippet = window[max(0, day_match.start() - 20):day_match.end() + 40]
    time_match = re.search(
        r"\b(\d{1,2}(?::\d{2})?\s*(?:am|pm))\b",
        snippet,
        re.I,
    )
    meeting_time = re.sub(r"\s+", " ", time_match.group(1)).upper() if time_match else ""
    meeting_time = meeting_time.replace("AM", " AM").replace("PM", " PM")
    meeting_time = re.sub(r"\s+", " ", meeting_time).strip()
    return day, meeting_time


def extract_member_count(text):
    match = re.search(r"\b(\d{2,6})\s+members\b", text[:12000], re.I)
    if not match:
        return None
    return int(match.group(1))


def fingerprint_for(name, website):
    raw = f"{name_key(name)}|{domain_of(website)}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]


def empty_record():
    return {
        "name": "",
        "description": "",
        "suburb": "",
        "city": "",
        "category": "",
        "raw_categories": [],
        "website_url": "",
        "contact_email": "",
        "instagram_url": "",
        "image_url": "",
        "meeting_location": "",
        "meeting_days": "",
        "meeting_time": "",
        "source_url": "",
        "source_platform": "",
        "source_type": "",
        "member_count": None,
        "fingerprint": "",
        "created_at": CREATED_AT,
    }


def add_candidate(store, name, url, source_url, platform, source_type, category, raw_categories=None, email=""):
    name = pick_club_name(name)
    url = normalize_url(url)
    if not name or not acceptable_name(name, source_type) or not url or is_excluded(url):
        return
    if listing_url(url) or re.search(r"/(shop|store)(/|$)", urlparse(url).path, re.I):
        return
    if domain_of(url).startswith(("shop.", "store.")):
        return

    domain = domain_of(url)
    key = (name_key(name), domain)
    if not key[0] or not domain:
        return

    email = choose_email([email] if email else [], url)
    raw_categories = [item for item in (raw_categories or []) if item]

    existing = store.get(key)
    if existing:
        if email and not existing["contact_email"]:
            existing["contact_email"] = email
        for item in raw_categories:
            if item not in existing["raw_categories"]:
                existing["raw_categories"].append(item)
        return

    store[key] = {
        "name": name,
        "website": url,
        "source_url": source_url,
        "source_platform": platform,
        "source_type": source_type,
        "category_hint": category,
        "raw_categories": raw_categories,
        "contact_email": email,
    }


def discover_football(store):
    print("Discovering clubs from Football NSW directory...")
    result = fetch(FOOTBALL_DIRECTORY)
    if not result:
        return

    final_url, html = result
    soup = BeautifulSoup(html, "html.parser")
    cards = soup.select(".uabb-blog-post-inner-wrap")
    print("Directory cards:", len(cards))

    for card in cards:
        heading = card.find(["h2", "h3", "h4"])
        if heading is None:
            continue
        name = heading.get_text(" ", strip=True)
        website = ""
        for anchor in card.find_all("a", href=True):
            label = anchor.get_text(" ", strip=True).lower()
            if label == "visit website":
                website = urljoin(final_url, anchor["href"])
                break
        if not website:
            continue

        parts = [part.strip() for part in card.get_text(" | ", strip=True).split("|")]
        raw = []
        if len(parts) >= 2 and parts[1] and parts[1].lower() != name.lower():
            raw.append(parts[1])

        emails = valid_emails(EMAIL_RE.findall(card.get_text(" ", strip=True)))
        add_candidate(
            store,
            name,
            website,
            FOOTBALL_DIRECTORY,
            "Football NSW",
            "directory",
            "Sports",
            raw,
            emails[0] if emails else "",
        )
    time.sleep(REQUEST_DELAY)


def discover_from_search(store, queries):
    print("Discovering clubs from web search...")
    with DDGS() as search:
        for query, category in queries:
            print("Search:", query)
            try:
                results = search.text(query, region="au-en", max_results=15)
                for item in results:
                    title = item.get("title", "")
                    url = item.get("href") or item.get("url") or ""
                    if not url:
                        continue
                    add_candidate(
                        store,
                        title,
                        url,
                        url,
                        "DuckDuckGo",
                        "search",
                        category,
                        [category],
                    )
            except Exception as exc:
                print("Search failed:", str(exc)[:160])
            time.sleep(REQUEST_DELAY)


def registrable_domain(host):
    parts = host.split(".")
    if len(parts) >= 3 and parts[-1] == "au" and parts[-2] in {
        "com", "net", "org", "gov", "edu", "asn", "id",
    }:
        return ".".join(parts[-3:])
    if len(parts) >= 2:
        return ".".join(parts[-2:])
    return host


def site_key(url):
    host = domain_of(url)
    for platform in HOST_PLATFORMS:
        if host == platform or host.endswith("." + platform):
            path = urlparse(url).path.rstrip("/").lower()
            return platform + path
    return registrable_domain(host)


def name_signature(name):
    stop = {
        "the", "of", "inc", "incorporated", "ltd", "and", "official",
        "website", "home", "welcome", "to", "a", "club", "clubs",
    }
    return frozenset(
        token for token in re.findall(r"[a-z0-9]+", name.lower())
        if token not in stop and not token.isdigit()
    )


def close_names(left, right):
    weak = {
        "calendar", "updates", "news", "profile", "about", "adult",
        "chapter", "events", "latest", "nbl", "whats", "on",
    }
    if not left or not right:
        return False
    if left == right:
        return True
    if len(left) >= 2 and left < right and right - left <= weak:
        return True
    if len(right) >= 2 and right < left and left - right <= weak:
        return True
    return False


def same_organisation(existing, name, website):
    left = name_signature(existing["name"])
    right = name_signature(name)
    if close_names(left, right):
        return True
    if site_key(existing["website_url"]) != site_key(website):
        return False
    if not left or not right or left <= right or right <= left:
        return True
    path_a = urlparse(existing["website_url"]).path.strip("/")
    path_b = urlparse(website).path.strip("/")
    return not (path_a and path_b and path_a != path_b)


def extract_details(candidate):
    url = candidate["website"]
    if not allowed_by_robots(url):
        print("Skipped by robots/access policy:", url)
        return None, "robots"

    result = fetch(url)
    if not result:
        return None, "fetch failed"

    final_url, html = result
    if is_excluded(final_url):
        return None, "excluded redirect"

    soup = BeautifulSoup(html, "html.parser")
    title = soup.title.get_text(" ", strip=True) if soup.title else ""
    if re.search(r"\b(sign in|log in|login|gmail|outlook)\b", title, re.I):
        return None, "login page"

    description_tag = soup.find(
        "meta", attrs={"name": re.compile(r"^description$", re.I)}
    )
    description = ""
    if description_tag and description_tag.get("content"):
        description = clean_name(description_tag["content"])[:500]

    text = soup.get_text(" ", strip=True)
    if len(text) < 80:
        return None, "thin page"

    name = candidate["name"]
    if not acceptable_name(name, candidate["source_type"]):
        return None, "not a club"
    if NON_SYDNEY_NAME.search(title):
        return None, "outside Sydney"

    sample = " ".join((name, title, description, text[:1500]))
    if not sydney_related(name, title, description, text[:1500]):
        return None, "outside Sydney"

    page_emails = EMAIL_RE.findall(text)
    if candidate["contact_email"]:
        page_emails.append(candidate["contact_email"])
    email = choose_email(page_emails, final_url)
    instagram = extract_instagram(soup, final_url)
    if domain_of(final_url) == "instagram.com":
        return None, "instagram is not a website"

    suburb = find_suburb(name) or find_suburb(title, description) or find_suburb(text[:1500])
    city = "Sydney" if suburb or re.search(r"\bsydney\b", sample, re.I) else ""

    raw_categories = list(candidate["raw_categories"])
    category = classify(name, description, raw_categories, candidate["category_hint"])
    if category not in raw_categories:
        raw_categories.append(category)

    meeting_days, meeting_time = extract_meeting(text)
    record = empty_record()
    record.update({
        "name": name,
        "description": description,
        "suburb": suburb,
        "city": city or "Sydney",
        "category": category,
        "raw_categories": raw_categories,
        "website_url": normalize_url(final_url),
        "contact_email": email,
        "instagram_url": instagram,
        "image_url": extract_image(soup, final_url),
        "meeting_days": meeting_days,
        "meeting_time": meeting_time,
        "source_url": candidate["source_url"],
        "source_platform": candidate["source_platform"],
        "source_type": candidate["source_type"],
        "member_count": extract_member_count(text),
        "fingerprint": fingerprint_for(name, final_url),
    })
    return record, ""


def order_candidates(candidates):
    """Round-robin categories so the top 100 is not only one sport."""
    buckets = {category: [] for category in CATEGORIES}
    for candidate in candidates:
        hint = candidate["category_hint"]
        if hint not in buckets:
            hint = "Social"
        buckets[hint].append(candidate)

    ordered = []
    while any(buckets.values()):
        for category in CATEGORIES:
            if buckets[category]:
                ordered.append(buckets[category].pop(0))
    return ordered


def write_tables(df, csv_path, excel_path):
    """Write CSV and Excel, falling back if a previous file is still open."""
    try:
        df.to_csv(csv_path, index=False, encoding="utf-8-sig")
    except PermissionError:
        csv_path = OUTPUT_DIR / "sydney_clubs_updated.csv"
        df.to_csv(csv_path, index=False, encoding="utf-8-sig")
        print("CSV was open, wrote", csv_path.name)

    return csv_path, OUTPUT_DIR / "sydney_clubs_grouped_min.xlsx"


def listing_url(url):
    path = urlparse(url).path.lower()
    return bool(re.search(
        r"/(events|news|calendar|whatson|whats-on|congress|tag|category)/",
        path,
    ))


def save_clubs(rows):
    path = OUTPUT_DIR / "top_100_clubs.json"
    path.write_text(
        json.dumps(rows, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    return path


def load_existing():
    path = OUTPUT_DIR / "top_100_clubs.json"
    if not path.exists():
        return []

    loaded = json.loads(path.read_text(encoding="utf-8"))
    kept = []
    for row in loaded:
        website = row.get("website_url") or ""
        name = row.get("name") or ""
        source_type = row.get("source_type") or "search"
        if not website or is_excluded(website) or listing_url(website):
            continue
        if not acceptable_name(name, source_type):
            continue
        if any(same_organisation(existing, name, website) for existing in kept):
            continue
        kept.append(row)
    print("Kept clubs from the previous run:", len(kept))
    return kept


def place_queries():
    """Searches for the suburb, city, or country set in the env file."""
    import events as club_events
    places = club_events.location_places(club_events.configured_location())
    kinds = (
        ("football club official website", "Sports"),
        ("cricket club official website", "Sports"),
        ("rugby club official website", "Sports"),
        ("netball club official website", "Sports"),
        ("tennis club official website", "Sports"),
        ("golf club official website", "Sports"),
        ("surf club official website", "Sports"),
        ("RSL club official website", "Social"),
        ("leagues club official website", "Social"),
        ("bowling club official website", "Social"),
    )
    return [(f"{place} {kind}", category) for place in places for kind, category in kinds]


def main():
    import events as club_events

    rows = load_existing()
    club_events.attach_events(rows)
    have = len(club_events.clubs_with_events(rows))
    print(
        f"Minimum is {MIN_CLUBS} clubs with events. "
        f"{have} already have events. {len(rows)} clubs are saved."
    )
    store = {}
    rejected = {}
    candidates = []
    if have >= MIN_CLUBS:
        print("Saved clubs with events already reach MIN_CLUBS.")
    else:
        scope = club_events.configured_location()
        print(f"Searching for clubs with events in {scope['label']}...")
        if scope["label"].lower() in ("sydney", "australia"):
            discover_football(store)
        label = scope["label"]
        queries = []
        for query, category in SEARCH_QUERIES + EXTRA_QUERIES + FILL_QUERIES + GROWTH_QUERIES + place_queries():
            text = re.sub(r"\bSydney\b", label, query, flags=re.I)
            if label.lower() not in text.lower():
                text = f"{label} {text}"
            queries.append((text, category))
        for query in queries:
            if len(club_events.clubs_with_events(rows)) >= MIN_CLUBS:
                break
            batch = {}
            discover_from_search(batch, [query])
            for candidate in batch.values():
                if len(club_events.clubs_with_events(rows)) >= MIN_CLUBS:
                    break
                if any(same_organisation(existing, candidate["name"], candidate["website"]) for existing in rows):
                    rejected["duplicate"] = rejected.get("duplicate", 0) + 1
                    continue
                if not acceptable_name(candidate["name"], candidate.get("source_type") or "search"):
                    rejected["not a club"] = rejected.get("not a club", 0) + 1
                    continue
                print(f"[{have}/{MIN_CLUBS} clubs with events]", candidate["name"], candidate["website"])
                details, reason = extract_details(candidate)
                if details is None:
                    rejected[reason] = rejected.get(reason, 0) + 1
                    continue
                if not acceptable_name(details["name"], "search") or is_excluded(details["website_url"]):
                    rejected["not a club"] = rejected.get("not a club", 0) + 1
                    continue
                if any(same_organisation(existing, details["name"], details["website_url"]) for existing in rows):
                    rejected["duplicate"] = rejected.get("duplicate", 0) + 1
                    continue
                if details["fingerprint"] in {row["fingerprint"] for row in rows}:
                    rejected["duplicate"] = rejected.get("duplicate", 0) + 1
                    continue
                club_events.enrich_clubs([details])
                club_events.attach_events([details])
                found = details.get("events") or []
                if not found:
                    print("  No events, club not added")
                    rejected["no events"] = rejected.get("no events", 0) + 1
                    continue
                rows.append(details)
                have = len(club_events.clubs_with_events(rows))
                save_clubs([{key: value for key, value in row.items() if key != "events"} for row in rows])
                print(f"  Added. Clubs with events: {have}/{MIN_CLUBS}. Events on this club: {len(found)}")
                club_events.write_updated_clubs(rows)
                time.sleep(REQUEST_DELAY)
        candidates = list(store.values())

    print("Writing clubs that have events...")
    kept = club_events.clubs_with_events(rows)
    events_excel = club_events.write_workbook(kept)
    clubs_excel = club_events.write_updated_clubs(kept)
    for row in rows:
        row.pop("events", None)

    json_path = save_clubs(rows)
    category_counts = {}
    for row in kept:
        category_counts[row["category"]] = category_counts.get(row["category"], 0) + 1

    print("\nCrawl complete.")
    print("Records processed:", len(candidates))
    print("Clubs saved:", len(rows))
    print("Clubs with events:", len(kept))
    print("Minimum clubs with events:", MIN_CLUBS)
    print("Rejected:", sum(rejected.values()))
    if rejected:
        print("Rejected reasons:")
        for reason, count in sorted(rejected.items(), key=lambda item: -item[1]):
            print(f"- {reason}: {count}")
    print("Categories:", category_counts)
    print("JSON:", json_path.resolve())
    print("Excel:", Path(clubs_excel).resolve())
    print("Events Excel:", events_excel.resolve())


if __name__ == "__main__":
    main()
