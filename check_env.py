import os
from dotenv import load_dotenv

load_dotenv()

key = os.getenv('SUPABASE_SERVICE_ROLE_KEY', 'NOT SET')
if key != 'NOT SET':
    print('SERVICE_KEY:', key[:20] + '...')
else:
    print('SERVICE_KEY: NOT SET')
