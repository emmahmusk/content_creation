from PIL import Image, ImageDraw, ImageEnhance, ImageFont

def create_thumbnail(frame_path, title, destination):
    image=Image.open(frame_path).convert("RGB"); image.thumbnail((1280,720))
    canvas=Image.new("RGB",(1280,720),(15,23,20)); canvas.paste(image,((1280-image.width)//2,(720-image.height)//2))
    canvas=ImageEnhance.Brightness(canvas).enhance(.65); draw=ImageDraw.Draw(canvas)
    try: font=ImageFont.truetype("arialbd.ttf",64)
    except OSError: font=ImageFont.load_default()
    words=title.upper().split(); lines=[]; line=""
    for word in words:
        trial=f"{line} {word}".strip()
        if draw.textbbox((0,0),trial,font=font)[2]>1050 and line: lines.append(line); line=word
        else: line=trial
    if line: lines.append(line)
    y=470-len(lines)*42
    for line in lines[:3]:
        draw.text((70,y),line,font=font,fill=(255,255,255),stroke_width=4,stroke_fill=(0,0,0)); y+=78
    draw.rectangle((70,y+12,350,y+22),fill=(187,243,61)); canvas.save(destination,quality=92)
    return destination
