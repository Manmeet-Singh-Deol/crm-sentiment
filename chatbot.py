from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer
import db

analyzer = SentimentIntensityAnalyzer()

# Troubleshooting steps for the 4 key categories
DIAGNOSTIC_STEPS = {
    "database slowness": [
        "Create database indexes on columns used in query filters (e.g. run <code>CREATE INDEX idx_notes_contact ON notes(contact_id);</code>).",
        "Implement SQLite connection pooling or ensure connections are closed immediately after query execution.",
        "Check for open database transactions or locked tables causing process blocking."
    ],
    "API authentication": [
        "Verify that the header <code>Authorization: Bearer &lt;YOUR_API_KEY&gt;</code> is attached to all outbound requests.",
        "Verify that the API token has not expired and matches the active environment configuration.",
        "Ensure your server auth middleware is expecting Bearer tokens rather than Basic Auth or sessions."
    ],
    "billing and invoices": [
        "Go to <strong>Settings > Billing</strong> to update your billing details and retry the invoice payment.",
        "Check the billing logs panel in settings to download official PDF invoice copies.",
        "Submit a billing support ticket in the portal for manual billing refunds."
    ],
    "application crashes": [
        "Open browser DevTools (F12) to inspect the console tab for Javascript exceptions.",
        "Clear browser cache and cookies, then try reloading the page.",
        "Check your server tracebacks and console output logs for uncaught exceptions or memory limits."
    ]
}

class ChatSession:
    def __init__(self, contact_name, active_issue=None):
        self.contact_name = contact_name
        self.active_issue = active_issue
        self.state = "GREETING"  # GREETING, TROUBLESHOOTING, RESOLVED
        self.current_step_index = 0
        self.history = []

