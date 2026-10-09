from flask import Flask, request, jsonify
from google import genai
from flask_cors import CORS
import requests
import tempfile
import base64
import os

app = Flask(__name__)
CORS(app)


PROMPTS = {
    "Summary": """
You are a professional tourist guide.

Provide a high-level overview of "{place}" in {language}.

Focus on:
- The historical significance
- Why the place is famous
- Key architectural or cultural highlights

Keep the explanation concise, engaging, and easy to follow.
Avoid excessive details and dates.
Limit the response to around 200 words.

Respond ONLY in {language}.
""",

    "Detailed": """
You are a professional tourist guide.

Provide a detailed and immersive explanation of "{place}" in {language}.

Cover:
- Historical background and timeline
- Architectural design and unique features
- Cultural importance and notable events
- Interesting facts and visitor insights

Explain concepts clearly and in a storytelling manner.
Include relevant details and examples to create a rich experience.
Limit the response to around 400 words.

Respond ONLY in {language}.
"""
}


GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
MURF_API_KEY = os.getenv("MURF_API_KEY")

if not GEMINI_API_KEY:
    raise RuntimeError("GEMINI_API_KEY environment variable is missing")

if not MURF_API_KEY:
    raise RuntimeError("MURF_API_KEY environment variable is missing")


client = genai.Client(api_key=GEMINI_API_KEY)


def generate_description(place, answer_type, language):

    prompt = PROMPTS[answer_type].format(
        place=place,
        language=language
    )

    response = client.models.generate_content(
        model="gemini-3.1-flash-lite",
        contents=prompt
    )

    return response.text


def generate_speech(text, voice_id, locale):

    temp_file = tempfile.NamedTemporaryFile(
        suffix=".mp3",
        delete=False
    )

    temp_file.close()  

    url = "https://global.api.murf.ai/v1/speech/stream"

    headers = {
        "api-key": MURF_API_KEY,
        "Content-Type": "application/json"
    }

    data = {
        "voiceId": voice_id,
        "text": text,
        "locale": locale,
        "model": "falcon-2",
        "format": "MP3",
        "sampleRate": 24000,
        "channelType": "MONO"
    }

    response = requests.post(
        url,
        headers=headers,
        json=data,
        timeout=120
    )

    # IMPORTANT:
    # Return the actual Murf error
    if response.status_code != 200:
        print("Murf status:", response.status_code)
        print("Murf response:", response.text)

        raise Exception(
            f"Murf API error {response.status_code}: {response.text}"
        )

    with open(temp_file.name, "wb") as f:
        for chunk in response.iter_content(chunk_size=8192):
            if chunk:
                f.write(chunk)

    return temp_file


@app.route("/generate-audio-guide", methods=["POST"])
def generate_audio_guide():

    try:

        data = request.get_json()

        if not data:
            return jsonify({
                "error": "Request body is empty"
            }), 400

        place = data.get("place")
        answer_type = data.get("answerType")
        language = data.get("language")
        voice_id = data.get("voiceId")
        locale = data.get("locale")

        print("\n========== REQUEST ==========")
        print("Place:", place)
        print("Answer type:", answer_type)
        print("Language:", language)
        print("Voice:", voice_id)
        print("Locale:", locale)

        if not place:
            return jsonify({"error": "Place is required"}), 400

        if answer_type not in PROMPTS:
            return jsonify({"error": "Invalid answerType"}), 400

        # Generate AI description
        text_description = generate_description(
            place,
            answer_type,
            language
        )

        print("Gemini description generated successfully.")

        # Generate audio
        audio_path = generate_speech(
            text=text_description,
            voice_id=voice_id,
            locale=locale
        )

        print("Murf audio generated successfully.")

        with open(audio_path.name, "rb") as f:
            audio_bytes = f.read()

        os.remove(audio_path.name)

        audio_base64 = base64.b64encode(
            audio_bytes
        ).decode("utf-8")

        return jsonify({
            "description": text_description,
            "audioBase64": audio_base64
        })

    except Exception as e:

        print("\n========== ERROR ==========")
        print(str(e))

        return jsonify({
            "error": str(e)
        }), 500


if __name__ == "__main__":
    app.run(
        host="0.0.0.0",
        port=int(os.environ.get("PORT", 5000)),
        debug=False
    )