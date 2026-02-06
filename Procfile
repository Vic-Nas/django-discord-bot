release: python manage.py migrate && python manage.py init_defaults && python manage.py collectstatic --noinput
web: gunicorn project.wsgi:application --bind 0.0.0.0:$PORT
bot: python bot/main.py
