# models.py
from flask_sqlalchemy import SQLAlchemy
from datetime import datetime
from sqlalchemy import func

db = SQLAlchemy()


class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


class Agency(db.Model):
    id = db.Column(db.String(36), primary_key=True)
    name = db.Column(db.String(255))
    email = db.Column(db.String(255))

    itineraries = db.relationship("Itinerary", back_populates="agency")
    suppliers = db.relationship("Supplier", back_populates="agency")


class Itinerary(db.Model):
    id = db.Column(db.String(36), primary_key=True)
    agency_id = db.Column(db.String(36), db.ForeignKey("agency.id"))
    number_of_travelers = db.Column(db.Integer)
    budget = db.Column(db.Numeric)
    country = db.Column(db.String(255))
    activity_type = db.Column(db.String(255))
    start_date = db.Column(db.Date)
    end_date = db.Column(db.Date)

    agency = db.relationship("Agency", back_populates="itineraries")
    travelers = db.relationship(
        "Traveler",
        secondary="itinerary_traveler",
        back_populates="itineraries",
    )
    suppliers = db.relationship(
        "Supplier",
        secondary="itinerary_supplier",
        back_populates="itineraries",
    )


class Traveler(db.Model):
    id = db.Column(db.String(36), primary_key=True)
    first_name = db.Column(db.String(255))
    last_name = db.Column(db.String(255))
    age = db.Column(db.Integer)
    email = db.Column(db.String(255))

    itineraries = db.relationship(
        "Itinerary",
        secondary="itinerary_traveler",
        back_populates="travelers",
    )

    @property
    def full_name(self):
        return f"{self.first_name} {self.last_name}"


class Supplier(db.Model):
    id = db.Column(db.String(36), primary_key=True)
    agency_id = db.Column(db.String(36), db.ForeignKey("agency.id"))
    company_id = db.Column(db.String(255))
    name = db.Column(db.String(255))
    type = db.Column(db.String(255))

    agency = db.relationship("Agency", back_populates="suppliers")

    itineraries = db.relationship(
        "Itinerary",
        secondary="itinerary_supplier",
        back_populates="suppliers",
    )


class ItineraryTraveler(db.Model):
    itinerary_id = db.Column(db.String(36), db.ForeignKey("itinerary.id"), primary_key=True)
    traveler_id = db.Column(db.String(36), db.ForeignKey("traveler.id"), primary_key=True)


class ItinerarySupplier(db.Model):
    itinerary_id = db.Column(db.String(36), db.ForeignKey("itinerary.id"), primary_key=True)
    supplier_id = db.Column(db.String(36), db.ForeignKey("supplier.id"), primary_key=True)


# ================================
#       ALGORITHM
# ================================

def supplier_score_for_itinerary(itinerary):
    suppliers = Supplier.query.all()
    results = []

    for s in suppliers:
        score = 0

        # if supplier type matches activity_type
        if s.type and itinerary.activity_type:
            if s.type.lower() == itinerary.activity_type.lower():
                score += 3
            elif s.type.lower() in itinerary.activity_type.lower():
                score += 2

        # Popularity score
        usage_count = (
            db.session.query(func.count(ItinerarySupplier.itinerary_id))
            .filter(ItinerarySupplier.supplier_id == s.id)
            .scalar()
        )

        score += min(usage_count, 5)

        results.append((s, score))

    results.sort(key=lambda x: x[1], reverse=True)
    return results
