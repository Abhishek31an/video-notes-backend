import os
import time
import json
import math
import random
import requests
from urllib.parse import urlparse, parse_qs

# --- Third Party Libraries ---
from dotenv import load_dotenv
from groq import Groq
import google.generativeai as genai
from fastapi import FastAPI, Form
from fastapi.middleware.cors import CORSMiddleware

# --- 1. CONFIGURATION ---
load_dotenv()

GROQ_API_KEY = os.getenv("GROQ_API_KEY")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

if not GROQ_API_KEY or not GEMINI_API_KEY:
    # We print a warning but don't crash, in case you set them in Render Dashboard directly
    print("⚠️  Warning: API Keys not found in .env. Ensure they are set in Render Environment Variables.")

# Initialize Clients
groq_client = Groq(api_key=GROQ_API_KEY)
genai.configure(api_key=GEMINI_API_KEY)

app = FastAPI()

# --- SECURITY CONFIGURATION (CORS) ---
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Allows all origins
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Create static folder for temp files if it doesn't exist
os.makedirs("static", exist_ok=True)


# --- 2. AUDIO ENGINE (The New Federated Downloader) ---

# --- 2. AUDIO ENGINE (The Federated Downloader V2) ---

# Expanded Cobalt List (Mixed reliability, high rotation)
COBALT_INSTANCES = [
    "https://api.cobalt.best",                 # Reliable
    "https://cobalt.moskas.io",                # Frequent updates
    "https://cobalt.xy2401.com",               # Backup
    "https://api.cobalt.kwiatekmiki.pl",       # Poland
    "https://cobalt.steamys.me",               # US
    "https://cobalt.q11.app",                  # US
    "https://api.cobalt.minaev.su",            # Russia (often ignores IP bans)
    "https://cobalt.lacus.mynetgear.com",      # Home hosting
    "https://cobalt.mc.hzuccon.com",           # Brazil
    "https://api.server.cobalt.tools",         # Official (Strict)
    "https://cobalt.154.53.58.117.sslip.io",   # Direct IP
]

# Expanded Piped List (Frontend APIs)
PIPED_INSTANCES = [
    "https://pipedapi.tokhmi.xyz",             # US
    "https://pipedapi.moomoo.me",              # UK
    "https://pipedapi.syncpundit.io",          # India/Global
    "https://pipedapi.kavin.rocks",            # Official (Often strict)
    "https://piped-api.lunar.icu",             # Germany
    "https://ytapi.dc09.ru",                   # Russia
    "https://pipedapi.r4fo.com",               # Germany
    "https://api.piped.yt",                    # Germany
    "https://pipedapi.rivo.lol",               # Chile
    "https://api-piped.mha.fi",                # Finland
    "https://pipedapi.leptons.xyz",            # Austria
]

def download_audio_federated(video_url: str, output_filename="temp_audio"):
    """
    Downloader V5.1: Massive Rotation Strategy.
    Brute-forces through a large list of mirrors to find one that allows Render IPs.
    """
    output_path = os.path.join(os.getcwd(), output_filename + ".mp3")
    
    if os.path.exists(output_path):
        os.remove(output_path)
    
    print(f"🚀 Starting Federated Download for: {video_url}")

    # --- STRATEGY A: COBALT ROTATOR ---
    print(f"⚔️  Attempting {len(COBALT_INSTANCES)} Cobalt Instances...")
    
    headers = {
        "Accept": "application/json",
        "Content-Type": "application/json",
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
    }

    cobalt_payload = {
        "url": video_url,
        "vCodec": "h264",
        "vQuality": "720",
        "aFormat": "mp3",
        "isAudioOnly": True
    }

    random.shuffle(COBALT_INSTANCES)

    for instance in COBALT_INSTANCES:
        try:
            base_url = instance.rstrip("/")
            api_url = f"{base_url}/api/json"
            
            # Short timeout (6s) to skip dead servers fast
            resp = requests.post(api_url, json=cobalt_payload, headers=headers, timeout=6)
            
            if resp.status_code == 200:
                data = resp.json()
                download_link = data.get("url") or data.get("picker", [{}])[0].get("url") or data.get("audio")
                
                if download_link:
                    print(f"✅ Link found via {base_url}! Downloading...")
                    with requests.get(download_link, stream=True, timeout=30) as r:
                        r.raise_for_status()
                        with open(output_path, 'wb') as f:
                            for chunk in r.iter_content(chunk_size=8192):
                                f.write(chunk)
                    
                    if os.path.exists(output_path) and os.path.getsize(output_path) > 1024:
                        print(f"🎉 Success via Cobalt: {base_url}")
                        return output_path
            else:
                # Print specific error codes (403=Forbidden, 429=RateLimit)
                # print(f"   -> {base_url} returned {resp.status_code}")
                pass
            
        except Exception as e:
            # print(f"   -> {instance} Error: {str(e)[:50]}...")
            continue

    # --- STRATEGY B: PIPED API FALLBACK ---
    print(f"\n🛡️ Cobalt failed. Engaging {len(PIPED_INSTANCES)} Piped Mirrors...")
    
    video_id = get_video_id(video_url)
    if not video_id:
        print("❌ Could not extract Video ID for Piped.")
        return None

    random.shuffle(PIPED_INSTANCES)

    for instance in PIPED_INSTANCES:
        try:
            base_url = instance.rstrip("/")
            api_url = f"{base_url}/streams/{video_id}"
            
            resp = requests.get(api_url, timeout=6)
            
            if resp.status_code == 200:
                data = resp.json()
                audio_streams = data.get("audioStreams", [])
                
                # Prioritize m4a/mp3
                target_stream = next((s for s in audio_streams if s.get("mimeType", "").startswith("audio")), None)
                
                if target_stream:
                    stream_url = target_stream["url"]
                    print(f"✅ Stream found via {base_url}! Downloading...")
                    
                    with requests.get(stream_url, stream=True, timeout=30) as r:
                        r.raise_for_status()
                        with open(output_path, 'wb') as f:
                            for chunk in r.iter_content(chunk_size=8192):
                                f.write(chunk)
                                
                    if os.path.exists(output_path) and os.path.getsize(output_path) > 1024:
                        print(f"🎉 Success via Piped: {base_url}")
                        return output_path
            else:
                # print(f"   -> {base_url} returned {resp.status_code}")
                pass
                
        except Exception:
            continue

    print("💀 Total Failure: All mirrors blocked or down.")
    return None
