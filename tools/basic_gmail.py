from __future__ import print_function
import os.path
import base64
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from google.auth.transport.requests import Request
import pickle

SCOPES = ['https://www.googleapis.com/auth/gmail.readonly']

def get_service():
    creds = None

    if os.path.exists('token.pickle'):
        with open('token.pickle', 'rb') as token:
            creds = pickle.load(token)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(
                'credentials.json', SCOPES)
            creds = flow.run_local_server(port=0)

        with open('token.pickle', 'wb') as token:
            pickle.dump(creds, token)

    return build('gmail', 'v1', credentials=creds)


def get_body(payload):
    if 'parts' in payload:
        for part in payload['parts']:
            if part['mimeType'] == 'text/plain':
                data = part['body'].get('data')
                if data:
                    return base64.urlsafe_b64decode(data).decode('utf-8')
    else:
        data = payload['body'].get('data')
        if data:
            return base64.urlsafe_b64decode(data).decode('utf-8')

    return "No body found"


def main():
    service = get_service()

    results = service.users().messages().list(
        userId='me',
        q='is:unread',
        maxResults=15
    ).execute()

    messages = results.get('messages', [])

    if not messages:
        print("No unread emails")
        return

    for msg in messages:
        message = service.users().messages().get(
            userId='me',
            id=msg['id'],
            format='full'
        ).execute()

        headers = message['payload']['headers']

        subject = sender = None

        for h in headers:
            if h['name'] == 'Subject':
                subject = h['value']
            if h['name'] == 'From':
                sender = h['value']

        body = get_body(message['payload'])

        print("=" * 50)
        print("From:", sender)
        print("Subject:", subject)
        print("Body:", body[:300])


if __name__ == '__main__':
    main()