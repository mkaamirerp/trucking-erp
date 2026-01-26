#!/bin/sh
set -a
[ -f /run/secrets/truckerp.env ] && . /run/secrets/truckerp.env
set +a
exec "$@"
