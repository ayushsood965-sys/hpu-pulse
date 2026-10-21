# 🏛 HPU Pulse — 24/7 Autonomous Instagram News & Student Updates Agent

An autonomous, production-grade Instagram news agent for **Himachal Pradesh University (HPU Shimla)** operating under `@hpu.pulse`.

---

## ⚡ Core Architecture & Features

- **Multi-Source Scraping Engine:**
  - `nexams.hpushimla.in` (Results, Date Sheets, Time Tables)
  - `nadmissions.hpushimla.in` (Merit Lists, Seat Vacancy Reports, Counselling)
  - `hpuniv.ac.in` (VC Orders, Official Circulars, Holiday Notices)
  - Google News RSS (Amar Ujala, Divya Himachal, The Tribune)
- **Scanned PDF & Image OCR:**
  - Fallback engine using `pypdf`, `tesseract-ocr`, and Gemini Vision for scanned circulars.
- **AI Triage & Synthesis:**
  - Dual AI pipeline: Primary Google Gemini (`gemini-3.6-flash`) with automatic high-speed fallback to OpenRouter free models (`minimax/minimax-m3.1-flash:free`, `nvidia/nemotron-3.5-lightning:free`).
  - Summarizes bureaucratic circulars into concise, authentic, human student language inspired by `@hpuupdates`.
  - Zero URL policy: Automatically strips web domains and citations.
- **Media Generation:**
  - **Carousels (1080x1350):** Mint green student aesthetic with solid black typography.
  - **Reels (1080x1920 9:16):** Looping vertical videos with breathing zoom and trending ambient/cinematic audio library.
- **Publishing & Engagement:**
  - Meta Graph API direct integration with token-bucket rate limiting.
  - Autonomous comment auto-responder.
- **Web Control Center:**
  - Live dashboard with real-time log streaming, system uptime, and manual workflow triggers.
  - Protected by password authentication.

---

## 🚀 Quick Start

### 1. Install Dependencies

```bash
# Python dependencies
pip install -r requirements.txt

# Node.js dependencies
npm install
```

### 2. Configure Environment

Copy `.env.example` to `.env` and fill in your API credentials:

```bash
cp .env.example .env
```

### 3. Run the Agent

```bash
# Start 24/7 autonomous growth scheduler
python main.py --schedule

# Or start the Web Dashboard Control Center
python server.py
```

---

## 🐳 Docker Deployment

```bash
docker build -t hpu-pulse .
docker run -d -p 8000:8000 --env-file .env hpu-pulse
```
