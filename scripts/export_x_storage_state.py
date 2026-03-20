#!/usr/bin/env python3
import argparse
import json
import sys
from pathlib import Path


def parse_args():
    parser = argparse.ArgumentParser(
        description='Open a real browser, let you log into X manually, then export Playwright storageState JSON.'
    )
    parser.add_argument(
        '--output',
        default='data/browser-session/x-storage-state.json',
        help='Where to write the exported storage state JSON.',
    )
    parser.add_argument(
        '--start-url',
        default='https://x.com/i/flow/login',
        help='Initial URL to open in the browser.',
    )
    parser.add_argument(
        '--channel',
        default='',
        help='Optional browser channel such as "chrome" or "msedge".',
    )
    parser.add_argument(
        '--slow-mo',
        type=int,
        default=0,
        help='Optional Playwright slow motion delay in milliseconds.',
    )
    return parser.parse_args()


def main():
    args = parse_args()

    try:
        from playwright.sync_api import sync_playwright
    except Exception:
        print('Playwright is not installed. Install dependencies and run `python -m playwright install chromium`.', file=sys.stderr)
        return 1

    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    print('Opening a real browser for manual X login.')
    print(f'Start URL: {args.start_url}')
    print('Steps:')
    print('1. Log into X manually in the opened browser window.')
    print('2. Wait until you can see the home timeline or compose page.')
    print('3. Return to this terminal and press Enter to save the session state.')
    print('4. Press Ctrl+C instead if you want to cancel.')

    try:
        with sync_playwright() as playwright:
            launch_kwargs = {
                'headless': False,
                'slow_mo': args.slow_mo,
            }
            if args.channel:
                launch_kwargs['channel'] = args.channel

            browser = playwright.chromium.launch(**launch_kwargs)
            context = browser.new_context(locale='en-US')
            page = context.new_page()

            try:
                page.goto(args.start_url, wait_until='domcontentloaded')
                input('\nPress Enter after you have logged in successfully...')

                try:
                    page.goto('https://x.com/home', wait_until='domcontentloaded', timeout=15000)
                except Exception:
                    pass

                state = context.storage_state()
                output_path.write_text(json.dumps(state, indent=2), encoding='utf-8')

                cookies = len(state.get('cookies', []))
                origins = len(state.get('origins', []))
                print(f'\nSaved storage state to: {output_path}')
                print(f'Cookies: {cookies} | Origins: {origins}')
                print('Paste the JSON from that file into the app under "Save Browser Session State".')
            finally:
                context.close()
                browser.close()
    except KeyboardInterrupt:
        print('\nCanceled.')
        return 130

    return 0


if __name__ == '__main__':
    raise SystemExit(main())
