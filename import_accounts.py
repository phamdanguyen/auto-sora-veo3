from app.database import SessionLocal
from app.models import Account
import sys

# List from user request
EMAILS = [
    "khj68510@gmail.com",
    "phammjhkdbb23@gmail.com",
    "komh331@gmail.com"
]

PASSWORD = "Canhpk98@123"
PLATFORM = "sora"

def import_accounts():
    db = SessionLocal()
    count_added = 0
    count_skipped = 0
    
    print(f"Starting import of {len(EMAILS)} accounts...")
    
    for email in EMAILS:
        email = email.lower().strip()
        # Check if exists
        existing = db.query(Account).filter(Account.email == email).first()
        if existing:
            print(f"[SKIP] {email} already exists.")
            count_skipped += 1
            continue
        
        # Create new
        new_acc = Account(
            platform=PLATFORM,
            email=email,
            password=PASSWORD,
            status="live"
        )
        db.add(new_acc)
        print(f"[ADD] {email}")
        count_added += 1
    
    try:
        db.commit()
        print(f"\nImport Finished!")
        print(f"Added: {count_added}")
        print(f"Skipped: {count_skipped}")
    except Exception as e:
        print(f"Error committing to DB: {e}")
        db.rollback()
    finally:
        db.close()

if __name__ == "__main__":
    import_accounts()
