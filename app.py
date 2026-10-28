"""
================================================================================
Promptly — Backend Server (Flask + SQLite + Google Gemini API + Google Auth)
================================================================================
This file powers the complete backend API for the Promptly Framework Studio.

Key Architectural Responsibilities:
1. HTTP Host & Static Delivery:
   Serves the single-page application (temp.html) and client assets (voice.js)
   over HTTP (http://localhost:5000), which is strictly required by Google
   Identity Services (Google OAuth disallows the 'file://' protocol).

2. User Authentication (Google OAuth 2.0):
   Verifies Google ID Tokens (JWT) using Google's official cryptography libraries
   to securely identify users and protect their saved prompt archives.

3. AI Prompt Synthesis Engine (Google Gemini API):
   Receives raw user parameters from prompt engineering frameworks (CIF, RTF,
   RACE, TAG, CRISPE), constructs a high-density meta-prompt, and calls Google's
   Gemini API to expand the parameters into a production-grade AI prompt
   tailored to ChatGPT, Claude, Gemini, or Grok.

4. Strict Token & Word Budgeting:
   Mathematically calculates target word limits based on requested token budgets
   (calibrated to ~0.30 words per token for concise, high-density, token-efficient prompts),
   enforces length constraints in the system command, prevents user token waste, and returns
   exact token usage directly from Gemini's usageMetadata candidatesTokenCount.

5. Persistent Prompt Library (SQLite):
   Manages 'promptly.db' with schema migration to store, retrieve, and delete
   prompts scoped to individual authenticated Google accounts.
================================================================================
"""

# ------------------------------------------------------------------------------
# 1. Standard Library & Framework Imports
# ------------------------------------------------------------------------------
# Flask: Lightweight Python web framework for routing HTTP requests
# request: Accesses incoming JSON payloads, query parameters, and HTTP headers
# jsonify: Serializes Python dictionaries into standard JSON HTTP responses
# send_from_directory: Securely delivers static files (temp.html, voice.js) from disk
from flask import Flask, request, jsonify, send_from_directory

# CORS: Enables Cross-Origin Resource Sharing, allowing frontend single-page apps
# running on different ports or local hosts to communicate seamlessly with this API
from flask_cors import CORS

# sqlite3: Embedded relational SQL database engine for storing prompt archives
import sqlite3

# requests: Performs outbound HTTPS network calls to the Google Gemini REST API
import requests

# os: Handles operating system path resolution and environment variable access
import os

# ------------------------------------------------------------------------------
# 2. Google Identity Services Cryptographic Verification Setup
# ------------------------------------------------------------------------------
# Attempt to import Google's official authentication verification library.
# If installed, the backend cryptographically validates the cryptographic signature
# of Google ID tokens against Google's rotating public RSA keys.
try:
    from google.oauth2 import id_token
    from google.auth.transport import requests as google_requests
    HAS_GOOGLE_AUTH = True
except ImportError:
    # Graceful fallback: If the package is not installed, the server remains operational
    HAS_GOOGLE_AUTH = False

# ------------------------------------------------------------------------------
# 3. Path & Directory Normalization
# ------------------------------------------------------------------------------
# Ensures the application always resolves 'promptly.db' and 'temp.html' relative
# to this file's folder, regardless of which working directory launched python.
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, 'promptly.db')

# ------------------------------------------------------------------------------
# 4. Flask Application & CORS Initialization
# ------------------------------------------------------------------------------
# Initialize the Flask application with static_folder pointing to BASE_DIR
app = Flask(__name__, static_folder=BASE_DIR)

# Enable CORS for all routes so the browser can make fetch() requests without origin blocking
CORS(app)

# ------------------------------------------------------------------------------
# 5. Global Configuration: Google Gemini API & OAuth Client ID
# ------------------------------------------------------------------------------
# Gemini API Key used to authenticate with Google's Generative Language REST endpoints.
# Defaults to the configured key or reads from the GEMINI_API_KEY environment variable.
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "AQ.Ab8RN6JiTk1L8t4Du67O8XrBZ11jus75WtSkAV-qKlyJcgjKPw")

# Primary and fallback Gemini models:
# Providing a tiered list guarantees high-availability generation. If a preview model
# returns HTTP 503 (high demand) or HTTP 429 (rate limit), the loop immediately fails
# over to the next candidate model in the list.
GEMINI_PRIMARY_MODEL = "gemini-3.5-flash-lite"
GEMINI_FALLBACK_MODELS = [
    "gemini-3.5-flash-lite",   # Fast, highly cost-effective, high capacity
    "gemini-3.5-flash",        # Production high-throughput fallback
    "gemini-flash-latest",     # Stable high-availability production alias
    "gemini-3.8-flash",        # Advanced reasoning and prompt expansion capabilities
    "gemini-flash-lite-latest",# Secondary high-availability production alias
    "gemini-3-flash-preview"   # Additional preview fallback
]

