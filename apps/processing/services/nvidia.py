import json, re, wave
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
