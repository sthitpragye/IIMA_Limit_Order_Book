# IIMA Limit Order Book — Trading Simulation Platform

A web-based trading system that simulates a real stock exchange limit order book. Built with Django and Django Channels, it supports multiple user roles, real-time order book updates via WebSockets (backed by Redis), iceberg orders, stop-loss orders, market pause/resume controls, and full admin tooling for classroom or demonstration use.

---

## Table of Contents

1. [Project Overview](#project-overview)
2. [Features](#features)
3. [System Architecture](#system-architecture)
4. [Prerequisites](#prerequisites)
5. [Installation and Setup](#installation-and-setup)
6. [Environment Configuration](#environment-configuration)
7. [User Roles and Permissions](#user-roles-and-permissions)
8. [Creating Users](#creating-users)
   - [Self-Registration](#self-registration)
   - [Creating a Superuser (Admin)](#creating-a-superuser-admin)
   - [Bulk User Creation via CSV (Admin Only)](#bulk-user-creation-via-csv-admin-only)
   - [Bulk User Deletion via CSV (Admin Only)](#bulk-user-deletion-via-csv-admin-only)
9. [Logging In and Role Routing](#logging-in-and-role-routing)
10. [Placing Orders](#placing-orders)
    - [Market Maker — Limit Orders](#market-maker--limit-orders)
    - [Trader — Market Orders](#trader--market-orders)
    - [Stop-Loss Orders](#stop-loss-orders)
    - [Iceberg (Disclosed Quantity) Orders](#iceberg-disclosed-quantity-orders)
    - [Immediate-or-Cancel (IOC) Orders](#immediate-or-cancel-ioc-orders)
11. [Modifying and Cancelling Orders](#modifying-and-cancelling-orders)
12. [Order Matching Logic](#order-matching-logic)
13. [Admin Controls](#admin-controls)
14. [Real-Time Updates (WebSockets + Redis)](#real-time-updates-websockets--redis)
15. [Downloading Data](#downloading-data)
16. [Docker Deployment](#docker-deployment)
17. [URL Reference](#url-reference)
18. [Contributing](#contributing)
19. [License](#license)

---

## Project Overview

The IIMA Limit Order Book simulates a two-sided securities exchange for educational and demonstration purposes (e.g., finance courses at IIM Ahmedabad). An instructor (Admin) sets up the session, creates participant accounts, and controls the market. Participants log in as either **Market Makers** (who post limit orders to build the book) or **Traders** (who submit market orders that execute against the book). All order-book changes and trade prints are pushed to every connected browser in real time via WebSockets.

---

## Features

- **Authentication**: Registration, login/logout, and in-session password reset
- **Role-based dashboards**: Separate UIs for Admin, Market Maker, and Trader
- **Limit orders** (Market Makers): priced buy/sell orders that rest on the book
- **Market orders** (Traders): execute immediately at the best available price
- **Stop-loss orders**: triggered when the last trade price crosses a target level
- **Iceberg / disclosed-quantity orders**: show only a portion of total size to the market
- **Immediate-or-Cancel (IOC)**: unfilled portion is cancelled upon submission
- **Order modification and cancellation** (Admin)
- **Real-time order book and trade feed** via Django Channels + Redis
- **Market pause / resume** (Admin): halts all new order submissions
- **Bulk user creation** via CSV upload (Admin)
- **Bulk user deletion** via CSV upload (Admin)
- **CSV download** of order book and trade data
- **Docker-ready** with a single `docker compose up` workflow

---

## System Architecture

```
Browser (WebSocket + HTTP)
        │
        ▼
  Daphne (ASGI server)
        │
   ┌────┴────────────────────┐
   │  Django Application     │
   │  ┌──────────────────┐   │
   │  │  trading app     │   │  ← Orders, Trades, Stop-Loss, Market Control
   │  │  students app    │   │  ← Registration, Bulk upload/delete, Password reset
   │  └──────────────────┘   │
   └─────────────┬───────────┘
                 │
         Redis (Channel Layer)
          (real-time broadcasts)
                 │
        PostgreSQL / SQLite
          (persistent data)
```

---

## Prerequisites

| Requirement | Version |
|---|---|
| Python | 3.8 or later (3.11 recommended) |
| Django | 5.x |
| Redis | 6.x or later |
| PostgreSQL | 13+ (optional; SQLite works for local dev) |
| pip | latest |

---

## Installation and Setup

### 1. Clone the Repository

```sh
git clone <repository-url>
cd IIMA_Limit_Order_Book
```

### 2. Create and Activate a Virtual Environment

```sh
python -m venv .venv

# macOS / Linux
source .venv/bin/activate

# Windows (PowerShell)
.venv\Scripts\Activate.ps1

# Windows (cmd.exe)
.venv\Scripts\activate.bat
```

### 3. Install Python Dependencies

```sh
cd trading_system
pip install -r requirements.txt
```

### 4. Start Redis

Redis is required for real-time WebSocket broadcasting. Install and start it before running the server.

**Ubuntu / Debian**
```sh
sudo apt update && sudo apt install -y redis-server
sudo systemctl enable --now redis-server
redis-cli ping          # should return PONG
```

**macOS (Homebrew)**
```sh
brew install redis
brew services start redis
redis-cli ping
```

**Windows**
Use [Memurai](https://www.memurai.com/) (a Redis-compatible server for Windows) or run Redis via WSL2.

### 5. Configure Environment Variables

Copy the example file and fill in your values (see [Environment Configuration](#environment-configuration)):

```sh
cp .env.example .env
# then edit .env with your preferred editor
```

### 6. Apply Database Migrations

```sh
python manage.py migrate
```

### 7. Create a Superuser (Admin Account)

```sh
python manage.py createsuperuser
```

You will be prompted for:

```
User ID: admin           ← used to log in (must be unique)
Name: Admin User
Email address: admin@example.com
Password: ************
Password (again): ************
```

> **Note:** The `Username` field in this project maps to `User ID`, not a human name. Use a short, memorable value like `admin` or your roll/employee number.

### 8. Run the Development Server

```sh
python manage.py runserver
```

### 9. Open the Application

Navigate to [http://127.0.0.1:8000/](http://127.0.0.1:8000/) in your browser.

---

## Environment Configuration

The application reads configuration from a `.env` file placed inside `trading_system/`. The available variables are:

| Variable | Default | Description |
|---|---|---|
| `DEBUG` | `0` | Set to `1` to enable Django debug mode |
| `SECRET_KEY` | (insecure default) | Django secret key — **change this in production** |
| `DB_NAME` | `trading_platform` | PostgreSQL database name |
| `DB_USER` | `trading_user` | PostgreSQL user |
| `DB_PASSWORD` | — | PostgreSQL password |
| `DB_HOST` | `localhost` | PostgreSQL host |
| `DB_PORT` | `5432` | PostgreSQL port |
| `REDIS_URL` | `redis://127.0.0.1:6379` | Redis connection URL |
| `ALLOWED_HOSTS` | `*` | Comma-separated list of allowed hostnames |

**Example `.env` for local development (SQLite + local Redis):**

```env
DEBUG=1
SECRET_KEY=change-me-to-a-long-random-string
REDIS_URL=redis://127.0.0.1:6379
ALLOWED_HOSTS=127.0.0.1,localhost
```

---

## User Roles and Permissions

| Role | Login | Capabilities |
|---|---|---|
| **Admin** | Django superuser account | Full dashboard, bulk user management, order modification, market pause/resume, clear database |
| **Market Maker** | Standard account with role `MARKET_MAKER` | Place/cancel limit buy and sell orders, view order book, view own trades |
| **Trader** | Standard account with role `TRADER` | Place/cancel market orders (executes against best limit), view order book, view own trades |

Role is set at account creation time and determines both the dashboard shown after login and the order types permitted.

---

## Creating Users

### Self-Registration

Any visitor can register at `/register/`. They must provide:

- **User ID** — unique identifier used to log in (numbers and letters, no spaces)
- **Name** — display name (letters and spaces only)
- **Email** — valid email address
- **Role** — `Trader` or `Market Maker`
- **Password** — must mix letters, digits, and special characters

After successful registration the user is redirected to the login page.

### Creating a Superuser (Admin)

Run the management command (described in step 7 of setup):

```sh
python manage.py createsuperuser
```

Superuser accounts automatically receive the `ADMIN` role and full platform access.

### Bulk User Creation via CSV (Admin Only)

Admins can create many participant accounts at once by uploading a CSV file at `/bulk_user_upload/`.

**Required CSV format:**

The file must have exactly these column headers in the first row (case-sensitive):

```
Roll,Name,Mail,Role,Password
```

**Example `users.csv`:**

```csv
Roll,Name,Mail,Role,Password
2301001,Aisha Sharma,aisha@iima.ac.in,MARKET_MAKER,Pass@123
2301002,Rohan Mehta,rohan@iima.ac.in,TRADER,Trade#456
2301003,Priya Nair,priya@iima.ac.in,MARKET_MAKER,Maker!789
2301004,Arjun Das,arjun@iima.ac.in,TRADER,Trade#321
```

**Field validation rules:**

| Field | Rule |
|---|---|
| `Roll` | Numbers only; becomes the user's login ID |
| `Name` | Letters, spaces, and hyphens only |
| `Mail` | Must contain `@` and `.` |
| `Role` | Must be exactly `TRADER` or `MARKET_MAKER` |
| `Password` | Must contain letters, digits, and at least one special character |

After upload, the page displays:
- ✅ **Created** — successfully created accounts
- ⚠️ **Skipped** — rolls that already exist in the database
- ❌ **Invalid** — rows that failed validation, with per-row error messages

### Bulk User Deletion via CSV (Admin Only)

Admins can delete accounts in bulk at `/bulk-delete/`. The CSV must have at least two columns:

```
Roll,Name
2301001,Aisha Sharma
2301002,Rohan Mehta
```

Only `Roll` is used for lookup. `Name` is displayed in the results summary for readability. Rows with non-numeric rolls or missing roll numbers are rejected with an error message.

---

## Logging In and Role Routing

Navigate to [http://127.0.0.1:8000/](http://127.0.0.1:8000/). Enter your **User ID** (the `Roll` number or the ID set at registration) and **Password**.

After login, the system automatically routes each user to their appropriate dashboard:

| Role | Redirected to |
|---|---|
| Admin (superuser) | `/admin_home/` |
| Market Maker | `/market_maker_home/` |
| Trader | `/trader_home/` |

To **reset your password**, go to `/password-reset/` while logged in.

---

## Placing Orders

### Market Maker — Limit Orders

Market Makers access their dashboard at `/market_maker_home/`. Each order requires:

| Field | Description |
|---|---|
| **Order Type** | `BUY` or `SELL` |
| **Quantity** | Total number of shares |
| **Disclosed Quantity** | Visible portion (≥ 10% of quantity; equal to quantity for a fully visible order) |
| **Price** | Limit price (decimal, e.g. `152.50`) |
| **IOC** | `True` to cancel any unfilled portion immediately |
| **Stop-loss** | See [Stop-Loss Orders](#stop-loss-orders) |

Market Maker orders are passive — they rest on the book and are matched only when incoming Trader market orders cross them.

> **Tip:** To place a two-sided quote, submit a BUY limit order and a SELL limit order with the same quantity. The system validates that paired quantities match.

### Trader — Market Orders

Traders access their dashboard at `/trader_home/`. Each market order requires:

| Field | Description |
|---|---|
| **Order Type** | `BUY` or `SELL` |
| **Quantity** | Number of shares |
| **Disclosed Quantity** | Visible portion (≥ 10% of quantity) |
| **IOC** | `True` to cancel any unfilled portion immediately |

A Trader BUY market order executes against the best (lowest) ask in the book. A Trader SELL market order executes against the best (highest) bid. If no matching limit order exists, the order cannot be placed and an error is shown.

### Stop-Loss Orders

Available to Market Makers on the market maker dashboard. When placing an order, enable the **Stop-loss** toggle and provide:

- **Target Price** — the trigger level
- **Price** — the limit price at which the converted order will be placed (optional for market-mode stop-loss)

A stop-loss BUY triggers when the last trade price rises to or above the target. A stop-loss SELL triggers when the last trade price falls to or below the target. On trigger, the stop-loss is converted to a regular order and sent through the normal matching engine.

### Iceberg (Disclosed Quantity) Orders

Any order where **Disclosed Quantity < Total Quantity** is treated as an iceberg order. Only the disclosed portion is visible in the public order book. When the visible tranche is fully matched, the next tranche becomes visible automatically. The minimum disclosed quantity is 10% of total quantity (or 1 share, whichever is larger).

### Immediate-or-Cancel (IOC) Orders

Set the **IOC** flag to `True` when placing any order. Any portion of the order that cannot be matched immediately is cancelled; no residual rests on the book.

---

## Modifying and Cancelling Orders

### Cancellation (any logged-in user)

Each user can cancel their own unmatched orders from their dashboard by clicking **Cancel** next to the order. Stop-loss orders have a separate cancel button. Matched orders cannot be cancelled.

### Admin Order Modification

Admins can modify any unmatched limit order's **quantity**, **disclosed quantity**, and **price** via the modify order page at `/modify_order/`. Rules:

- The order must not already be matched.
- New disclosed quantity must be ≥ 10% of new quantity.
- Disclosed quantity cannot exceed total quantity.
- Price must be greater than 0.

---

## Order Matching Logic

The matching engine runs whenever a new Trader market order is submitted (`match_order` in `utils.py`):

1. A Trader BUY market order is matched against the cheapest unmatched SELL limit orders, in ascending price order (ties broken by timestamp — FIFO).
2. A Trader SELL market order is matched against the most expensive unmatched BUY limit orders, in descending price order (ties broken by timestamp — FIFO).
3. Partial fills are supported — a single incoming order may consume multiple resting limit orders.
4. For iceberg orders, only the currently disclosed tranche is consumed; the next tranche is revealed automatically.
5. Each matched pair creates a `Trade` record (buyer, seller, quantity, price, timestamp).
6. After each trade, the stop-loss engine checks whether any pending stop-loss orders have been triggered by the new closing price.

---

## Admin Controls

The admin dashboard at `/admin_home/` provides:

- **Live statistics**: trader count, market maker count, active orders, trades today, total trades, best bid/ask, spread, last trade price
- **Recent trades**: last 10 executed trades
- **Market Pause / Resume**: immediately halts all new order submissions platform-wide. A custom message can be displayed to users while the market is paused.
- **Order modification**: edit any resting limit order
- **Clear database**: wipe all orders and trades (useful between sessions)
- **Bulk user upload / delete**: manage participant accounts via CSV

---

## Real-Time Updates (WebSockets + Redis)

The order book and trade feed update in real time without page refresh. The flow is:

1. Any order placement, cancellation, modification, or trade triggers `broadcast_orderbook_update()`.
2. This function sends a message to the `orderbook_group` channel via the Redis channel layer.
3. All connected browsers receive the update via their WebSocket connection and re-render the order book and trade tables in place.

The WebSocket endpoint is managed by Django Channels (`consumers.py`) running under the Daphne ASGI server.

---

## Downloading Data

From any order book page, use the **Download CSV** buttons (where present in the template) to export:

- **Order Book** — all current unmatched limit orders with price, disclosed quantity, timestamp, and user ID
- **Trades** — all executed trades with price, quantity, buyer, seller, and timestamp

---

## Docker Deployment

A `Dockerfile` and `entrypoint.sh` are included for containerised deployment (e.g. Railway, Render, or a VPS).

### Quick Start with Docker Compose

From the project root:

```sh
docker compose up -d
```

The `entrypoint.sh` script automatically:
1. Runs `python manage.py migrate`
2. Creates a default superuser (`admin` / `admin123`) if one does not exist
3. Starts Daphne on `0.0.0.0:$PORT` (defaults to 8000)

> **Important:** Change the default superuser password immediately after the first login in any non-local environment.

### Environment Variables for Docker

Pass the same variables listed in [Environment Configuration](#environment-configuration) via your `docker-compose.yml` or platform environment settings. At minimum, set `SECRET_KEY`, `REDIS_URL`, and (if using PostgreSQL) the `DB_*` variables.

### Makefile Shortcuts (local dev)

```sh
make deps      # create .venv and install requirements
make migrate   # run database migrations
make run       # start the development server
make up        # docker compose up -d
```

---

## URL Reference

| URL | Description | Access |
|---|---|---|
| `/` | Login page | Public |
| `/register/` | Self-registration | Public |
| `/logout/` | Log out | Authenticated |
| `/role_router/` | Redirect to role-appropriate home | Authenticated |
| `/admin_home/` | Admin dashboard | Admin only |
| `/trader_home/` | Trader dashboard | Trader only |
| `/market_maker_home/` | Market Maker dashboard | Market Maker only |
| `/orderbook/` | Live order book view | Authenticated |
| `/modify_order/` | Order modification UI | Admin only |
| `/cancel_order/` | Cancel an order (POST) | Authenticated |
| `/cancel_stoploss_order/` | Cancel a stop-loss (POST) | Authenticated |
| `/bulk_user_upload/` | Bulk user creation via CSV | Admin only |
| `/bulk-delete/` | Bulk user deletion via CSV | Admin only |
| `/password-reset/` | Change password | Authenticated |
| `/clear/` | Wipe all orders and trades | Admin only |
| `/orderbook/get_buy_orders/` | JSON: current buy orders | Authenticated |
| `/orderbook/get_sell_orders/` | JSON: current sell orders | Authenticated |
| `/orderbook/get_recent_trades/` | JSON: last 10 trades | Authenticated |
| `/orderbook/get_best_bid/` | JSON: best bid | Authenticated |
| `/orderbook/get_best_ask/` | JSON: best ask | Authenticated |
| `/orderbook/get_market_status/` | JSON: pause state | Authenticated |
| `/market/toggle_market_pause/` | Pause or resume market (POST) | Admin only |

---

## Contributing

1. Fork the repository
2. Create a feature branch: `git checkout -b feature/your-feature`
3. Make your changes and add tests where applicable
4. Commit: `git commit -m 'Add your feature'`
5. Push: `git push origin feature/your-feature`
6. Open a pull request against `main`

Please follow the existing code style (PEP 8 for Python, consistent template structure) and describe the motivation and scope of your change in the pull request description.

---

## License

This project is licensed under the **MIT License** — see the [LICENSE](LICENSE) file for details.   
   ```
