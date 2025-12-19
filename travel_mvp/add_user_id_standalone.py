"""
Standalone script om de user_id kolom toe te voegen aan de itinerary tabel.
Dit script werkt zonder Flask dependencies - alleen psycopg2 nodig.
Run dit script met: python add_user_id_standalone.py
"""
import psycopg2
from urllib.parse import urlparse

# Database connection string uit config.py
DATABASE_URL = "postgresql://postgres.dfpsbewjkvhrietohwes:30wFSILqx3dVYNgX@aws-1-eu-central-1.pooler.supabase.com:6543/postgres"

def add_user_id_column():
    try:
        print("=" * 60)
        print("Connecting to database...")
        print("=" * 60)
        
        # Connect to database
        conn = psycopg2.connect(DATABASE_URL)
        cur = conn.cursor()
        
        # Check if column already exists
        cur.execute("""
            SELECT column_name 
            FROM information_schema.columns 
            WHERE table_schema = 'public' 
            AND table_name = 'itinerary' 
            AND column_name = 'user_id'
        """)
        
        if cur.fetchone():
            print("✓ The user_id column already exists in the itinerary table.")
            print("✓ You can now save trips to your account!")
        else:
            print("Column does not exist. Adding it now...")
            
            # Add the column
            cur.execute("""
                ALTER TABLE itinerary 
                ADD COLUMN user_id INTEGER
            """)
            print("✓ Column added successfully.")
            
            # Check if foreign key constraint already exists
            cur.execute("""
                SELECT constraint_name 
                FROM information_schema.table_constraints 
                WHERE table_schema = 'public' 
                AND table_name = 'itinerary' 
                AND constraint_type = 'FOREIGN KEY'
                AND constraint_name = 'fk_itinerary_user'
            """)
            
            if cur.fetchone():
                print("✓ Foreign key constraint already exists.")
            else:
                # Add foreign key constraint
                try:
                    cur.execute("""
                        ALTER TABLE itinerary 
                        ADD CONSTRAINT fk_itinerary_user 
                        FOREIGN KEY (user_id) REFERENCES users(user_id)
                    """)
                    print("✓ Foreign key constraint added.")
                except psycopg2.errors.DuplicateObject as e:
                    print("✓ Foreign key constraint already exists.")
                except Exception as fk_error:
                    print(f"⚠ Warning: Could not add foreign key constraint: {fk_error}")
                    print("  The column was added, but the foreign key constraint failed.")
                    print("  This might be okay if there are data issues.")
            
            conn.commit()
            print("=" * 60)
            print("✓ SUCCESS! The user_id column has been added!")
            print("✓ You can now save trips to your account using the 'Save Trip' button.")
            print("=" * 60)
        
        cur.close()
        conn.close()
        
    except psycopg2.OperationalError as e:
        print("=" * 60)
        print(f"✗ Database connection error: {e}")
        print("=" * 60)
        print("\nPlease check:")
        print("1. That you're connected to the internet")
        print("2. That the database URL is correct in config.py")
        raise
    except Exception as e:
        print("=" * 60)
        print(f"✗ ERROR: {e}")
        print("=" * 60)
        print("\nPlease check:")
        print("1. That you have psycopg2 installed: pip install psycopg2-binary")
        print("2. That the itinerary table exists")
        print("3. That the users table exists")
        import traceback
        traceback.print_exc()
        raise

if __name__ == "__main__":
    add_user_id_column()

