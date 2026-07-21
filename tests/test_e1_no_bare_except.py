"""
E1: Тест для проверки отсутствия bare except: pass в кодовой базе.

Все исключения должны логироваться для observability.
"""
import ast
import os
from pathlib import Path


def test_no_bare_except_pass():
    """Проверяет, что в app/ нет конструкций 'except Exception: pass'."""
    app_dir = Path(__file__).parent.parent / 'app'
    violations = []
    
    for py_file in app_dir.rglob('*.py'):
        try:
            with open(py_file, 'r', encoding='utf-8') as f:
                content = f.read()
            
            tree = ast.parse(content, filename=str(py_file))
            
            for node in ast.walk(tree):
                if isinstance(node, ast.ExceptHandler):
                    # Проверяем, что это except Exception (без конкретного типа)
                    if node.type is None or (isinstance(node.type, ast.Name) and node.type.id == 'Exception'):
                        # Проверяем, что тело содержит только pass
                        if len(node.body) == 1 and isinstance(node.body[0], ast.Pass):
                            violations.append(f"{py_file}:{node.lineno}")
        
        except Exception as e:
            # Если не можем распарсить файл - логируем, но не падаем
            print(f"Warning: Could not parse {py_file}: {e}")
    
    assert not violations, (
        f"Found bare 'except Exception: pass' in {len(violations)} location(s):\n"
        + "\n".join(violations)
        + "\n\nAll exceptions must be logged. Use 'except Exception as e: logger.warning(..., exc_info=True)'"
    )


if __name__ == '__main__':
    test_no_bare_except_pass()
    print("✓ E1: No bare except: pass found")
