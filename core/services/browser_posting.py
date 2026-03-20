import os
import logging
import json
import time
from datetime import datetime, UTC
from pathlib import Path

from core.models.accounts import PostingAccount
from core.services.encryption import decrypt
from core.services.history import redact_secrets
from core.services.x_response_parser import interpret_create_tweet_response

logger = logging.getLogger(__name__)

POST_BUTTON_SELECTORS = [
    '[data-testid="tweetButtonInline"]',
    '[data-testid="tweetButton"]',
    'button:has-text("Post")',
    'div[role="button"]:has-text("Post")',
    'button:has-text("Tweet")',
    'div[role="button"]:has-text("Tweet")',
    'button:has-text("Publicar")',
    'div[role="button"]:has-text("Publicar")',
]

STEALTH_INIT_SCRIPT = """
Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
window.chrome = window.chrome || { runtime: {} };
Object.defineProperty(navigator, 'languages', { get: () => ['en-US', 'en'] });
Object.defineProperty(navigator, 'plugins', { get: () => [1, 2, 3, 4, 5] });
"""

try:
    from playwright.sync_api import TimeoutError as PlaywrightTimeoutError, sync_playwright
    PLAYWRIGHT_IMPORT_ERROR = None
except Exception as exc:  # pragma: no cover - environment-dependent import
    sync_playwright = None
    PlaywrightTimeoutError = Exception
    PLAYWRIGHT_IMPORT_ERROR = exc


def execute_browser_post(account: PostingAccount, content: str) -> tuple[bool, str, dict]:
    if PLAYWRIGHT_IMPORT_ERROR is not None or sync_playwright is None:
        return False, 'Playwright is not installed on this runtime.', {}

    if not hasattr(account, 'browser_credential'):
        return False, 'Account missing browser credentials', {}

    try:
        username = decrypt(account.browser_credential.encrypted_username)
        password = decrypt(account.browser_credential.encrypted_password)
        storage_state = _load_storage_state(account)
    except Exception:
        return False, 'Browser credentials or storage state decryptable check failed', {}

    timeout_ms = int(os.environ.get('X_BROWSER_TIMEOUT_MS', '45000'))
    headless = os.environ.get('X_BROWSER_HEADLESS', 'true').lower() != 'false'
    slow_mo = int(os.environ.get('X_BROWSER_SLOW_MO_MS', '0'))
    channel = os.environ.get('X_BROWSER_CHANNEL', '').strip()

    try:
        with sync_playwright() as playwright:
            browser = _launch_browser(playwright, headless=headless, slow_mo=slow_mo, channel=channel)
            context_kwargs = {'locale': 'en-US'}
            if storage_state:
                context_kwargs['storage_state'] = storage_state
            context = browser.new_context(**context_kwargs)
            context.add_init_script(STEALTH_INIT_SCRIPT)
            page = context.new_page()
            page.set_default_timeout(timeout_ms)
            trace_started = False

            try:
                context.tracing.start(screenshots=True, snapshots=True)
                trace_started = True
                if storage_state:
                    logger.info('Browser post using saved storage state for account=%s', account.id)
                    page.goto('https://x.com/home', wait_until='domcontentloaded')
                else:
                    logger.info('Browser post using username/password login for account=%s', account.id)
                    _login(page, username, password)
                success, error_detail, response_meta = _submit_tweet(page, content, timeout_ms=timeout_ms)
                return success, error_detail, response_meta
            except PlaywrightTimeoutError:
                artifacts = _capture_debug_artifacts(context, page, label='timeout', trace_started=trace_started)
                logger.warning('Browser automation timed out. Artifacts=%s', artifacts)
                return False, _build_debug_error('Browser automation timed out while logging in or posting', artifacts), {
                    'mode': 'browser',
                    'artifacts': artifacts,
                }
            except Exception as exc:
                artifacts = _capture_debug_artifacts(context, page, label='error', trace_started=trace_started)
                logger.warning('Browser post failed: %s artifacts=%s', str(exc), artifacts)
                return False, _build_debug_error(str(exc), artifacts), {
                    'mode': 'browser',
                    'artifacts': artifacts,
                }
            finally:
                if trace_started:
                    _stop_trace_safely(context)
                context.close()
                browser.close()
    except Exception as exc:
        logger.warning('Browser setup failed: %s', str(exc))
        return False, str(exc), {}


