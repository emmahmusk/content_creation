import base64, json, re, wave
from pathlib import Path
import requests
from django.conf import settings

class NvidiaConfigurationError(RuntimeError): pass

def _key():
    if not settings.NVIDIA_API_KEY: raise NvidiaConfigurationError("NVIDIA_API_KEY is not configured.")
    return settings.NVIDIA_API_KEY

def generate_json(system, prompt, fallback):
    if not settings.NVIDIA_API_KEY:
        if settings.PIPELINE_ALLOW_MOCK_AI: return fallback
        _key()
    from openai import OpenAI
    client=OpenAI(base_url=settings.NVIDIA_LLM_BASE_URL, api_key=_key())
    response=client.chat.completions.create(model=settings.NVIDIA_LLM_MODEL,
        messages=[{"role":"system","content":system},{"role":"user","content":prompt}],
        temperature=.25, top_p=.9, max_tokens=7000, stream=False)
    content=response.choices[0].message.content
    match=re.search(r"```(?:json)?\s*(.*?)```",content,re.S)
    return json.loads(match.group(1) if match else content)

def transcribe(audio_path, fallback_text=""):
    if not settings.NVIDIA_API_KEY:
        if not settings.PIPELINE_ALLOW_MOCK_AI: _key()
        words=fallback_text.split() or ["Add", "an", "NVIDIA", "API", "key", "to", "generate", "the", "real", "transcript."]
        segments=[]
        for i in range(0,len(words),12):
            start=i*450; chunk=words[i:i+12]
            segments.append({"start_ms":start,"end_ms":start+max(1800,len(chunk)*450),"text":" ".join(chunk),"words":[]})
        return segments
    import riva.client
    auth=riva.client.Auth(uri=settings.NVIDIA_ASR_SERVER,use_ssl=True,metadata_args=[
        ["function-id",settings.NVIDIA_ASR_FUNCTION_ID],["authorization",f"Bearer {_key()}"]])
    service=riva.client.ASRService(auth)
    with wave.open(str(audio_path),"rb") as wav:
        rate=wav.getframerate(); audio=wav.readframes(wav.getnframes())
    config=riva.client.RecognitionConfig(encoding=riva.client.AudioEncoding.LINEAR_PCM,
        sample_rate_hertz=rate,language_code=settings.NVIDIA_ASR_LANGUAGE,max_alternatives=1,
        enable_automatic_punctuation=True,enable_word_time_offsets=True)
    response=service.offline_recognize(audio,config)
    segments=[]
    for result in response.results:
        alt=result.alternatives[0]; words=[]
        for word in alt.words:
            start=int((word.start_time.seconds+word.start_time.nanos/1e9)*1000)
            end=int((word.end_time.seconds+word.end_time.nanos/1e9)*1000)
            words.append({"word":word.word,"start_ms":start,"end_ms":end})
        if words: segments.append({"start_ms":words[0]["start_ms"],"end_ms":words[-1]["end_ms"],"text":alt.transcript,"words":words})
    return segments

