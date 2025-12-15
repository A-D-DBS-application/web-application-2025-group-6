from datetime import datetime
from . import db
from sqlalchemy.dialects.postgresql import ARRAY # Nodig voor de array-kolom (PostgreSQL/Supabase database)
from flask_login import UserMixin

# =========================================================================
# SQLAlchemy ORM Models
# ORM voordelen: directe database connectie, minder code, lazy loading
# Database wordt automatisch omgezet naar Python objecten (geen JSON nodig)
# =========================================================================

# =========================================================================
# 1. TRAVEL PLANNER MVP CORE MODELLEN (NIEUW TOEGEVOEGD)
# Deze zijn essentieel voor jullie Step 1/2/Resultaat logica en Algoritme
# =========================================================================

class Traveler(db.Model):
    # Komt overeen met de data van step1.html en step2.html (de gebruikersinvoer)
    __tablename__ = 'traveler' # Tabel naam in database
    
    traveler_id = db.Column(db.Integer, primary_key=True)
    
    # Data van Step 1
    start_date = db.Column(db.Date, nullable=False)
    end_date = db.Column(db.Date, nullable=False)
    budget_range = db.Column(db.String(50)) # Bijv. 'low', 'medium', 'high'
    accommodation_type = db.Column(db.String(50)) # Bijv. 'hostel', 'hotel'
    country = db.Column(db.String(50)) # Bijv. 'Uganda', 'Rwanda'
    
    # Data van Step 2
    adults = db.Column(db.Integer, default=1)
    children = db.Column(db.Integer, default=0)
    
    # Interesses (We slaan de ruwe voorkeuren op, bijv. 'Culture': 5, 'Wildlife': 3)
    interest_culture = db.Column(db.Integer)
    interest_food = db.Column(db.Integer)
    interest_wildlife = db.Column(db.Integer)
    interest_history = db.Column(db.Integer)
    interest_beach = db.Column(db.Integer)

    # Relatie met het gegenereerde reisschema
    # lazy=True: Lazy loading - data wordt alleen geladen wanneer nodig (ORM voordeel)
    itineraries = db.relationship('Itinerary', backref='traveler', lazy=True)


class ActivityType(db.Model):
    # Komt overeen met de 'activity_type' tabel in de database
    __tablename__ = 'activity_type'

    activity_type_id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(255), nullable=False)
    description = db.Column(db.Text)
    duration_days = db.Column(db.Integer)
    price_estimation = db.Column(db.Numeric(10, 2)) # Numeric voor geldwaarden
    country = db.Column(db.String(50))
    # Images via Buckets pattern: database slaat alleen file path/URL op, niet de file zelf
    # Images worden opgeslagen in storage bucket, alleen de URL wordt in database bewaard
    images_url_text = db.Column(db.String(500)) # URL/path naar de foto (van storage bucket)
    
    # Dit is de cruciale kolom voor je algoritme: [ 'Wildlife', 'Culture' ]
    # We gebruiken ARRAY(db.String) om de PostgreSQL array functionaliteit te ondersteunen.
    interest_categ = db.Column(ARRAY(db.String))
    
    # Child-friendly filter
    is_child_friendly = db.Column(db.Boolean, default=True)
    
    # Relatie met Itinerary items
    # lazy=True: Lazy loading - data wordt alleen geladen wanneer nodig (ORM voordeel)
    itinerary_items = db.relationship('Itinerary', backref='activity_type', lazy=True)


class Itinerary(db.Model):
    # De tabel die de gegenereerde reisroute opslaat (wat de gebruiker ziet op de resultaatpagina)
    __tablename__ = 'itinerary'
    
    itinerary_id = db.Column(db.Integer, primary_key=True)
    traveler_id = db.Column(db.Integer, db.ForeignKey('traveler.traveler_id'), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('users.user_id'), nullable=True)  # Link to user
    
    day = db.Column(db.Integer, nullable=False)
    day_activity_id = db.Column(db.Integer, db.ForeignKey('activity_type.activity_type_id'), nullable=False)
    
    # De titel en beschrijving die in de resultatenpagina worden getoond
    title = db.Column(db.String(100), nullable=False)
    description = db.Column(db.Text)

    # Relatie naar ActivityType (backref wordt automatisch aangemaakt door ActivityType model)
    # Via backref in ActivityType kunnen we: activity_type.itinerary_items gebruiken
    # En via de foreign key kunnen we: itinerary.activity_type gebruiken (automatisch via backref)


# =========================================================================
# 2. BESTAANDE MARKTPLAATS MODELLEN (BEHOUDEN)
# Deze zijn nuttig voor de volledige casus, maar niet direct voor de MVP planning
# =========================================================================

class User(UserMixin, db.Model):
    __tablename__ = "users"

    user_id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(100), unique=True, nullable=False)
    role = db.Column(db.String(20), default="traveller") 	# traveller, host, admin
    contact_email = db.Column(db.String(255))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    # Flask-Login requires get_id() method, but we use user_id instead of id
    def get_id(self):
        return str(self.user_id)

    profile = db.relationship("Profile", back_populates="user", uselist=False)
    listings = db.relationship("Listing", back_populates="host", lazy="dynamic")
    bookings = db.relationship("Booking", back_populates="traveller", lazy="dynamic")
    reviews = db.relationship("Review", back_populates="traveller", lazy="dynamic")
    notifications = db.relationship("Notification", back_populates="user", lazy="dynamic")
    itineraries = db.relationship("Itinerary", backref="user", lazy="dynamic")

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
    status = db.Column(db.String(20), default="pending") 	# pending, confirmed, cancelled
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
    payment_status = db.Column(db.String(20), default="unpaid") 	# unpaid, paid, refunded

    booking = db.relationship("Booking", back_populates="invoice")

class Review(db.Model):
    __tablename__ = "reviews"

    review_id = db.Column(db.Integer, primary_key=True)
    listing_id = db.Column(db.Integer, db.ForeignKey("listings.listing_id"), nullable=False)
    traveller_id = db.Column(db.Integer, db.ForeignKey("users.user_id"), nullable=False)
    rating = db.Column(db.Integer) 	# 1–5
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