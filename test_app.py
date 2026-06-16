import unittest
import os
import tempfile
import json
import db

# Override database path for testing
TEST_DB_PATH = os.path.join(os.path.dirname(__file__), 'test_crm.db')
db.DATABASE_PATH = TEST_DB_PATH

# Now import app, so it uses the test database path when initializing
from app import app

class CRMTestCase(unittest.TestCase):
    
    def setUp(self):
        # Set up test database
        db.init_db()
        self.app = app.test_client()
        self.app.testing = True
        self.login('admin', 'admin')

    def login(self, username, role='admin', user_id=1):
        with self.app.session_transaction() as sess:
            sess['user_id'] = user_id
            sess['username'] = username
            sess['role'] = role

    def logout(self):
        with self.app.session_transaction() as sess:
            sess.clear()

    def tearDown(self):
        # Close connection and delete database file
        if os.path.exists(TEST_DB_PATH):
            try:
                os.remove(TEST_DB_PATH)
            except PermissionError:
                pass # SQLite might lock the file, clean up will happen on next run or os exit

    def test_contact_operations(self):
        # 1. Test empty database listing
        response = self.app.get('/api/contacts')
        self.assertEqual(response.status_code, 200)
        contacts = json.loads(response.data)
        self.assertEqual(len(contacts), 0)

        # 2. Test create valid contact
        response = self.app.post('/api/contacts', 
            data=json.dumps({'name': 'John Doe', 'email': 'john@example.com'}),
            content_type='application/json'
        )
        self.assertEqual(response.status_code, 201)
        data = json.loads(response.data)
        self.assertEqual(data['name'], 'John Doe')
        self.assertEqual(data['email'], 'john@example.com')
        self.assertEqual(data['status'], 'Neutral')
        self.assertIn('id', data)
        contact_id = data['id']

        # 3. Test list contacts after creation
        response = self.app.get('/api/contacts')
        self.assertEqual(response.status_code, 200)
        contacts = json.loads(response.data)
        self.assertEqual(len(contacts), 1)
        self.assertEqual(contacts[0]['name'], 'John Doe')

        # 4. Test duplicate email creation failure
        response = self.app.post('/api/contacts', 
            data=json.dumps({'name': 'Another John', 'email': 'john@example.com'}),
            content_type='application/json'
        )
        self.assertEqual(response.status_code, 409)

        # 5. Test validation failures
        response = self.app.post('/api/contacts', 
            data=json.dumps({'name': '', 'email': 'bad_email'}),
            content_type='application/json'
        )
        self.assertEqual(response.status_code, 400)

    def test_notes_and_sentiment_flow(self):
        # Create a contact first
        response = self.app.post('/api/contacts', 
            data=json.dumps({'name': 'Alice Smith', 'email': 'alice@example.com'}),
            content_type='application/json'
        )
        contact_id = json.loads(response.data)['id']

        # 1. Test empty notes list
        response = self.app.get(f'/api/contacts/{contact_id}/notes')
        self.assertEqual(response.status_code, 200)
        notes = json.loads(response.data)
        self.assertEqual(len(notes), 0)

        # 2. Add a positive note
        # "Customer was extremely happy with the project delivery!" -> expected high positive score
        response = self.app.post(f'/api/contacts/{contact_id}/notes',
            data=json.dumps({'note_text': 'Customer was extremely happy with the project delivery!'}),
            content_type='application/json'
        )
        self.assertEqual(response.status_code, 201)
        res_data = json.loads(response.data)
        self.assertGreater(res_data['note']['sentiment_score'], 0.2)
        # Should change contact status to Happy
        self.assertEqual(res_data['contact']['status'], 'Happy')

        # 3. Add an extremely negative note
        # "I am highly frustrated and angry. The product is broken and support is useless!" -> negative score
        response = self.app.post(f'/api/contacts/{contact_id}/notes',
            data=json.dumps({'note_text': 'I am highly frustrated and angry. The product is broken and support is useless!'}),
            content_type='application/json'
        )
        self.assertEqual(response.status_code, 201)
        res_data = json.loads(response.data)
        self.assertLess(res_data['note']['sentiment_score'], -0.25)
        # Should immediately flag the client as At Risk
        self.assertEqual(res_data['contact']['status'], 'At Risk')

        # 4. Fetch timeline and verify order (newest first)
        response = self.app.get(f'/api/contacts/{contact_id}/notes')
        self.assertEqual(response.status_code, 200)
        notes = json.loads(response.data)
        self.assertEqual(len(notes), 2)
        self.assertIn('broken', notes[0]['note_text']) # latest note first

    def test_dashboard_stats(self):
        # Create 1 happy and 1 neutral contact
        response = self.app.post('/api/contacts', 
            data=json.dumps({'name': 'Bob Happy', 'email': 'bob@example.com'}),
            content_type='application/json'
        )
        bob_id = json.loads(response.data)['id']
        self.app.post(f'/api/contacts/{bob_id}/notes',
            data=json.dumps({'note_text': 'This is absolutely wonderful and great!'}),
            content_type='application/json'
        )

        response = self.app.post('/api/contacts', 
            data=json.dumps({'name': 'Charlie Neutral', 'email': 'charlie@example.com'}),
            content_type='application/json'
        )
        
        # Query global stats
        response = self.app.get('/api/stats')
        self.assertEqual(response.status_code, 200)
        stats = json.loads(response.data)
        self.assertEqual(stats['total'], 2)
        self.assertEqual(stats['happy'], 1)
        self.assertEqual(stats['neutral'], 1)
        self.assertEqual(stats['at_risk'], 0)

    def test_page_rendering_and_recent_notes(self):
        # 1. Create a contact to test detail page rendering
        response = self.app.post('/api/contacts', 
            data=json.dumps({'name': 'Page Tester', 'email': 'page@example.com'}),
            content_type='application/json'
        )
        contact_id = json.loads(response.data)['id']

        # Log a note for recent feed testing
        self.app.post(f'/api/contacts/{contact_id}/notes',
            data=json.dumps({'note_text': 'Rendering test interaction notes'}),
            content_type='application/json'
        )

        # 2. Test rendering all pages
        pages = ['/', '/contacts', f'/contacts/{contact_id}', '/analytics']
        for page in pages:
            response = self.app.get(page)
            self.assertEqual(response.status_code, 200)

        # 3. Test non-existent contact detail rendering
        response = self.app.get('/contacts/9999')
        self.assertEqual(response.status_code, 404)

        # 4. Test recent notes API
        response = self.app.get('/api/notes/recent?limit=2')
        self.assertEqual(response.status_code, 200)
        recent = json.loads(response.data)
        self.assertEqual(len(recent), 1)
        self.assertEqual(recent[0]['note_text'], 'Rendering test interaction notes')
        self.assertEqual(recent[0]['contact_name'], 'Page Tester')

    def test_chatbot_flow(self):
        # 1. Create contact
        response = self.app.post('/api/contacts', 
            data=json.dumps({'name': 'Chat Client', 'email': 'chat_client@example.com'}),
            content_type='application/json'
        )
        contact_id = json.loads(response.data)['id']

        # 2. Test chat page renders (without greeting)
        response = self.app.get(f'/contacts/{contact_id}/chat')
        self.assertEqual(response.status_code, 200)
        self.assertNotIn(b"Proactive Support Assistant", response.data)

        # 2b. Make client At Risk with a specific keyword note (latency)
        response = self.app.post(f'/api/contacts/{contact_id}/notes',
            data=json.dumps({'note_text': 'This is terrible. The latency is very high and database is extremely slow!'}),
            content_type='application/json'
        )
        self.assertEqual(response.status_code, 201)
        res_data = json.loads(response.data)
        self.assertEqual(res_data['contact']['status'], 'At Risk')

        # 2c. Test chat page renders with personalized greeting for At Risk client
        response = self.app.get(f'/contacts/{contact_id}/chat')
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"Proactive Support Assistant", response.data)
        self.assertIn(b"database latency and query slowness", response.data)

        # 3. Test chatbot responses
        # Test slowness keyword (starts database slowness troubleshooting)
        response = self.app.post(f'/api/contacts/{contact_id}/chat',
            data=json.dumps({'message': 'My database is running extremely slow'}),
            content_type='application/json'
        )
        self.assertEqual(response.status_code, 200)
        data = json.loads(response.data)
        self.assertIn('database slowness', data['reply'])
        self.assertIn('indexes', data['reply'])
        self.assertFalse(data['unlock_review'])

        # Test auth keyword (switches focus to API authentication)
        response = self.app.post(f'/api/contacts/{contact_id}/chat',
            data=json.dumps({'message': 'I keep getting 401 integration errors'}),
            content_type='application/json'
        )
        self.assertEqual(response.status_code, 200)
        data = json.loads(response.data)
        self.assertIn('API authentication', data['reply'])
        self.assertFalse(data['unlock_review'])

        # Test greeting response (personalized to active API authentication issue)
        response = self.app.post(f'/api/contacts/{contact_id}/chat',
            data=json.dumps({'message': 'Hello there'}),
            content_type='application/json'
        )
        self.assertEqual(response.status_code, 200)
        data = json.loads(response.data)
        self.assertIn('AURA Support Assistant', data['reply'])
        self.assertIn('Hello!', data['reply'])
        self.assertIn('API authentication', data['reply'])
        self.assertFalse(data['unlock_review'])

        # Test negative confirmation response (advances steps for API authentication)
        response = self.app.post(f'/api/contacts/{contact_id}/chat',
            data=json.dumps({'message': 'No, it still does not work.'}),
            content_type='application/json'
        )
        self.assertEqual(response.status_code, 200)
        data = json.loads(response.data)
        self.assertIn("API token", data['reply']) # should offer Step 2 of API auth
        self.assertFalse(data['unlock_review'])

        # Test positive confirmation response (resolves issue and flags unlock)
        response = self.app.post(f'/api/contacts/{contact_id}/chat',
            data=json.dumps({'message': 'Okay, that worked! Thanks!'}),
            content_type='application/json'
        )
        self.assertEqual(response.status_code, 200)
        data = json.loads(response.data)
        self.assertIn('Wonderful!', data['reply'])
        self.assertTrue(data['unlock_review'])

        # Test generic fallback response after resolution (which reminds user of resolution state)
        response = self.app.post(f'/api/contacts/{contact_id}/chat',
            data=json.dumps({'message': 'xyz123abc'}),
            content_type='application/json'
        )
        self.assertEqual(response.status_code, 200)
        data = json.loads(response.data)
        self.assertIn('updated review', data['reply'])

        # 4. Test client submitting feedback review logs notes and changes status
        response = self.app.post(f'/api/contacts/{contact_id}/notes',
            data=json.dumps({'note_text': 'The support chatbot solved my issue! Extremely helpful and happy!'}),
            content_type='application/json'
        )
        self.assertEqual(response.status_code, 201)
        res_data = json.loads(response.data)
        self.assertEqual(res_data['contact']['status'], 'Happy')

    def test_websocket_configuration(self):
        from app import socketio
        
        # Verify that all required websocket events are registered on the root namespace
        self.assertIn('connect', socketio.server.handlers['/'])
        self.assertIn('join_chat', socketio.server.handlers['/'])
        self.assertIn('leave_chat', socketio.server.handlers['/'])

    def test_authentication_and_rbac(self):
        # 1. Test unauthenticated redirects & errors
        self.logout()
        
        # Pages redirect to login
        response = self.app.get('/')
        self.assertEqual(response.status_code, 302)
        self.assertIn('/login', response.headers['Location'])
        
        # API endpoints return 401
        response = self.app.get('/api/contacts')
        self.assertEqual(response.status_code, 401)
        data = json.loads(response.data)
        self.assertIn('error', data)
        self.assertIn('log in', data['error'].lower())

        # 2. Test staff role access
        self.login('staff_user', 'staff')
        
        # Dashboard is accessible
        response = self.app.get('/')
        self.assertEqual(response.status_code, 200)
        
        # Analytics is forbidden (403)
        response = self.app.get('/analytics')
        self.assertEqual(response.status_code, 403)
        
        # API delete is forbidden (403)
        response = self.app.delete('/api/contacts/1')
        self.assertEqual(response.status_code, 403)
        
        # 3. Test admin role access
        self.login('admin_user', 'admin')
        
        # Create a contact to delete
        response = self.app.post('/api/contacts', 
            data=json.dumps({'name': 'To Delete', 'email': 'delete@example.com'}),
            content_type='application/json'
        )
        contact_id = json.loads(response.data)['id']
        
        # Analytics is accessible
        response = self.app.get('/analytics')
        self.assertEqual(response.status_code, 200)
        
        # Delete contact is allowed (200)
        response = self.app.delete(f'/api/contacts/{contact_id}')
        self.assertEqual(response.status_code, 200)
        data = json.loads(response.data)
        self.assertEqual(data['contact_id'], contact_id)
        
        # Verify it is deleted from the DB
        response = self.app.get('/api/contacts')
        contacts = json.loads(response.data)
        self.assertNotIn('delete@example.com', [c['email'] for c in contacts])

    def test_user_registration_flow(self):
        self.logout()
        
        # 1. Test registration page renders
        response = self.app.get('/register')
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"Create Account", response.data)
        
        # 2. Test registration failure: mismatched passwords
        response = self.app.post('/register', data={
            'username': 'new_user',
            'password': 'password123',
            'password_confirm': 'password321',
            'role': 'staff'
        })
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"Passwords do not match", response.data)
        
        # 3. Test registration failure: existing username (MANMEET)
        response = self.app.post('/register', data={
            'username': 'MANMEET',
            'password': 'password123',
            'password_confirm': 'password123',
            'role': 'staff'
        })
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"Username is already taken", response.data)
        
        # 4. Test registration success: new staff user
        response = self.app.post('/register', data={
            'username': 'unique_staff',
            'password': 'password123',
            'password_confirm': 'password123',
            'role': 'staff'
        })
        self.assertEqual(response.status_code, 302)
        self.assertIn('/login', response.headers['Location'])
        
        # Verify user exists in the database
        user = db.get_user_by_username('unique_staff')
        self.assertIsNotNone(user)
        self.assertEqual(user['role'], 'staff')
        
        # 5. Test registration failure: registering as admin is restricted
        response = self.app.post('/register', data={
            'username': 'unique_admin',
            'password': 'password123',
            'password_confirm': 'password123',
            'role': 'admin'
        })
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"Admin registration is restricted", response.data)
        
        # Verify user does NOT exist in the database
        user = db.get_user_by_username('unique_admin')
        self.assertIsNone(user)

if __name__ == '__main__':
    unittest.main()
