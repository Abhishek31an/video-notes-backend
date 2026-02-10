import os
import time
import json
import math
import yt_dlp
from dotenv import load_dotenv
from groq import Groq
import google.generativeai as genai
from fastapi import FastAPI, Form, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
import base64
import requests # <--- Add this at the very top if missing!
import random

# --- 1. CONFIGURATION ---
load_dotenv()

GROQ_API_KEY = os.getenv("GROQ_API_KEY")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

if not GROQ_API_KEY or not GEMINI_API_KEY:
    raise ValueError("❌ Missing API Keys. Please check your .env file.")

# Initialize Clients
groq_client = Groq(api_key=GROQ_API_KEY)
genai.configure(api_key=GEMINI_API_KEY)

app = FastAPI()

# --- SECURITY CONFIGURATION (CORS) ---
# This allows the frontend (Cloudflare) to talk to the backend (Render)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Allows ALL websites (Simplest for now)
    allow_credentials=True,
    allow_methods=["*"],  # Allows all methods (GET, POST, etc.)
    allow_headers=["*"],
)
os.makedirs("static", exist_ok=True)
# --- 2. AUDIO ENGINE (Video Download) ---
# --- 2. AUDIO ENGINE (Video Download) ---
# --- 2. AUDIO ENGINE (Video Download) ---
def download_audio_nuclear(video_url: str, output_filename="temp_audio"):
    """
    Hybrid Downloader:
    1. Tries multiple Cobalt API mirrors (Bypasses YouTube Block).
    2. Falls back to yt-dlp if APIs fail.
    """
    output_path = os.path.join(os.getcwd(), output_filename + ".mp3")
    
    # Cleanup old file
    if os.path.exists(output_path):
        os.remove(output_path)

    print(f"🔄 Trying API Download for: {video_url}")

    # --- STRATEGY 1: COBALT API MIRRORS (The Cloud Bypass) ---
    # These are public instances that process the video for us.
    # We rotate through them to find one that is online.
    cobalt_instances = [
        "https://api.cobalt.tools/api/json",      # Official Instance
        "https://cobalt.tacohitbox.com/api/json", # Reliable Mirror
        "https://coapi.kelig.me/api/json",        # Reliable Mirror
        "https://cobalt-api.ayo.tf/api/json",     # Reliable Mirror
        "https://api.oxidenetworks.com/api/json", # Backup
    ]

    # Shuffle to distribute load (and avoid hitting the same bad one first)
    random.shuffle(cobalt_instances)

    for api_url in cobalt_instances:
        try:
            print(f"🌐 Testing API: {api_url} ...")
            headers = {
                "Accept": "application/json",
                "Content-Type": "application/json",
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"
            }
            
            data = {
                "url": video_url,
                "vCodec": "h264",
                "vQuality": "720",
                "aFormat": "mp3",
                "isAudioOnly": True
            }

            response = requests.post(api_url, json=data, headers=headers, timeout=12)
            
            if response.status_code == 200:
                result = response.json()
                # Different instances return the link in different keys ('url' or 'picker')
                direct_link = result.get("url") or result.get("picker", [{}])[0].get("url")
                
                if direct_link:
                    print(f"✅ API Success! Downloading from: {api_url}")
                    
                    # Download the actual file from the link
                    with requests.get(direct_link, stream=True) as r:
                        r.raise_for_status()
                        with open(output_path, 'wb') as f:
                            for chunk in r.iter_content(chunk_size=8192):
                                f.write(chunk)
                    
                    return output_path
        except Exception as e:
            print(f"⚠️ API {api_url} failed. Trying next... ({str(e)[:50]})")
            continue 

    # --- STRATEGY 2: FALLBACK TO YT-DLP (Internal) ---
    print("⚠️ All APIs failed. Falling back to internal yt-dlp...")
    
    # Simple yt-dlp configuration as last resort
    import yt_dlp
    ydl_opts = {
        'format': 'bestaudio/best',
        'outtmpl': os.path.join(os.getcwd(), output_filename),
        'postprocessors': [{'key': 'FFmpegExtractAudio','preferredcodec': 'mp3','preferredquality': '32'}],
        'quiet': True,
        'no_warnings': True,
        'nocheckcertificate': True,
    }
    
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            ydl.download([video_url])
        return f"{output_path}"
    except Exception as e:
        print(f"❌ Internal Download Error: {e}")
        return None

# --- 3. AI ENGINE (Transcription & Generation) ---
MODEL_PRIORITY_LIST = [
    'gemini-2.5-flash',
    'gemini-2.5-flash-lite',
    'gemini-2.5-flash-preview-09-2025',
    'gemini-2.0-flash',
    'gemini-2.0-flash-lite',
    'gemini-2.0-flash-001',
    'gemini-2.0-flash-lite-001',
    'gemini-flash-latest',
    'gemini-flash-lite-latest',
    'gemini-3-flash-preview',       # 🚀 Gemini 3 Preview!
    'gemini-2.5-pro',
    'gemini-pro-latest',
    'gemini-3-pro-preview',         # 🚀 Gemini 3 Pro!
    'gemini-exp-1206',
    'gemma-3-27b-it',               # Gemma models as final backups
    'gemma-3-12b-it',
    'gemma-3-4b-it'
]