def _login(page, username: str, password: str):
    page.goto('https://x.com/i/flow/login', wait_until='domcontentloaded')

    username_input = page.locator('input[name="text"]').first
    username_input.wait_for(state='visible')
    username_input.fill(username)
    _click_first(page, [
        'button:has-text("Next")',
        'div[role="button"]:has-text("Next")',
        'button:has-text("Siguiente")',
        'div[role="button"]:has-text("Siguiente")',
    ])

    password_input = page.locator('input[name="password"]').first
    if not password_input.is_visible():
        challenge_input = page.locator('input[name="text"]').first
        challenge_input.wait_for(state='visible')
        challenge_input.fill(username)
        _click_first(page, [
            'button:has-text("Next")',
            'div[role="button"]:has-text("Next")',
            'button:has-text("Siguiente")',
            'div[role="button"]:has-text("Siguiente")',
        ])

    password_input = page.locator('input[name="password"]').first
    password_input.wait_for(state='visible')
    password_input.fill(password)
    _click_first(page, [
        'button:has-text("Log in")',
        'div[role="button"]:has-text("Log in")',
        'button:has-text("Iniciar sesión")',
        'div[role="button"]:has-text("Iniciar sesión")',
    ])

    page.wait_for_load_state('networkidle')


def _submit_tweet(page, content: str, *, timeout_ms: int) -> tuple[bool, str, dict]:
    page.goto('https://x.com/compose/post', wait_until='domcontentloaded')

    editor = page.locator(
        '[data-testid="tweetTextarea_0"], div[role="textbox"][contenteditable="true"]'
    ).first
    editor.wait_for(state='visible')
    editor.click()
    page.keyboard.type(content, delay=25)

    response = _dispatch_post(page, timeout_ms=timeout_ms)
    response_meta = {'status_code': response.status, 'mode': 'browser'}

    try:
        data = response.json()
    except Exception:
        body = response.text()
        logger.warning('Browser CreateTweet non-JSON response: status=%s body=%s', response.status, body[:1000])
        return False, 'Invalid JSON response from browser-posted CreateTweet', response_meta

    success, error_detail = interpret_create_tweet_response(data)
    logger.info(
        'Browser CreateTweet response: status=%s success=%s body=%s',
        response.status,
        success,
        str(redact_secrets(data))[:1000],
    )
    return success, error_detail, response_meta


def _dispatch_post(page, *, timeout_ms: int):
    attempts = [
        ('button click', lambda: _click_post_button(page, timeout_ms=min(timeout_ms, 8000))),
        ('Control+Enter', lambda: page.keyboard.press('Control+Enter')),
    ]

    last_error = None
    response_timeout = min(timeout_ms, 12000)

    for label, action in attempts:
        try:
            with page.expect_response(
                lambda response: '/CreateTweet' in response.url and response.request.method == 'POST',
                timeout=response_timeout,
            ) as response_info:
                action()
            logger.info('Browser post submitted via %s', label)
            return response_info.value
        except PlaywrightTimeoutError as exc:
            last_error = exc
            logger.warning('Browser post submit attempt timed out via %s', label)
        except Exception as exc:
            last_error = exc
            logger.warning('Browser post submit attempt failed via %s: %s', label, str(exc))

    raise RuntimeError(f'Could not submit tweet after multiple attempts: {last_error}')


