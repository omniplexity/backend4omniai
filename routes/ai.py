from fastapi import APIRouter, UploadFile, File, Form
from services.lmstudio_client import query_lm_studio

router = APIRouter()

@router.post("/chat")
async def chat(prompt: str = Form(...)):
    response = query_lm_studio(prompt)
    return {"response": response}

@router.post("/vision")
async def vision_query(
    prompt: str = Form(...),
    image: UploadFile = File(...)
):
    content = await image.read()
    response = query_lm_studio(prompt, image_bytes=content)
    return {"response": response}
