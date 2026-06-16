from flask import Flask, request, jsonify, render_template, session, redirect, url_for
from flask.ctx import RequestContext

# Monkey-patch RequestContext to add session setter for Flask-SocketIO compatibility in Flask 3
if hasattr(RequestContext, 'session'):
    prop = RequestContext.session
    if isinstance(prop, property) and prop.fset is None:
        RequestContext.session = property(
            prop.fget,
            lambda self, value: setattr(self, "_session", value)
        )

from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer
import db
from chatbot import LocalChatbot
from flask_socketio import SocketIO, emit
from functools import wraps

app = Flask(__name__)
app.secret_key = 'aura-secret-key-for-session-signing-12345'
analyzer = SentimentIntensityAnalyzer()
chatbot_engine = LocalChatbot()
socketio = SocketIO(app, cors_allowed_origins="*")

# Initialize Database
db.init_db()

# Decorators for Web Views
def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            return redirect(url_for('login_view'))
            
        # Restrict clients from viewing staff dashboard/directory/analytics
        if session.get('role') == 'client':
            if request.endpoint == 'contact_chat_view':
                target_id = kwargs.get('contact_id')
                if session.get('user_id') != target_id:
                    return render_template('403.html'), 403
            elif request.endpoint not in ['logout_view']:
                return redirect(url_for('contact_chat_view', contact_id=session.get('user_id')))
                
        return f(*args, **kwargs)
    return decorated_function

def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            return redirect(url_for('login_view'))
        if session.get('role') != 'admin':
            return render_template('403.html'), 403
        return f(*args, **kwargs)
    return decorated_function

# Decorators for JSON API Endpoints
def api_login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            return jsonify({'error': 'Unauthorized. Please log in.'}), 401
            
        # Restrict client API scopes
        if session.get('role') == 'client':
            if request.endpoint == 'chatbot_message':
                target_id = kwargs.get('contact_id')
                if session.get('user_id') != target_id:
                    return jsonify({'error': 'Forbidden.'}), 403
            elif request.endpoint == 'get_notes':
                target_id = kwargs.get('contact_id')
                if session.get('user_id') != target_id:
                    return jsonify({'error': 'Forbidden.'}), 403
            elif request.endpoint == 'add_note':
                target_id = kwargs.get('contact_id')
                if session.get('user_id') != target_id:
                    return jsonify({'error': 'Forbidden.'}), 403
            elif request.endpoint not in ['logout_view']:
                return jsonify({'error': 'Forbidden. Staff privileges required.'}), 403
                
        return f(*args, **kwargs)
    return decorated_function

def api_admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            return jsonify({'error': 'Unauthorized. Please log in.'}), 401
        if session.get('role') != 'admin':
            return jsonify({'error': 'Forbidden. Admin privileges required.'}), 403
        return f(*args, **kwargs)
    return decorated_function

@app.route('/login', methods=['GET', 'POST'])
def login_view():
    if 'user_id' in session:
        if session.get('role') == 'client':
            return redirect(url_for('contact_chat_view', contact_id=session.get('user_id')))
        return redirect(url_for('dashboard_view'))
        
    error = None
    if request.method == 'POST':
        client_email = request.form.get('client_email', '').strip()
        if client_email:
            # Client Login
            contact = db.get_contact_by_email(client_email)
            if contact:
                session['user_id'] = contact['id']
                session['username'] = contact['name']
                session['role'] = 'client'
                session['client_email'] = contact['email']
                return redirect(url_for('contact_chat_view', contact_id=contact['id']))
            else:
                error = "Client email not found. Please contact support or register as staff."
        else:
            # Staff Login
            username = request.form.get('username', '').strip()
            password = request.form.get('password', '').strip()
            
            user = db.authenticate_user(username, password)
            if user:
                session['user_id'] = user['id']
                session['username'] = user['username']
                session['role'] = user['role']
                return redirect(url_for('dashboard_view'))
            else:
                error = "Invalid username or password"
            
    admin_user, admin_pw = db.get_admin_setup_credentials()
    return render_template('login.html', error=error, admin_username=admin_user, admin_password=admin_pw)