def _click_post_button(page, *, timeout_ms: int):
    deadline = time.monotonic() + (timeout_ms / 1000)
    last_states = []

    while time.monotonic() < deadline:
        current_states = []
        for selector in POST_BUTTON_SELECTORS:
            locator = page.locator(selector).first
            try:
                count = locator.count()
            except Exception:
                continue

            if not count:
                continue

            try:
                visible = locator.is_visible()
            except Exception:
                visible = False

            if not visible:
                current_states.append(f'{selector}=hidden')
                continue

            disabled = _is_disabled(locator)
            current_states.append(f'{selector}={"disabled" if disabled else "enabled"}')
            if disabled:
                continue

            try:
                locator.scroll_into_view_if_needed(timeout=min(timeout_ms, 2000))
            except Exception:
                pass

            locator.click(timeout=min(timeout_ms, 5000))
            return selector

        if current_states:
            last_states = current_states
        page.wait_for_timeout(200)

    state_summary = ', '.join(last_states) if last_states else 'no visible post button found'
    raise RuntimeError(f'Could not find an enabled post button: {state_summary}')


def _is_disabled(locator) -> bool:
    disabled_attr = locator.get_attribute('disabled')
    aria_disabled = locator.get_attribute('aria-disabled')
    data_disabled = locator.get_attribute('data-disabled')
    return (
        disabled_attr is not None
        or aria_disabled == 'true'
        or data_disabled == 'true'
    )


def _click_first(page, selectors):
    for selector in selectors:
        locator = page.locator(selector).first
        if locator.count() and locator.is_visible():
            locator.click()
            return
    raise RuntimeError(f'Could not find clickable element for selectors: {selectors}')


def _load_storage_state(account: PostingAccount):
    encrypted_storage_state = getattr(account.browser_credential, 'encrypted_storage_state', None)
    if not encrypted_storage_state:
        return None

    decrypted = decrypt(encrypted_storage_state)
    parsed = json.loads(decrypted)
    if not isinstance(parsed, dict):
        raise ValueError('Storage state must decrypt to a JSON object')
    return parsed


def _launch_browser(playwright, *, headless: bool, slow_mo: int, channel: str):
    launch_kwargs = {
        'headless': headless,
        'slow_mo': slow_mo,
        'args': [
            '--disable-blink-features=AutomationControlled',
            '--disable-dev-shm-usage',
            '--start-maximized',
        ],
    }
    if channel:
        launch_kwargs['channel'] = channel
        logger.info('Launching browser with channel=%s', channel)

    return playwright.chromium.launch(**launch_kwargs)


def _capture_debug_artifacts(context, page, *, label: str, trace_started: bool) -> dict:
    artifact_dir = Path(os.environ.get('X_BROWSER_ARTIFACT_DIR', '/app/data/browser-debug'))
    artifact_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(UTC).strftime('%Y%m%d-%H%M%S')
    base = artifact_dir / f'x-browser-{stamp}-{label}'
    artifacts = {}

    try:
        screenshot_path = base.with_suffix('.png')
        page.screenshot(path=str(screenshot_path), full_page=True)
        artifacts['screenshot'] = str(screenshot_path)
    except Exception:
        pass

    try:
        html_path = base.with_suffix('.html')
        html_path.write_text(page.content(), encoding='utf-8')
        artifacts['html'] = str(html_path)
    except Exception:
        pass

    if trace_started:
        try:
            trace_path = base.with_suffix('.zip')
            context.tracing.stop(path=str(trace_path))
            artifacts['trace'] = str(trace_path)
        except Exception:
            pass

    return artifacts


def _stop_trace_safely(context):
    try:
        context.tracing.stop()
    except Exception:
        pass


def _build_debug_error(message: str, artifacts: dict) -> str:
    if not artifacts:
        return message
    artifact_summary = ', '.join(f'{key}={value}' for key, value in artifacts.items())
    return f'{message}. Debug artifacts: {artifact_summary}'
