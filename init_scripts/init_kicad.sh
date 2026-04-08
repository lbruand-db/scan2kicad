#!/bin/bash
# init_kicad.sh — install KiCad CLI on Databricks cluster nodes
set -euo pipefail

apt-get update -qq
apt-get install -y -qq kicad kicad-library 2>/dev/null || {
    # Fallback: install from PPA for Ubuntu-based images
    add-apt-repository -y ppa:kicad/kicad-9.0-releases
    apt-get update -qq
    apt-get install -y -qq kicad kicad-library
}
