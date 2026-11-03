import os
from pathlib import Path

from dotenv import load_dotenv
from flask import (
    Flask, abort, flash, jsonify, redirect, render_template,
    request, session, url_for,
)
from werkzeug.utils import secure_filename

import club_mvp

load_dotenv()

app = Flask(__name__)
app.secret_key = os.getenv("SECRET_KEY", "aussie-club-finder-local")
app.config["MAX_CONTENT_LENGTH"] = 4 * 1024 * 1024
UPLOADS = Path("static/uploads")
UPLOADS.mkdir(parents=True, exist_ok=True)


def page_args():
    args = request.args.to_dict()
    try:
        page = max(1, int(args.get("page") or 1))
    except ValueError:
        page = 1
    return args, page


ENV_PATH = Path(".env")


def read_max_clubs():
    if ENV_PATH.exists():
        for line in ENV_PATH.read_text(encoding="utf-8").splitlines():
            if line.startswith("MAX_CLUBS="):
                try:
                    return max(1, int(line.split("=", 1)[1].strip()))
                except ValueError:
                    break
    return 100


def write_max_clubs(count):
    lines = ENV_PATH.read_text(encoding="utf-8").splitlines() if ENV_PATH.exists() else []
    updated = []
    found = False
    for line in lines:
        if line.startswith("MAX_CLUBS="):
            updated.append(f"MAX_CLUBS={count}")
            found = True
        else:
            updated.append(line)
    if not found:
        updated.insert(0, f"MAX_CLUBS={count}")
    ENV_PATH.write_text("\n".join(updated) + "\n", encoding="utf-8")
    os.environ["MAX_CLUBS"] = str(count)


def requested_count(args):
    raw = (args.get("count") or "").strip()
    if not raw:
        return None
    try:
        count = int(raw)
    except ValueError:
        return None
    if count < 1:
        return None
    return min(count, 500)


def generate_clubs(args):
    """Generate as many clubs as Number of clubs, and store that value in MAX_CLUBS."""
    pool = club_mvp.filter_clubs(club_mvp.all_clubs(), args)
    count = requested_count(args)
    if count is None:
        count = read_max_clubs()
    else:
        write_max_clubs(count)
    return pool[:count], count, len(pool)


@app.route("/")
def directory():
    args, page = page_args()
    clubs, requested, available = generate_clubs(args)
    suburbs = sorted({club["suburb"] for club in club_mvp.all_clubs() if club["suburb"]})
    cities = sorted({club["city"] for club in club_mvp.all_clubs() if club["city"]})
    return render_template(
        "directory.html",
        clubs=clubs,
        total=len(clubs),
        requested=requested,
        available=available,
        max_clubs=read_max_clubs(),
        page=1,
        pages=1,
        start=1 if clubs else 0,
        end=len(clubs),
        suburbs=suburbs,
        cities=cities,
        args=args,
        categories=club_mvp.CATEGORIES,
        category_slugs=club_mvp.CATEGORY_SLUGS,
        days=club_mvp.DAYS,
        heading="Discover clubs in Sydney",
        intro="Clubs and groups around Sydney. The map shows the same list.",
    )


@app.route("/sydney/<slug>")
def category_page(slug):
    category = club_mvp.SLUG_TO_CATEGORY.get(slug)
    if category is None:
        abort(404)
    args, page = page_args()
    args["category"] = category
    args["city"] = "Sydney"
    clubs, requested, available = generate_clubs(args)
    title = f"{category} clubs in Sydney"
    return render_template(
        "directory.html",
        clubs=clubs,
        total=len(clubs),
        requested=requested,
        available=available,
        max_clubs=read_max_clubs(),
        page=1,
        pages=1,
        start=1 if clubs else 0,
        end=len(clubs),
        suburbs=sorted({club["suburb"] for club in club_mvp.all_clubs() if club["suburb"]}),
        cities=["Sydney"],
        args=args,
        categories=club_mvp.CATEGORIES,
        category_slugs=club_mvp.CATEGORY_SLUGS,
        days=club_mvp.DAYS,
        heading=title,
        intro=f"Browse {category.lower()} clubs around Sydney.",
        seo_title=title,
        seo_description=f"Find {category.lower()} clubs in Sydney. See meeting times, websites and how to join.",
    )


