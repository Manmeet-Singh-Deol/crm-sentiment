import os
from datetime import datetime, timezone
from pymongo import MongoClient, ReturnDocument, DESCENDING
from pymongo.errors import DuplicateKeyError
from werkzeug.security import generate_password_hash, check_password_hash

# MongoDB Connection Configuration
# Set MONGO_URI environment variable on Render / locally to override the default
MONGO_URI = os.environ.get(
    "MONGO_URI",
    "mongodb+srv://Manmeet:7017354872@cluster0.70jqrfq.mongodb.net/?appName=Cluster0"
)
DB_NAME = os.environ.get("MONGO_DB_NAME", "aura_crm")

_client = None
_db = None


def get_db():
    """Get the MongoDB database instance (lazy singleton)."""
    global _client, _db
    if _db is None:
        _client = MongoClient(MONGO_URI)
        _db = _client[DB_NAME]
    return _db


def close_db():
    """Close the MongoDB client connection."""
    global _client, _db
    if _client:
        _client.close()
        _client = None
        _db = None


def _next_id(collection_name):
    """Atomically increment and return the next integer ID for a collection.
    Uses a 'counters' collection to simulate SQL AUTO_INCREMENT."""
    database = get_db()
    result = database.counters.find_one_and_update(
        {'_id': collection_name},
        {'$inc': {'seq': 1}},
        upsert=True,
        return_document=ReturnDocument.AFTER
    )
    return result['seq']


def _doc_to_dict(doc):
    """Convert a MongoDB document to a plain dict.
    Removes the internal _id field and formats datetime objects as strings."""
    if doc is None:
        return None
    d = dict(doc)
    d.pop('_id', None)
    # Convert datetime objects to string for JSON/template compatibility
    if 'date' in d and isinstance(d['date'], datetime):
        d['date'] = d['date'].strftime('%Y-%m-%d %H:%M:%S')
    return d


# ---------------------------------------------------------------------------
# Database Initialization & Seeding
# ---------------------------------------------------------------------------

def seed_default_users():
    """Seed or update the default admin and staff accounts."""
    database = get_db()

    # Custom admin credentials from environment variables (or defaults)
    admin_username = os.environ.get("ADMIN_USERNAME", "MANMEET")
    admin_password = os.environ.get("ADMIN_PASSWORD", "1234567890")

    # Delete any legacy admin role accounts that don't match the new custom account
    database.users.delete_many({'role': 'admin', 'username': {'$ne': admin_username}})

    admin_pw_hash = generate_password_hash(admin_password)

    existing = database.users.find_one({'username': admin_username})
    if not existing:
        next_id = _next_id('users')
        database.users.insert_one({
            'id': next_id,
            'username': admin_username,
            'password_hash': admin_pw_hash,
            'role': 'admin'
        })
    else:
        database.users.update_one(
            {'username': admin_username},
            {'$set': {'password_hash': admin_pw_hash}}
        )

    # Write to admin_credentials.txt in the same directory
    creds_path = os.path.join(os.path.dirname(__file__), 'admin_credentials.txt')
    with open(creds_path, 'w') as f:
        f.write(f"AURA CRM Admin Setup\n")
        f.write(f"====================\n")
        f.write(f"Username: {admin_username}\n")
        f.write(f"Password: {admin_password}\n")
        f.write(f"Role: admin\n")

    print("\n" + "=" * 60)
    print("[AURA CRM] SPECIFIED ADMIN CREDENTIALS SEEDED/UPDATED:")
    print(f"  Username: {admin_username}")
    print(f"  Password: {admin_password}")
    print(f"  Saved to: {creds_path}")
    print("=" * 60 + "\n")

    # Seed default staff if not exists
    if not database.users.find_one({'username': 'staff'}):
        staff_pw = generate_password_hash("staff123")
        next_id = _next_id('users')
        database.users.insert_one({
            'id': next_id,
            'username': 'staff',
            'password_hash': staff_pw,
            'role': 'staff'
        })


def init_db():
    """Initialize MongoDB collections and indexes."""
    database = get_db()

    # Create unique indexes (idempotent — safe to call multiple times)
    database.contacts.create_index('id', unique=True)
    database.contacts.create_index('email', unique=True)
    database.users.create_index('id', unique=True)
    database.users.create_index('username', unique=True)
    database.notes.create_index('id', unique=True)
    database.notes.create_index('contact_id')

    seed_default_users()


# ---------------------------------------------------------------------------
# Contacts CRUD
# ---------------------------------------------------------------------------

def add_contact(name, email):
    database = get_db()
    try:
        next_id = _next_id('contacts')
        database.contacts.insert_one({
            'id': next_id,
            'name': name,
            'email': email,
            'status': 'Neutral'
        })
        return next_id
    except DuplicateKeyError:
        return None