def plan_package(transcript, brief, duration_ms):
    fallback_clips=[]
    segment=max(15000,duration_ms//10 if duration_ms else 30000)
    for i in range(10):
        start=i*segment; end=min(start+min(segment,60000),duration_ms or (i+1)*segment)
        fallback_clips.append({"rank":i+1,"title":f"Key moment {i+1}","hook":f"The idea most people miss — part {i+1}","caption":f"A standout idea from {brief[:80]}","start_ms":start,"end_ms":max(end,start+5000),"score":8-(i*.1),"rationale":"Evenly sampled development placeholder."})
    fallback={"clips":fallback_clips,"social_posts":{"linkedin":"A practical lesson from our latest conversation.","x":"One idea can change how you approach the work.","instagram":"Save this for later. A useful lesson from the full conversation."},"youtube":{"titles":["The Conversation You Need to Hear"],"description":brief,"chapters":["00:00 Introduction"]},"newsletter":{"title":"The idea worth sharing","body":brief}}
    system="You are a senior content strategist. Return valid JSON only. Never invent timestamps beyond the supplied transcript."
    prompt=f'''Create a complete repurposing package. Select exactly 10 self-contained clips, each 20-60 seconds where possible. Use milliseconds. Each clip requires rank,title,hook,caption,start_ms,end_ms,score (0-10),rationale. Also return social_posts with linkedin,x,instagram; youtube with titles (3),description,chapters; newsletter with title,body. Brief: {brief}\nDuration ms: {duration_ms}\nTranscript:\n{transcript[:60000]}'''
    return generate_json(system,prompt,fallback)


def plan_broll(clip_context, intensity, clip_duration_ms):
    scene_limit = {"minimal": 1, "moderate": 2, "aggressive": 3}.get(intensity, 2)
    safe_start = min(2500, max(0, clip_duration_ms // 5))
    usable = max(1000, clip_duration_ms - safe_start)
    fallback = {
        "scenes": [
            {
                "start_ms": safe_start + int((usable * index) / max(1, scene_limit)),
                "duration_ms": min(4000, max(1800, usable // max(1, scene_limit + 1))),
                "visual_prompt": "A cinematic, text-free visual metaphor supporting the spoken idea",
                "stock_query": "creative team working cinematic",
                "reason": "Adds visual context without covering the opening hook.",
            }
            for index in range(scene_limit)
        ]
    }
    system = (
        "You are a senior short-form video editor. Return valid JSON only. "
        "Plan concise B-roll that supports the approved clip without changing its meaning."
    )
    prompt = f"""Plan {scene_limit} B-roll insert(s) for this approved short-form clip.
The clip is {clip_duration_ms}ms long. Do not place B-roll in the first 2000ms. Each insert must be 1800-4000ms, must not overlap another insert, and total coverage must stay restrained. Avoid faces of identifiable people, logos, text, copyrighted characters, and claims not supported by the transcript.
Return: {{"scenes":[{{"start_ms":integer relative to clip,"duration_ms":integer,"visual_prompt":"cinematic generation prompt","stock_query":"short literal stock search","reason":"why this visual helps retention"}}]}}.

Approved clip context:
{clip_context[:18000]}"""
    return generate_json(system, prompt, fallback)


def _generated_bytes(payload):
    data = payload.get("data")
    if isinstance(data, list) and data:
        data = data[0]
    if isinstance(data, dict) and data.get("b64_json"):
        return base64.b64decode(data["b64_json"])
    artifacts = payload.get("artifacts") or []
    if artifacts:
        encoded = artifacts[0].get("base64") or artifacts[0].get("b64_json")
        if encoded:
            return base64.b64decode(encoded)
    raise RuntimeError("The NVIDIA visual API returned no generated media.")


def generate_broll_image(prompt, destination):
    if not settings.NVIDIA_IMAGE_API_URL:
        raise NvidiaConfigurationError("NVIDIA_IMAGE_API_URL is not configured.")
    response = requests.post(
        settings.NVIDIA_IMAGE_API_URL,
        headers={"Authorization": f"Bearer {_key()}", "Accept": "application/json"},
        json={
            "model": settings.NVIDIA_IMAGE_MODEL,
            "prompt": prompt,
            "n": 1,
            "size": "1024x1024",
            "response_format": "b64_json",
        },
        timeout=(20, 240),
    )
    response.raise_for_status()
    Path(destination).write_bytes(_generated_bytes(response.json()))
    return destination


def generate_broll_video(prompt, destination, seconds=4):
    if not settings.NVIDIA_VIDEO_API_URL:
        raise NvidiaConfigurationError("NVIDIA_VIDEO_API_URL is not configured.")
    response = requests.post(
        settings.NVIDIA_VIDEO_API_URL,
        headers={"Authorization": f"Bearer {_key()}", "Accept": "application/json"},
        json={
            "model": settings.NVIDIA_VIDEO_MODEL,
            "prompt": prompt,
            "size": "832x480",
            "seconds": max(2, min(int(seconds), 5)),
        },
        timeout=(20, 420),
    )
    response.raise_for_status()
    Path(destination).write_bytes(_generated_bytes(response.json()))
    return destination
