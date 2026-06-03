import ast

with open('app.py', 'r', encoding='utf-8') as f:
    content = f.read()

tree = ast.parse(content)

for node in ast.walk(tree):
    if isinstance(node, ast.FunctionDef):
        if node.name == 'register':
            print(f'Function: {node.name}')
            for item in node.body:
                if isinstance(item, ast.Assign):
                    for target in item.targets:
                        if isinstance(target, ast.Name):
                            print(f'  Assign: {target.id} = ...')
