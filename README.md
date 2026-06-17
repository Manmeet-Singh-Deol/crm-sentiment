# AURA CRM & Proactive Support Portal

[![Live Demo](https://img.shields.io/badge/Live%20Demo-Render-blue?style=for-the-badge&logo=render&logoColor=white)](https://aura-crm-j2vl.onrender.com)

A premium, modern customer relationship management (CRM) application featuring real-time natural language sentiment analysis, role-based access controls (RBAC), offline stateful chatbot diagnostics, and real-time dashboard synchronization using WebSockets.

Powered by **MongoDB Atlas** (cloud-hosted NoSQL) for persistent data storage, with **zero paid API dependencies** (no Pusher, no OpenAI keys needed), making it lightweight, extremely fast, and instantly testable.

---

## 🌟 Key Features

*   **Proactive Support Assistant (Stateful & Offline)**: Integrates an in-memory state tracker (`LocalChatbot`) that detects client issues (database latency, API 401 unauthorized errors, billing, application crashes) and guides them through step-by-step diagnostic workflows.
*   **Real-Time Sentiment Analysis**: Analyzes client messages and support interaction logs using the VADER NLP library, automatically calculating client health scores and flagging accounts as *Happy*, *Neutral*, or *At Risk*.
*   **WebSocket Real-Time Synchronization**: Emits database updates and client presence events via `Flask-SocketIO` to keep staff dashboards in sync without manual refreshing or polling.
*   **Role-Based Access Control (RBAC)**: Supports three distinct user portals:
    *   **Admin**: Complete CRUD capabilities over client profiles, access to "Sentiment Insights" analytics views, and cascade deletion of client histories.
    *   **Staff**: Access to dashboard metrics, client directory logging, note management, and active chat presence feeds.
    *   **Client**: Secure, email-only authenticated portal that restricts users to their dedicated support chat and feedback submission forms, hiding confidential internal dashboards.
*   **Dynamic Dual Authentication & Registration**: Beautiful, tabbed glassmorphic login and registration cards with validation error state preservation.

---

## 🛠️ Technology Stack

*   **Backend Framework**: Flask (Python 3.10+)
*   **Real-Time Communication**: Flask-SocketIO (WebSocket protocol)
*   **Natural Language Processing**: VADER Sentiment Analysis (`vaderSentiment`)
*   **Database Engine**: MongoDB Atlas (cloud-hosted NoSQL via PyMongo, aggregation pipelines, auto-increment IDs)
*   **Authentication & Hashing**: Werkzeug Hashing Utilities (PBKDF2-SHA256)
*   **Frontend Design System**: Vanilla CSS3 + Modern Typography (Inter & Outfit via Google Fonts) with Glassmorphic visual style.

---

## 📁 Directory Structure

```text
crm-sentiment/
├── app.py                     # Flask-SocketIO Server, routes, and decorator middlewares
├── chatbot.py                 # Stateful local chatbot engine, VADER rules, and escalations
├── db.py                      # MongoDB database operations (PyMongo), collection indexes, and seeders
├── populate_db.py             # Script to seed sample client contacts and dummy history logs
├── requirements.txt           # Project dependencies
├── render.yaml                # Render blueprint configuration (optional)
├── static/
│   ├── css/
│   │   └── style.css          # Premium design system tokens and glassmorphism styling
│   └── js/
│       └── app.js             # Client-side WebSocket integration and timeline animations
├── templates/
│   ├── 403.html               # Custom Access Denied error screen
│   ├── 404.html               # Custom Not Found screen
│   ├── analytics.html         # Admin sentiment analytics graphs and charts
│   ├── base.html              # Global navigation, context-aware sidebar, and socket.io client
│   ├── chat.html              # Client-facing support chat portal & feedback cards
│   ├── contact_detail.html    # Profile page containing timeline notes and admin delete actions
│   ├── contacts.html          # Staff-facing client directory
│   ├── dashboard.html         # Live-updating operations dashboard
│   ├── login.html             # Tab-switching portal for Admin/Staff/Client credentials
│   └── register.html          # Tab-switching portal for registering Staff or Client accounts
└── test_app.py                # Automated test suite (9 test cases asserting RBAC & APIs)
```

---

## 🚀 Getting Started

### 1. Prerequisites
Ensure you have **Python 3.10+** installed on your system.

### 2. Installation
Clone the repository and navigate to the project directory:
```bash
git clone https://github.com/Manmeet-Singh-Deol/crm-sentiment.git
cd crm-sentiment
```

Create and activate a virtual environment:
```bash
# Windows
python -m venv .venv
.venv\Scripts\activate

# macOS / Linux
python3 -m venv .venv
source .venv/bin/activate
```

Install the dependencies:
```bash
pip install -r requirements.txt
```

### 3. MongoDB Atlas Setup
This project uses **MongoDB Atlas** (free tier). Set your connection string:
```bash
# Windows PowerShell
$env:MONGO_URI = "mongodb+srv://<username>:<password>@cluster0.xxxxx.mongodb.net/?appName=Cluster0"

# macOS / Linux
export MONGO_URI="mongodb+srv://<username>:<password>@cluster0.xxxxx.mongodb.net/?appName=Cluster0"
```

The database collections, indexes, and sample data are **auto-created on first run** — no manual setup needed.

### 4. Running the Application
Start the Flask development server:
```bash
python app.py
```
Open [http://127.0.0.1:5000](http://127.0.0.1:5000) in your browser. You will be automatically redirected to `/login`.

---

## 🔑 Demo Credentials

On initial setup, the database seeds default tester credentials (you can customize these in production using environment variables like `ADMIN_USERNAME` and `ADMIN_PASSWORD`):

| Portal | Username / Email | Password | Role / Details |
| :--- | :--- | :--- | :--- |
| **Admin** | `MANMEET` (or custom `ADMIN_USERNAME`) | `1234567890` (or custom `ADMIN_PASSWORD`) | Full administrative capabilities |
| **Staff** | `staff` | `staff123` | Operational access (directory & metrics) |
| **Client**| *(Select a seeded email)* | *(No Password)* | Email-only support chat access |

*Note: For local testing, credentials can also be viewed in the auto-generated `admin_credentials.txt` file.*

---

## 🧪 Automated Testing

The project contains a comprehensive automated testing suite verifying endpoint protection, RBAC decorators, chatbot states, database queries, and WebSocket structures.

To execute the test suite:
```bash
python -m unittest test_app.py
```

Expected Output:
```text
.........
----------------------------------------------------------------------
Ran 9 tests in ~28s

OK
```

---

## ☁️ Deploying to Render.com

Deploying AURA CRM to Render is free and easy:
1. Create a repository on **GitHub** and push the codebase.
2. Log into your **Render Dashboard**, click **New +**, and select **Web Service**.
3. Link your GitHub repository.
4. Configure the Web Service settings:
    *   **Build Command**: `pip install -r requirements.txt`
    *   **Start Command**: `python app.py`
5. Under **Environment Variables**, add:
    *   `MONGO_URI` → Your MongoDB Atlas connection string
    *   *(Optional)* `ADMIN_USERNAME` and `ADMIN_PASSWORD` to customize admin credentials
6. Render will automatically build the package and deploy the live URL.

> **Note**: Data is stored in MongoDB Atlas cloud, so it **persists across deployments** — no data loss on redeploy.
