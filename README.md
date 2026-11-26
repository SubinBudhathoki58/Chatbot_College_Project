# Taste of Himalaya — NLP Food Delivery Chatbot

An NLP-based Nepali food ordering and tracking chatbot built as a CSIT final-year project, redesigned to run **100% free (no credit card)** on **Vercel + Neon PostgreSQL** with a **self-hosted Python NLP engine** (zero Google Cloud / Dialogflow dependency).

## Architecture

- **Frontend (`public/`)**: Static HTML/CSS/JS restaurant website with an integrated floating chat widget (served via Vercel's CDN).
- **Backend (`api/index.py`)**: FastAPI serverless API (`/api/chat`, `/api/menu`, `/api/health`, `/api/reset`) running natively on Vercel.
- **NLP Engine (`api/_lib/nlp_engine.py`)**: Self-hosted Python NLP pipeline trained on the project's exported intents (`api/_lib/intents_data.json`):
  - Text normalization & contraction expansion
  - Word unigram/bigram + character n-gram **TF-IDF & Cosine Similarity** intent classifier
  - Context-aware dialogue management (`ongoing-order`, `ongoing-tracking`)
  - Synonym + fuzzy-match Named Entity Recognition (NER) for Nepali menu items, quantities (digits & English words), and order IDs
- **Database (`database/schema_postgres.sql`, `api/_lib/db_helper.py`)**: **Neon** Serverless PostgreSQL storing `food_items`, `orders`, `order_tracking`, and `chat_sessions` (for stateless serverless cart persistence).

## Project Structure

```text
├── api/
│   ├── index.py                # FastAPI Vercel entrypoint
│   └── _lib/
│       ├── db_helper.py        # Neon PostgreSQL queries + auto-schema setup
│       ├── intents_data.json   # Intent training phrases & Nepali food entities
│       └── nlp_engine.py       # TF-IDF intent classifier + NER + dialogue manager
├── public/                     # Static frontend served by Vercel CDN
│   ├── index.html
│   ├── css/style.css
│   └── img/
├── database/
│   └── schema_postgres.sql     # PostgreSQL schema & seed data
├── scripts/
│   └── init_db.py              # Optional manual DB initialization script
├── DialogFLow intents/         # Original exported Dialogflow ES archive
├── requirements.txt
├── vercel.json
└── .env.example
```

## Deploy for Free on Neon + Vercel (No Credit Card)

### 1. Create a Free Neon Database
1. Sign up at [neon.tech](https://neon.tech) (with GitHub — no credit card required).
2. Click **New Project** (e.g., `himalaya-chatbot`) and choose a region close to your users.
3. Copy the **Connection String** (PostgreSQL URI starting with `postgresql://...`).
   - *(Optional)* You can run `database/schema_postgres.sql` inside Neon's **SQL Editor**, or skip it — the backend automatically creates and seeds the tables on the first API request!

### 2. Deploy on Vercel
1. Push this repository to GitHub.
2. Sign up / log in at [vercel.com](https://vercel.com) (Hobby plan — free, no credit card required).
3. Click **Add New → Project** and import your GitHub repo.
4. Under **Environment Variables**, add:
   - **Key:** `DATABASE_URL`
   - **Value:** *(paste your Neon connection string)*
5. Click **Deploy**.
6. Once live, visit `https://<your-app>.vercel.app/api/health` to confirm `"database": "neon-postgres"` and `"connected": true`, then open `https://<your-app>.vercel.app` and test the chatbot!

## Local Development

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# Optional: copy .env.example to .env and add your Neon DATABASE_URL
# (If DATABASE_URL is omitted, the app runs with an in-memory demo fallback.)
uvicorn api.index:app --reload --port 8000
```

Then open [http://localhost:8000](http://localhost:8000).

## Credits

Original CSIT final-year project by **Subin Budhathoki** ([SubinBudhathoki58/Chatbot_College_Project](https://github.com/SubinBudhathoki58/Chatbot_College_Project)).

