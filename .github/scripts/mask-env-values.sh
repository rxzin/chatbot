#!/usr/bin/env bash
#
# Tells GitHub Actions to hide every value in an env file from the logs.

set -euo pipefail

while IFS= read -r line || [ -n "$line" ]; do
  case "$line" in
    '' | \#*) continue ;;
    *=*) ;;
    *) continue ;;
  esac

  value="${line#*=}"
  value="${value%\"}"
  value="${value#\"}"
  value="${value%\'}"
  value="${value#\'}"

  # Short values like ports and "true" aren't sensitive, and masking them garbles logs.
  if [ "${#value}" -ge 6 ]; then
    printf '::add-mask::%s\n' "$value"
  fi
done < "$1"
