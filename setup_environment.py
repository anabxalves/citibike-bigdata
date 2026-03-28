#!/usr/bin/env python3
"""
Setup do ambiente para o projeto Citi Bike Big Data.
Instala dependências e cria a estrutura de pastas.
"""

import subprocess
import sys
import os
from pathlib import Path

def install_packages():
    
    packages = [
        'pyspark',
        'pyarrow',
        'pandas',
        'requests',
        'holidays',
        'tqdm',
        'matplotlib',
        'seaborn',
    ]
    
    print(" Instalando dependências...")
    for pkg in packages:
        print(f"   → {pkg}")
        subprocess.check_call(
            [sys.executable, '-m', 'pip', 'install', pkg, '-q'],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL
        )
    print("✅ Dependências instaladas!\n")

def create_directories():
    
    project_root = Path(__file__).parent.parent
    
    dirs = [
        'dados/bronze/trips',
        'dados/bronze/weather',
        'dados/bronze/holidays',
        'dados/bronze/stations',
        'dados/silver',
        'dados/gold',
        'dados/streaming/events',
        'dados/streaming/checkpoint',
        'dados/streaming/output',
        'dados/raw_downloads',
        'documentacao',
        'notebooks',
        'src',
    ]
    
    print(" Criando estrutura de diretórios...")
    for d in dirs:
        path = project_root / d
        path.mkdir(parents=True, exist_ok=True)
        print(f"   ✅ {d}/")
    
    
    for d in dirs:
        gitkeep = project_root / d / '.gitkeep'
        if not any((project_root / d).iterdir()):
            gitkeep.touch()
    
    print(f"\n Raiz do projeto: {project_root}")

def create_gitignore():
    
    project_root = Path(__file__).parent.parent
    gitignore_content = """# Dados grandes (não versionar)
dados/raw_downloads/
dados/bronze/trips/
dados/streaming/
*.zip
*.csv

# Python
__pycache__/
*.pyc
.ipynb_checkpoints/
*.egg-info/
dist/
build/

# Spark
metastore_db/
derby.log
spark-warehouse/

# IDE
.vscode/
.idea/
*.swp

# OS
.DS_Store
Thumbs.db
"""
    
    gitignore_path = project_root / '.gitignore'
    gitignore_path.write_text(gitignore_content)
    print("✅ .gitignore criado")

if __name__ == '__main__':
    print("=" * 50)
    print("🚲 Setup — Projeto Citi Bike Big Data")
    print("=" * 50 + "\n")
    
    install_packages()
    create_directories()
    create_gitignore()
    
  