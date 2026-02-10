import os
import time
import json
import shutil
from fastapi import FastAPI, Form, UploadFile, File, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv
from groq import Groq
import google.generativeai as genai

# --- CONFIGURATION ---
load_dotenv()

GROQ_API_KEY = os.getenv("GROQ_API_KEY")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

if not GROQ_API_KEY or not GEMINI_API_KEY:
    print("⚠️ Warning: API Keys missing.")

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

# --- HELPER FUNCTIONS ---

def transcribe_audio(file_path):
    """Transcribes uploaded audio using Groq."""
    try:
        with open(file_path, "rb") as file:
            return groq_client.audio.transcriptions.create(
                file=(file_path, file.read()),
                model="whisper-large-v3",
                response_format="text"
            )
    except Exception as e:
        print(f"Groq Error: {e}")
        return None

def generate_study_notes(text, language="English"):
    """Generates notes using Gemini."""
    model = genai.GenerativeModel('gemini-2.0-flash')
    prompt = f"""
    You are an expert AI tutor. Target Language: {language}.
    Create detailed study notes and a quiz from this transcript:
    
    Format:
    # 📝 Summary
    [Content]
    ## 🔑 Key Concepts
    - [Points]
    
    ```json
    [ {{ "question": "...", "options": ["A", "B"], "answer": 0 }} ]
    ```
    
    Transcript: {text[:50000]}
    """
    try:
        response = model.generate_content(prompt)
        return response.text
    except Exception as e:
        return f"AI Error: {e}"

# --- ENDPOINTS ---

@app.get("/")
async def root():
    return {"status": "Online", "mode": "Client-Side-Handoff"}

@app.post("/process-transcript")
async def process_transcript(transcript: str = Form(...), language: str = Form(...)):
    """
    Method A: Frontend found the transcript (Fastest).
    Directly generates notes.
    """
    if len(transcript) < 50:
        raise HTTPException(status_code=400, detail="Transcript too short.")
    
    notes = generate_study_notes(transcript, language)
    return {"status": "success", "markdown": notes, "transcript": transcript}

@app.post("/process-audio")
async def process_audio(file: UploadFile = File(...), language: str = Form(...)):
    """
    Method B: Frontend downloaded audio and uploaded it here.
    """
    temp_filename = f"temp_{int(time.time())}.mp3"
    
    try:
        # Save uploaded file
        with open(temp_filename, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)
            
        # Transcribe
        transcript = transcribe_audio(temp_filename)
        if not transcript:
            raise HTTPException(status_code=500, detail="Transcription failed")
            
        # Generate Notes
        notes = generate_study_notes(transcript, language)
        
        return {"status": "success", "markdown": notes, "transcript": transcript}
        
    finally:
        # Cleanup
        if os.path.exists(temp_filename):
            os.remove(temp_filename)
