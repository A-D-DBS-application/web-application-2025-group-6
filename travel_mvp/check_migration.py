"""
Script om te controleren of de user_id kolom bestaat in de itinerary tabel.
Run dit script met: python check_migration.py
"""
from app import create_app, db
from sqlalchemy import text
from app.utils import check_column_exists

app = create_app()

with app.app_context():
    try:
        print("Checking if user_id column exists in itinerary table...")
        
        # Method 1: Using the utility function
        has_column = check_column_exists('itinerary', 'user_id')
        
        # Method 2: Direct SQL check
        result = db.session.execute(text("""
            SELECT column_name, data_type, is_nullable
            FROM information_schema.columns 
            WHERE table_name='itinerary' AND column_name='user_id'
        """))
        
        column_info = result.fetchone()
        
        if has_column and column_info:
            print("✓ SUCCESS! The user_id column exists in the itinerary table.")
            print(f"  Column type: {column_info[1]}")
            print(f"  Nullable: {column_info[2]}")
            print("\n✓ You can now use the 'Save Trip' button to save trips to your account!")
        else:
            print("✗ The user_id column does NOT exist yet.")
            print("\nPlease run one of these commands:")
            print("  1. flask db upgrade")
            print("  2. python run_migration.py")
            print("  3. python add_user_id_column.py")
            
    except Exception as e:
        print(f"✗ Error checking column: {e}")
        print("\nThis might indicate a database connection issue.")
        raise
