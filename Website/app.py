# app.py
import os
from flask import Flask, render_template, redirect, url_for, request, session, flash
from datetime import date

from models import (
    db,
    User,
    Agency,
    Itinerary,
    Traveler,
    Supplier,
    ItineraryTraveler,
    ItinerarySupplier,
    supplier_score_for_itinerary,
)


def create_app():
    app = Flask(__name__)

    # SQLITE DATABASE (GEEN SUPABASE)
    app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///travel_agency.db"
    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
    app.secret_key = "dev-secret"

    db.init_app(app)

    with app.app_context():
        db.create_all()

    # =======================
    #     LOGIN REQUIRED
    # =======================
    from functools import wraps

    def login_required(fn):
        @wraps(fn)
        def wrapper(*args, **kwargs):
            if "user_id" not in session:
                flash("Please log in first.", "warning")
                return redirect(url_for("login"))
            return fn(*args, **kwargs)

        return wrapper

    # =======================
    #      AUTHENTICATION
    # =======================

    @app.route("/")
    def index():
        if "user_id" in session:
            return redirect(url_for("dashboard"))
        return redirect(url_for("login"))

    @app.route("/register", methods=["GET", "POST"])
    def register():
        if request.method == "POST":
            username = request.form.get("username").strip()

            if not username:
                flash("Username required.", "danger")
                return redirect(url_for("register"))

            existing = User.query.filter_by(username=username).first()
            if existing:
                flash("Username already exists.", "warning")
                return redirect(url_for("login"))

            user = User(username=username)
            db.session.add(user)
            db.session.commit()

            flash("Account created. Please log in.", "success")
            return redirect(url_for("login"))

        return render_template("register.html")

    @app.route("/login", methods=["GET", "POST"])
    def login():
        if request.method == "POST":
            username = request.form.get("username").strip()

            user = User.query.filter_by(username=username).first()
            if not user:
                flash("User not found. Register first.", "danger")
                return redirect(url_for("register"))

            session["user_id"] = user.id
            session["username"] = user.username

            flash(f"Welcome, {user.username}!", "success")
            return redirect(url_for("dashboard"))

        return render_template("login.html")

    @app.route("/logout")
    def logout():
        session.clear()
        flash("Logged out.", "info")
        return redirect(url_for("login"))

    # =======================
    #        DASHBOARD
    # =======================

    @app.route("/dashboard")
    @login_required
    def dashboard():
        return render_template(
            "dashboard.html",
            itinerary_count=Itinerary.query.count(),
            traveler_count=Traveler.query.count(),
            supplier_count=Supplier.query.count(),
            upcoming_itineraries=Itinerary.query.filter(
                Itinerary.start_date >= date.today()
            )
            .order_by(Itinerary.start_date)
            .limit(5)
            .all(),
        )

    # =======================
    #       ITINERARIES
    # =======================

    @app.route("/itineraries")
    @login_required
    def itineraries_list():
        itineraries = Itinerary.query.order_by(Itinerary.start_date).all()
        return render_template("itineraries.html", itineraries=itineraries)

    @app.route("/itineraries/new", methods=["GET", "POST"])
    @login_required
    def itinerary_create():
        agencies = Agency.query.all()

        if request.method == "POST":
            it = Itinerary(
                id=os.urandom(16).hex(),
                agency_id=request.form.get("agency_id"),
                number_of_travelers=int(request.form.get("number_of_travelers")),
                budget=request.form.get("budget"),
                country=request.form.get("country"),
                activity_type=request.form.get("activity_type"),
                start_date=date.fromisoformat(request.form.get("start_date")),
                end_date=date.fromisoformat(request.form.get("end_date")),
            )

            db.session.add(it)
            db.session.commit()
            flash("Itinerary created.", "success")

            return redirect(url_for("itineraries_list"))

        return render_template("itinerary_detail.html", mode="new", agencies=agencies)

    @app.route("/itineraries/<itinerary_id>", methods=["GET", "POST"])
    @login_required
    def itinerary_detail(itinerary_id):
        itinerary = Itinerary.query.get_or_404(itinerary_id)
        all_travelers = Traveler.query.all()
        all_suppliers = Supplier.query.all()

        if request.method == "POST":
            # Add traveler to itinerary
            if "add_traveler" in request.form:
                t_id = request.form.get("traveler_id")
                db.session.add(ItineraryTraveler(itinerary_id=itinerary.id, traveler_id=t_id))
                db.session.commit()
                flash("Traveler added.", "success")

            # Add supplier to itinerary
            if "add_supplier" in request.form:
                s_id = request.form.get("supplier_id")
                db.session.add(ItinerarySupplier(itinerary_id=itinerary.id, supplier_id=s_id))
                db.session.commit()
                flash("Supplier added.", "success")

            return redirect(url_for("itinerary_detail", itinerary_id=itinerary.id))

        supplier_scores = supplier_score_for_itinerary(itinerary)

        return render_template(
            "itinerary_detail.html",
            itinerary=itinerary,
            all_travelers=all_travelers,
            all_suppliers=all_suppliers,
            supplier_scores=supplier_scores,
            mode="view",
        )

    # =======================
    #       TRAVELERS
    # =======================

    @app.route("/travelers", methods=["GET", "POST"])
    @login_required
    def travelers_list():
        if request.method == "POST":
            t = Traveler(
                id=os.urandom(16).hex(),
                first_name=request.form.get("first_name"),
                last_name=request.form.get("last_name"),
                age=int(request.form.get("age")),
                email=request.form.get("email"),
            )
            db.session.add(t)
            db.session.commit()
            flash("Traveler added.", "success")
            return redirect(url_for("travelers_list"))

        return render_template("travelers.html", travelers=Traveler.query.all())

    # =======================
    #       SUPPLIERS
    # =======================

    @app.route("/suppliers", methods=["GET", "POST"])
    @login_required
    def suppliers_list():
        agencies = Agency.query.all()

        if request.method == "POST":
            s = Supplier(
                id=os.urandom(16).hex(),
                agency_id=request.form.get("agency_id"),
                company_id=request.form.get("company_id"),
                name=request.form.get("name"),
                type=request.form.get("type"),
            )
            db.session.add(s)
            db.session.commit()
            flash("Supplier added.", "success")
            return redirect(url_for("suppliers_list"))

        return render_template(
            "suppliers.html",
            suppliers=Supplier.query.all(),
            agencies=agencies,
        )

    # =======================
    #       AGENCIES
    # =======================

    @app.route("/agencies", methods=["GET", "POST"])
    @login_required
    def agencies_list():
        if request.method == "POST":
            agency = Agency(
                id=os.urandom(16).hex(),
                name=request.form.get("name"),
                email=request.form.get("email"),
            )
            db.session.add(agency)
            db.session.commit()
            flash("Agency created.", "success")
            return redirect(url_for("agencies_list"))

        return render_template("agencies.html", agencies=Agency.query.all())

    return app
