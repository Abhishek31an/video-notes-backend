import os
import requests
import re
import time
from urllib.parse import urlparse, parse_qs

# --- CONFIGURATION ---
# List of Cobalt Instances (Wrappers that download for you)
# These run on various servers, effectively rotating your IP for you.
COBALT_INSTANCES = [
    "https://api.cobalt.best",         # Often reliable
    "https://cobalt.moskas.io",        # Alternative
    "https://on.soundcloud.com",       # (Just kidding, placeholder for rotation logic)
    "https://api.cobalt.kwiatekmiki.pl",
    "https://cobalt.steamys.me",
    "https://cobalt.q11.app",
]

# List of Piped Instances (YouTube Frontend APIs)
# Piped proxies streams, bypassing the IP check.
PIPED_INSTANCES = [
    "https://pipedapi.kavin.rocks",
    "https://api.piped.privacy.com.de",
    "https://pipedapi.drgns.space",
    "https://api-piped.mha.fi",
]

def get_video_id(url):
    """Extracts video ID from various YouTube URL formats."""
    query = urlparse(url)
    if query.hostname == 'youtu.be':
        return query.path[1:]
    if query.hostname in ('www.youtube.com', 'youtube.com'):
        if query.path == '/watch':
            p = parse_qs(query.query)
            return p['v'][0]
        if query.path[:7] == '/embed/':
            return query.path.split('/')[2]
        if query.path[:3] == '/v/':
            return query.path.split('/')[3]
    return None

def download_audio_federated(video_url: str, output_filename="temp_audio"):
    """
    Strategy: 
    1. Try Cobalt Mirrors (Downloads file on their server, sends to us).
    2. Try Piped API (Gets a proxied stream URL).
    """
    output_path = os.path.join(os.getcwd(), output_filename + ".mp3")
    
    # 1. Setup
    if os.path.exists(output_path):
        os.remove(output_path)
    
    print(f"🚀 Starting Federated Download for: {video_url}")

    # --- STRATEGY A: COBALT ROTATOR ---
    print("⚔️  Attempting Cobalt Instances...")
    
    headers = {
        "Accept": "application/json",
        "Content-Type": "application/json",
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }

    cobalt_payload = {
        "url": video_url,
        "vCodec": "h264",
        "vQuality": "720",
        "aFormat": "mp3",
        "isAudioOnly": True
    }

    for instance in COBALT_INSTANCES:
        try:
            api_url = f"{instance}/api/json"
            print(f"   -> Trying {instance}...", end=" ")
            
            resp = requests.post(api_url, json=cobalt_payload, headers=headers, timeout=15)
            
            if resp.status_code == 200:
                data = resp.json()
                download_link = data.get("url")
                
                if download_link:
                    print("✅ Link found! Downloading...")
                    # Stream download to file
                    with requests.get(download_link, stream=True, timeout=30) as r:
                        r.raise_for_status()
                        with open(output_path, 'wb') as f:
                            for chunk in r.iter_content(chunk_size=8192):
                                f.write(chunk)
                    
                    if os.path.getsize(output_path) > 1024: # Check valid file size
                        print(f"🎉 Success via Cobalt: {instance}")
                        return output_path
            
            print("❌ Failed (Status/No Link)")
            
        except Exception as e:
            print(f"⚠️ Error: {str(e)}")
            continue # Try next instance

    # --- STRATEGY B: PIPED API FALLBACK ---
    # If all Cobalt instances fail (likely due to overload), try Piped.
    print("\n🛡️ All Cobalt instances failed. Engaging Piped API fallback...")
    
    video_id = get_video_id(video_url)
    if not video_id:
        print("❌ Could not extract Video ID for Piped.")
        return None

    for instance in PIPED_INSTANCES:
        try:
            # Piped Endpoint: /streams/{video_id}
            api_url = f"{instance}/streams/{video_id}"
            print(f"   -> Trying Piped {instance}...", end=" ")
            
            resp = requests.get(api_url, timeout=10)
            if resp.status_code == 200:
                data = resp.json()
                audio_streams = data.get("audioStreams", [])
                
                # Sort by bitrate (highest first) and pick mp3/m4a
                # Piped usually returns m4a, we might need to rely on ffmpeg later or just save as mp3
                target_stream = next((s for s in audio_streams if s.get("format") == "M4A" or s.get("mimeType", "").startswith("audio")), None)
                
                if target_stream:
                    stream_url = target_stream["url"]
                    print("✅ Stream found! Downloading...")
                    
                    # NOTE: Piped streams might be proxied. If they are direct Google links, 
                    # Render might block them. We hope for a proxied link.
                    with requests.get(stream_url, stream=True, timeout=30) as r:
                        r.raise_for_status()
                        with open(output_path, 'wb') as f:
                            for chunk in r.iter_content(chunk_size=8192):
                                f.write(chunk)
                                
                    if os.path.getsize(output_path) > 1024:
                        print(f"🎉 Success via Piped: {instance}")
                        return output_path
            print("❌ Failed")
            
        except Exception as e:
            print(f"⚠️ Error: {str(e)}")
            continue

    print("💀 Total Failure: No instances could download the audio.")
    return None
