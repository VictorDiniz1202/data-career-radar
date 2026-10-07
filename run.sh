#!/usr/bin/env bash
# One-click pipeline: database -> migrations -> ingest -> classify -> evaluate.
#
# Required:  RESUME_PATH   local .md/.txt resume or skills inventory (outside the repo)
# Optional:  BOARDS        space-separated source:slug pairs
#                          (default: "greenhouse:clara ashby:constructor")
#            LIMIT         max postings scored by Gemini this run (default: 5, hard cap 20)
#            ALLOWED_COUNTRIES  comma-separated country codes besides unknown (default: BR)
#
# Example: RESUME_PATH=~/private/skills.md ./run.sh
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")"

BOARDS="${BOARDS:-greenhouse:clara ashby:constructor}"
LIMIT="${LIMIT:-5}"
ALLOWED_COUNTRIES="${ALLOWED_COUNTRIES:-BR}"

# Fail before touching anything: evaluation is the paid step and needs the resume.
if [ -z "${RESUME_PATH:-}" ]; then
  echo "RESUME_PATH is required (local .md/.txt outside the repository)." >&2
  exit 2
fi

# Prefer the project virtualenv (Windows Scripts/ or POSIX bin/) over PATH.
if [ -x ".venv/Scripts/python.exe" ]; then
  PYTHON=".venv/Scripts/python.exe"
elif [ -x ".venv/bin/python" ]; then
  PYTHON=".venv/bin/python"
else
  PYTHON="${PYTHON:-python}"
fi

if docker compose version >/dev/null 2>&1; then
  COMPOSE=(docker compose)
else
  COMPOSE=(docker-compose)
fi

step() { printf '\n==> %s\n' "$1"; }

step "1/5 Starting PostgreSQL"
"${COMPOSE[@]}" up -d
for _ in $(seq 1 30); do
  if "${COMPOSE[@]}" exec -T db sh -c 'pg_isready -U "$POSTGRES_USER" -d "$POSTGRES_DB"' >/dev/null 2>&1; then
    ready=1
    break
  fi
  sleep 1
done
if [ -z "${ready:-}" ]; then
  echo "PostgreSQL did not become ready within 30s." >&2
  exit 1
fi

step "2/5 Applying migrations"
# python -m avoids the alembic launcher, which breaks when the venv is moved.
"$PYTHON" -m alembic upgrade head

step "3/5 Ingesting boards"
for board in $BOARDS; do
  "$PYTHON" -m career_radar.cli --action ingest --source "${board%%:*}" --slug "${board#*:}"
done

step "4/5 Classifying data-family postings (pre-filter)"
"$PYTHON" -m career_radar.cli --action classify

step "5/5 Evaluating data-family postings with Gemini"
"$PYTHON" -m career_radar.cli --action evaluate \
  --resume-path "$RESUME_PATH" --limit "$LIMIT" --allowed-countries "$ALLOWED_COUNTRIES"

echo
echo "Pipeline finished."
