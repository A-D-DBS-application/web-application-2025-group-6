import os

class Config:
    SECRET_KEY = os.environ.get("SECRET_KEY") or "change_me"
    SQLALCHEMY_DATABASE_URI = "sqlite:///travel_mvp.db"
    SQLALCHEMY_TRACK_MODIFICATIONS = False