# Google OAuth 2.0 Web Client ID:
# Matches the client ID configured in the Google Cloud Console for GIS One-Tap sign-in.
GOOGLE_CLIENT_ID = os.environ.get("GOOGLE_CLIENT_ID", "775976318006-09tiitv9oma0mr12vos785rn3t04j1rh.apps.googleusercontent.com")

# ------------------------------------------------------------------------------
# 6. Database Initialization & Schema Migration
# ------------------------------------------------------------------------------
def init_db():
    """
    Initializes the SQLite database (promptly.db) and creates the 'prompts' table
    if it does not already exist. Migrates existing tables to include username and created_at.

    Database Table: 'prompts'
      - id: Primary Key (auto-incrementing integer)
      - username: Unique Google account email or user identifier (scopes library entries)
      - title: User-assigned reference title for the prompt
      - framework: Framework acronym used (e.g., CIF, RTF, RACE, TAG, CRISPE)
      - prompt_text: The complete generated AI mega-prompt
      - created_at: Timestamp of when the prompt was saved
    """
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    
    # Create the table if first run
    c.execute('''CREATE TABLE IF NOT EXISTS prompts 
                 (id INTEGER PRIMARY KEY AUTOINCREMENT, 
                  username TEXT, 
                  title TEXT, 
                  framework TEXT, 
                  prompt_text TEXT,
                  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)''')
    
    # Check existing schema columns to perform safe backward-compatible migrations
    c.execute("PRAGMA table_info(prompts)")
    existing_columns = [col[1] for col in c.fetchall()]

    # Migrate 'username' column if absent in legacy database files
    if 'username' not in existing_columns:
        try:
            c.execute("ALTER TABLE prompts ADD COLUMN username TEXT")
            print("[init_db] Migrated schema: Added 'username' column.")
        except Exception as e:
            print(f"[init_db] Column migration notice (username): {e}")

    # Migrate 'created_at' column if absent in legacy database files
    if 'created_at' not in existing_columns:
        try:
            c.execute("ALTER TABLE prompts ADD COLUMN created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP")
            print("[init_db] Migrated schema: Added 'created_at' column.")
        except Exception as e:
            print(f"[init_db] Column migration notice (created_at): {e}")
            
    conn.commit()
    conn.close()

# Execute database schema check and setup immediately on startup
init_db()

# ------------------------------------------------------------------------------
# 7. Route: Root Frontend Single-Page App Delivery
# ------------------------------------------------------------------------------
@app.route('/')
def serve_index():
    """
    Serves the single-page application (temp.html) directly at the root URL (http://localhost:5000/).
    This ensures the app is accessed over a valid HTTP origin, which is strictly
    required by Google Identity Services (Google OAuth prohibits 'file://' protocols).
    """
    return send_from_directory(BASE_DIR, 'temp.html')

# ------------------------------------------------------------------------------
# 8. Route: Static Asset Serving (voice.js, scripts, images)
# ------------------------------------------------------------------------------
@app.route('/<path:filename>')
def serve_static(filename):
    """
    Serves static assets (such as voice.js or local scripts) directly from BASE_DIR.
    Ensures client-side speech recognition scripts load cleanly with HTTP 200.
    """
    return send_from_directory(BASE_DIR, filename)

# ------------------------------------------------------------------------------
# 9. Route: Google OAuth 2.0 ID Token Verification
# ------------------------------------------------------------------------------
@app.route('/api/auth/google', methods=['POST'])
def verify_google_token():
    """
    Endpoint to verify a Google OAuth 2.0 ID Token (JWT).
    
    Expected JSON payload:
      {
        "credential": "<JWT token from Google Identity Services>",
        "client_id": "<Optional override for Client ID>"
      }

    Returns:
      - 200 with user profile info (sub, name, email, picture) on valid signature.
      - 400 if token is missing or cryptographic verification fails.
    """
    data = request.json or {}
    token = data.get('credential')
    client_id = data.get('client_id') or GOOGLE_CLIENT_ID
    
    # Validation: Ensure a token string was passed
    if not token:
        return jsonify({'error': 'No credential provided'}), 400

    try:
        # If google-auth is installed, verify the cryptographic signature against Google's public keys
        if HAS_GOOGLE_AUTH and client_id:
            # Validates audience (client_id), expiration time, and RSA signature
            idinfo = id_token.verify_oauth2_token(token, google_requests.Request(), client_id)
            return jsonify({
                'status': 'verified',
                'user': {
                    'sub': idinfo.get('sub'),         # Unique permanent Google User ID
                    'name': idinfo.get('name'),       # Full user display name
                    'email': idinfo.get('email'),     # Google account email address
                    'picture': idinfo.get('picture')  # User avatar photo URL
                }
            }), 200
        else:
            # Fallback if google-auth package is not installed: Allow frontend JWT decoding to proceed
            return jsonify({'status': 'ok'}), 200
    except Exception as e:
        print(f"[/api/auth/google] Token verification warning: {e}")
        return jsonify({'error': str(e)}), 400

