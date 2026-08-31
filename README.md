# DrinkMeUp

https://drinkmeup.onrender.com/

## Overview

DrinkMeUp recommends a cocktail from a curated menu based on taste, spirits, and how boozy you want it. You can sign in, use Google, or order as a guest.

Signed-in users get a Bar page: the order form plus the last 10 drinks they made (with rating and comment). Guests get the same order flow without a saved history.

## Technology

- Python 3.13, Django 5, django-allauth
- HTML / CSS
- Django REST Framework + JWT (`/api/`)
- Flutter app in `mobile/`
- Local database: SQLite (leave `DATABASE_URL` empty)
- Production: Render (web) + Neon (Postgres)

## Features

- Auth: sign up, log in, log out, change / reset password, Google OAuth
- Guest mode (no account)
- Bar order form: taste, spirits, boozy level
- Spirit families: Rum matches white / dark / spiced rum; Scotch matches blended and Islay; Whiskey matches Irish and rye. Those extra names are hidden on the form. Bourbon stays its own checkbox.
- If there is no exact boozy match, a nearby level or another drink in that taste is offered
- Cocktail page: ingredients, instructions, shuffle, mark as made, rate and comment
- Menu grouped by boozy nicknames (Starting slow / It's getting hot in here / to infinity and beyond)
- Imprint and Privacy Policy
- JWT API for the mobile app

## Run locally

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp bp/.env.example bp/.env
# set SECRET_KEY and DEBUG=True in bp/.env
cd bp
python manage.py migrate
python manage.py loaddata drinks
python manage.py runserver
```

Tests:

```bash
cd bp
source ../.venv/bin/activate
python manage.py test bar_do_pedro
```

## Production notes

- Hosting is Render. Database is Neon Postgres via `DATABASE_URL`.
- After adding new drinks, load them on Neon, for example: `python bp/manage.py loaddata drinks_coverage`
- Google login is optional. The operator sets `GOOGLE_CLIENT_ID` and `GOOGLE_CLIENT_SECRET` once on Render and adds this redirect URI in Google Cloud:

  `https://drinkmeup.onrender.com/accounts/google/login/callback/`

- Render free blocks SMTP, so password-reset email may not send unless you use another mail path.

## Expected later

- Online shop
- AI-driven suggestions
- Wine section

## Roles

Product owner: Pedro Pereira  
Developer: Ana Pereira
