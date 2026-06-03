import sys
sys.path.insert(0, '.')
from app import app

routes = [rule.rule for rule in app.url_map.iter_rules() if 'my-applications' in rule.rule]
print('Routes with my-applications:', routes)

# Check for duplicate endpoints
from collections import Counter
endpoints = [rule.endpoint for rule in app.url_map.iter_rules()]
duplicates = [ep for ep, count in Counter(endpoints).items() if count > 1]
if duplicates:
    print('DUPLICATE ENDPOINTS:', duplicates)
else:
    print('No duplicate endpoints found')
