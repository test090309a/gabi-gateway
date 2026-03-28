import sys
import subprocess
import requests
import json
import io
from datetime import datetime, timedelta

# Fix Windows Unicode encoding
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')

PROJECT_ID = "openclaw-gmail-1769952449"

def get_access_token():
    """Holt das gcloud Access Token"""
    try:
        token = subprocess.check_output(
            ['gcloud', 'auth', 'application-default', 'print-access-token', '--project', PROJECT_ID],
            shell=True
        ).decode('utf-8').strip()
        return token
    except Exception as e:
        return None

def get_headers(token):
    return {
        'Authorization': f'Bearer {token}',
        'X-Goog-User-Project': PROJECT_ID,
        'Content-Type': 'application/json'
    }

def get_gmail_messages(limit=10, days_back=7):
    """Holt Gmail-Nachrichten mit Details"""
    token = get_access_token()
    if not token:
        return {"error": "Nicht authentifiziert. Führe aus: gcloud auth application-default login"}
    
    since_date = (datetime.now() - timedelta(days=days_back)).strftime('%Y/%m/%d')
    query = f"after:{since_date}"
    
    url = f"https://gmail.googleapis.com/gmail/v1/users/me/messages?maxResults={limit}&q={query}"
    
    try:
        response = requests.get(url, headers=get_headers(token))
        list_data = response.json()
        
        if 'messages' not in list_data:
            return {"ok": True, "messages": [], "info": "Keine Nachrichten gefunden"}
        
        detailed_messages = []
        for msg in list_data['messages'][:limit]:
            details = get_message_details(msg['id'], token)
            detailed_messages.append(details)
        
        return {
            "ok": True,
            "messages": detailed_messages,
            "query": query,
            "total_in_inbox": list_data.get('resultSizeEstimate', 0)
        }
    except Exception as e:
        return {"error": str(e)}

def get_message_details(msg_id, token):
    """Holt Details einer einzelnen Nachricht"""
    url = f"https://gmail.googleapis.com/gmail/v1/users/me/messages/{msg_id}?format=metadata&metadataHeaders=Subject&metadataHeaders=From&metadataHeaders=Date"
    
    try:
        response = requests.get(url, headers=get_headers(token))
        data = response.json()
        
        headers_dict = {}
        if 'payload' in data and 'headers' in data['payload']:
            for header in data['payload']['headers']:
                headers_dict[header['name']] = header['value']
        
        return {
            'id': msg_id,
            'subject': headers_dict.get('Subject', 'Kein Betreff'),
            'from': headers_dict.get('From', 'Unbekannt'),
            'date': headers_dict.get('Date', 'Unbekannt'),
            'snippet': data.get('snippet', '')[:150] + '...' if data.get('snippet') else ''
        }
    except Exception as e:
        return {
            'id': msg_id,
            'subject': 'Fehler beim Laden',
            'from': 'Unbekannt',
            'date': 'Unbekannt',
            'snippet': str(e)
        }

def get_calendar_events(days=7, max_results=10):
    """Holt Google Calendar Termine"""
    token = get_access_token()
    if not token:
        return {"error": "Nicht authentifiziert"}
    
    now = datetime.utcnow()
    time_min = now.isoformat() + 'Z'
    time_max = (now + timedelta(days=days)).isoformat() + 'Z'
    
    url = f"https://www.googleapis.com/calendar/v3/calendars/primary/events?timeMin={time_min}&timeMax={time_max}&maxResults={max_results}&orderBy=startTime&singleEvents=true"
    
    try:
        response = requests.get(url, headers=get_headers(token))
        data = response.json()
        
        if 'items' not in data:
            return {"ok": True, "events": [], "info": "Keine Termine gefunden"}
        
        events = []
        for event in data['items']:
            start = event.get('start', {})
            start_time = start.get('dateTime', start.get('date', 'Unbekannt'))
            
            events.append({
                'id': event.get('id'),
                'title': event.get('summary', 'Kein Titel'),
                'start': start_time,
                'end': event.get('end', {}).get('dateTime', event.get('end', {}).get('date', '')),
                'location': event.get('location', ''),
                'description': event.get('description', '')[:200] + '...' if event.get('description') else '',
                'organizer': event.get('organizer', {}).get('email', ''),
                'attendees': [a.get('email') for a in event.get('attendees', [])]
            })
        
        return {
            "ok": True,
            "events": events,
            "time_range": f"{time_min} bis {time_max}",
            "count": len(events)
        }
    except Exception as e:
        return {"error": str(e)}

