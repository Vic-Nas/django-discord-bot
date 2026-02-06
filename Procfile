release: python manage.py migrate && python manage.py collectstatic --noinput
web: gunicorn project.wsgi:application --bind 0.0.0.0:$PORT