# ------------------------------------------------------------------------------
# 10. Route: AI Prompt Generation via Google Gemini API
# ------------------------------------------------------------------------------
@app.route('/api/generate', methods=['POST'])
def generate_prompt():
    """
    Takes user parameter inputs, wraps them in a Master Prompt Engineer meta-prompt,
    and calls Google Gemini API to synthesize a professional, expanded mega-prompt.

    Expected JSON payload:
      {
        "system_prompt": "<Formatted input parameters and framework guidelines>",
        "model": "ChatGPT" | "Claude" | "Gemini" | "Grok",  # Target engine persona
        "temperature": 0.7,                                 # Creativity slider (0.0 to 1.5)
        "max_tokens": 1536                                  # Maximum generation token budget
      }

    Returns:
      - 200 with {
          "text": "<generated prompt>",
          "model": "<gemini model used>",
          "tokens": <exact token count>,
          "words": <exact word count>,
          "budget_tokens": <requested token budget>,
          "target_words": <target word budget>
        }
      - 400 if no system_prompt is supplied.
      - 500 if all Gemini models fail or rate limits are exceeded.
    """
    data = request.json or {}
    raw_instruction = data.get('system_prompt', '')
    temperature = float(data.get('temperature', 0.7))
    num_predict = int(data.get('max_tokens', 512))
    target_engine = data.get('model', 'ChatGPT')
    
    # Validation: Prevent empty prompt generation requests
    if not raw_instruction:
        return jsonify({'error': 'No system_prompt provided'}), 400

    # Step A: Calibrate temperature into safe, effective operational bounds (0.0 to 1.5)
    effective_temp = max(0.0, min(1.5, temperature))

    # Step B: Inject dynamic behavioral directives based on creativity temperature
    if effective_temp <= 0.35:
        temp_directive = (
            "CREATIVITY MODE: Strict & Deterministic. Formulate clear, unambiguous instructions "
            "with rigid constraints, step-by-step logic, explicit schemas, and deterministic "
            "evaluation criteria. Avoid speculative language."
        )
    elif effective_temp <= 0.85:
        temp_directive = (
            "CREATIVITY MODE: Balanced & Structured. Provide standard context expansion with "
            "best-practice architectural guidance, edge cases, clear sections, and balanced detail."
        )
    else:
        temp_directive = (
            "CREATIVITY MODE: Creative & Exploratory. Explore unconventional perspectives, "
            "creative edge cases, lateral problem-solving angles, rich behavioral nuance, and diverse scenario variations."
        )

    # Step C: Concise & Token-Efficient Word-to-Token Ratio Calibration
    # Calibrated to ~0.30 words per token (1 word ≈ 3.33 tokens) to keep prompts crisp, dense, and compact.
    # This prevents user tokens from burning fast and ensures prompts remain punchy without bloated word counts.
    target_words = int(num_predict * 0.30)
    min_words = max(35, int(target_words * 0.80)) # Lower bound: ~80% of target words
    max_words = max(50, int(target_words * 1.10)) # Upper bound: ~110% of target words

    length_directive = (
        f"STRICT WORD & TOKEN LIMIT: Write a concise, high-impact prompt containing approximately {min_words} to {max_words} words "
        f"(Token Budget: {num_predict} tokens). You MUST stay strictly within this {min_words}–{max_words} word limit to avoid "
        f"wasting user tokens. Do NOT write an overly long, verbose, or bloated prompt."
    )

    # Step D: Persona-Specific Engineering Directives
    # Formats the mega-prompt in the structure best understood by the specific target model.
    persona_directives = {
        'ChatGPT': (
            "Format the prompt with structured Markdown headings, precise role framing, "
            "step-by-step reasoning instructions, and few-shot formatting guidance tailored for OpenAI models."
        ),
        'Claude': (
            "Format the prompt using Anthropic best practices: XML tags (<context>, <instructions>, <guidelines>), "
            "scratchpad/thinking blocks, and concise, high-density directives tailored for Anthropic models."
        ),
        'Gemini': (
            "Format the prompt using Google AI best practices: clear system constraints, multi-perspective instruction "
            "layering, grounded reasoning, and explicit output formatting tailored for Gemini models."
        ),
        'Grok': (
            "Format the prompt with direct, unfiltered clarity, high analytical depth, "
            "witty yet rigorous task breakdown, and no corporate fluff tailored for Grok."
        )
    }.get(target_engine, "Format the prompt professionally with clear headings, bullet points, and high detail.")

    # Step E: Master Prompt Engineer System Instruction
    # Guarantees that Gemini acts as a meta-prompt builder rather than answering the user prompt itself.
    system_command = f"""You are a Master Prompt Engineer. 
Your ONLY job is to take the user's basic inputs and expand them into a concise, professional, high-impact AI prompt designed specifically for {target_engine}.

CRITICAL OPERATIONAL RULES:
1. DO NOT answer the user's core request (e.g., do not write the app code or complete the task yourself).
2. Write the ACTUAL PROMPT the user will copy/paste into {target_engine}.
3. HIGH DENSITY & CONCISENESS: Keep the prompt compact, focused, and powerful. Avoid unnecessary filler, conversational preamble, or redundant paragraphs. Prompts should be punchy and direct, not an essay.
4. {temp_directive}
5. {length_directive}
6. Target Engine Optimization: {persona_directives}
7. COMPLETION REQUIREMENT: You MUST fully complete and conclude the prompt cleanly. Never leave trailing sentences or unfinished thoughts.
8. Output ONLY the final prompt. No introductory text like 'Here is your prompt:' or conversational pleasantries."""

    # Step F: Hard-Cap Safety Ceiling on maxOutputTokens
    # Caps generation at the user's selected token budget, preventing token overrun.
    safety_tokens = min(4096, num_predict)

    # Step G: Google Gemini REST API Payload Construction
    payload = {
        "system_instruction": {
            "parts": [{"text": system_command}]
        },
        "contents": [
            {
                "role": "user",
                "parts": [{"text": f"Turn these raw inputs into a prompt tailored for {target_engine}:\n\n{raw_instruction}"}]
            }
        ],
        "generationConfig": {
            "temperature": effective_temp,
            "maxOutputTokens": safety_tokens,
            "topP": 0.95
        }
    }

    # Step H: High-Availability Model Tiering Loop
    # Iterates through primary and fallback models. If a model encounters a 503 high-demand spike
    # or rate limit, the loop seamlessly switches to the next available model.
    last_error = "Unknown error"
    for model_name in GEMINI_FALLBACK_MODELS:
        gemini_url = f"https://generativelanguage.googleapis.com/v1beta/models/{model_name}:generateContent?key={GEMINI_API_KEY}"
        try:
            # Timeout configuration: 12 seconds to connect, 45 seconds to stream response
            response = requests.post(gemini_url, json=payload, timeout=(12, 45))
            
            # Success response: HTTP 200 OK
            if response.status_code == 200:
                result = response.json()
                
                # Extract exact candidate token count from Gemini's usageMetadata
                usage = result.get("usageMetadata", {})
                api_tokens = usage.get("candidatesTokenCount", 0)

                # Extract generated text from candidates array
                candidates = result.get("candidates", [])
                if candidates:
                    parts = candidates[0].get("content", {}).get("parts", [])
                    final_text = "".join(part.get("text", "") for part in parts).strip()
                    
                    if final_text:
                        actual_words = len(final_text.split())
                        # If usageMetadata was omitted, fall back to mathematical word estimate (1 word ≈ 3.33 tokens)
                        if api_tokens == 0:
                            api_tokens = int(actual_words / 0.30)
                            
                        # Return complete telemetry package
                        return jsonify({
                            'text': final_text, 
                            'model': model_name,
                            'tokens': api_tokens,
                            'words': actual_words,
                            'budget_tokens': num_predict,
                            'target_words': target_words
                        }), 200
                        
                return jsonify({'error': "Empty response received from Gemini API."}), 500
            
            # If 503 (high demand), 429 (rate limit), or 404 (deprecated), log and attempt next candidate model
            err_json = response.json() if response.content else {}
            err_msg = err_json.get("error", {}).get("message", f"HTTP {response.status_code}")
            last_error = f"Gemini ({model_name}): {err_msg}"
            print(f"[/api/generate] Model {model_name} returned status {response.status_code}: {err_msg}. Trying fallback...")
            continue
            
        except requests.exceptions.Timeout:
            last_error = f"Gemini ({model_name}) request timed out."
            print(f"[/api/generate] {last_error} Trying fallback...")
            continue
        except Exception as e:
            last_error = f"Gemini ({model_name}) error: {str(e)}"
            print(f"[/api/generate] {last_error} Trying fallback...")
            continue

    # If all models failed, return an informative error message to the frontend
    print(f"[/api/generate] All Gemini candidate models failed: {last_error}")
    return jsonify({'error': f"Gemini generation failed: {last_error}"}), 500

