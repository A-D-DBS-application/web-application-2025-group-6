import os

class Config:
    SECRET_KEY = os.environ.get("SECRET_KEY") or "change_me"

    # Vul hier JE ECHTE DATABASE PASSWORD in tussen de dubbele quotes
    SQLALCHEMY_DATABASE_URI = "postgresql://postgres:30wFSILqx3dVYNgX@db.dfpsbewjkvhrietohwes.supabase.co:5432/postgres?sslmode=require"

    SQLALCHEMY_TRACK_MODIFICATIONS = False
