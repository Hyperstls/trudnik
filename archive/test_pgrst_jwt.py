#!/usr/bin/env python3
"""Test PostgREST JWT authentication behavior."""

import hmac
import json
import base64
import urllib.request
import urllib.error
import sys

SECRET = b'9671f571463b29d1b93339c75082974856af1f5d3cce302aaa76f449a50447a1106d1e496728324fc31a654866c7c842456ee4fa077c91841d3fb8ac7e8fb1f6'


def b64url(data):
    if isinstance(data, str):
        data = data.encode()
    return base64.urlsafe_b64encode(data).rstrip(b'=').decode()


def make_jwt(payload):
    header = b64url(json.dumps({'alg': 'HS256', 'typ': 'JWT'}))
    body = b64url(json.dumps(payload, separators=(',', ':')))
    sig = hmac.new(SECRET, f'{header}.{body}'.encode(), 'sha256').digest()
    return f'{header}.{body}.{b64url(sig)}'


def test(label, token=None, role_desc=''):
    headers = {'Accept': 'application/json'}
    if token:
        headers['Authorization'] = f'Bearer {token}'
    try:
        req = urllib.request.Request('http://localhost:3000/profiles', headers=headers)
        r = urllib.request.urlopen(req, timeout=5)
        body = r.read()
        print(f'[{label}] Status: {r.status} (200=OK)')
        print(f'  Body (first 200): {body[:200]}')
    except urllib.error.HTTPError as e:
        body = e.read()
        print(f'[{label}] Status: {e.code} (401=UNAUTHORIZED)')
        print(f'  Body: {body[:300]}')


# Test 1: Anonymous (no JWT) - uses PGRST_DB_ANON_ROLE=anon
print('=' * 60)
print('TEST 1: Anonymous request (no JWT)')
print(f'  PostgREST uses PGRST_DB_ANON_ROLE=anon')
print('=' * 60)
test('ANON')

print()

# Test 2: JWT with role=trudnikapp (как делает Flask)
print('=' * 60)
print('TEST 2: JWT with role=trudnikapp (как Flask)')
print(f'  Flask sends role=trudnikapp in JWT')
print(f'  PostgREST tries: SET ROLE trudnikapp')
print('=' * 60)
t = make_jwt({'role': 'trudnikapp', 'sub': 'test', 'exp': 9999999999, 'iat': 1700000000})
test('trudnikapp', t)

print()

# Test 3: JWT with role=authenticated
print('=' * 60)
print('TEST 3: JWT with role=authenticated')
print(f'  PostgREST tries: SET ROLE authenticated')
print('=' * 60)
t = make_jwt({'role': 'authenticated', 'sub': 'test', 'exp': 9999999999, 'iat': 1700000000})
test('authenticated', t)

print()

# Test 4: JWT with role=anon
print('=' * 60)
print('TEST 4: JWT with role=anon')
print(f'  PostgREST tries: SET ROLE anon')
print('=' * 60)
t = make_jwt({'role': 'anon', 'sub': 'test', 'exp': 9999999999, 'iat': 1700000000})
test('anon', t)

print()
print('DONE')
sys.stdout.flush()
