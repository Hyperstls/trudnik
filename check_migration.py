with open('migrations/add_max_workers.sql', 'r', encoding='utf-8') as f:
    content = f.read()
    print('Rows:', len(content.splitlines()))
    print('Notifications table:', 'notifications' in content)
    print('Ratings table:', 'ratings' in content)
    print('max_workers:', 'max_workers' in content)
    print('is_read:', 'is_read' in content)
