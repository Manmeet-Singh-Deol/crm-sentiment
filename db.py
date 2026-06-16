import sqlite3
import os
from werkzeug.security import generate_password_hash, check_password_hash

DATABASE_PATH = os.path.join(os.path.dirname(__file__), 'crm.db')

def get_db_connection():
    conn = sqlite3.connect(DATABASE_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON;")
    return conn

def seed_default_users(cursor):
    # Set custom requested admin username and password
    admin_username = "MANMEET"
    admin_password = "1234567890"

    # Delete any legacy admin role accounts that don't match the new custom account
    cursor.execute("DELETE FROM users WHERE role = 'admin' AND username != ?", (admin_username,))

    cursor.execute("SELECT COUNT(*) FROM users WHERE username = ?", (admin_username,))
    if cursor.fetchone()[0] == 0:
        admin_pw_hash = generate_password_hash(admin_password)
        cursor.execute("INSERT INTO users (username, password_hash, role) VALUES (?, ?, ?)", (admin_username, admin_pw_hash, "admin"))
        
        # Write to admin_credentials.txt in the same directory
        creds_path = os.path.join(os.path.dirname(__file__), 'admin_credentials.txt')
        with open(creds_path, 'w') as f:
            f.write(f"AURA CRM Admin Setup\n")
            f.write(f"====================\n")
            f.write(f"Username: {admin_username}\n")
            f.write(f"Password: {admin_password}\n")
            f.write(f"Role: admin\n")
            
        print("\n" + "="*60)
        print("[AURA CRM] SPECIFIED ADMIN CREDENTIALS SEEDED:")
        print(f"  Username: {admin_username}")
        print(f"  Password: {admin_password}")
        print(f"  Saved to: {creds_path}")
        print("="*60 + "\n")

    cursor.execute("SELECT COUNT(*) FROM users WHERE username = 'staff'")
    if cursor.fetchone()[0] == 0:
        staff_pw = generate_password_hash("staff123")
        cursor.execute("INSERT INTO users (username, password_hash, role) VALUES (?, ?, ?)", ("staff", staff_pw, "staff"))

def init_db():
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # Create contacts table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS contacts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            email TEXT UNIQUE NOT NULL,
            status TEXT NOT NULL DEFAULT 'Neutral'
        )
    ''')
    
    # Create notes table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS notes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            contact_id INTEGER NOT NULL,
            note_text TEXT NOT NULL,
            sentiment_score REAL NOT NULL,
            date DATETIME DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (contact_id) REFERENCES contacts (id) ON DELETE CASCADE
        )
    ''')
    
    # Create users table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            role TEXT NOT NULL
        )
    ''')
    
    seed_default_users(cursor)
    
    conn.commit()
    conn.close()

def add_contact(name, email):
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute(
            "INSERT INTO contacts (name, email, status) VALUES (?, ?, 'Neutral')",
            (name, email)
        )
        conn.commit()
        contact_id = cursor.lastrowid
        return contact_id
    except sqlite3.IntegrityError:
        return None
    finally:
        conn.close()

def get_all_contacts():
    conn = get_db_connection()
    cursor = conn.cursor()
    
    query = """
        SELECT c.*, n.note_text AS last_note_text, n.date AS last_note_date, n.sentiment_score AS last_note_sentiment
        FROM contacts c
        LEFT JOIN (
            SELECT contact_id, note_text, date, sentiment_score,
                   ROW_NUMBER() OVER(PARTITION BY contact_id ORDER BY date DESC, id DESC) as rn
            FROM notes
        ) n ON c.id = n.contact_id AND n.rn = 1
        ORDER BY c.name ASC
    """
    cursor.execute(query)
    contacts = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return contacts

def get_contact_by_id(contact_id):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM contacts WHERE id = ?", (contact_id,))
    row = cursor.fetchone()
    conn.close()
    return dict(row) if row else None

def get_contact_by_email(email):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM contacts WHERE email = ?", (email,))
    row = cursor.fetchone()
    conn.close()
    return dict(row) if row else None

def update_contact_status(contact_id, status):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(
        "UPDATE contacts SET status = ? WHERE id = ?",
        (status, contact_id)
    )
    conn.commit()
    conn.close()

def add_note(contact_id, note_text, sentiment_score):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO notes (contact_id, note_text, sentiment_score) VALUES (?, ?, ?)",
        (contact_id, note_text, sentiment_score)
    )
    conn.commit()
    note_id = cursor.lastrowid
    conn.close()
    return note_id

def get_notes_for_contact(contact_id):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(
        "SELECT * FROM notes WHERE contact_id = ? ORDER BY date DESC, id DESC",
        (contact_id,)
    )
    notes = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return notes

def get_db_stats():
    conn = get_db_connection()
    cursor = conn.cursor()
    
    cursor.execute("SELECT COUNT(*) FROM contacts")
    total_contacts = cursor.fetchone()[0]
    
    cursor.execute("SELECT COUNT(*) FROM contacts WHERE status = 'Happy'")
    happy_contacts = cursor.fetchone()[0]
    
    cursor.execute("SELECT COUNT(*) FROM contacts WHERE status = 'Neutral'")
    neutral_contacts = cursor.fetchone()[0]
    
    cursor.execute("SELECT COUNT(*) FROM contacts WHERE status = 'At Risk'")
    at_risk_contacts = cursor.fetchone()[0]
    
    conn.close()
    
    return {
        'total': total_contacts,
        'happy': happy_contacts,
        'neutral': neutral_contacts,
        'at_risk': at_risk_contacts
    }

def get_recent_notes(limit=5):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT n.*, c.name as contact_name, c.email as contact_email
        FROM notes n
        JOIN contacts c ON n.contact_id = c.id
        ORDER BY n.date DESC, n.id DESC
        LIMIT ?
    """, (limit,))
    notes = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return notes

def add_user(username, password, role):
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        pw_hash = generate_password_hash(password)
        cursor.execute(
            "INSERT INTO users (username, password_hash, role) VALUES (?, ?, ?)",
            (username, pw_hash, role)
        )
        conn.commit()
        user_id = cursor.lastrowid
        return user_id
    except sqlite3.IntegrityError:
        return None
    finally:
        conn.close()

def get_user_by_username(username):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM users WHERE username = ?", (username,))
    row = cursor.fetchone()
    conn.close()
    return dict(row) if row else None

def authenticate_user(username, password):
    user = get_user_by_username(username)
    if user and check_password_hash(user['password_hash'], password):
        return user
    return None

def delete_contact(contact_id):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM contacts WHERE id = ?", (contact_id,))
    conn.commit()
    conn.close()
    return True

def get_admin_setup_credentials():
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
