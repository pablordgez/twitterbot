import os
from unittest.mock import patch, MagicMock

from django.core.management import call_command
from django.test import TestCase

from core.management.commands.runproduction import scheduler_supervisor


class TestRunProductionCommand(TestCase):
    @patch.dict(os.environ, {
        'APP_SECRET_KEY': 'test-secret',
        'ENCRYPTION_KEY': 'test-key',
        'ALLOWED_HOSTS': '*'
    })
    @patch('core.management.commands.runproduction.call_command')
    @patch('core.management.commands.runproduction.connection')
    @patch('core.management.commands.runproduction.threading.Thread')
    @patch('core.management.commands.runproduction.waitress.serve')
    def test_successful_startup(self, mock_serve, mock_thread, mock_connection, mock_call_command):
        # Mock cursor for WAL mode
        mock_cursor = MagicMock()
        mock_cursor.fetchone.return_value = ['wal']
        mock_connection.cursor.return_value.__enter__.return_value = mock_cursor

        # Run command
        call_command('runproduction')

        # Assert migrations ran
        mock_call_command.assert_any_call('migrate', interactive=False)

        # Assert WAL mode was attempted
        mock_cursor.execute.assert_called_with('PRAGMA journal_mode=WAL;')

        # Assert scheduler thread started
        mock_thread.return_value.start.assert_called_once()

        # Assert waitress started
        mock_serve.assert_called_once()

    @patch.dict(os.environ, clear=True)
    def test_missing_env_vars(self):
        with self.assertRaises(SystemExit) as cm:
            call_command('runproduction')

        self.assertEqual(cm.exception.code, 1)

    @patch.dict(os.environ, {
        'APP_SECRET_KEY': 'change_me',
        'ENCRYPTION_KEY': 'test-key',
        'ALLOWED_HOSTS': '*'
    })
    def test_default_env_vars(self):
        with self.assertRaises(SystemExit) as cm:
            call_command('runproduction')

        self.assertEqual(cm.exception.code, 1)

    @patch.dict(os.environ, {
        'APP_SECRET_KEY': 'test-secret',
        'ENCRYPTION_KEY': 'test-key',
        'ALLOWED_HOSTS': '*'
    })
    @patch('core.management.commands.runproduction.call_command')
    @patch('core.management.commands.runproduction.waitress.serve')
    @patch('core.management.commands.runproduction.threading.Thread')
    @patch('core.management.commands.runproduction.sys.exit')
    def test_waitress_exception_triggers_shutdown(self, mock_exit, mock_thread, mock_serve, mock_call_command):
        mock_serve.side_effect = Exception("Waitress failed")

        call_command('runproduction')

        mock_thread.return_value.join.assert_called_once()
        mock_exit.assert_called_once_with(0)

    @patch('core.management.commands.runproduction.log_event')
    @patch('core.management.commands.runproduction.run_scheduler_loop')
    def test_scheduler_supervisor_restarts_after_crash(self, mock_loop, mock_log_event):
        mock_loop.side_effect = [Exception("boom"), None]

        class StopAfterSecondWait:
            def __init__(self):
                self.wait_calls = 0

            def is_set(self):
                return False

            def wait(self, timeout):
                self.wait_calls += 1
                return self.wait_calls >= 2

        stop_event = StopAfterSecondWait()

        scheduler_supervisor(stop_event, restart_delay_seconds=0)

        self.assertEqual(mock_loop.call_count, 2)
        mock_log_event.assert_called_once()
        self.assertEqual(stop_event.wait_calls, 2)
