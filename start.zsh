#!/bin/zsh
set -eu
PROJECT_ROOT=${0:A:h}
for brew_bin in /opt/homebrew/bin/brew /usr/local/bin/brew; do
  if [[ -x "$brew_bin" ]]; then
    eval "$("$brew_bin" shellenv)"
    break
  fi
done
if command -v brew >/dev/null 2>&1; then
  [[ -x "$(brew --prefix)/bin/python3.12" ]] || brew install python@3.12
  command -v node >/dev/null 2>&1 || brew install node@24
  if [[ -d "$(brew --prefix)/opt/node@24/bin" ]]; then
    export PATH="$(brew --prefix)/opt/node@24/bin:$PATH"
  fi
  if [[ " ${*} " != *" --skip-topic-model "* ]]; then
    command -v llama-server >/dev/null 2>&1 || brew install llama.cpp
  fi
fi
if [[ -x "$PROJECT_ROOT/.wxq-runtime/bin/python" ]]; then
  PYTHON="$PROJECT_ROOT/.wxq-runtime/bin/python"
elif command -v python3.12 >/dev/null 2>&1; then
  PYTHON=$(command -v python3.12)
elif command -v python3 >/dev/null 2>&1; then
  PYTHON=$(command -v python3)
else
  print -u2 'Install Homebrew (https://brew.sh), then run this script again.'
  exit 1
fi
exec "$PYTHON" "$PROJECT_ROOT/frontend/launch.py" "$@"
