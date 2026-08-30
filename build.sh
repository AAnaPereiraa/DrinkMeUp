#!/usr/bin/env bash
set -o errexit

pip install -r requirements.txt
python bp/manage.py collectstatic --noinput