# --- 3. AI ENGINE (Transcription & Generation) ---

MODEL_PRIORITY_LIST = [
    'gemini-2.0-flash',
    'gemini-2.0-flash-lite',
    'gemini-1.5-flash',
    'gemini-1.5-pro',
]

def get_working_gemini_response(prompt_parts):
    """Helper: Tries multiple Gemini models until one works."""
    for i, model_name in enumerate(MODEL_PRIORITY_LIST):
        try:
            model = genai.GenerativeModel(model_name)
            response = model.generate_content(prompt_parts)
            return response.text
        except Exception as e:
            error_msg = str(e)
            if "429" in error_msg:
                print(f"⚠️ Quota Limit on {model_name}. Switching...")
                time.sleep(1)
                continue
            elif "404" in error_msg:
                continue
            else:
                print(f"❌ Error on {model_name}: {e}")
                continue

    return "Sorry, the AI is currently overloaded. Please wait 1 minute and try again."

def transcribe_with_gemini(audio_path):
    """Backup transcription using Gemini."""
    print("⚠️ Switching to Gemini Backup...")
    try:
        # Upload file to Gemini
        print("   -> Uploading to Gemini...")
        audio_file = genai.upload_file(path=audio_path)
        
        # Wait for processing
        while audio_file.state.name == "PROCESSING":
            time.sleep(1)
            audio_file = genai.get_file(audio_file.name)

        if audio_file.state.name == "FAILED":
            raise ValueError("Gemini file processing failed.")

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

    # Estimate length constraints
    words = len(transcript_text.split())
    # Cap output to avoid timeouts on huge videos
    target_length = max(300, min(1500, words // 2))

    print(f"🧠 Generating Notes ({target_language})...")

    prompt = f"""
    You are an expert AI tutor. 
    Target Language: {target_language}.
    
    Generate:
    1. A Comprehensive Markdown Summary.
    2. Key Concepts (Bullet points).
    3. A JSON Quiz block at the very end.

    Format:
    # 📝 Video Summary
    [Summary]
    ## 🔑 Key Concepts
    - [Point 1]
    - [Point 2]
    
    ```json
    [
        {{ "question": "...", "options": ["A", "B", "C", "D"], "answer": 0 }}
    ]
    ```

    **Transcript:**
    {transcript_text[:50000]} 
    """
    # Note: We truncate transcript to 50k chars to stay safe within limits for Flash models
    return get_working_gemini_response(prompt)

def chat_with_video(transcript_text, user_question):
    """Chat Bot."""
    # print(f"💬 Chatting... Q: {user_question[:20]}...")

    prompt = f"""
    You are a helpful and friendly AI Assistant.
    
    **Context (Video Transcript):**
    {transcript_text[:20000]}
    
    **User Question:**
    {user_question}
    
    Answer the user based on the video. If the answer isn't in the video, say so politely.
    """
    return get_working_gemini_response(prompt)


# --- 4. API ENDPOINTS ---

@app.get("/")
async def read_root():
    return {"message": "✅ Backend is running! Access this via your Frontend URL."}

@app.post("/generate")
async def generate_notes_endpoint(url: str = Form(...), language: str = Form(...)):
    print(f"🚀 Processing: {url}")
    
    # 1. Download
    audio_file = download_audio_federated(url)
    if not audio_file: 
        return {"error": "Download failed. YouTube blocked all servers."}

    try:
        # 2. Transcribe
        transcript = transcribe_audio(audio_file)
        if not transcript: 
            return {"error": "Transcription failed"}

        # 3. Generate Notes
        notes = generate_study_notes(transcript, language)

        # 4. Clean up audio file
        if os.path.exists(audio_file): 
            os.remove(audio_file)

        return {"status": "success", "markdown": notes, "transcript": transcript}
    except Exception as e:
        return {"error": str(e)}

@app.post("/chat")
async def chat_endpoint(question: str = Form(...), transcript: str = Form(...)):
    if not question or not transcript:
        return {"answer": "Error: Missing data."}

    answer = chat_with_video(transcript, question)
    return {"answer": answer}