@app.route('/logout')
def logout_view():
    session.clear()
    return redirect(url_for('login_view'))

@app.route('/register', methods=['GET', 'POST'])
def register_view():
    if 'user_id' in session:
        return redirect(url_for('dashboard_view'))
        
    error = None
    username = ''
    role = 'staff'
    client_name = ''
    client_email = ''
    
    if request.method == 'POST':
        client_email = request.form.get('client_email', '').strip()
        if client_email or 'client_name' in request.form:
            # Client Registration
            client_name = request.form.get('client_name', '').strip()
            
            if not client_name:
                error = "Full Name is required"
            elif not client_email:
                error = "Email address is required"
            elif '@' not in client_email or '.' not in client_email:
                error = "Invalid email format"
            else:
                # Check if contact email already exists
                existing = db.get_contact_by_email(client_email)
                if existing:
                    error = "Email address is already registered"
                else:
                    contact_id = db.add_contact(client_name, client_email)
                    if contact_id:
                        return redirect(url_for('login_view', success="Client account created successfully! Please log in."))
                    else:
                        error = "Failed to create client account. Please try again."
        else:
            # Staff Registration
            username = request.form.get('username', '').strip()
            password = request.form.get('password', '')
            password_confirm = request.form.get('password_confirm', '')
            role = request.form.get('role', 'staff').strip()
            
            if not username:
                error = "Username is required"
            elif not password:
                error = "Password is required"
            elif password != password_confirm:
                error = "Passwords do not match"
            elif role != 'staff':
                error = "Admin registration is restricted. Only Staff accounts can be registered."
            else:
                # Check if user already exists
                existing_user = db.get_user_by_username(username)
                if existing_user:
                    error = "Username is already taken"
                else:
                    user_id = db.add_user(username, password, role)
                    if user_id:
                        return redirect(url_for('login_view', success="Account created successfully! Please log in."))
                    else:
                        error = "Failed to create account. Please try again."
                    
    return render_template('register.html', error=error, username=username, role=role, client_name=client_name, client_email=client_email)

@app.route('/')
@login_required
def dashboard_view():
    return render_template('dashboard.html')

@app.route('/contacts')
@login_required
def contacts_view():
    return render_template('contacts.html')

@app.route('/contacts/<int:contact_id>')
@login_required
def contact_detail_view(contact_id):
    contact = db.get_contact_by_id(contact_id)
    if not contact:
        return render_template('404.html'), 404
    return render_template('contact_detail.html', contact=contact)

@app.route('/analytics')
@admin_required
def analytics_view():
    return render_template('analytics.html')

