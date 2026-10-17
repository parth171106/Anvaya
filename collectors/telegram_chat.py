"""Find private chat IDs for a dedicated bot without exposing its token in shell history."""
import getpass
import re
import sys

import httpx


def main():
    print('First open your dedicated bot in Telegram and press Start.')
    token = getpass.getpass('Bot token (hidden; not saved): ').strip()
    if not re.fullmatch(r'[0-9]{5,20}:[A-Za-z0-9_-]{20,100}', token):
        print('Invalid token format.'); return 1
    try:
        with httpx.Client(timeout=15, follow_redirects=False, trust_env=False) as client:
            response = client.post(f'https://api.telegram.org/bot{token}/getUpdates', json={'limit': 100, 'timeout': 0})
        data = response.json()
        if not response.is_success or not isinstance(data, dict) or not data.get('ok'):
            print('Telegram rejected the request. Check the token and use a dedicated bot without another webhook or polling service.')
            return 1
        chats = set()
        for update in data.get('result', []):
            chat = update.get('message', {}).get('chat', {})
            if chat.get('type') == 'private' and isinstance(chat.get('id'), int):
                chats.add(chat['id'])
        for chat_id in sorted(chats):
            print(f'Private chat ID: {chat_id}')
        if not chats:
            print('No private chat found. Send your bot a new message, then run this helper again.')
        elif len(chats) > 1:
            print('Multiple chats found. Use a dedicated bot only you have started; do not select an unknown recipient.')
        return 0
    except (httpx.HTTPError, ValueError, TypeError, AttributeError):
        print('Could not read Telegram updates. Check connectivity and try again.')
        return 1


if __name__ == '__main__':
    sys.exit(main())
