import io
import os
import tempfile

import numpy as np
import speech_recognition as sr
import torch
from pydub import AudioSegment
from transformers import WhisperProcessor, WhisperForConditionalGeneration

processor = WhisperProcessor.from_pretrained("openai/whisper-large")
model = WhisperForConditionalGeneration.from_pretrained("openai/whisper-large")
BASE_DIR = "/tmp/asr_sessions"
os.makedirs(BASE_DIR, exist_ok=True)


def load_audio(file_obj, target_sr=16000):
    """Carga un archivo de audio con pydub y devuelve un tensor de PyTorch."""
    audio = AudioSegment.from_file(file_obj)
    audio = audio.set_frame_rate(target_sr).set_channels(1)
    samples = np.array(audio.get_array_of_samples()).astype(np.float32) / 32768.0
    return torch.tensor(samples).unsqueeze(0), target_sr


def convert_to_wav(file_obj):
    """Convierte cualquier archivo de audio a WAV PCM temporal."""
    audio = AudioSegment.from_file(file_obj)
    temp_wav = tempfile.NamedTemporaryFile(delete=False, suffix=".wav")
    audio.export(temp_wav.name, format="wav")
    return temp_wav.name


def transcribir_whisper(file_obj, target_sr=16000):
    """Transcribe un archivo de audio usando Whisper fine-tuned."""
    try:
        # Si es una ruta de archivo, abrir el archivo
        if isinstance(file_obj, str):
            with open(file_obj, 'rb') as f:
                audio = AudioSegment.from_file(f)
        else:
            audio = AudioSegment.from_file(file_obj)
        
        # Validar que el audio tenga duración mínima (al menos 1 segundo)
        if len(audio) < 1000:  # menos de 1 segundo
            return ""
            
        audio = audio.set_frame_rate(target_sr).set_channels(1)
        samples = np.array(audio.get_array_of_samples()).astype(np.float32) / 32768.0
        
        # Validar que tenemos samples suficientes
        if len(samples) < target_sr:  # menos de 1 segundo de audio
            return ""
        
        # Debug info
        print(f"[DEBUG] Audio duration: {len(audio)}ms, samples: {len(samples)}")
            
        inputs = processor(samples, sampling_rate=target_sr, return_tensors="pt")
        
        with torch.no_grad():
            # Configurar para español y mejorar parámetros
            pred_ids = model.generate(
                inputs.input_features,
                language="spanish",  # Forzar español
                task="transcribe",   # Tarea específica
                no_repeat_ngram_size=3,
                repetition_penalty=1.1,
                max_length=448,
                num_beams=5,  # Mejorar calidad
                early_stopping=True,
                forced_decoder_ids=processor.get_decoder_prompt_ids(language="spanish", task="transcribe")
            )
        
        result = processor.batch_decode(pred_ids, skip_special_tokens=True)[0]
        clean_result = result.strip()
        
        # Debug info
        print(f"[DEBUG] Whisper result: '{clean_result}'")
        
        # Filtrar resultados muy cortos o que claramente no son válidos
        if len(clean_result) < 2 or clean_result.lower() in ["you", ".", "", " "]:
            return ""
            
        return clean_result
        
    except Exception as e:
        print(f"Error en transcribir_whisper: {e}")
        import traceback
        traceback.print_exc()
        return ""


def session_dir(session_id):
    directory = os.path.join(BASE_DIR, session_id)
    os.makedirs(directory, exist_ok=True)
    return directory


def combined_audio_path(session_id, ext="webm"):
    return os.path.join(session_dir(session_id), f"combined.{ext}")


def combined_wav_path(session_id):
    """Ruta específica para el archivo WAV combinado (solo para Whisper)."""
    return os.path.join(session_dir(session_id), "combined.wav")


