# NeXT Mission

**Navigating eXperience and Transitions**  
An AI-powered platform to support U.S. military veterans as they transition to civilian life.

---

## Overview

**NeXT Mission** is a web-based prototype designed to guide both retired and transitioning veterans through key areas of post-service life. It combines a structured resume builder, real-time chatbot assistant, mentor discovery engine, and a social forum into one unified platform.

Built with a Django + Vue.js architecture, this project leverages **Meta's LLaMA 4 Scout 17B 16E Instruct** model, served through Groq, for all text generation tasks—from civilian resume enrichment to dynamic conversational support.

This project was developed for the **ai+expo hackathon** on **Meta Track**, with an emphasis on showcasing how Meta's models can create impactful, real-world applications.

---

## Key Features

### 🔹 Veteran Professional Summary Generator
- Uses **Meta's LLaMA 4 Scout 17B 16E Instruct** to translate military profiles into civilian resumes.
- Outputs a clean JSON structure for rendering or download.
- PDF generation included using WeasyPrint.

### 🔹 Chatbot (LLaMA-driven)
- Multi-purpose assistant trained on prompt engineering and task-switching.
- Handles:
  - Mental health check-ins
  - Civilian career advice
  - Entrepreneurship and business guidance
  - Resource recommendations

### 🔹 Job and Mentor Discovery
- Integrates with SerpAPI to extract and enrich job and mentor profiles from LinkedIn.
- Matches jobs and mentors based on MOS history, skills, and user keywords.

### 🔹 Events Discovery
- Integrates with SerpAPI to search through internet for veteran related events.
- Shows recent events happening in and around U.S

### 🔹 Community Forum
- Authenticated veterans can post updates, share experiences, and support each other.

---

## Meta + LLaMA Integration

This platform is exclusively powered by **Meta's LLaMA 4 Scout 17B 16E Instruct** model for all language understanding and generation tasks. The model was chosen for:

- Instruction-following accuracy
- Domain adaptability (military to civilian)
- Compatibility with low-latency serving via Groq

Meta’s commitment to open, powerful models made it possible to build a production-quality assistant capable of handling highly contextual veteran-specific prompts.

---

## Tech Stack

| Layer           | Stack                            |
|-----------------|----------------------------------|
| Frontend        | Vue.js                           |
| Backend         | Django + DRF + Uvicorn (ASGI)    |
| AI Model        | Meta LLaMA 4 (via Groq API)      |
| Database        | MongoDB + SQLite3 (Dev)          |
| Resume to PDF   | WeasyPrint                       |
| OCR Support     | Tesseract                        |
| Search Engine   | SerpAPI (LinkedIn scraping)      |

---

## Running the Application

### Prerequisites

- Python 3.9+
- Node.js (for Vue frontend)
- MongoDB (local or Atlas)
- Groq API Key (for LLaMA model)
- SerpAPI Key (for mentor search)

### Backend Setup

```bash
pip install -r requirements.txt
python3 manage.py runserver 0.0.0.0:9005
uvicorn next_mission_backend.asgi:application --host 0.0.0.0 --port 9000
```

### Frontend Repo
Github - https://github.com/ruthvik-vijayakumar/next-mission-ui