#!/usr/bin/env python3
"""
Скрипт для проверки шаблона через Flask
"""

import os
import sys

# Добавляем путь к приложению
sys.path.insert(0, '/home/hyperstls/mysite')

from flask import Flask, render_template_string

app = Flask(__name__)

@app.route('/debug-template')
def debug_template():
    """Маршрут для отладки шаблона"""
    template_path = '/home/hyperstls/mysite/templates/job_new.html'
    
    if os.path.exists(template_path):
        with open(template_path, 'r', encoding='utf-8') as f:
            content = f.read()
        
        return f"""
        <html>
        <head><title>Debug Template</title></head>
        <body>
            <h1>Debug Template</h1>
            <p>Path: {template_path}</p>
            <p>Exists: True</p>
            <p>Length: {len(content)} characters</p>
            <p>max_workers found: {'YES' if 'max_workers' in content else 'NO'}</p>
            
            <h2>Relevant line:</h2>
            <pre>{content[content.find('max_workers')-100:content.find('max_workers')+200] if 'max_workers' in content else 'NOT FOUND'}</pre>
        </body>
        </html>
        """
    else:
        return f"<h1>Template not found</h1><p>Path: {template_path}</p>"

if __name__ == '__main__':
    print("Run: flask --app debug_app run")
    print("Then visit: http://localhost:5000/debug-template")