@app.route("/clubs/<slug>")
def club_page(slug):
    club = club_mvp.get_club(slug)
    if club is None:
        abort(404)
    return render_template(
        "club.html",
        club=club,
        reviews=club_mvp.reviews_for(slug),
        seo_title=f"{club['name']} | Aussie Club Finder",
        seo_description=(club["description"] or f"{club['name']} in {club['city']}")[:160],
    )


@app.route("/clubs/<slug>/reviews", methods=["POST"])
def add_review(slug):
    photo_path = ""
    upload = request.files.get("photo")
    if upload and upload.filename:
        filename = secure_filename(upload.filename)
        if filename.lower().endswith((".png", ".jpg", ".jpeg", ".webp", ".gif")):
            stored = f"{slug}-{filename}"
            upload.save(UPLOADS / stored)
            photo_path = f"uploads/{stored}"
    if club_mvp.add_review(slug, request.form, photo_path):
        flash("Thanks, your review was added.")
    else:
        flash("Add a star rating and a short review.")
    return redirect(url_for("club_page", slug=slug))


@app.route("/map")
def map_page():
    clubs = club_mvp.all_clubs()
    mapped = [club for club in clubs if club["lat"] is not None and club["lng"] is not None]
    unmapped = [club for club in clubs if club["lat"] is None or club["lng"] is None]
    return render_template("map.html", clubs=mapped, unmapped=unmapped)


@app.route("/add", methods=["GET", "POST"])
def add_club():
    if request.method == "POST":
        record, error = club_mvp.add_submission(request.form)
        if error:
            flash(error)
        else:
            flash("Thanks. Your club was submitted and is waiting for review.")
            return redirect(url_for("add_club"))
    return render_template("add.html", categories=club_mvp.CATEGORIES, days=club_mvp.DAYS)


@app.route("/saved")
def saved():
    return render_template("saved.html")


@app.route("/api/clubs")
def api_clubs():
    ids = [item for item in (request.args.get("ids") or "").split(",") if item]
    clubs = club_mvp.all_clubs()
    if ids:
        wanted = set(ids)
        clubs = [club for club in clubs if club["id"] in wanted]
    return jsonify(clubs)


@app.route("/admin/login", methods=["GET", "POST"])
def admin_login():
    if request.method == "POST":
        password = os.getenv("ADMIN_PASSWORD", "clubadmin")
        if request.form.get("password") == password:
            session["admin"] = True
            return redirect(url_for("admin"))
        flash("That password did not match.")
    return render_template("login.html")


@app.route("/admin/logout", methods=["POST"])
def admin_logout():
    session.clear()
    return redirect(url_for("directory"))


def require_admin():
    if not session.get("admin"):
        return redirect(url_for("admin_login"))
    return None


@app.route("/admin")
def admin():
    locked = require_admin()
    if locked:
        return locked
    clubs = club_mvp.all_clubs()
    return render_template(
        "admin.html",
        clubs=clubs,
        pending=club_mvp.pending_submissions(),
        stats=club_mvp.analytics(clubs),
        categories=club_mvp.CATEGORIES,
    )


@app.route("/admin/clubs/<slug>/approve", methods=["POST"])
def approve(slug):
    locked = require_admin()
    if locked:
        return locked
    club_mvp.approve_submission(slug)
    flash("Club approved and given a verified badge.")
    return redirect(url_for("admin"))


@app.route("/admin/clubs/<slug>/hide", methods=["POST"])
def hide(slug):
    locked = require_admin()
    if locked:
        return locked
    club_mvp.hide_club(slug)
    flash("Club removed from the public directory.")
    return redirect(url_for("admin"))


@app.route("/admin/clubs/<slug>/edit", methods=["POST"])
def edit(slug):
    locked = require_admin()
    if locked:
        return locked
    if club_mvp.update_club(slug, request.form):
        flash("Listing updated.")
    return redirect(url_for("admin"))


@app.errorhandler(404)
def missing(_error):
    return render_template("missing.html"), 404


if __name__ == "__main__":
    app.run(debug=True, port=5000)
