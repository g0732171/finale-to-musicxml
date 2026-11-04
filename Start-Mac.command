#!/bin/sh
set -eu
APP_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
case "$(uname -m)" in
    arm64) ARCH=arm64 ;;
    x86_64) ARCH=x86_64 ;;
    *) echo "This package requires an Apple Silicon or Intel Mac."; exit 1 ;;
esac
exec "$APP_DIR/runtime/$ARCH/bin/python3.12" -I "$APP_DIR/app/server.py"
