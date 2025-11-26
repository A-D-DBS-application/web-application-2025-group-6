from flask import Blueprint, render_template, request, session

main_bp = Blueprint("main", __name__)

@main_bp.route("/")
def index():
    return render_template("index.html")

@main_bp.route("/step1")
def step1():
    return render_template("step1.html")

@main_bp.route("/step2", methods=["GET", "POST"])
def step2():
    budget = request.args.get("budget") or request.form.get("budget")
    country = request.args.get("country")
    duration = request.args.get("duration")

    return render_template(
        "step2.html",
        budget=budget,
        country=country,
        duration=duration
    )


@main_bp.route("/result", methods=["POST"])
def result():
    data = {
        "start": session.get("start"),
        "end": session.get("end"),
        "budget": session.get("budget"),
        "adults": request.form.get("adults"),
        "children": request.form.get("children"),
        "wildlife": request.form.get("wildlife"),
        "culture": request.form.get("culture"),
        "adventure": request.form.get("adventure"),
        "relax": request.form.get("relax"),
        "accommodation": request.form.get("accommodation"),
    }
    return render_template("result.html", **data)
