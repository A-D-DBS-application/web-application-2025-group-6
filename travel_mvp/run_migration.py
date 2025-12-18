"""
Script om de database migratie uit te voeren voor user_id kolom in itinerary tabel.
Run dit script met: python run_migration.py
"""
from app import create_app, db
from flask_migrate import upgrade

app = create_app()

with app.app_context():
    print("Running database migrations...")
    try:
        # Run all pending migrations
        upgrade()
        print("✓ Migrations completed successfully!")
        print("✓ The user_id column has been added to the itinerary table.")
    except Exception as e:
        print(f"✗ Error running migrations: {e}")
        print("\nIf you see an error about the migration already being applied,")
        print("you can try running: flask db upgrade")
        raise