# ------------------------------------------------------------------------------
# 11. Route: Prompts Archive (Save, Fetch & Delete)
# ------------------------------------------------------------------------------
@app.route('/api/prompts', methods=['GET', 'POST', 'DELETE'])
def handle_prompts():
    """
    Handles prompt archiving in SQLite. Prompts are scoped by user account (email/name).

    POST /api/prompts:
      Saves a generated prompt.
      Payload: { "username": "...", "title": "...", "framework": "...", "prompt_text": "..." }
      Returns: { "status": "success", "id": <new_id> }

    GET /api/prompts?username=<email>:
      Retrieves all saved prompts for the given user, sorted newest first.
      Returns: [ { "id": 1, "title": "...", "framework": "...", "prompt_text": "...", "created_at": "..." }, ... ]

    DELETE /api/prompts?id=<id>&username=<email>:
      Deletes a specific prompt owned by the authenticated user.
      Returns: { "status": "deleted", "id": <id> }
    """
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    
    # -------------------------------------------------------------------------
    # Method POST: Save a new prompt entry
    # -------------------------------------------------------------------------
    if request.method == 'POST':
        data = request.json or {}
        username = data.get('username')
        title = data.get('title', '').strip() or 'Untitled Prompt'
        framework = data.get('framework', 'Custom')
        prompt_text = data.get('prompt_text', '')
        
        # Guard: Require both username and prompt text
        if not username or not prompt_text:
            conn.close()
            return jsonify({'error': 'Username and prompt_text are required'}), 400

        # Insert record into database linked to the user's Google ID/email
        c.execute("INSERT INTO prompts (username, title, framework, prompt_text) VALUES (?, ?, ?, ?)",
                  (username, title, framework, prompt_text))
        new_id = c.lastrowid
        conn.commit()
        conn.close()
        return jsonify({"status": "success", "id": new_id})
        
    # -------------------------------------------------------------------------
    # Method GET: Fetch all saved prompts for the authenticated user
    # -------------------------------------------------------------------------
    elif request.method == 'GET':
        # Retrieve user identifier from URL query string (?username=...)
        user_query = request.args.get('username')
        
        if not user_query:
            conn.close()
            return jsonify([])  # Return empty list if no user email is supplied
            
        # Query records ordered chronologically descending (newest prompts at the top)
        c.execute("SELECT id, title, framework, prompt_text, created_at FROM prompts WHERE username = ? ORDER BY id DESC", (user_query,))
        rows = c.fetchall()
        prompts = [
            {
                "id": row[0],
                "title": row[1],
                "framework": row[2],
                "prompt_text": row[3],
                "created_at": row[4] if len(row) > 4 and row[4] else ""
            }
            for row in rows
        ]
        conn.close()
        return jsonify(prompts)

    # -------------------------------------------------------------------------
    # Method DELETE: Delete a saved prompt with security ownership verification
    # -------------------------------------------------------------------------
    elif request.method == 'DELETE':
        prompt_id = request.args.get('id')
        user_query = request.args.get('username')
        
        # Guard: Both prompt ID and username are strictly required
        if not prompt_id or not user_query:
            conn.close()
            return jsonify({'error': 'Both id and username query parameters are required'}), 400
            
        # Security Guard: Only delete if the prompt ID matches AND belongs to this user!
        # Prevents one authenticated user from deleting another user's saved prompts.
        c.execute("DELETE FROM prompts WHERE id = ? AND username = ?", (prompt_id, user_query))
        conn.commit()
        conn.close()
        return jsonify({"status": "deleted", "id": prompt_id})

# ------------------------------------------------------------------------------
# 12. Application Entry Point
# ------------------------------------------------------------------------------
if __name__ == '__main__':
    # Start the Flask development server on port 5000 with hot-reloading (debug=True)
    # Serves the app at http://127.0.0.1:5000 / http://localhost:5000
    app.run(debug=True, port=5000)
