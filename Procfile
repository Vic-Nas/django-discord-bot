web: python manage.py collectstatic --noinput && gunicorn --bind 0.0.0.0:${PORT:-8080} --workers 1 --worker-class sync project.wsgi:application