def get_keep_notes(limit=10):
    """Holt Google Keep Notizen (wenn verfügbar)"""
    token = get_access_token()
    if not token:
        return {"error": "Nicht authentifiziert"}
    
    # Google Keep API ist limitiert verfügbar, wir probieren es
    url = "https://keep.googleapis.com/v1/notes"
    
    try:
        response = requests.get(url, headers=get_headers(token))
        data = response.json()
        
        if 'notes' in data:
            notes = []
            for note in data['notes'][:limit]:
                notes.append({
                    'id': note.get('name'),
                    'title': note.get('title', 'Kein Titel'),
                    'content': note.get('content', '')[:300] + '...' if note.get('content') else '',
                    'created': note.get('createTime', ''),
                    'updated': note.get('updateTime', '')
                })
            return {"ok": True, "notes": notes, "count": len(notes)}
        else:
            return {"ok": True, "notes": [], "info": "Keine Notizen gefunden oder API nicht verfügbar"}
    except Exception as e:
        return {"ok": False, "error": str(e), "note": "Google Keep API erfordert spezielle Berechtigungen"}

def main():
    if len(sys.argv) < 2:
        # Standard: Alles anzeigen
        print("=== GOOGLE WORKSPACE ÜBERSICHT ===\n")
        
        print("📧 GMAIL (letzte 7 Tage):")
        gmail = get_gmail_messages(5, 7)
        if gmail.get('ok'):
            for msg in gmail.get('messages', []):
                print(f"  • {msg['date'][:10]} | {msg['subject'][:50]}")
                print(f"    Von: {msg['from'][:40]}")
        else:
            print(f"  Fehler: {gmail.get('error')}")
        
        print("\n📅 KALENDER (nächste 7 Tage):")
        calendar = get_calendar_events(7, 10)
        if calendar.get('ok'):
            for event in calendar.get('events', []):
                start = event['start'][:16] if len(event['start']) > 16 else event['start']
                print(f"  • {start} | {event['title']}")
        else:
            print(f"  Fehler: {calendar.get('error')}")
        
        print("\n📝 KEEP NOTIZEN:")
        keep = get_keep_notes(5)
        if keep.get('ok'):
            for note in keep.get('notes', []):
                print(f"  • {note['title'][:40]}")
        else:
            print(f"  Info: {keep.get('error', keep.get('info', 'Keine Notizen'))}")
        
        return
    
    command = sys.argv[1]
    
    if command == "mails":
        limit = int(sys.argv[2]) if len(sys.argv) > 2 else 10
        days = int(sys.argv[3]) if len(sys.argv) > 3 else 7
        result = get_gmail_messages(limit, days)
        print(json.dumps(result, ensure_ascii=False, indent=2))
    
    elif command == "termine":
        days = int(sys.argv[2]) if len(sys.argv) > 2 else 7
        result = get_calendar_events(days)
        print(json.dumps(result, ensure_ascii=False, indent=2))
    
    elif command == "notizen":
        limit = int(sys.argv[2]) if len(sys.argv) > 2 else 10
        result = get_keep_notes(limit)
        print(json.dumps(result, ensure_ascii=False, indent=2))
    
    elif command == "alle":
        result = {
            "gmail": get_gmail_messages(10, 7),
            "calendar": get_calendar_events(14, 20),
            "keep": get_keep_notes(10)
        }
        print(json.dumps(result, ensure_ascii=False, indent=2))
    
    else:
        print("Verwendung: gog.py [mails|termine|notizen|alle] [optionen]")
        print("  mails [limit] [tage]     - Gmail Nachrichten")
        print("  termine [tage]           - Kalender Termine")
        print("  notizen [limit]          - Keep Notizen")
        print("  alle                     - Alles zusammen")
        print("  (ohne Argument)          - Übersicht")

if __name__ == "__main__":
    main()
