"""Import club records into the database without creating duplicates.

Sources used here:
- the saved crawler file output/top_100_clubs.json
- City of Sydney open data (sports facilities), kept only when the name is a club
- an optional reviewed spreadsheet (--csv)

Outscraper, Apify, and the Meetup API are skipped unless a key is set.
Those tools can cost money or need Meetup Pro approval.
"""

import argparse
import csv
import json
from collections import Counter

import requests

import club_mvp
import database

CITY_QUERY = database.CITY_OF_SYDNEY_QUERY
CLUB_WORDS = ("club", "association", "society", "rotary", "probus")


def load_seed_records():
    if not club_mvp.SEED_PATH.exists():
        return []
    rows = json.loads(club_mvp.SEED_PATH.read_text(encoding="utf-8"))
    records = []
    for row in rows:
        club = club_mvp.enrich_record(row, verified=True)
        point = club_mvp.coords_for(club["suburb"])
        club["lat"] = point[0] if point else None
        club["lng"] = point[1] if point else None
        club["image_url"] = (club.get("photos") or [""])[0]
        club["status"] = "published"
        club["verified"] = True
        club["fingerprint"] = row.get("fingerprint") or database.fingerprint_for(
            club["name"], club.get("website_url") or "", club.get("source_url") or ""
        )
        records.append(club)
    return records


def city_of_sydney_records():
    """Download the public sports-facility layer and keep club-like names only."""
    kept = []
    skipped = Counter()
    offset = 0
    while True:
        response = requests.get(
            CITY_QUERY,
            params={
                "where": "1=1",
                "outFields": "FacilityName,Address,Suburb,FacilityType,URL,Status",
                "returnGeometry": "false",
                "resultRecordCount": 200,
                "resultOffset": offset,
                "f": "json",
            },
            timeout=30,
        )
        response.raise_for_status()
        payload = response.json()
        features = payload.get("features") or []
        if not features:
            break
        for feature in features:
            attributes = feature.get("attributes") or {}
            name = (attributes.get("FacilityName") or "").strip()
            if not name:
                skipped["Missing club name"] += 1
                continue
            if not any(word in name.lower() for word in CLUB_WORDS):
                skipped["Council facility, not a club"] += 1
                continue
            if (attributes.get("Status") or "").lower() not in ("", "current"):
                skipped["Facility is not current"] += 1
                continue
            suburb = (attributes.get("Suburb") or "").strip()
            point = club_mvp.coords_for(suburb)
            source = attributes.get("URL") or CITY_QUERY
            kept.append({
                "id": database.fingerprint_for(name, source, source),
                "name": name,
                "category": "Sports",
                "subcategory": attributes.get("FacilityType") or "",
                "description": "Listed in the City of Sydney sports and recreation facilities dataset.",
                "suburb": suburb,
                "city": "Sydney",
                "meeting_location": attributes.get("Address") or "",
                "website_url": source if str(source).startswith("http") else "",
                "source_url": source,
                "source_platform": "City of Sydney Open Data",
                "source_type": "open-data",
                "status": "pending",
                "verified": False,
                "lat": point[0] if point else None,
                "lng": point[1] if point else None,
                "fingerprint": database.fingerprint_for(name, source, source),
            })
        if not payload.get("exceededTransferLimit"):
            break
        offset += len(features)
    return kept, skipped


def load_csv(path):
    records = []
    with open(path, newline="", encoding="utf-8-sig") as handle:
        for row in csv.DictReader(handle):
            name = (row.get("name") or row.get("club_name") or "").strip()
            website = (row.get("website_url") or row.get("website") or "").strip()
            records.append({
                "name": name,
                "category": row.get("category") or "Social",
                "description": row.get("description") or "",
                "suburb": row.get("suburb") or "",
                "city": row.get("city") or "Sydney",
                "website_url": website,
                "contact_email": row.get("contact_email") or row.get("public_email") or "",
                "instagram_url": row.get("instagram_url") or "",
                "source_url": row.get("source_url") or website,
                "source_platform": row.get("source_platform") or "Reviewed spreadsheet",
                "source_type": "spreadsheet",
                "status": "pending",
                "verified": False,
            })
    return records


def print_report(title, report, extra=None):
    print(title)
    print(f"{report['processed']} records processed")
    print(f"{report['created']} created")
    print(f"{report['updated']} updated")
    print(f"{len(report['rejected'])} rejected")
    if report["rejected"]:
        counts = Counter(report["rejected"])
        print("Rejected:")
        for reason, count in counts.most_common():
            print(f"- {reason}: {count}")
    if extra:
        for reason, count in extra.most_common():
            print(f"- {reason}: {count}")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--csv", help="Reviewed spreadsheet to import")
    args = parser.parse_args()

    for note in database.skipped_paid_sources():
        print(note)

    seed_report = database.import_records(load_seed_records())
    print_report("Crawler seed", seed_report)

    kept, skipped = city_of_sydney_records()
    city_report = database.import_records(kept)
    city_report["rejected"].extend(
        reason for reason, count in skipped.items() for _ in range(count)
    )
    city_report["processed"] += sum(skipped.values())
    print_report("City of Sydney Open Data", city_report)

    if args.csv:
        sheet_report = database.import_records(load_csv(args.csv))
        print_report("Reviewed spreadsheet", sheet_report)

    again = database.import_records(load_seed_records())
    print_report("Crawler seed imported again", again)
    print("Published clubs:", len(database.list_clubs("published")))


if __name__ == "__main__":
    main()
