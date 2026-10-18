# 💸 SplitLite

A premium, elegant, and mobile-responsive group expense-splitting PWA (inspired by Splitwise). Designed with modern dark glassmorphism, native-feeling micro-animations, and a robust backend engine to split bills, track friendships, simplify group debts, and resolve expenses in seconds.

Developed and designed with 🤍 by **Garv Jindal**.

---
![SplitLite Logo](tracker/static/tracker/icon-512.png)


---

## 🚀 Key Features

* **Precision Math Splitting Engine**: Split bills equally, by exact amounts, by percentage, or by custom share ratios. Includes protection against decimal rounding drift (assigning remainder cents to the payer).
* **Greedy Debt Simplification**: A robust matrix algorithm that matches all group debtors and creditors, simplifying net outstanding balances into the absolute minimum number of peer-to-peer transfers.
* **Self-Contained Google OAuth2 SSO**: Secure, zero-dependency one-click social authentication running purely on Python standard libraries without external package bloat.
* **Progressive Web App (PWA)**: Installed directly on iOS and Android with maskable high-res logos, service-worker caching, offline readiness, and custom standalone status bar configurations.
* **Launch Splash Screen**: Dynamic fullscreen session launch overlay `#0f1117` complete with scaling logo spring entries, staggered fade-ins, and a looping, glowing pulsing heart `🤍`.
* **Analytics & Timelines**: Seamless activity feeds tracking group logs, friendly ledger balances, and comprehensive monthly category distribution charts.

---

## 🛠️ Technology Stack

* **Backend**: Python, Django 5.1.4, WhiteNoise (static handling), Gunicorn
* **Frontend**: HTML5 Semantic Structure, Vanilla CSS (Custom Design Token System), Vanilla ES6 JavaScript
* **Database**: SQLite (Development), PostgreSQL (Production)
* **Hosting**: Railway (Auto-deployment pipeline synced with GitHub)

---

## ⚙️ Installation & Local Setup

### 1️⃣ Clone the Repository
```bash
git clone https://github.com/Jindalgarv/splitlite.git
cd splitlite
```

### 2️⃣ Configure Environment Variables
Create a `.env` file in the root folder:
```env
DEBUG=True
SECRET_KEY="your-local-django-secret-key"
GOOGLE_CLIENT_ID="your-google-oauth-client-id.apps.googleusercontent.com"
GOOGLE_CLIENT_SECRET="your-google-oauth-client-secret"
VAPID_PUBLIC_KEY="your-vapid-public-key"
VAPID_PRIVATE_KEY="your-vapid-private-key"
```

Push notifications need a VAPID key pair. Generate one with `python generate_vapid_keys.py` and paste the two lines it prints into `.env` (and into your Railway variables in production). Push stays off while they're unset.

### 3️⃣ Create Virtual Environment & Install Dependencies
```bash
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
pip install -r requirements.txt
```

### 4️⃣ Set Up database & Seed Categories
```bash
python manage.py migrate
python manage.py seed_categories
```

### 5️⃣ Boot the Local Server
```bash
python manage.py runserver
```
Visit the local dashboard at **`http://127.0.0.1:8000/`**!

---

## 🧪 Running Automated Tests
The application is backed by an automated Django unit-testing suite covering split mathematical edge cases, friendship validations, and authentication routes:
```bash
python manage.py test
```

---

## 🚀 One-Click Railway Production Deployment

This project is fully optimized for containerized cloud deployment on **Railway** via `railway.json` and a production-grade `Procfile`:

1. Sign in to **Railway.app** using your GitHub account.
2. Click **New Project** and provision a cloud **PostgreSQL** database.
3. Add a **GitHub Web Service** and select this repository.
4. Inject the environment variables inside Railway's service panel:
   * `DATABASE_URL` ➡️ `${{Postgres.DATABASE_URL}}`
   * `SECRET_KEY` ➡️ *[Your secure production secret key]*
   * `DEBUG` ➡️ `False`
   * `GOOGLE_CLIENT_ID` ➡️ *[Your Google OAuth ID]*
   * `GOOGLE_CLIENT_SECRET` ➡️ *[Your Google OAuth Secret]*
5. Add your custom domain (e.g. `splitlite.up.railway.app`) to your Google Cloud Console authorized redirect URIs:
   `https://splitlite.up.railway.app/accounts/google/callback/`

---

## 🤝 Contributing
Contributions, feature recommendations, and pull requests are highly welcome! Feel free to open issues or suggest design changes.

## 📄 License
This project is open-source and licensed under the MIT License.

## ✨ Author
**Garv Jindal**  
* GitHub: [@Jindalgarv](https://github.com/Jindalgarv)
