import os
import sys

# Add app directory to path so relative imports work
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), 'app')))

# Read and execute app/main.py
main_path = os.path.join(os.path.dirname(__file__), 'app', 'main.py')
with open(main_path, 'r', encoding='utf-8') as f:
    code = compile(f.read(), main_path, 'exec')
    exec(code, globals())
