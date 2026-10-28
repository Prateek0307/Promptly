# Promptly — Technical Architecture & Project Guide

> **Promptly — By Design (Prompt Engineering Framework Studio)**
> An AI-assisted Prompt Engineering Studio powered by **Google Gemini API**, **Flask**, **SQLite**, and **Google OAuth 2.0 (GIS)**.

---

## 1. What Is Promptly?
Instead of forcing users to manually construct large, complex prompts from scratch, **Promptly** structures user requirements across 5 established prompt engineering frameworks (**CIF**, **RTF**, **RACE**, **TAG**, **CRISPE**) and uses **Google Gemini AI** to synthesize production-grade mega-prompts tailored to specific target foundation models (**ChatGPT**, **Claude**, **Gemini**, and **Grok**).

---

## 2. Tech Stack Summary

| Component | Technology | Description |
| :--- | :--- | :--- |
| **Frontend UI** | HTML5 + Tailwind CSS | Single-Page Application (SPA) with glassmorphism and dark/light mode. |
| **Client Scripting** | Vanilla JavaScript (ES6+) | Form generation, typewriter streaming, telemetry calculation, parallel API orchestration. |
| **Authentication** | Google Identity Services (GIS) | Official Google OAuth 2.0 Sign-In and cryptographic JWT session hydration. |
| **Backend Server** | Python 3 + Flask + Flask-CORS | REST API handling token verification, prompt synthesis, and CRUD database queries. |
| **Cloud AI** | Google Gemini API (`v1beta`) | Model: `gemini-3.5-flash-lite` (with automatic fallback to `gemini-3.8-flash` & `gemini-3.5-flash`). |
| **Database** | SQLite 3 (`promptly.db`) | Local database storing saved prompts scoped to individual Google emails. |

---

## 3. End-to-End Workflow

```
[ User Input (Role, Task, Scope) ]
                 │
                 ▼
[ Choose Framework & Model (e.g., RTF + Claude) ]
                 │
                 ▼
[ Flask API (/api/generate) ]
  ├── Injects Master Prompt Engineer meta-prompt
  └── Attaches Engine Persona Rules (e.g. Anthropic XML tags)
                 │
                 ▼
[ Google Gemini Cloud API (gemini-3.5-flash-lite) ]
                 │
                 ▼
[ Dual Canvas Stream & Live Token Telemetry ]
                 │
                 ▼
[ One-Click Save to SQLite (promptly.db) ]
```

---

## 4. How Target Engines Differ

When Promptly crafts a prompt, it instructs Gemini to tailor the prompt for the target engine:
1. **ChatGPT**: Structured Markdown headers (`### Role`, `### Objectives`), step-by-step reasoning steps, and few-shot formatting patterns.
2. **Claude**: Official Anthropic XML tags (`<context>`, `<instructions>`, `<guidelines>`) and scratchpad/thinking blocks.
3. **Gemini**: Layered multi-perspective constraints, grounded reasoning, and explicit output formatting.
4. **Grok**: High analytical depth, direct unfiltered task breakdown, and no corporate filler.

---

## 5. How To Run The Project

### Step 1: Install Python dependencies
```bash
pip install flask flask-cors requests
```

### Step 2: Start the server
```bash
python app.py
```

### Step 3: Open in browser
Navigate to:
```
http://localhost:5000
```

---

## 6. How To Share This Guide
- **Interactive Presentation**: Double-click [`PROMPTLY_EXPLAINED.html`](PROMPTLY_EXPLAINED.html) to open in any web browser, or send that file over WhatsApp / Email / Drive.
- **Save as PDF**: Open [`PROMPTLY_EXPLAINED.html`](PROMPTLY_EXPLAINED.html) in your browser and click the **Save as PDF** button at the top right.
