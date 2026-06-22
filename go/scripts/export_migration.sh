#!/usr/bin/env bash
set -euo pipefail

mkdir -p data/migrations
cp -f internal/store/migrations/0001_initial_schema.sql data/migrations/0001_initial_schema.sql
