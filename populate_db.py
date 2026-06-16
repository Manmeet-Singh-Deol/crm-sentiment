import db
from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer

def seed():
    db.init_db()
    analyzer = SentimentIntensityAnalyzer()
    
    # Check if contacts already exist
    existing = db.get_all_contacts()
    if existing:
        print("Database already contains data. Skipping seeding.")
        return
        
    sample_contacts = [
        {"name": "Steve Jobs", "email": "steve@apple.com", "notes": [
            "We are absolutely thrilled with the speed of delivery and execution! Fantastic team.",
            "Loved the product demo. The new user interface is a masterpiece."
        ]},
        {"name": "Bill Gates", "email": "bill@microsoft.com", "notes": [
            "Extremely disappointed with the latency issues we encountered. It crashed twice during our meeting.",
            "Support team is taking too long to respond to our high-priority tickets. This is very frustrating."
        ]},
        {"name": "Elon Musk", "email": "elon@tesla.com", "notes": [
            "Requested standard documentation for the APIs.",
            "Discussed renewal options. Scheduled a follow-up meeting for next Tuesday."
        ]},
        {"name": "Jeff Bezos", "email": "jeff@amazon.com", "notes": [
            "Great support! The integration was quick and seamless.",
            "The system is running efficiently without any issues."
        ]},
        {"name": "Mark Zuckerberg", "email": "mark@meta.com", "notes": [
            "Customer was highly frustrated with the unexpected delivery delays and is demanding a refund.",
            "Still waiting on the feature request. Communication has been poor."
        ]}
    ]
    
    for c in sample_contacts:
        contact_id = db.add_contact(c["name"], c["email"])
        if contact_id:
            # Add notes and compute status
            sentiment_scores = []
            for note_text in c["notes"]:
                vs = analyzer.polarity_scores(note_text)
                score = vs['compound']
                db.add_note(contact_id, note_text, score)
                sentiment_scores.append(score)
            
            # Re-evaluate status
            latest_score = sentiment_scores[-1]
            avg_score = sum(sentiment_scores) / len(sentiment_scores)
            
            # Determine status using same backend logic:
            if latest_score <= -0.25:
                status = 'At Risk'
            elif avg_score < -0.05:
                status = 'At Risk'
            elif avg_score >= 0.15:
                status = 'Happy'
            else:
                status = 'Neutral'
                
            db.update_contact_status(contact_id, status)
            print(f"Added {c['name']} with status: {status}")

if __name__ == '__main__':
    seed()
