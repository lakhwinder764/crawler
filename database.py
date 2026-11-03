"""SQLite store for approved club records.

The public site reads this database. It does not search the web.
Re-importing the same club updates the existing row.
"""

import hashlib
import os
import re
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent
DB_PATH = ROOT / "data" / "clubs.db"

CITY_OF_SYDNEY_QUERY = (
    "https://services1.arcgis.com/cNVyNtjGVZybOQWZ/arcgis/rest/services/"
    "Sport/FeatureServer/0/query"
)

COLUMNS = (
    "id", "fingerprint", "name", "category", "subcategory", "description",
    "suburb", "city", "meeting_location", "meeting_days", "meeting_time",
    "website_url", "instagram_url", "facebook_url", "contact_email",
    "whatsapp", "image_url", "price", "beginner_friendly", "age_group",
    "audience", "source_url", "source_platform", "source_type",
    "status", "verified", "lat", "lng", "created_at", "updated_at",
)


def connect():
    DB_PATH.parent.mkdir(exist_ok=True)
    connection = sqlite3.connect(DB_PATH)
    connection.row_factory = sqlite3.Row
    return connection


def init_db():
    with connect() as connection:
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS clubs (
                id TEXT PRIMARY KEY,
                fingerprint TEXT NOT NULL UNIQUE,
                name TEXT NOT NULL,
                category TEXT,
                subcategory TEXT,
                description TEXT,
                suburb TEXT,
                city TEXT,
                meeting_location TEXT,
                meeting_days TEXT,
                meeting_time TEXT,
                website_url TEXT,
                instagram_url TEXT,
                facebook_url TEXT,
                contact_email TEXT,
                whatsapp TEXT,
                image_url TEXT,
                price TEXT,
                beginner_friendly INTEGER,
                age_group TEXT,
                audience TEXT,
                source_url TEXT,
                source_platform TEXT,
                source_type TEXT,
                status TEXT NOT NULL DEFAULT 'published',
                verified INTEGER NOT NULL DEFAULT 0,
                lat REAL,
                lng REAL,
                created_at TEXT,
                updated_at TEXT
            )
            """
        )


def name_key(name):
    return re.sub(r"[^a-z0-9]", "", (name or "").lower())


def domain_of(url):
    if not url:
        return ""
    host = re.sub(r"^https?://", "", url.lower()).split("/")[0]
    host = host.split(":")[0]
    if host.startswith("www."):
        host = host[4:]
    return host


def fingerprint_for(name, website, source_url=""):
    raw = f"{name_key(name)}|{domain_of(website) or (source_url or '').strip()}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]


def now():
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _flag(value):
    if value is None or value == "":
        return None
    return 1 if value in (True, 1, "1", "yes", "Yes") else 0


def import_records(records):
    """Insert new clubs and update clubs that share a fingerprint."""
    init_db()
    report = {"processed": 0, "created": 0, "updated": 0, "rejected": []}
    timestamp = now()
    with connect() as connection:
        for record in records:
            report["processed"] += 1
            name = (record.get("name") or "").strip()
            if not name:
                report["rejected"].append("Missing club name")
                continue
            fingerprint = record.get("fingerprint") or fingerprint_for(
                name, record.get("website_url") or "", record.get("source_url") or ""
            )
            existing = connection.execute(
                "SELECT id, status, verified, created_at FROM clubs WHERE fingerprint = ?",
                (fingerprint,),
            ).fetchone()
            status = record.get("status") or "published"
            verified = _flag(record.get("verified")) or 0
            created_at = timestamp
            if existing:
                status = existing["status"]
                verified = existing["verified"]
                created_at = existing["created_at"]
            values = {
                "id": existing["id"] if existing else record.get("id") or fingerprint,
                "fingerprint": fingerprint,
                "name": name,
                "category": record.get("category") or "",
                "subcategory": record.get("subcategory") or "",
                "description": record.get("description") or "",
                "suburb": record.get("suburb") or "",
                "city": record.get("city") or "Sydney",
                "meeting_location": record.get("meeting_location") or "",
                "meeting_days": record.get("meeting_days") or "",
                "meeting_time": record.get("meeting_time") or "",
                "website_url": record.get("website_url") or "",
                "instagram_url": record.get("instagram_url") or "",
                "facebook_url": record.get("facebook_url") or "",
                "contact_email": record.get("contact_email") or "",
                "whatsapp": record.get("whatsapp") or "",
                "image_url": record.get("image_url") or (record.get("photos") or [""])[0],
                "price": record.get("price") or "",
                "beginner_friendly": _flag(record.get("beginner_friendly")),
                "age_group": record.get("age_group") or "",
                "audience": record.get("audience") or "",
                "source_url": record.get("source_url") or "",
                "source_platform": record.get("source_platform") or "",
                "source_type": record.get("source_type") or "",
                "status": status,
                "verified": verified,
                "lat": record.get("lat"),
                "lng": record.get("lng"),
                "created_at": created_at,
                "updated_at": timestamp,
            }
            if existing:
                assignments = ", ".join(f"{column} = ?" for column in COLUMNS if column != "fingerprint")
                connection.execute(
                    f"UPDATE clubs SET {assignments} WHERE fingerprint = ?",
                    [values[column] for column in COLUMNS if column != "fingerprint"] + [fingerprint],
                )
                report["updated"] += 1
            else:
                placeholders = ", ".join("?" for _ in COLUMNS)
                connection.execute(
                    f"INSERT INTO clubs ({', '.join(COLUMNS)}) VALUES ({placeholders})",
                    [values[column] for column in COLUMNS],
                )
                report["created"] += 1
    return report


def list_clubs(status=None):
    init_db()
    query = "SELECT * FROM clubs"
    params = []
    if status:
        query += " WHERE status = ?"
        params.append(status)
    query += " ORDER BY name"
    with connect() as connection:
        return [dict(row) for row in connection.execute(query, params)]


def get_club_row(slug):
    init_db()
    with connect() as connection:
        row = connection.execute("SELECT * FROM clubs WHERE id = ?", (slug,)).fetchone()
    return dict(row) if row else None


def set_status(slug, status, verified=None):
    init_db()
    with connect() as connection:
        if verified is None:
            connection.execute(
                "UPDATE clubs SET status = ?, updated_at = ? WHERE id = ?",
                (status, now(), slug),
            )
        else:
            connection.execute(
                "UPDATE clubs SET status = ?, verified = ?, updated_at = ? WHERE id = ?",
                (status, 1 if verified else 0, now(), slug),
            )
        return connection.execute("SELECT changes()").fetchone()[0] > 0


def save_club(record):
    """Insert or replace one club by id, used for submissions and admin edits."""
    init_db()
    current = get_club_row(record["id"])
    record = dict(record)
    record["fingerprint"] = record.get("fingerprint") or fingerprint_for(
        record.get("name"), record.get("website_url") or "", record.get("source_url") or ""
    )
    if current and current["fingerprint"] != record["fingerprint"]:
        with connect() as connection:
            connection.execute("DELETE FROM clubs WHERE id = ?", (record["id"],))
    report = import_records([record])
    if current is None:
        return report
    with connect() as connection:
        connection.execute(
            """
            UPDATE clubs
            SET status = ?, verified = ?, updated_at = ?
            WHERE id = ?
            """,
            (
                record.get("status") or current["status"],
                _flag(record.get("verified")),
                now(),
                record["id"],
            ),
        )
    return report


def count_clubs():
    init_db()
    with connect() as connection:
        return connection.execute("SELECT COUNT(*) FROM clubs").fetchone()[0]


def skipped_paid_sources():
    """Paid or approval-gated tools from the comparison. They are not called."""
    notes = []
    if not os.getenv("OUTSCRAPER_API_KEY"):
        notes.append(
            "Outscraper: skipped, no API key. The comparison says to confirm the cost before running."
        )
    if not os.getenv("APIFY_TOKEN"):
        notes.append("Apify: skipped, no API token. The free plan still spends usage credit.")
    if not os.getenv("MEETUP_API_KEY"):
        notes.append("Meetup API: skipped, no key. Access requires Meetup Pro approval.")
    return notes
