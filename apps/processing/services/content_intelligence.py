import json

from django.conf import settings
from django.db import transaction

from apps.processing.models import ContentIntelligence, RepurposeAsset
from apps.processing.services import groq_provider


PLATFORMS=("LinkedIn","Instagram","TikTok","YouTube Shorts","X","Newsletter","Blog")


def _clip_transcript(clip):
    segments=clip.order.transcript_segments.filter(start_ms__lt=clip.end_ms,end_ms__gt=clip.start_ms)
    return " ".join(segment.text for segment in segments).strip()


def _default_analysis(clip):
    transcript=_clip_transcript(clip)
    audience=clip.order.importance_definition or clip.order.content_brief or "The creator's target audience"
    quality=max(1,min(100,round(float(clip.score)*10)))
    quote=clip.hook or (transcript[:180] if transcript else clip.title)
    dna={
        "overall_quality_score":quality,"overall_recommendation":"Publish after applying the hook and pacing recommendations.","ai_confidence":82,
        "content_category":"Educational insight","intent":"Teach and spark discussion","primary_emotion":"Curiosity","secondary_emotion":"Confidence","audience":audience,
        "knowledge_level":"Accessible","story_structure":"Hook → insight → resolution","narrative_arc":"Problem to practical takeaway","content_type":"Short-form insight",
        "educational_depth":78,"entertainment_value":68,"authority":80,"originality":72,"conversation_potential":76,"virality_potential":quality,
        "retention_prediction":74,"estimated_completion_rate":71,"most_memorable_quote":quote,"primary_takeaway":clip.caption or clip.title,
        "cta_detected":False,"objections_addressed":[],"stories_detected":[],"frameworks_detected":[],"statistics_detected":[],"questions_detected":[],"examples_detected":[],"analogies_detected":[]}
    reasoning={"strengths":[clip.rationale or "Clear standalone value","Strong opening idea"],"weaknesses":["The opening can become more immediate"],"opportunities":["Connect the takeaway to a concrete audience outcome"],"suggested_improvements":["Remove any setup before the first useful sentence","End immediately after the resolved idea"],"alternative_start":clip.hook,"alternative_end":"Close on the primary takeaway without an outro.","recommended_hook":clip.hook,"recommended_thumbnail_text":clip.title[:45],"recommended_cta":"Save this and apply it to your next project.","audience_relevance":audience}
    strategy={name:{"score":max(1,min(100,quality-(index*2))),"best_publish_time":"Weekday, 9:00 AM in the audience timezone","caption":clip.caption or clip.hook,"title":clip.title,"hook":clip.hook,"description":clip.rationale,"hashtags":["#ContentStrategy","#CreatorEconomy"],"thumbnail_text":clip.title[:45],"aspect_ratio":"9:16" if name not in {"Newsletter","Blog"} else "Editorial","clip_length":f"{clip.duration_seconds}s","cta":"Share your experience in the comments."} for index,name in enumerate(PLATFORMS)}
    impact={name:{"score":score,"confidence":78} for name,score in {"comment_potential":74,"share_potential":70,"lead_generation":61,"newsletter_signup_potential":55,"follower_growth":64,"brand_awareness":76,"educational_impact":82,"discussion_potential":75}.items()}
    audiences={name:score for name,score in {"Founders":78,"Developers":55,"Teachers":68,"Students":64,"Creators":86,"Parents":42,"Marketers":80,"Small Businesses":76,"Enterprise":58,"Custom audience":88}.items()}
    graph={"topics":[clip.title],"entities":[],"concepts":["content strategy","audience value"],"relationships":[{"source":clip.title,"target":"audience value","type":"supports"}],"quotes":[quote],"stories":[],"arguments":[clip.caption or clip.title],"questions":[],"counterarguments":[]}
    editor=[{"id":"trim-start","title":"Tighten the opening","description":"Trim setup before the first complete high-value sentence.","impact":"retention","confidence":84},{"id":"boost-hook","title":"Boost the hook","description":f"Open with: {clip.hook}","impact":"hook strength","confidence":88},{"id":"highlight-quote","title":"Highlight the key quote","description":quote,"impact":"memorability","confidence":80}]
    repurpose={
        "linkedin_post":f"{clip.hook}\n\n{clip.caption}\n\nWhat would you add?",
        "x_thread":f"1/ {clip.hook}\n\n2/ {clip.caption}\n\n3/ The takeaway: {clip.title}",
        "instagram_caption":f"{clip.caption}\n\nSave this for later. #ContentStrategy #Creators",
        "youtube_description":f"{clip.title}\n\n{clip.caption}\n\nKey moment from {clip.order.title}.",
        "newsletter":f"# {clip.title}\n\n{clip.caption}\n\nThe practical takeaway is simple: {clip.hook}",
        "blog_outline":f"# {clip.title}\n\n- The problem\n- The key insight\n- How to apply it\n- Common mistakes\n- Next step",
        "seo_metadata":json.dumps({"title":clip.title,"description":clip.caption[:155],"keywords":["content strategy","creator workflow"]},indent=2),
        "email":f"Subject: {clip.title}\n\n{clip.hook}\n\n{clip.caption}\n\nWatch the full insight and reply with your take.",
        "carousel_outline":f"Slide 1: {clip.title}\nSlide 2: The problem\nSlide 3: {clip.hook}\nSlide 4: {clip.caption}\nSlide 5: Save and share",
        "podcast_summary":f"In this segment, {clip.caption or clip.title}. The central takeaway is: {clip.hook}"}
    return {"content_dna":dna,"selection_reasoning":reasoning,"platform_strategy":strategy,"business_impact":impact,"audience_matching":audiences,"semantic_graph":graph,"editor_recommendations":editor,"repurpose":repurpose}


