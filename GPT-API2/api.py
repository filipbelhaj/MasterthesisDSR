"""
Ontology Triple Extractor – API + UI (multi-file version).

This app serves:
  - GET /               -> index.html UI
  - POST /api/extract   -> JSON API (input_text -> qs_output + explain_output)

Run locally:
  1) Set your OpenAI key (do NOT hardcode it in code):
       export OPENAI_API_KEY="..."
  2) Ensure these files exist in the same folder as this api.py:
       - index.html
       - query.json
  3) Start:
       python api.py
  4) Open:
       http://127.0.0.1:8000
"""
from flask import Flask
from app.config import BASE_DIR, HOST, PORT
from app.routes import bp

app = Flask(__name__, static_folder=str(BASE_DIR), static_url_path="")
app.register_blueprint(bp)

if __name__ == "__main__":
    app.run(host=HOST, port=PORT, debug=False)


