import requests

LM_STUDIO_URL = "http://10.0.0.198:11434/v1/chat/completions"  # Modify if needed

def query_lm_studio(prompt: str, image_bytes: bytes = None):
    headers = {"Content-Type": "application/json"}

    data = {
        "model": "local-model",
        "messages": [{"role": "user", "content": prompt}],
    }

    if image_bytes:
        # LM Studio supports base64 images in messages
        import base64
        b64 = base64.b64encode(image_bytes).decode("utf-8")

        data["messages"][0]["images"] = [b64]

    try:
        response = requests.post(LM_STUDIO_URL, json=data, headers=headers)
        result = response.json()

        return result["choices"][0]["message"]["content"]
    except Exception as e:
        return f"Error communicating with LM Studio: {str(e)}"
