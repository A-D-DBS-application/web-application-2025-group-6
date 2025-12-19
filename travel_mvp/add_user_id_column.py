"""
Script om handmatig de user_id kolom toe te voegen aan de itinerary tabel.
Gebruik dit alleen als de migratie niet werkt.
Run dit script met: python add_user_id_column.py
"""
from app import create_app, db
from sqlalchemy import text

app = create_app()

with app.app_context():
    try:
        print("=" * 60)
        print("Adding user_id column to itinerary table...")
        print("=" * 60)
        
        # Check if column already exists (PostgreSQL compatible)
        result = db.session.execute(text("""
            SELECT column_name 
            FROM information_schema.columns 
            WHERE table_schema = 'public' 
            AND table_name = 'itinerary' 
            AND column_name = 'user_id'
        """))
        
        if result.fetchone():
            print("✓ The user_id column already exists in the itinerary table.")
            print("✓ You can now save trips to your account!")
        else:
            print("Column does not exist. Adding it now...")
            
            # Add the column (PostgreSQL syntax)
            db.session.execute(text("""
                ALTER TABLE itinerary 
                ADD COLUMN IF NOT EXISTS user_id INTEGER
            """))
            print("✓ Column added successfully.")
            
            # Check if foreign key constraint already exists
            fk_check = db.session.execute(text("""
                SELECT constraint_name 
                FROM information_schema.table_constraints 
                WHERE table_schema = 'public' 
                AND table_name = 'itinerary' 
                AND constraint_type = 'FOREIGN KEY'
                AND constraint_name = 'fk_itinerary_user'
            """))
            
            if fk_check.fetchone():
                print("✓ Foreign key constraint already exists.")
            else:
                # Add foreign key constraint
                try:
                    db.session.execute(text("""
                        ALTER TABLE itinerary 
                        ADD CONSTRAINT fk_itinerary_user 
                        FOREIGN KEY (user_id) REFERENCES users(user_id)
                    """))
                    print("✓ Foreign key constraint added.")
                except Exception as fk_error:
                    error_msg = str(fk_error)
                    if "already exists" in error_msg.lower():
                        print("✓ Foreign key constraint already exists.")
                    else:
                        print(f"⚠ Warning: Could not add foreign key constraint: {fk_error}")
                        print("  The column was added, but the foreign key constraint failed.")
                        print("  This might be okay if there are data issues.")
            
            db.session.commit()
            print("=" * 60)
            print("✓ SUCCESS! The user_id column has been added!")
            print("✓ You can now save trips to your account using the 'Save Trip' button.")
            print("=" * 60)
            
    except Exception as e:
        db.session.rollback()
        print("=" * 60)
        print(f"✗ ERROR: {e}")
        print("=" * 60)
        print("\nPlease check:")
        print("1. That you're connected to the database")
        print("2. That you have the necessary permissions")
        print("3. That the itinerary table exists")
        print("4. That the users table exists")
        import traceback
        traceback.print_exc()
        raise

