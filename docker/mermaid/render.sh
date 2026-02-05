#!/bin/sh
set -e

INPUT=${1:-input.mmd}
OUTPUT=${2:-output.svg}

cat > /data/puppeteer.json <<'EOF'
{
	"args": ["--no-sandbox", "--disable-setuid-sandbox"]
}
EOF

mmdc -i "/data/${INPUT}" -o "/data/${OUTPUT}" --backgroundColor transparent -p /data/puppeteer.json
