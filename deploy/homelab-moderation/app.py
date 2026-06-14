"""NSFW moderation fallback service for HiloBakeStands.

Runs on media.home (16 GB box). Loads a small open-source ViT classifier
(Falconsai/nsfw_image_detection, ~350 MB, CPU is fine) and exposes one
endpoint:

    POST /check
    Headers: X-Auth-Token: <shared secret>
    Body: raw image bytes
    → {"nsfw": 0.0123}

The Django site calls this only when Google SafeSearch is unreachable or
over quota. Score ≥ 0.5 is treated as flagged by the caller.
"""
import io
import os

from fastapi import FastAPI, HTTPException, Request
from PIL import Image
from transformers import pipeline

TOKEN = os.environ['MODERATION_TOKEN']  # required; refuse to start without

app = FastAPI()
classifier = pipeline('image-classification',
                      model='Falconsai/nsfw_image_detection', device=-1)


@app.get('/healthz')
def healthz():
    return {'ok': True}


@app.post('/check')
async def check(request: Request):
    if request.headers.get('X-Auth-Token') != TOKEN:
        raise HTTPException(status_code=401, detail='bad token')
    data = await request.body()
    if len(data) > 15 * 1024 * 1024:
        raise HTTPException(status_code=413, detail='too large')
    try:
        img = Image.open(io.BytesIO(data)).convert('RGB')
    except Exception:
        raise HTTPException(status_code=400, detail='not an image')
    results = classifier(img)
    nsfw = next((r['score'] for r in results if r['label'] == 'nsfw'), 0.0)
    return {'nsfw': round(float(nsfw), 4)}
