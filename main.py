import os
import shutil
import time
import json
from fastapi import FastAPI, Form, File, UploadFile, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv
from groq import Groq
import google.generativeai as genai

# --- 1. CONFIGURATION ---
load_dotenv()

GROQ_API_KEY = os.getenv("GROQ_API_KEY")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

# Safety Check
if not GROQ_API_KEY or not GEMINI_API_KEY:
    print("⚠️  CRITICAL: API Keys missing in .env or Render Environment Variables.")

# Initialize Clients
try:
    groq_client = Groq(api_key=GROQ_API_KEY)
    genai.configure(api_key=GEMINI_API_KEY)
except Exception as e:
    print(f"❌ Client Init Error: {e}")

app = FastAPI()

# --- 2. SECURITY (CORS) ---
# This allows your Cloudflare frontend to talk to this Render backend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # In production, change this to your Cloudflare URL
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

os.makedirs("temp", exist_ok=True)

# --- 3. HELPER FUNCTIONS ---

def transcribe_audio_groq(file_path):
    """
    Uses Groq (Whisper-Large-V3) to transcribe uploaded audio files.
    """
    print(f"🎙️ Transcribing file: {file_path}")
    try:
        with open(file_path, "rb") as file:
            transcription = groq_client.audio.transcriptions.create(
                file=(file_path, file.read()),
                model="whisper-large-v3",
                response_format="text",
                language="en" # Detects automatically if omitted, but 'en' is faster
            )
        return transcription
    except Exception as e:
        print(f"❌ Groq Transcription Failed: {e}")
        return None

def generate_study_material(text, target_language="English"):
    """
    Uses Gemini 2.0 Flash to generate Notes + Quiz.
    """
    if not text:
        return None

    print(f"🧠 Generating Notes via Gemini (Length: {len(text)} chars)...")
    
    model = genai.GenerativeModel('gemini-2.0-flash')
    
    prompt = f"""
    You are an expert AI tutor. 
    TARGET LANGUAGE: {target_language}
    
    Task:
    1. Summarize the video content in standard Markdown.
    2. Extract key bullet points.
    3. Create a short quiz in JSON format at the end.

    STRICT OUTPUT FORMAT:
    
    # 📝 Summary
    [Your summary here...]

    ## 🔑 Key Concepts
    - [Point 1]
    - [Point 2]
    - [Point 3]

    ## 🧠 Quiz
    ```json
    [
        {{ "question": "Question text?", "options": ["A", "B", "C", "D"], "answer": 0 }},
        {{ "question": "Question text?", "options": ["A", "B", "C", "D"], "answer": 1 }}
    ]
    ```

    TRANSCRIPT DATA:
    {text[:100000]} 
    """

    try:
        response = model.generate_content(prompt)
        return response.text
    except Exception as e:
        return f"Gemini Error: {str(e)}"

# --- 4. API ENDPOINTS ---

@app.get("/")
async def health_check():
    return {"status": "active", "mode": "Client-Handoff", "version": "2.0"}

@app.post("/process-transcript")
async def process_transcript(transcript: str = Form(...), language: str = Form(...)):
    """
    METHOD A (Primary): Frontend sends the text directly.
    Fastest method. No downloading required.
    """
    if not transcript or len(transcript) < 10:
        raise HTTPException(status_code=400, detail="Transcript is empty or too short.")

    notes = generate_study_material(transcript, language)
    return {"status": "success", "markdown": notes, "source": "text-handoff"}

@app.post("/process-audio")
async def process_audio(file: UploadFile = File(...), language: str = Form(...)):
    """
    METHOD B (Backup): Frontend uploads an MP3 file.
    Used when the browser cannot find captions and the user uploads a file manually.
    """
    temp_filename = f"temp/{int(time.time())}_{file.filename}"
    
    try:
        # 1. Save File
        with open(temp_filename, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)
            
        # 2. Transcribe
        transcript = transcribe_audio_groq(temp_filename)
        if not transcript:
            raise HTTPException(status_code=500, detail="Transcription failed")
            
        # 3. Generate Notes
        notes = generate_study_material(transcript, language)
        
        return {"status": "success", "markdown": notes, "source": "audio-upload"}

    except Exception as e:
        return {"error": str(e)}
        
    finally:
        # 4. Cleanup
        if os.path.exists(temp_filename):
            os.remove(temp_filename)