class LocalChatbot:
    def __init__(self):
        self.sessions = {}

    def get_or_create_session(self, contact_id, contact_name, active_issue=None):
        if contact_id not in self.sessions:
            self.sessions[contact_id] = ChatSession(contact_name, active_issue)
        else:
            if active_issue:
                self.sessions[contact_id].active_issue = active_issue
        return self.sessions[contact_id]

    def reset_session(self, contact_id, contact_name, active_issue=None):
        self.sessions[contact_id] = ChatSession(contact_name, active_issue)
        return self.sessions[contact_id]

    def process_message(self, contact_id, contact_name, user_message):
        # 1. Retrieve or create session
        session = self.get_or_create_session(contact_id, contact_name)
        msg_lower = user_message.lower().strip()
        
        # 2. Analyze sentiment for frustration (VADER score <= -0.35)
        sentiment_res = analyzer.polarity_scores(user_message)
        frustrated = sentiment_res['compound'] <= -0.35
        
        apology_prefix = ""
        if frustrated:
            apology_prefix = "⚠️ <strong>I understand this is very frustrating and I apologize for the hassle. Let's get this sorted.</strong><br><br>"

        # 3. Detect category switch dynamically
        new_issue = None
        if any(k in msg_lower for k in ['slow', 'latency', 'speed', 'lag']):
            new_issue = "database slowness"
        elif any(k in msg_lower for k in ['unauthorized', '401', 'api', 'token', 'auth']):
            new_issue = "API authentication"
        elif any(k in msg_lower for k in ['billing', 'card', 'pay', 'invoice']):
            new_issue = "billing and invoices"
        elif any(k in msg_lower for k in ['error', 'crash', 'bug', 'fail']):
            new_issue = "application crashes"

        if new_issue and (new_issue != session.active_issue or session.state == "GREETING"):
            focus_str = f"Switching troubleshooting focus to **{new_issue}**" if (new_issue != session.active_issue and session.active_issue is not None) else f"Let's troubleshoot **{new_issue}**"
            session.active_issue = new_issue
            session.current_step_index = 0
            session.state = "TROUBLESHOOTING"
            steps = DIAGNOSTIC_STEPS[new_issue]
            reply = (f"{apology_prefix}{focus_str}.<br><br>"
                     f"🛠️ <strong>Step 1:</strong> {steps[0]}<br><br>"
                     f"<em>Did this step resolve the issue?</em>")
            return reply, False

        # Check if already resolved
        if session.state == "RESOLVED":
            reply = ("🎉 <strong>Troubleshooting Complete</strong>:<br><br>"
                     "The issue has already been resolved! Please take a moment to submit your updated review "
                     "in the card on the right so we can refresh your account standing in our database.")
            return reply, True

        # 4. Check for resolution / confirmations
        is_positive = any(k in msg_lower for k in ['yes', 'work', 'fixed', 'solved', 'resolved', 'thanks', 'thank you', 'helped', 'great', 'happy', 'awesome', 'perfect'])
        is_negative = any(k in msg_lower for k in ['no', 'not', 'didnt', "didn't", 'still', 'unable'])

        # Prioritize negations over positive matches (e.g. "not working" contains "work")
        if is_negative:
            if session.active_issue:
                steps = DIAGNOSTIC_STEPS.get(session.active_issue, [])
                session.current_step_index += 1
                session.state = "TROUBLESHOOTING"
                
                if session.current_step_index < len(steps):
                    reply = (f"{apology_prefix}I see. Let's try the next step:<br><br>"
                             f"🛠️ <strong>Step {session.current_step_index + 1}:</strong> {steps[session.current_step_index]}<br><br>"
                             f"<em>Did this step help, or are you still experiencing the issue?</em>")
                    return reply, False
                else:
                    session.state = "RESOLVED"
                    reply = (f"{apology_prefix}⚠️ <strong>I apologize, we have exhausted our automated troubleshooting steps.</strong><br><br>"
                             f"I have unlocked the review card on the right so you can log your feedback. "
                             f"I will escalate this immediately to a Senior support engineer to contact you directly.")
                    return reply, True
            else:
                reply = (f"{apology_prefix}I am here to help you resolve technical issues! Please tell me if you are experiencing: "
                         f"<strong>database slowness</strong>, <strong>API 401 unauthorized errors</strong>, "
                         f"<strong>billing/invoices issues</strong>, or <strong>application crashes</strong>.")
                return reply, False

        elif is_positive:
            session.state = "RESOLVED"
            reply = (f"🎉 <strong>Wonderful!</strong> I am thrilled that resolved the issue for you.<br><br>"
                     f"Please take a moment to submit your updated review in the card on the right so we can refresh your account standing in our database.")
            return reply, True

        # 5. Handle greetings
        if any(k in msg_lower for k in ['hello', 'hi', 'hey', 'greetings']):
            if session.active_issue:
                reply = (f"{apology_prefix}👋 <strong>AURA Support Assistant</strong>:<br>"
                         f"Hello! I am here to help you resolve your current issue regarding <strong>{session.active_issue}</strong>.<br><br>"
                         f"We were on Step {session.current_step_index + 1}: <code>{DIAGNOSTIC_STEPS[session.active_issue][session.current_step_index]}</code>.<br><br>"
                         f"Please let me know if this step solved it, or if we should move to the next step.")
            else:
                reply = (f"👋 <strong>AURA Support Assistant</strong>:<br>"
                         f"Hello! I am here to help you resolve technical issues. Please tell me if you are experiencing: "
                         f"<strong>database slowness</strong>, <strong>API 401 unauthorized errors</strong>, "
                         f"<strong>billing/invoices issues</strong>, or <strong>application crashes</strong>.")
            return reply, False

        # 6. Fallback (unrecognized conversational text)
        if session.active_issue:
            steps = DIAGNOSTIC_STEPS.get(session.active_issue, [])
            reply = (f"{apology_prefix}We are currently troubleshooting your <strong>{session.active_issue}</strong> issue.<br><br>"
                     f"Current Step: <code>{steps[session.current_step_index]}</code><br><br>"
                     f"Please let me know if this step resolved the issue (type 'yes' or 'it worked'), "
                     f"or if it didn't (type 'no' or 'still failing') to try the next step.")
            return reply, False
        else:
            reply = (f"👋 <strong>AURA Support Assistant</strong>:<br>"
                     f"I am here to help you resolve technical issues! Please tell me if you are experiencing: "
                     f"<strong>database slowness</strong>, <strong>API 401 unauthorized errors</strong>, "
                     "<strong>billing/invoices issues</strong>, or <strong>application crashes</strong>.")
            return reply, False
