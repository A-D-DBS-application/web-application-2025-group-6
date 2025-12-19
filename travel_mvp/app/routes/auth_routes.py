"""
Authentication routes for the travel MVP application.

Handles user login, logout, and registration functionality.
"""

from flask import Blueprint, render_template, request, session, redirect, url_for, flash
from flask_login import login_user, logout_user, login_required, current_user
from app import db
from app.models import User
from app.utils import clear_session_preserve_login, save_session_preferences

auth_bp = Blueprint("auth", __name__)


@auth_bp.route("/login", methods=["GET", "POST"])
def login_route():
    """
    Login page. For MVP, this is a simple username entry.
    If user doesn't exist, they will be registered automatically.
    """
    if request.method == "POST":
        username = request.form.get("username")
        contact_email = request.form.get("contact_email", "")
        
        if username:
            # Check if user exists
            user = User.query.filter_by(username=username).first()
            
            if not user:
                # Create new user (simple MVP registration)
                user = User(
                    username=username,
                    contact_email=contact_email if contact_email else None,
                    role="traveller"
                )
                db.session.add(user)
                db.session.commit()
                flash(f"Account created! Welcome, {username}!", "success")
            else:
                flash(f"Welcome back, {username}!", "success")
            
            # Log in the user
            login_user(user)
            
            # Check if user was in the middle of planning
            # If all preferences are saved, redirect to result to generate trip
            if session.get("country") and session.get("start_date"):
                # Check if we have all step2 preferences
                has_all_preferences = (
                    session.get("adults") is not None and
                    session.get("accommodation_type") and
                    session.get("interest_culture") is not None
                )
                if has_all_preferences:
                    # All preferences are there, redirect to result to generate trip
                    return redirect(url_for("main.result_route"))
                else:
                    # Some preferences missing, go back to step2
                    return redirect(url_for("main.step2_route"))
            
            return redirect(url_for("main.index"))
    
    return render_template("login.html")


@auth_bp.route("/logout")
@login_required
def logout_route():
    """Log out the current user."""
    logout_user()
    flash("You have been logged out.", "info")
    return redirect(url_for("main.index"))

