lines = open('app.py', encoding='utf-8').readlines()
matches = []
for i, line in enumerate(lines):
    if 'my-applications' in line.lower():
        matches.append(f'{i+1}: {line.rstrip()}')
print('\n'.join(matches))