@app.route('/contacts/<int:contact_id>/chat')
@login_required
def contact_chat_view(contact_id):
    contact = db.get_contact_by_id(contact_id)
    if not contact:
        return render_template('404.html'), 404
        
    active_issue = None
    personalized_greeting = None
    
    if contact['status'] == 'At Risk':
        notes = db.get_notes_for_contact(contact_id)
        # Find the latest negative note
        neg_notes = [n for n in notes if n['sentiment_score'] <= -0.15]
        if neg_notes:
            lower_neg = neg_notes[0]['note_text'].lower()
            
            if any(k in lower_neg for k in ['slow', 'latency', 'speed', 'lag']):
                active_issue = "database slowness"
                issue_label = "database latency and query slowness"
                solution = "Create database indexes on columns used in query filters (e.g. run <code>CREATE INDEX idx_notes_contact ON notes(contact_id);</code>)."
            elif any(k in lower_neg for k in ['unauthorized', '401', 'api', 'token', 'auth']):
                active_issue = "API authentication"
                issue_label = "API authentication (401 unauthorized errors)"
                solution = "Verify that the header <code>Authorization: Bearer &lt;YOUR_API_KEY&gt;</code> is attached to all outbound requests."
            elif any(k in lower_neg for k in ['billing', 'card', 'pay', 'invoice']):
                active_issue = "billing and invoices"
                issue_label = "billing and invoice access"
                solution = "Go to <strong>Settings > Billing</strong> to update your billing details and retry the invoice payment."
            elif any(k in lower_neg for k in ['error', 'crash', 'bug', 'fail']):
                active_issue = "application crashes"
                issue_label = "application crashes or errors"
                solution = "Open browser DevTools (F12) to inspect the console tab for Javascript exceptions."
            else:
                issue_label = "recent service issues"
                solution = "Please describe the problem in detail so I can help walk you through the troubleshooting steps."
                
            personalized_greeting = (
                f"Hello {contact['name']}, I am AURA's Proactive Support Assistant. 🤖<br><br>"
                f"I noticed that you recently had trouble regarding <strong>{issue_label}</strong> and I want to help you fix this immediately!<br>"
                f"I sincerely apologize for the frustration this has caused.<br><br>"
                f"🛠️ <strong>Step 1:</strong> {solution}<br><br>"
                f"<em>Please let me know if these instructions resolved your issue, or if you need more help!</em>"
            )
            
    # Reset chat session state for this client
    chatbot_engine.reset_session(contact_id, contact['name'], active_issue)
    
    return render_template('chat.html', contact=contact, personalized_greeting=personalized_greeting)

@app.route('/api/contacts/<int:contact_id>/chat', methods=['POST'])
@api_login_required
def chatbot_message(contact_id):
    contact = db.get_contact_by_id(contact_id)
    if not contact:
        return jsonify({'error': 'Contact not found'}), 404
        
    data = request.get_json() or {}
    message = data.get('message', '').strip()
    
    if not message:
        return jsonify({'error': 'Message is required'}), 400
        
    reply, unlock_review = chatbot_engine.process_message(contact_id, contact['name'], message)
    
    return jsonify({'reply': reply, 'unlock_review': unlock_review})

@app.route('/api/notes/recent', methods=['GET'])
@api_login_required
def get_recent_notes_api():
    limit = request.args.get('limit', default=5, type=int)
    notes = db.get_recent_notes(limit=limit)
    return jsonify(notes)

@app.route('/api/contacts', methods=['GET'])
@api_login_required
def get_contacts():
    contacts = db.get_all_contacts()
    return jsonify(contacts)

@app.route('/api/contacts', methods=['POST'])
@api_login_required
def create_contact():
    data = request.get_json() or {}
    name = data.get('name', '').strip()
    email = data.get('email', '').strip()
    
    if not name or not email:
        return jsonify({'error': 'Name and Email are required'}), 400
        
    # Simple email check
    if '@' not in email or '.' not in email:
        return jsonify({'error': 'Invalid email format'}), 400
        
    existing = db.get_contact_by_email(email)
    if existing:
        return jsonify({'error': 'Contact with this email already exists'}), 409
        
    contact_id = db.add_contact(name, email)
    if contact_id:
        new_contact = db.get_contact_by_id(contact_id)
        return jsonify(new_contact), 201
    else:
        return jsonify({'error': 'Failed to create contact'}), 500

@app.route('/api/contacts/<int:contact_id>', methods=['DELETE'])
@api_admin_required
def delete_contact_api(contact_id):
    contact = db.get_contact_by_id(contact_id)
    if not contact:
        return jsonify({'error': 'Contact not found'}), 404
        
    db.delete_contact(contact_id)
    
    # Broadcast database update to dashboards via SocketIO
    stats = db.get_db_stats()
    socketio.emit('db_update', {
        'contact': {'id': contact_id, 'deleted': True},
        'stats': stats
    })
    
    return jsonify({'message': 'Contact deleted successfully', 'contact_id': contact_id})