def get_all_contacts():
    """Retrieve all contacts with their latest note (MongoDB aggregation pipeline).
    Equivalent to the SQLite LEFT JOIN + ROW_NUMBER query."""
    database = get_db()
    pipeline = [
        # Join with notes collection
        {
            '$lookup': {
                'from': 'notes',
                'localField': 'id',
                'foreignField': 'contact_id',
                'as': 'all_notes'
            }
        },
        # Sort the embedded notes array (newest first)
        {
            '$addFields': {
                'sorted_notes': {
                    '$sortArray': {
                        'input': '$all_notes',
                        'sortBy': {'date': -1, 'id': -1}
                    }
                }
            }
        },
        # Extract the latest note's fields (equivalent to ROW_NUMBER = 1)
        {
            '$addFields': {
                'last_note_text': {
                    '$ifNull': [{'$arrayElemAt': ['$sorted_notes.note_text', 0]}, None]
                },
                'last_note_date': {
                    '$ifNull': [{'$arrayElemAt': ['$sorted_notes.date', 0]}, None]
                },
                'last_note_sentiment': {
                    '$ifNull': [{'$arrayElemAt': ['$sorted_notes.sentiment_score', 0]}, None]
                }
            }
        },
        # Project only the fields we need (exclude internal fields)
        {
            '$project': {
                '_id': 0,
                'id': 1,
                'name': 1,
                'email': 1,
                'status': 1,
                'last_note_text': 1,
                'last_note_date': 1,
                'last_note_sentiment': 1
            }
        },
        # Sort alphabetically by name
        {'$sort': {'name': 1}}
    ]

    results = list(database.contacts.aggregate(pipeline))
    # Convert datetime objects to strings
    for r in results:
        if isinstance(r.get('last_note_date'), datetime):
            r['last_note_date'] = r['last_note_date'].strftime('%Y-%m-%d %H:%M:%S')
    return results


def get_contact_by_id(contact_id):
    database = get_db()
    doc = database.contacts.find_one({'id': contact_id})
    return _doc_to_dict(doc)


def get_contact_by_email(email):
    database = get_db()
    doc = database.contacts.find_one({'email': email})
    return _doc_to_dict(doc)


def update_contact_status(contact_id, status):
    database = get_db()
    database.contacts.update_one(
        {'id': contact_id},
        {'$set': {'status': status}}
    )


def delete_contact(contact_id):
    """Delete a contact and all associated notes (manual cascade).
    MongoDB does not have ON DELETE CASCADE, so we delete notes explicitly."""
    database = get_db()
    database.notes.delete_many({'contact_id': contact_id})
    database.contacts.delete_one({'id': contact_id})
    return True


# ---------------------------------------------------------------------------
# Notes CRUD
# ---------------------------------------------------------------------------

def add_note(contact_id, note_text, sentiment_score):
    database = get_db()
    next_id = _next_id('notes')
    database.notes.insert_one({
        'id': next_id,
        'contact_id': contact_id,
        'note_text': note_text,
        'sentiment_score': sentiment_score,
        'date': datetime.now(timezone.utc)
    })
    return next_id


def get_notes_for_contact(contact_id):
    database = get_db()
    cursor = database.notes.find(
        {'contact_id': contact_id},
        {'_id': 0}
    ).sort([('date', DESCENDING), ('id', DESCENDING)])
    return [_doc_to_dict(doc) for doc in cursor]


def get_recent_notes(limit=5):
    """Get the most recent notes across all contacts, joined with contact info.
    Equivalent to the SQLite JOIN + ORDER BY + LIMIT query."""
    database = get_db()
    pipeline = [
        {'$sort': {'date': -1, 'id': -1}},
        {'$limit': limit},
        # Join with contacts to get name and email
        {
            '$lookup': {
                'from': 'contacts',
                'localField': 'contact_id',
                'foreignField': 'id',
                'as': 'contact_info'
            }
        },
        {'$unwind': '$contact_info'},
        {
            '$addFields': {
                'contact_name': '$contact_info.name',
                'contact_email': '$contact_info.email'
            }
        },
        {
            '$project': {
                '_id': 0,
                'contact_info': 0
            }
        }
    ]
    results = list(database.notes.aggregate(pipeline))
    for r in results:
        if isinstance(r.get('date'), datetime):
            r['date'] = r['date'].strftime('%Y-%m-%d %H:%M:%S')
    return results


# ---------------------------------------------------------------------------
# Dashboard Stats
# ---------------------------------------------------------------------------

def get_db_stats():
    database = get_db()
    total = database.contacts.count_documents({})
    happy = database.contacts.count_documents({'status': 'Happy'})
    neutral = database.contacts.count_documents({'status': 'Neutral'})
    at_risk = database.contacts.count_documents({'status': 'At Risk'})
    return {
        'total': total,
        'happy': happy,
        'neutral': neutral,
        'at_risk': at_risk
    }


# ---------------------------------------------------------------------------
# Users & Authentication
# ---------------------------------------------------------------------------

def add_user(username, password, role):
    database = get_db()
    try:
        pw_hash = generate_password_hash(password)
        next_id = _next_id('users')
        database.users.insert_one({
            'id': next_id,
            'username': username,
            'password_hash': pw_hash,
            'role': role
        })
        return next_id
    except DuplicateKeyError:
        return None


def get_user_by_username(username):
    database = get_db()
    doc = database.users.find_one({'username': username})
    return _doc_to_dict(doc)


def authenticate_user(username, password):
    user = get_user_by_username(username)
    if user and check_password_hash(user['password_hash'], password):
        return user
    return None


def get_admin_setup_credentials():
    """Read admin credentials from file. This function does not touch the database."""
    creds_path = os.path.join(os.path.dirname(__file__), 'admin_credentials.txt')
    username = "MANMEET"
    password = "1234567890"
    if os.path.exists(creds_path):
        try:
            with open(creds_path, 'r') as f:
                lines = f.readlines()
                for line in lines:
                    if line.startswith("Username:"):
                        username = line.split("Username:")[1].strip()
                    elif line.startswith("Password:"):
                        password = line.split("Password:")[1].strip()
        except Exception:
            pass
    return username, password
