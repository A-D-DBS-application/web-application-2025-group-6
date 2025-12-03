import os

class Config:
    SECRET_KEY = os.environ.get("SECRET_KEY") or "change_me"
    SQLALCHEMY_DATABASE_URI = "postgresql://postgres:wyBuDBeVOy2kW8nV@aws-1-eu-central-1.pooler.supabase.com:5432/postgres"
    SQLALCHEMY_TRACK_MODIFICATIONS = False
