#!/bin/bash
OUT="system_truth.txt"
echo "=== TRUCKING ERP SYSTEM AUDIT ($(date)) ===" > $OUT

echo -e "\n--- 1. HOST PROCESSES (The Secret Nginx) ---" >> $OUT
ps aux | grep -E "nginx|uvicorn|gunicorn|python" | grep -v grep >> $OUT
sudo netstat -tulpn | grep LISTEN >> $OUT

echo -e "\n--- 2. DOCKER STATUS ---" >> $OUT
docker ps -a >> $OUT
docker network ls >> $OUT
docker inspect truckerp-postgres --format='{{.NetworkSettings.Networks}}' 2>/dev/null >> $OUT

echo -e "\n--- 3. GIT DISASTER CHECK ---" >> $OUT
git status >> $OUT
git log -n 5 --oneline >> $OUT
git remote -v >> $OUT

echo -e "\n--- 4. SYSTEMD GHOSTS ---" >> $OUT
systemctl list-units --type=service | grep -E "truck|nginx|postgres" >> $OUT

echo -e "\n--- 5. DIRECTORY MAP ---" >> $OUT
ls -R /home/admin/trucking_erp | grep ":$" | sed -e 's/:$//' -e 's/[^-][^\/]*\//--/g' -e 's/^/   /' >> $OUT

echo "DONE. Report saved to system_truth.txt"
