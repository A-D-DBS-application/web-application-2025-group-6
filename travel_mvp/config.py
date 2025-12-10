import os

class Config:
    SECRET_KEY = os.environ.get("SECRET_KEY") or "change_me"

    # Vul hier JE ECHTE DATABASE PASSWORD in tussen de dubbele quotes
    SQLALCHEMY_DATABASE_URI = "postgresql://postgres.dfpsbewjkvhrietohwes:30wFSILqx3dVYNgX@aws-1-eu-central-1.pooler.supabase.com:6543/postgres"

    SQLALCHEMY_TRACK_MODIFICATIONS = False