def _merge(base, generated):
    for key,value in generated.items():
        if isinstance(value,dict) and isinstance(base.get(key),dict): base[key].update(value)
        elif value not in (None,"",[],{}): base[key]=value
    return base


def _groq_analysis(clip, base):
    if not settings.GROQ_API_KEY: return base
    prompt={"mission":clip.order.content_brief,"importance_definition":clip.order.importance_definition,"brand_voice":clip.order.brand_voice,"target_platforms":clip.order.target_platforms,"clip":{"title":clip.title,"hook":clip.hook,"caption":clip.caption,"rationale":clip.rationale,"duration_seconds":clip.duration_seconds},"transcript":_clip_transcript(clip)}
    generated=groq_provider.generate_json(
        "Act as a senior content strategist. Return JSON only. Preserve every top-level key from the supplied baseline, replacing generic values with evidence-based analysis. Scores are 0-100. Never invent quotations or statistics.",
        json.dumps({"baseline":base,"source":prompt}),
    )
    return _merge(base,generated)


@transaction.atomic
def generate_for_clip(clip_id):
    from apps.processing.models import Clip
    clip=Clip.objects.select_related("order").get(pk=clip_id)
    intelligence,_=ContentIntelligence.objects.get_or_create(clip=clip)
    intelligence.status=ContentIntelligence.Status.RUNNING;intelligence.error="";intelligence.save(update_fields=["status","error","updated_at"])
    try:
        baseline=_default_analysis(clip);provider_error=""
        try: result=_groq_analysis(clip,baseline)
        except Exception as exc: result=baseline;provider_error=f"AI enrichment was unavailable; baseline analysis was used. {exc}"
        for field in ("content_dna","selection_reasoning","platform_strategy","business_impact","audience_matching","semantic_graph","editor_recommendations"): setattr(intelligence,field,result[field])
        intelligence.confidence=int(result["content_dna"].get("ai_confidence",0));intelligence.model=settings.GROQ_TEXT_MODEL if settings.GROQ_API_KEY and not provider_error else "deterministic-baseline";intelligence.error=provider_error;intelligence.status=ContentIntelligence.Status.READY;intelligence.version+=1;intelligence.save()
        labels=dict(RepurposeAsset.Kind.choices)
        for kind,content in result["repurpose"].items(): RepurposeAsset.objects.update_or_create(clip=clip,kind=kind,defaults={"title":labels.get(kind,kind.replace("_"," ").title()),"content":content})
    except Exception as exc:
        intelligence.status=ContentIntelligence.Status.FAILED;intelligence.error=str(exc);intelligence.save(update_fields=["status","error","updated_at"]);raise
    return intelligence
