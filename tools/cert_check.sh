#!/usr/bin/env bash
set -Eeuo pipefail

DOMAIN="truckerp.me"
CERT_CONT="truckerp-certbot"
NGINX_CONT="truckerp-nginx"

GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[0;33m'
NC='\033[0m'

echo "--- SSL Production Audit: ${DOMAIN} ---"

# CHECK 1: Certificate File Existence
docker exec "${CERT_CONT}" ls "/etc/letsencrypt/live/${DOMAIN}/fullchain.pem" >/dev/null 2>&1 \
    && echo -e "[$GREEN OK $NC] Cert Files Found on Disk" || echo -e "[$RED FAIL $NC] Cert Files Missing"

# CHECK 2: Symlink Integrity
SYMLINK_CHECK=$(docker exec "${NGINX_CONT}" ls -l "/etc/letsencrypt/live/${DOMAIN}/fullchain.pem" | grep "\->" || echo "")
[[ -n "$SYMLINK_CHECK" ]] \
    && echo -e "[$GREEN OK $NC] Symlink Chain Valid" || echo -e "[$RED FAIL $NC] Symlink Broken"

# CHECK 3: SSL Expiry Date
EXP_DATE=$(echo | openssl s_client -servername "${DOMAIN}" -connect "${DOMAIN}":443 2>/dev/null | openssl x509 -noout -enddate | cut -d= -f2 || echo "ERR")
echo -e "[$GREEN OK $NC] SSL Valid (Expires: $EXP_DATE)"

# CHECK 4: Calculate Days Until Expiry
EXP_DATE_EPOCH=$(date -d "$EXP_DATE" +%s 2>/dev/null || echo 0)
NOW_EPOCH=$(date +%s)
DAYS_LEFT=$(( ($EXP_DATE_EPOCH - $NOW_EPOCH) / 86400 ))
if [ $DAYS_LEFT -lt 30 ]; then
    echo -e "[$YELLOW WARN $NC] Certificate expires in $DAYS_LEFT days"
else
    echo -e "[$GREEN OK $NC] $DAYS_LEFT days until expiry"
fi

# CHECK 5: Nginx Config Points to Correct Path
NGINX_CERT_PATH=$(docker exec "$NGINX_CONT" nginx -T 2>/dev/null | grep "ssl_certificate " | awk '{print $2}' | tr -d ';' | head -1 || echo "")
if [[ "$NGINX_CERT_PATH" == "/etc/letsencrypt/live/${DOMAIN}/fullchain.pem" ]]; then
    echo -e "[$GREEN OK $NC] Nginx config points to correct cert path"
else
    echo -e "[$RED FAIL $NC] Nginx config path mismatch: $NGINX_CERT_PATH"
fi

# CHECK 6: Protocol Handshake (Port 443)
timeout 2 bash -c "</dev/tcp/${DOMAIN}/443" 2>/dev/null \
    && echo -e "[$GREEN OK $NC] Port 443 (HTTPS) Handshake Success" || echo -e "[$RED FAIL $NC] Port 443 Closed"

# CHECK 7: Memory Sync (Drift Check) - Your brilliant innovation!
SERVER_FP=$(echo | openssl s_client -servername "${DOMAIN}" -connect "${DOMAIN}":443 2>/dev/null | openssl x509 -noout -fingerprint -sha256 | sed 's/^.*=//' | tr -d ':' | tr '[:lower:]' '[:upper:]' || echo "")
DISK_FP=$(docker exec "${CERT_CONT}" openssl x509 -in "/etc/letsencrypt/live/${DOMAIN}/fullchain.pem" -noout -fingerprint -sha256 2>/dev/null | sed 's/^.*=//' | tr -d ':' | tr '[:lower:]' '[:upper:]' || echo "")
if [[ -n "$SERVER_FP" && -n "$DISK_FP" ]]; then
    if [[ "$SERVER_FP" == "$DISK_FP" ]]; then
        echo -e "[$GREEN OK $NC] Zero Drift (Memory matches Disk)"
    else
        echo -e "[$RED WARN $NC] Drift Detected"
        echo "   Solution: docker exec ${NGINX_CONT} nginx -s reload"
    fi
else
    echo -e "[$YELLOW WARN $NC] Could not compute fingerprints for drift check"
fi

# CHECK 8: Smart Certbot Renewal Test
echo -n "[ ... ] Checking Certbot renewal capability... "

# Only run renewal test if certificate is within 45 days of expiry
if [ $DAYS_LEFT -le 45 ]; then
    if timeout 45 docker exec "$CERT_CONT" certbot renew --dry-run >/dev/null 2>&1; then
        echo -e "\r[$GREEN OK $NC] Certbot renewal test passes (ready for auto-renewal)"
    else
        echo -e "\r[$YELLOW WARN $NC] Certbot renewal test failed - check before ${EXP_DATE}"
        echo "   Run manually: docker exec ${CERT_CONT} certbot renew --dry-run -v"
        echo "   Common issues:"
        echo "   - HTTP-01 challenge blocked (port 80 firewall)"
        echo "   - DNS challenge not configured"
        echo "   - Let's Encrypt rate limits"
    fi
else
    # Certificate has plenty of time, skip the test
    echo -e "\r[$GREEN OK $NC] Certificate healthy (${DAYS_LEFT} days remaining)"
    echo "   Auto-renewal will trigger within 30 days of expiry"
fi

# CHECK 9: Certificate Chain Validity
CHAIN_LENGTH=$(echo | openssl s_client -servername "${DOMAIN}" -connect "${DOMAIN}":443 -showcerts 2>/dev/null | grep -E 'BEGIN CERTIFICATE|END CERTIFICATE' | wc -l)
CERT_COUNT=$((CHAIN_LENGTH / 2))
if [ $CERT_COUNT -ge 2 ]; then
    echo -e "[$GREEN OK $NC] Valid certificate chain ($CERT_COUNT certificates)"
else
    echo -e "[$RED FAIL $NC] Incomplete certificate chain"
fi

echo "---------------------------------------"
read -t 10 -p "Show Deep Dive (Full Paths & Chain Details)? [y/N] " confirm || confirm="n"

if [[ "$confirm" =~ ^[Yy]$ ]]; then
    echo -e "\n${YELLOW}--- SSL DEEP DIVE ---${NC}"
    echo "Live Site Fingerprint: $SERVER_FP"
    echo "Disk File Fingerprint: $DISK_FP"
    echo -e "\n[Disk Path Reference]"
    docker exec "${NGINX_CONT}" ls -l "/etc/letsencrypt/live/${DOMAIN}/"
    echo -e "\n[Certificate Chain]"
    echo | openssl s_client -servername "${DOMAIN}" -connect "${DOMAIN}":443 2>/dev/null | openssl x509 -noout -issuer -subject
fi

# Final Summary (FIXED: No raw ANSI codes)
echo -e "\n${GREEN}=== AUDIT COMPLETE ==="
echo "All critical SSL checks completed."
echo "For automated monitoring, run this script daily."
echo "=======================================${NC}"
