# Twitter Bot Administrator

A self-hosted, single-user administrative tool for configuring and operating posting-only X/Twitter bot accounts.

## Overview

This application is designed to act as an ad hoc, self-hosted utility for managing one or more X/Twitter bot accounts. It bypasses the need for the official X/Twitter API by securely extracting and utilizing session data from browser-copied cURL requests, login information or session cookies. 

The system provides robust scheduling capabilities (one-time and recurring), tweet list management (including CSV imports), and a built-in execution engine, all packaged within a single, lightweight Docker container.

## Key Features

*   **Single-Admin Interface:** Secure, authenticated dashboard for managing all operations.
*   **cURL Account Import:** Configure posting accounts by simply pasting browser-copied cURL requests. The system automatically extracts, encrypts, and stores only the minimum required session fields, discarding the full raw request.
    * Alternatively, set up login credentials or an existing session's cookies to simulate a real user workflow with a headless browser to avoid automation detection. This method is more risky and can lead to account suspensions, but the alternative HTTP based method might not work at all.  
*   **Tweet Lists & CSV Import:** Organize tweets into reusable lists. Easily bulk-import tweets using single-column CSV files or direct text pasting.
*   **Advanced Scheduling:**
    *   **One-time:** Schedule a specific tweet or a randomly selected tweet from a list for a precise time.
    *   **Recurring:** Set up intervals (e.g., every 6 hours, every 2 days) with automatic daylight-saving time (DST) handling using IANA timezones.
    *   **Content Modes:** Choose fixed content, fixed content from a list, or random content dynamically resolved at post time.
*   **Multi-Account Support:** Target single or multiple accounts with the same schedule. For random content, choose to share the same tweet across accounts or randomize per account.
*   **Embedded Execution Engine:** A custom, database-backed scheduler loop runs securely in-process, ensuring exact at-most-once execution semantics without relying on external queues or workers (like Celery or Redis).
*   **Notifications & History:** Configure per-account SMTP email notifications for posting failures and review a comprehensive, searchable audit history.

## Architecture

*   **Framework:** Django 5.2 LTS (Python 3.12)
*   **Database:** SQLite (WAL mode enabled) on a persistent local volume.
*   **UI:** Django Templates + HTMX + Tabler UI Kit.
*   **Deployment:** Single Docker container running a custom entrypoint that manages migrations, the embedded scheduler thread, and Waitress WSGI server.
*   **Security:** Fernet-based application-level encryption for API secrets and SMTP credentials.

## Prerequisites

*   [Docker](https://docs.docker.com/get-docker/)
*   [Docker Compose](https://docs.docker.com/compose/install/)

## Quick Start (Deployment)

The application is designed to be deployed effortlessly via Docker Compose.

1.  **Clone the repository (or create a directory with the compose file):**
    ```bash
    git clone <repository-url>
    cd twitterbot
    ```

2.  **Generate a secure encryption key:**
    You need a valid 32-byte url-safe base64-encoded string for the Fernet encryption key.
    ```bash
    python3 -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
    ```

3.  **Configure Environment Variables:**
    Copy the example environment file and edit it:
    ```bash
    cp .env.example .env
    ```
    Edit `.env` and set your generated key and a secure Django secret key:
    ```env
    APP_SECRET_KEY=your-very-long-secure-random-string
    ENCRYPTION_KEY=your-generated-fernet-key
    ALLOWED_HOSTS=localhost,127.0.0.1,your-domain.com
    TZ=UTC
    ```

4.  **Start the Application:**
    ```bash
    docker-compose up -d
    ```

5.  **Access the Interface:**
    Open your browser and navigate to `http://localhost:8080`.

## Initial Setup & Usage

1.  **First-Run Setup:** Upon first visiting the application, you will be prompted to create the single Administrator account. This is a one-time process.
2.  **Add an Account:** Navigate to **Accounts > Add Account**. Open Twitter/X in your browser, open the Network Tab in Developer Tools, send a test tweet, right-click the `CreateTweet` request, and select "Copy as cURL (bash)". Paste this into the application.
    If X blocks direct request-based posting or automated login, you can instead import a real browser session. The app accepts Playwright `storage_state`, browser cookie-export JSON, simple cookie-map JSON, or a raw `Cookie:` header. One way to generate a compatible export is:
    ```bash
    py -3 scripts/export_x_storage_state.py
    ```
    Log into X manually in the opened browser, press Enter in the terminal, then paste the generated JSON from `data/browser-session/x-storage-state.json` into the account page under **Browser Session Import**.
3.  **Create Tweet Lists:** Go to **Tweet Lists** to manually add tweets or import them via CSV.
4.  **Schedule Posts:** Navigate to **Schedules** to create new one-time or recurring posting tasks.

## Security Considerations

*   **Protect your `.env` file:** It contains the keys used to encrypt your Twitter session tokens and SMTP passwords. If you lose the `ENCRYPTION_KEY`, you will not be able to decrypt your stored accounts.
*   **Data Volume:** The SQLite database is stored in the `app_data` Docker volume. Ensure the host filesystem is appropriately secured.
*   **Reverse Proxy:** While the application can bind to ports locally, if exposing to the public internet, it is highly recommended to place it behind a reverse proxy (like Nginx, Caddy, or Traefik) that handles TLS/SSL termination.

## Development Setup

If you wish to run the application locally for development:

1.  Create and activate a virtual environment:
    ```bash
    python3.12 -m venv .venv
    source .venv/bin/activate
    ```
2.  Install dependencies:
    ```bash
    pip install -r requirements.txt
    python -m playwright install chromium
    ```
3.  Set environment variables locally (or use a tool like `direnv`):
    ```bash
    export APP_SECRET_KEY="dev-secret"
    export ENCRYPTION_KEY=$(python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())")
    export ALLOWED_HOSTS="*"
    ```
4.  Run migrations:
    ```bash
    python manage.py migrate
    ```
5.  Start the development server (which also starts the embedded scheduler):
    ```bash
    python manage.py runserver
    ```

### Running Tests

```bash
# Run all tests
python manage.py test

# Run linting
ruff check .
```
