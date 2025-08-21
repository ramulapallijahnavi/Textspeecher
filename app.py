from flask import Flask, render_template, request, jsonify, send_file
from gtts import gTTS
import speech_recognition as sr
from io import BytesIO
import tempfile
import os
import sys
import PyPDF2
import docx
from flask_cors import CORS
from pydub.utils import which
from pydub import AudioSegment
import logging

app = Flask(__name__)
CORS(app)

def find_ffmpeg():
    # Try to find ffmpeg executable on Windows with .exe extension
    ffmpeg_exec = "ffmpeg.exe" if sys.platform == "win32" else "ffmpeg"
    path = which(ffmpeg_exec)
    if path:
        return path
    # Fallback common Windows paths
    common_paths = [
        r"C:\\ffmpeg\\bin\\ffmpeg.exe",
        r"C:\\Program Files\\ffmpeg\\bin\\ffmpeg.exe",
        r"C:\\Program Files (x86)\\ffmpeg\\bin\\ffmpeg.exe"
    ]
    for p in common_paths:
        if os.path.isfile(p):
            return p
    return None

def find_ffprobe():
    # Try to find ffprobe executable on Windows with .exe extension
    ffprobe_exec = "ffprobe.exe" if sys.platform == "win32" else "ffprobe"
    path = which(ffprobe_exec)
    if path:
        return path
    # Fallback common Windows paths
    common_paths = [
        r"C:\\ffmpeg\\bin\\ffprobe.exe",
        r"C:\\Program Files\\ffmpeg\\bin\\ffprobe.exe",
        r"C:\\Program Files (x86)\\ffmpeg\\bin\\ffprobe.exe"
    ]
    for p in common_paths:
        if os.path.isfile(p):
            return p
    return None

ffmpeg_path = find_ffmpeg()
ffprobe_path = find_ffprobe()
if ffmpeg_path is None:
    app.logger.error("ffmpeg executable not found. Audio conversion will fail.")
else:
    app.logger.info(f"ffmpeg found at: {ffmpeg_path}")
    AudioSegment.converter = ffmpeg_path

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/tts', methods=['POST'])
def tts():
    try:
        text = request.json.get('text')
        app.logger.debug(f"Received text for TTS: {text}")
        if not text:
            return jsonify({'error': 'No text provided'}), 400
        tts = gTTS(text=text, lang='en')
        audio_fp = BytesIO()
        tts.write_to_fp(audio_fp)
        audio_fp.seek(0)
        return send_file(audio_fp, mimetype='audio/mpeg')
    except Exception as e:
        app.logger.error(f"Text to speech error: {str(e)}")
        return jsonify({'error': f'Text to speech error: {str(e)}'}), 500

@app.route('/stt', methods=['POST'])
def stt():
    if 'audio' not in request.files:
        return jsonify({'error': 'No audio file provided'}), 400
    audio_file = request.files['audio']
    recognizer = sr.Recognizer()
    import io
    import uuid
    from pydub import AudioSegment
    filename = audio_file.filename
    suffix = os.path.splitext(filename)[1] if filename else '.ogg'
    temp_filename = f"temp_audio_{uuid.uuid4().hex}.wav"
    temp_filepath = os.path.join(tempfile.gettempdir(), temp_filename)
    try:
        audio_bytes = audio_file.read()
        if not audio_bytes:
            app.logger.error("Uploaded audio file is empty")
            return jsonify({'error': 'Uploaded audio file is empty'}), 400
        try:
            audio_segment = AudioSegment.from_file(io.BytesIO(audio_bytes))
        except Exception as e:
            import traceback
            tb_str = traceback.format_exc()
            app.logger.error(f"pydub failed to load audio: {str(e)}\\nTraceback:\\n{tb_str}")
            return jsonify({'error': f'Audio conversion error: {str(e)}'}), 500

        # Convert audio to wav in memory
        wav_io = io.BytesIO()
        audio_segment.export(wav_io, format="wav")
        wav_io.seek(0)
        app.logger.debug("Audio converted to WAV in memory")

        with sr.AudioFile(wav_io) as source:
            audio_data = recognizer.record(source)
        text = recognizer.recognize_google(audio_data)
        return jsonify({'text': text})
    except Exception as e:
        app.logger.error(f"Error processing audio: {str(e)}")
        return jsonify({'error': f'Error processing audio: {str(e)}'}), 500

@app.route('/doc-to-speech', methods=['POST'])
def doc_to_speech():
    try:
        if 'document' not in request.files:
            app.logger.debug("No document file provided in request")
            return jsonify({'error': 'No document file provided'}), 400
        doc_file = request.files['document']
        filename = doc_file.filename.lower()
        app.logger.debug(f"Received document for conversion: {filename}")
        text = ''
        try:
            if filename.endswith('.pdf'):
                reader = PyPDF2.PdfReader(doc_file)
                for page in reader.pages:
                    text += page.extract_text() + '\n\n'
            elif filename.endswith('.docx'):
                doc = docx.Document(doc_file)
                for para in doc.paragraphs:
                    text += para.text + '\n\n'
            else:
                app.logger.debug("Unsupported file format")
                return jsonify({'error': 'Unsupported file format. Please upload PDF or DOCX.'}), 400
        except Exception as e:
            app.logger.error(f"Failed to extract text from document: {str(e)}")
            return jsonify({'error': 'Failed to extract text from document.'}), 500

        if not text.strip():
            app.logger.debug("No text found in document")
            return jsonify({'error': 'No text found in document.'}), 400

        max_length = 5000
        if len(text) > max_length:
            app.logger.debug(f"Text length {len(text)} exceeds max length {max_length}, trimming text")
            text = text[:max_length]

        app.logger.debug(f"Extracted text length after trimming: {len(text)}")
        tts = gTTS(text=text, lang='en')
        audio_fp = BytesIO()
        tts.write_to_fp(audio_fp)
        audio_fp.seek(0)
        return send_file(audio_fp, mimetype='audio/mpeg')
    except Exception as e:
        app.logger.error(f"Document to speech error: {str(e)}")
        return jsonify({'error': f'Document to speech error: {str(e)}'}), 500

if __name__ == '__main__':
    app.run(debug=True)
