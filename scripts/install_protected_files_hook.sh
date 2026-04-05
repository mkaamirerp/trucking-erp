#!/usr/bin/env bash
# Installs the protected-files check as the repo pre-commit hook.
# Run once: ./scripts/install_protected_files_hook.sh

set -e
REPO_ROOT=$(git rev-parse --show-toplevel)
HOOK_SRC="$REPO_ROOT/scripts/check_protected_files.sh"
HOOK_DEST="$REPO_ROOT/.git/hooks/pre-commit"

if [[ ! -f "$HOOK_SRC" ]]; then
  echo "Missing $HOOK_SRC"
  exit 1
fi

chmod +x "$HOOK_SRC"
mkdir -p "$(dirname "$HOOK_DEST")"
cat > "$HOOK_DEST" << 'HOOK'
#!/usr/bin/env bash
exec "$(git rev-parse --show-toplevel)/scripts/check_protected_files.sh"
HOOK
chmod +x "$HOOK_DEST"
echo "Installed pre-commit hook: $HOOK_DEST"
echo "Protected files will block commits unless APPROVED_CONFIG_CHANGE=1 is set."
echo "To bypass once: APPROVED_CONFIG_CHANGE=1 git commit -m 'CONFIG-CHANGE: <reason>'"
echo ""
echo "To remove: rm .git/hooks/pre-commit"