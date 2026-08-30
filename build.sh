#!/usr/bin/env bash
set -o errexit

pip install -r requirements.txt
# collectstatic needs a key even when Render has not injected one yet
export SECRET_KEY="${SECRET_KEY:-collectstatic-build-only}"
export DEBUG="${DEBUG:-False}"
python bp/manage.py collectstatic --noinput
