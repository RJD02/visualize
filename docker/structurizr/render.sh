#!/bin/sh
set -e

INPUT=${1:-workspace.json}

/usr/local/structurizr-cli/structurizr.sh export -workspace "/data/${INPUT}" -format plantuml -output /data
