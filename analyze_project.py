"""
Project File Analyzer - Analyzes project files for refactoring
"""

import os
from pathlib import Path
from datetime import datetime

PROJECT_DIR = Path(__file__).parent

# Файлы, которые точно нужно сохранить
IMPORTANT_FILES = [
    "app.py",
    "config.py", 
    "requirements.txt",
    ".env",
    "static/",
    "templates/",
]

# Тестовые и отладочные файлы (можно оставить для справки)
TEST_FILES = [
    "full_flask_tester.py",
    "comprehensive_tester.py", 
    "run_all_tests.py",
    "my_browser_agent.py",
]

# Устаревшие файлы, которые можно удалить
LEGACY_FILES = []

# Результаты анализа
analysis = {
    "total_files": 0,
    "python_files": 0,
    "html_files": 0,
    "png_files": 0,
    "md_files": 0,
    "other_files": 0,
    "important": [],
    "legacy": [],
    "test_scripts": [],
    "screenshots": [],
    "docs": [],
}

def analyze_file(filepath, rel_path):
    """Analyze single file"""
    ext = filepath.suffix
    name = filepath.name
    
    analysis["total_files"] += 1
    
    if ext == ".py":
        analysis["python_files"] += 1
        if name in TEST_FILES:
            analysis["test_scripts"].append(name)
        elif name in IMPORTANT_FILES:
            analysis["important"].append(name)
        elif "_agent" in name or "check_" in name or "fix_" in name:
            analysis["legacy"].append(name)
        else:
            analysis["important"].append(name)
    elif ext == ".html":
        analysis["html_files"] += 1
    elif ext == ".png":
        analysis["png_files"] += 1
        analysis["screenshots"].append(name)
    elif ext == ".md":
        analysis["md_files"] += 1
        if "TEST" in name or "SOLUTION" in name or "RECOMMENDATIONS" in name:
            analysis["docs"].append(name)
    else:
        analysis["other_files"] += 1

# Проход по всем файлам
for filepath in PROJECT_DIR.iterdir():
    if filepath.is_dir():
        if filepath.name in [".venv", ".idea", "__pycache__"]:
            continue
        if filepath.name == "static":
            # Подсчет файлов в static
            for f in filepath.iterdir():
                analysis["total_files"] += 1
        elif filepath.name == "templates":
            for f in filepath.iterdir():
                analysis["total_files"] += 1
        else:
            continue
    else:
        if filepath.name.startswith("."):
            continue
        analyze_file(filepath, filepath.name)

# Вывод результатов
print("\n" + "="*70)
print("PROJECT FILE ANALYSIS")
print("="*70)

print(f"\n[SUMMARY]")
print(f"Total files: {analysis['total_files']}")
print(f"Python files: {analysis['python_files']}")
print(f"HTML files: {analysis['html_files']}")
print(f"PNG files (screenshots): {analysis['png_files']}")
print(f"Markdown files: {analysis['md_files']}")
print(f"Other files: {analysis['other_files']}")

print(f"\n[IMPORTANT FILES - KEEP]")
for f in analysis["important"]:
    print(f"  - {f}")

print(f"\n[TEST SCRIPTS - CAN KEEP]")
for f in analysis["test_scripts"]:
    print(f"  - {f}")

print(f"\n[LEGACY FILES - CAN REMOVE]")
for f in analysis["legacy"]:
    print(f"  - {f}")

print(f"\n[SCREENSHOTS]")
for f in analysis["screenshots"]:
    print(f"  - {f}")

print(f"\n[DOCUMENTATION]")
for f in analysis["docs"]:
    print(f"  - {f}")

# Рекомендации
print("\n" + "="*70)
print("RECOMMENDATIONS")
print("="*70)
print("\n⚠️  FILES THAT CAN BE REMOVED:")
print("1. Legacy check_*.py files (30+ files)")
print("2. Debug files (debug_*.py, create_job_*.py)")
print("3. Old solution files (solution_*.py, fix_*.py)")
print("4. Screenshots (unless needed for documentation)")

print("\n✅ FILES TO KEEP:")
print("1. app.py - main application")
print("2. config.py - configuration")
print("3. requirements.txt - dependencies")
print("4. templates/ - HTML templates")
print("5. static/ - static assets")
print("6. .env - environment variables")
print("7. test_results*.json - test results")
print("8. FINAL_TEST_REPORT.md - test report")
print("9. FIX_RECOMMENDATIONS.md - fix guide")

print("\n📝 SUGGESTED CLEANUP:")
print("- Remove all check_*.py files (30+ files)")
print("- Remove debug_*.py files")
print("- Remove create_job_*.py files (except last version)")
print("- Remove fix_*.py files")
print("- Remove solution_*.py files")
print("- Remove disable_*.py files")
print("- Remove update_*.py files")
print("- Remove remote_*.py files")
print("- Keep 1-2 main test scripts")
print("- Keep 1-2 diagnostic scripts")

print("\n" + "="*70)
