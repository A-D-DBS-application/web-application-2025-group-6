from datetime import datetime
from . import db

class User(db.Model):
    __tablename__ = "users"

    user_id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(100), unique=True, nullable=False)
    role = db.Column(db.String(20), default="traveller")  # traveller, host, admin
    contact_email = db.Column(db.String(255))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    profile = db.relationship("Profile", back_populates="user", uselist=False)
    listings = db.relationship("Listing", back_populates="host", lazy="dynamic")
    bookings = db.relationship("Booking", back_populates="traveller", lazy="dynamic")
    reviews = db.relationship("Review", back_populates="traveller", lazy="dynamic")
    notifications = db.relationship("Notification", back_populates="user", lazy="dynamic")

class Profile(db.Model):
    __tablename__ = "profiles"

    profile_id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.user_id"), nullable=False)
    bio = db.Column(db.Text)
    picture_url = db.Column(db.String(255))
    preferences = db.Column(db.Text)
    demographic_info = db.Column(db.Text)

    user = db.relationship("User", back_populates="profile")

class Category(db.Model):
    __tablename__ = "categories"

    category_id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    description = db.Column(db.Text)

    listings = db.relationship("Listing", back_populates="category", lazy="dynamic")

class ListingTag(db.Model):
    __tablename__ = "listing_tags"

    listing_id = db.Column(db.Integer, db.ForeignKey("listings.listing_id"), primary_key=True)
    tag_id = db.Column(db.Integer, db.ForeignKey("tags.tag_id"), primary_key=True)

class Tag(db.Model):
    __tablename__ = "tags"

    tag_id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), unique=True, nullable=False)

    listings = db.relationship(
        "Listing",
        secondary="listing_tags",
        back_populates="tags",
        lazy="dynamic"
    )

class Listing(db.Model):
    __tablename__ = "listings"

    listing_id = db.Column(db.Integer, primary_key=True)
    host_id = db.Column(db.Integer, db.ForeignKey("users.user_id"), nullable=False)
    title = db.Column(db.String(200), nullable=False)
    description = db.Column(db.Text)
    location = db.Column(db.String(255))
    category_id = db.Column(db.Integer, db.ForeignKey("categories.category_id"))
    price_per_night = db.Column(db.Float)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    is_available = db.Column(db.Boolean, default=True)

    host = db.relationship("User", back_populates="listings")
    category = db.relationship("Category", back_populates="listings")
    tags = db.relationship(
        "Tag",
        secondary="listing_tags",
        back_populates="listings",
        lazy="dynamic"
    )
    bookings = db.relationship("Booking", back_populates="listing", lazy="dynamic")
    reviews = db.relationship("Review", back_populates="listing", lazy="dynamic")

class Booking(db.Model):
    __tablename__ = "bookings"

    booking_id = db.Column(db.Integer, primary_key=True)
    listing_id = db.Column(db.Integer, db.ForeignKey("listings.listing_id"), nullable=False)
    traveller_id = db.Column(db.Integer, db.ForeignKey("users.user_id"), nullable=False)
    start_date = db.Column(db.Date)
    end_date = db.Column(db.Date)
    status = db.Column(db.String(20), default="pending")  # pending, confirmed, cancelled
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    listing = db.relationship("Listing", back_populates="bookings")
    traveller = db.relationship("User", back_populates="bookings")
    invoice = db.relationship("Invoice", back_populates="booking", uselist=False)

class Invoice(db.Model):
    __tablename__ = "invoices"

    invoice_id = db.Column(db.Integer, primary_key=True)
    booking_id = db.Column(db.Integer, db.ForeignKey("bookings.booking_id"), nullable=False)
    amount = db.Column(db.Float)
    payment_date = db.Column(db.DateTime)
    payment_status = db.Column(db.String(20), default="unpaid")  # unpaid, paid, refunded

    booking = db.relationship("Booking", back_populates="invoice")

class Review(db.Model):
    __tablename__ = "reviews"

    review_id = db.Column(db.Integer, primary_key=True)
    listing_id = db.Column(db.Integer, db.ForeignKey("listings.listing_id"), nullable=False)
    traveller_id = db.Column(db.Integer, db.ForeignKey("users.user_id"), nullable=False)
    rating = db.Column(db.Integer)  # 1–5
    comment = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    listing = db.relationship("Listing", back_populates="reviews")
    traveller = db.relationship("User", back_populates="reviews")

class Message(db.Model):
    __tablename__ = "messages"

    message_id = db.Column(db.Integer, primary_key=True)
    from_user_id = db.Column(db.Integer, db.ForeignKey("users.user_id"), nullable=False)
    to_user_id = db.Column(db.Integer, db.ForeignKey("users.user_id"), nullable=False)
    listing_id = db.Column(db.Integer, db.ForeignKey("listings.listing_id"))
    content = db.Column(db.Text)
    sent_at = db.Column(db.DateTime, default=datetime.utcnow)

class Notification(db.Model):
    __tablename__ = "notifications"

    notification_id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.user_id"), nullable=False)
    type = db.Column(db.String(100))
    content = db.Column(db.Text)
    is_read = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    user = db.relationship("User", back_populates="notifications")
