#!/usr/bin/env bash
set -e

PROJECT_DIR="/home/admin/trucking_erp"

cd "$PROJECT_DIR"

# 1. Initialize git
git init

# 2. Create .gitignore (ERP-safe)
cat > .gitignore <<'EOF'
# Python
__pycache__/
*.py[cod]
*.pyo
*.pyd

# Virtual environment
venv/
.env

# OS / Editor
.DS_Store
.vscode/
.idea/

# Logs
*.log

# Alembic
alembic/versions/__pycache__/
EOF

# 3. Initial commit
git add .
git commit -m "Phase 2 complete: FastAPI + async Postgres foundation"

echo
echo "✅ Local git initialized."
echo "➡️  Now add your GitHub remote and push:"
echo
echo "git branch -M main"
echo "git remote add origin <PASTE_GITHUB_REPO_URL>"
echo "git push -u origin main"
