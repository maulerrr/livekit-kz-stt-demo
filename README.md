# LiveKit - Kazakh Real-Time STT Demo

Minimal two-process proof-of-concept:

1. **agent/transcriber.py**  
   • Joins a LiveKit room as a bot  
   • Subscribes to every remote audio track  
   • Sends frames through Whisper (via OpenAI) with `language="kk"`  
   • Publishes interim/final transcripts on a data track

2. **web/app.py** (Streamlit)  
   • Captures your microphone in the browser via the LiveKit JS SDK  
   • Displays transcripts pushed by the agent

---

## Quick start

```bash
# clone / copy files
cd livekit-kz-stt-demo

# install deps
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

# spin up LiveKit server (dev mode, Docker required)
docker run --rm -p 7880:7880 -p 7881:7881 livekit/livekit-server --dev

```

1. Copy .env.example → .env and fill in keys (or leave defaults for local dev).

2. Terminal 1 → python agent/transcriber.py

3. Terminal 2 → uvicorn web.token_server:app --port 8000 --reload

4. Terminal 3 → streamlit run web/app.py → open http://localhost:8501

Open a second browser tab and speak: transcripts appear in real time.

## Requirements
* Python ≥ 3.11

* Docker (for local LiveKit server)

* An OpenAI API key with Whisper/GPT-4o-transcribe access