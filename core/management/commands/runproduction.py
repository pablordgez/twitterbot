import os
import sys
import signal
import threading
import uuid
from django.core.management.base import BaseCommand
from django.core.management import call_command
from django.db import connection

import waitress
from twitterbot.wsgi import application
from core.services.scheduler import run_scheduler_loop

class Command(BaseCommand):
    help = 'Runs the production server with scheduler and waitress'

    def handle(self, *args, **options):
        # Validate env vars
        required_env_vars = ['APP_SECRET_KEY', 'ENCRYPTION_KEY', 'ALLOWED_HOSTS']
        missing = []
        for var in required_env_vars:
            val = os.environ.get(var)
            if not val or val == 'change_me':
                missing.append(var)

        if missing:
            self.stderr.write(self.style.ERROR(f"Missing or default required environment variables: {', '.join(missing)}"))
            sys.exit(1)

        self.stdout.write("Running migrations...")
        call_command('migrate', interactive=False)

        self.stdout.write("Enabling WAL mode...")
        with connection.cursor() as cursor:
            # We wrap this in a try-except because some databases (if not SQLite) might not support this
            try:
                cursor.execute('PRAGMA journal_mode=WAL;')
                row = cursor.fetchone()
                if row and row[0].upper() != 'WAL':
                    self.stderr.write(self.style.ERROR(f"Failed to enable WAL mode. Got: {row[0]}"))
                else:
                    self.stdout.write(self.style.SUCCESS("WAL mode enabled."))
            except Exception as e:
                self.stderr.write(self.style.ERROR(f"Error setting WAL mode: {e}"))

        self.stdout.write("Starting scheduler thread...")

        stop_event = threading.Event()
        owner_id = str(uuid.uuid4())

        scheduler_thread = threading.Thread(
            target=run_scheduler_loop,
            args=(owner_id, stop_event),
            daemon=True
        )
        scheduler_thread.start()

        self.stdout.write("Starting Waitress...")

        def shutdown_handler(signum, frame):
            self.stdout.write("\nShutting down scheduler...")
            stop_event.set()
            scheduler_thread.join(timeout=15)
            self.stdout.write("Exiting...")
            sys.exit(0)

        signal.signal(signal.SIGINT, shutdown_handler)
        signal.signal(signal.SIGTERM, shutdown_handler)

        try:
            waitress.serve(application, host='0.0.0.0', port=8080)
        except Exception as e:
            self.stderr.write(self.style.ERROR(f"Waitress failed: {e}"))
            shutdown_handler(None, None)
