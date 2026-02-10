import os
import requests
import time
import shutil
import google.generativeai as genai
from fastapi import FastAPI, Form, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv
from groq import Groq

# --- CONFIGURATION ---
load_dotenv()

GROQ_API_KEY = os.getenv("GROQ_API_KEY")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

if not GROQ_API_KEY or not GEMINI_API_KEY:
    print("⚠️ CRITICAL: API Keys missing.")

# Initialize Clients
groq_client = Groq(api_key=GROQ_API_KEY)
genai.configure(api_key=GEMINI_API_KEY)

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

os.makedirs("temp", exist_ok=True)

# --- CORE FUNCTIONS ---

def download_file_from_url(url, filename):
    """
    Downloads a file from a direct URL (provided by Piped/Cobalt).
    This bypasses yt-dlp on the server.
    """
    print(f"⬇️ Downloading audio from relay: {url[:50]}...")
    try:
        # We use a stream to handle large files without memory issues
        with requests.get(url, stream=True, timeout=60) as r:
            r.raise_for_status()
            with open(filename, 'wb') as f:
                for chunk in r.iter_content(chunk_size=8192):
                    f.write(chunk)
        return True
    except Exception as e:
        print(f"❌ Download Error: {e}")
        return False

def transcribe_with_groq(file_path):
    """Transcribes audio using Groq (Whisper Large)."""
    print("🎙️ Transcribing with Groq...")
    try:
        with open(file_path, "rb") as file:
            return groq_client.audio.transcriptions.create(
                file=(file_path, file.read()),
                model="whisper-large-v3",
                response_format="text"
            )
    except Exception as e:
        print(f"❌ Groq Error: {e}")
        return None

def generate_notes(text, language):
    """Summarizes text using Gemini."""
    if not text: return None
    print("🧠 Generating Notes with Gemini...")
    
    model = genai.GenerativeModel('gemini-2.0-flash')
    prompt = f"""
    You are an expert AI tutor. Target Language: {language}.
    
    Create a study guide from this transcript:
    1. Summary (Markdown).
    2. Key Concepts (Bullet points).
    3. Quiz (JSON).

    Format:
    # 📝 Summary
    ...
    ## 🔑 Key Concepts
    ...
    ## 🧠 Quiz
    ```json
    [ {{ "question": "...", "options": ["A","B"], "answer": 0 }} ]
    ```

    Transcript:
    {text[:100000]}
    """
    try:
        response = model.generate_content(prompt)
        return response.text
    except Exception as e:
        return f"Gemini Error: {e}"

# --- ENDPOINTS ---

@app.post("/process-audio-url")
async def process_audio_url(audio_url: str = Form(...), language: str = Form(...)):
    """
    Receives a direct Audio Link (from Piped), downloads, transcribes, and summarizes.
    """
    temp_filename = f"temp/{int(time.time())}.mp3"
    
    try:
        # 1. Download the Audio (Server-side, but from a Relay URL)
        success = download_file_from_url(audio_url, temp_filename)
        if not success:
            raise HTTPException(status_code=400, detail="Failed to download audio from relay link.")

        # 2. Transcribe
        transcript = transcribe_with_groq(temp_filename)
        if not transcript:
            raise HTTPException(status_code=500, detail="Transcription failed.")

        # 3. Summarize
        notes = generate_notes(transcript, language)
        
        return {"status": "success", "markdown": notes, "transcript": transcript}

    finally:
        if os.path.exists(temp_filename):
            os.remove(temp_filename)

@app.post("/process-transcript")
async def process_transcript(transcript: str = Form(...), language: str = Form(...)):
    """Backup: If frontend already found text, just summarize it."""
    notes = generate_notes(transcript, language)
    return {"status": "success", "markdown": notes}

@app.post("/chat")
async def chat_endpoint(question: str = Form(...), transcript: str = Form(...)):
    model = genai.GenerativeModel('gemini-2.0-flash')
    prompt = f"Context: {transcript[:20000]}\n\nUser: {question}\nAnswer:"
    try:
        response = model.generate_content(prompt)
        return {"answer": response.text}
    except:
        return {"answer": "I am having trouble thinking right now."}