def get_working_gemini_response(prompt_parts):
    """Helper: Tries multiple Gemini models until one works."""
    for i, model_name in enumerate(MODEL_PRIORITY_LIST):
        try:
            # print(f"🤖 Attempt {i+1}: {model_name}...") 
            model = genai.GenerativeModel(model_name)
            response = model.generate_content(prompt_parts)
            return response.text
        except Exception as e:
            error_msg = str(e)
            if "429" in error_msg:
                print(f"⚠️ Quota Limit on {model_name}. Switching...")
                time.sleep(1 + (i * 0.5)) # Increasing delay (1s, 1.5s, 2s...) to let API cool down
                continue
            elif "404" in error_msg:
                # Silently skip models that aren't available for your key/region
                continue
            else:
                print(f"❌ Error on {model_name}: {e}")
                continue
    
    return "Sorry, the AI is currently overloaded. Please wait 1 minute and try again."

def transcribe_with_gemini(audio_path):
    """Backup transcription using Gemini."""
    print("⚠️ Switching to Gemini Backup...")
    try:
        audio_file = genai.upload_file(path=audio_path)
        while audio_file.state.name == "PROCESSING":
            time.sleep(1)
            audio_file = genai.get_file(audio_file.name)
        
        prompt = [audio_file, "Transcribe exactly word for word. Output raw text."]
        return get_working_gemini_response(prompt)
    except Exception as e:
        print(f"❌ Gemini Transcribe Error: {e}")
        return None

def transcribe_audio(audio_path):
    """Primary transcription using Groq (Whisper)."""
    print("🎙️ Transcribing with Groq...")
    try:
        with open(audio_path, "rb") as file:
            return groq_client.audio.transcriptions.create(
                file=(audio_path, file.read()),
                model="whisper-large-v3",
                response_format="text",
                language="en"
            )
    except Exception as e:
        print(f"⚠️ Groq Failed ({e}), switching to backup...")
        return transcribe_with_gemini(audio_path)

def generate_study_notes(transcript_text, target_language="English"):
    """Generates notes + Quiz."""
    if not transcript_text: return None
    
    # Estimate length
    words = len(transcript_text.split())
    minutes = math.ceil(words / 150)
    target_length = max(300, min(1200, 200 + (minutes * 15)))
    
    print(f"🧠 Generating Notes ({target_language})...")

    prompt = f"""
    You are an expert AI tutor. 
    Target Language: {target_language}.
    Total Output Length: ~{target_length} words.

    Generate:
    1. A Markdown Summary & Key Concepts.
    2. A JSON Quiz block at the end.

    Format:
    # 📝 Video Summary
    [Summary]
    ## 🔑 Key Concepts
    - [Points]
    
    ```json
    [
        {{ "question": "...", "options": ["A", "B", "C", "D"], "answer": 0 }}
    ]
    ```

    **Transcript:**
    {transcript_text}
    """
    return get_working_gemini_response(prompt)

def chat_with_video(transcript_text, user_question):
    """
    Chat Bot: Uses transcript as CONTEXT but allows general conversation.
    Tries multiple models to ensure a response.
    """
    print(f"💬 Chatting... Q: {user_question[:20]}...")
    
    prompt = f"""
    You are a helpful and friendly AI Assistant.
    
    You have access to a video transcript (provided below) which serves as CONTEXT for this conversation.
    
    **YOUR INSTRUCTIONS:**
    1. **If the user asks about the video:** Use the transcript to answer accurately.
    2. **If the user asks a general question (e.g., "Hi", "Who are you?", "Explain gravity"):** Answer normally using your own general knowledge. You do NOT need to stick to the transcript for these.
    3. **Be Conversational:** Don't be robotic. If the user says "Hi", say "Hi! How can I help you with this video?"
    
    **Video Transcript Context:**
    {transcript_text[:15000]}
    
    **User Question:**
    {user_question}
    """
    
    # --- USE THE GLOBAL LIST NOW ---
    for i, model_name in enumerate(MODEL_PRIORITY_LIST):
        try:
            model = genai.GenerativeModel(model_name)
            response = model.generate_content(prompt)
            return response.text
        except Exception as e:
            # print(f"⚠️ Chat failed on {model_name}, trying next...")
            continue 

    return "Sorry, all AI models are currently busy. Please try again in a moment."

# --- 4. API ENDPOINTS ---

@app.get("/")
async def read_root():
    return {"message": "✅ Backend is running! Access this via your Frontend URL."}

@app.post("/generate")
async def generate_notes_endpoint(url: str = Form(...), language: str = Form(...)):
    print(f"🚀 Processing: {url}")
    audio_file = download_audio_nuclear(url)
    if not audio_file: return {"error": "Download failed"}

    try:
        transcript = transcribe_audio(audio_file)
        if not transcript: return {"error": "Transcription failed"}
        
        notes = generate_study_notes(transcript, language)
        
        # Clean up
        if os.path.exists(audio_file): os.remove(audio_file)
            
        return {"status": "success", "markdown": notes, "transcript": transcript}
    except Exception as e:
        return {"error": str(e)}

@app.post("/chat")
async def chat_endpoint(question: str = Form(...), transcript: str = Form(...)):
    if not question or not transcript:
        return {"answer": "Error: Missing data."}
    
    answer = chat_with_video(transcript, question)
    return {"answer": answer}