def save_chunk_file(session_id, part_index, file_obj):
    """Guarda el chunk recibido y acumula los bytes en combined.webm + crea WAV para Whisper."""
    if hasattr(file_obj, "chunks"):
        data = b"".join(file_obj.chunks())
    else:
        data = file_obj.read()
    if hasattr(file_obj, "seek"):
        try:
            file_obj.seek(0)
        except (OSError, io.UnsupportedOperation):
            pass
    if not data:
        raise ValueError("chunk vacio")

    directory = session_dir(session_id)
    
    # Guardar chunk individual
    ext = ".webm"
    filename = f"part_{int(part_index):04d}{ext}"
    chunk_path = os.path.join(directory, filename)
    with open(chunk_path, "wb") as handle:
        handle.write(data)

    # Mantener el archivo WebM combinado para SpeechRecognition (método original)
    combined_webm_path = combined_audio_path(session_id)
    mode = "ab" if os.path.exists(combined_webm_path) else "wb"
    with open(combined_webm_path, mode) as handle:
        handle.write(data)

    # ADICIONALMENTE: Crear/actualizar archivo WAV para Whisper
    try:
        new_segment = AudioSegment.from_file(io.BytesIO(data))
        wav_path = combined_wav_path(session_id)
        
        if os.path.exists(wav_path):
            existing_audio = AudioSegment.from_wav(wav_path)
            combined_audio = existing_audio + new_segment
        else:
            combined_audio = new_segment
        
        combined_audio.export(wav_path, format="wav")
    except Exception as e:
        print(f"Error creando WAV combinado: {e}")

    return chunk_path, combined_webm_path  # Devolver WebM para SpeechRecognition


def concat_session_to_wav(session_id, out_name=None, target_sr=16000):
    """Devuelve un WAV con todo el audio acumulado en la sesion."""
    directory = session_dir(session_id)
    
    # Primero intentar usar el archivo WAV combinado existente
    wav_path = combined_wav_path(session_id)
    if os.path.exists(wav_path) and os.path.getsize(wav_path) > 0:
        if out_name and out_name != wav_path:
            # Si se solicita un nombre específico, copiar
            audio = AudioSegment.from_wav(wav_path)
            audio = audio.set_frame_rate(target_sr).set_channels(1)
            audio.export(out_name, format="wav")
            return out_name
        return wav_path
    
    # Si no existe WAV, crear desde WebM combinado
    combined_webm = combined_audio_path(session_id)
    if os.path.exists(combined_webm) and os.path.getsize(combined_webm) > 0:
        try:
            source = AudioSegment.from_file(combined_webm)
        except Exception as e:
            print(f"Error leyendo combined.webm: {e}")
            source = None
    else:
        source = None
    
    # Si no se pudo leer el archivo combinado, concatenar desde chunks individuales
    if source is None:
        files = sorted(
            os.path.join(directory, name)
            for name in os.listdir(directory)
            if name.startswith("part_") and name.endswith(".webm")
        )
        if not files:
            raise FileNotFoundError("No hay partes para concatenar")
        
        source = None
        for path in files:
            try:
                segment = AudioSegment.from_file(path)
                source = segment if source is None else source + segment
            except Exception as e:
                print(f"Error leyendo chunk {path}: {e}")
                continue
        
        if source is None:
            raise FileNotFoundError("No se pudo crear audio desde los chunks")

    # Normalizar y exportar
    source = source.set_frame_rate(target_sr).set_channels(1)
    out_path = out_name or wav_path
    source.export(out_path, format="wav")
    return out_path


def transcribir_google(file_obj, language="es-ES"):
    """Transcribe audio usando la API de Google via SpeechRecognition."""
    cleanup = False
    wav_path = None
    try:
        if isinstance(file_obj, str) and file_obj.lower().endswith(".wav"):
            wav_path = file_obj
        else:
            wav_path = convert_to_wav(file_obj)
            cleanup = True
        
        # Validar que el archivo existe y tiene contenido
        if not os.path.exists(wav_path) or os.path.getsize(wav_path) == 0:
            return ""
            
        recognizer = sr.Recognizer()
        with sr.AudioFile(wav_path) as source:
            audio_data = recognizer.record(source)
        return recognizer.recognize_google(audio_data, language=language)
    except sr.UnknownValueError:
        return ""
    except sr.RequestError:
        return ""
    except Exception as e:
        print(f"Error en transcribir_google: {e}")
        return ""
    finally:
        if cleanup and wav_path and os.path.exists(wav_path):
            os.remove(wav_path)