@app.route('/api/contacts/<int:contact_id>/notes', methods=['GET'])
@api_login_required
def get_notes(contact_id):
    contact = db.get_contact_by_id(contact_id)
    if not contact:
        return jsonify({'error': 'Contact not found'}), 404
        
    notes = db.get_notes_for_contact(contact_id)
    return jsonify(notes)

@app.route('/api/contacts/<int:contact_id>/notes', methods=['POST'])
@api_login_required
def add_note(contact_id):
    contact = db.get_contact_by_id(contact_id)
    if not contact:
        return jsonify({'error': 'Contact not found'}), 404
        
    data = request.get_json() or {}
    note_text = data.get('note_text', '').strip()
    
    if not note_text:
        return jsonify({'error': 'Note text is required'}), 400
        
    # Analyze Sentiment using VADER
    # vaderSentiment returns polarity scores: pos, neu, neg, compound
    sentiment_result = analyzer.polarity_scores(note_text)
    sentiment_score = sentiment_result['compound']
    
    # Save the note
    db.add_note(contact_id, note_text, sentiment_score)
    
    # Determine new status based on sentiment history
    notes = db.get_notes_for_contact(contact_id)
    
    # Logic for status:
    # 1. If latest note is highly negative (compound <= -0.25), immediately mark "At Risk"
    # 2. Else if average compound score is negative (avg < -0.05), mark "At Risk"
    # 3. Else if average compound score is positive (avg >= 0.15), mark "Happy"
    # 4. Otherwise, "Neutral"
    
    if not notes:
        new_status = 'Neutral'
    else:
        latest_score = notes[0]['sentiment_score']
        avg_score = sum(n['sentiment_score'] for n in notes) / len(notes)
        
        if latest_score <= -0.25:
            new_status = 'At Risk'
        elif avg_score < -0.05:
            new_status = 'At Risk'
        elif avg_score >= 0.15:
            new_status = 'Happy'
        else:
            new_status = 'Neutral'
            
    db.update_contact_status(contact_id, new_status)
    
    updated_contact = db.get_contact_by_id(contact_id)
    
    # Emit real-time WebSocket update for dashboards
    stats = db.get_db_stats()
    socketio.emit('db_update', {
        'contact': updated_contact,
        'note': {
            'contact_id': contact_id,
            'note_text': note_text,
            'sentiment_score': sentiment_score,
            'date': 'Just now'
        },
        'stats': stats
    })
    
    return jsonify({
        'message': 'Note added successfully',
        'note': {
            'contact_id': contact_id,
            'note_text': note_text,
            'sentiment_score': sentiment_score
        },
        'contact': updated_contact
    }), 201

@app.route('/api/stats', methods=['GET'])
@api_login_required
def get_stats():
    stats = db.get_db_stats()
    return jsonify(stats)

@app.after_request
def add_header(response):
    response.headers['Cache-Control'] = 'no-store, no-cache, must-revalidate, post-check=0, pre-check=0, max-age=0'
    response.headers['Pragma'] = 'no-cache'
    response.headers['Expires'] = '-1'
    return response

# Active Chat Tracking
active_chats = {}

@socketio.on('connect')
def handle_connect():
    emit('active_chats_list', list(active_chats.keys()))

@socketio.on('join_chat')
def handle_join_chat(data):
    contact_id = data.get('contact_id')
    contact_name = data.get('contact_name')
    if contact_id:
        active_chats[contact_id] = contact_name
        socketio.emit('client_active_chat', {'contact_id': contact_id, 'contact_name': contact_name})

@socketio.on('leave_chat')
def handle_leave_chat(data):
    contact_id = data.get('contact_id')
    if contact_id in active_chats:
        del active_chats[contact_id]
        socketio.emit('client_inactive_chat', {'contact_id': contact_id})

if __name__ == '__main__':
    import os
    port = int(os.environ.get("PORT", 5000))
    socketio.run(app, debug=True, host='0.0.0.0', port=port, allow_unsafe_werkzeug=True)
