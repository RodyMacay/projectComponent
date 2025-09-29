from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView
from django.shortcuts import render
from django.utils.decorators import method_decorator
from django.views import View
from django.views.decorators.csrf import csrf_exempt
import os

from .utils import (
    concat_session_to_wav,
    save_chunk_file,
    transcribir_google,
    transcribir_whisper,
    combined_wav_path,
)


def _short_error(exc):
    message = str(exc).strip() or exc.__class__.__name__
    return message.splitlines()[0][:200]


class ASRWhisperView(APIView):
    """Endpoint JSON que transcribe usando el modelo Whisper fine-tuned."""

    def post(self, request, *args, **kwargs):
        audio_file = request.FILES["audio"]
        whisper_text = transcribir_whisper(audio_file)
        return Response({"model": "Whisper fine-tuned", "text": whisper_text})


class ASRSpeechRecognitionView(APIView):
    """Endpoint JSON que transcribe usando la libreria SpeechRecognition (Google)."""

    def post(self, request, *args, **kwargs):
        audio_file = request.FILES["audio"]
        sr_text = transcribir_google(audio_file)
        return Response({"model": "SpeechRecognition (Google API)", "text": sr_text})


class CompareASRView(APIView):
    """Endpoint JSON que devuelve las transcripciones de Whisper y SpeechRecognition."""

    def post(self, request, *args, **kwargs):
        audio_file = request.FILES["audio"]
        whisper_text = transcribir_whisper(audio_file)

        audio_file.seek(0)
        sr_text = transcribir_google(audio_file)

        return Response({"whisper": whisper_text, "speechrecognition": sr_text})


class UploadView(View):
    """Renderiza un formulario para subir audio y ver resultados de ambos modelos."""

    def get(self, request):
        return render(request, "asr/upload.html")

    def post(self, request):
        audio_file = request.FILES["audio"]
        whisper_text = transcribir_whisper(audio_file)

        audio_file.seek(0)
        sr_text = transcribir_google(audio_file)

        results = {"whisper": whisper_text, "speech": sr_text}
        return render(request, "asr/upload.html", {"results": results})


class RecordView(View):
    """Renderiza la pagina para grabar audio en tiempo real desde el navegador."""

    def get(self, request):
        return render(request, "asr/record.html")


class RealtimeChunkView(APIView):
    """Recibe chunks parciales, los acumula y devuelve transcripciones parciales."""

    @method_decorator(csrf_exempt)
    def dispatch(self, *args, **kwargs):
        return super().dispatch(*args, **kwargs)

    def post(self, request, *args, **kwargs):
        session_id = request.POST.get("session_id")
        part_index = request.POST.get("part_index", "0")
        audio_file = request.FILES.get("audio")

        if not session_id or not audio_file:
            return Response(
                {"error": "missing session_id or audio"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            chunk_path, combined_webm_path = save_chunk_file(session_id, part_index, audio_file)
        except Exception as exc:
            return Response(
                {"error": f"Error guardando chunk: {_short_error(exc)}"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

        partial = {"whisper": "", "speech": ""}
        errors = {}

        # Transcribir con Google Speech Recognition usando el WebM combinado
        try:
            if os.path.exists(combined_webm_path) and os.path.getsize(combined_webm_path) > 0:
                partial["speech"] = transcribir_google(combined_webm_path)
        except Exception as exc:
            errors["speech"] = _short_error(exc)

        # Transcribir con Whisper usando el WAV combinado (SOLO después del chunk 4 para tener audio suficiente)
        part_num = int(part_index)
        if part_num >= 4:  # Esperar al menos 4 chunks (6+ segundos de audio)
            try:
                wav_path = combined_wav_path(session_id)
                if os.path.exists(wav_path):
                    file_size = os.path.getsize(wav_path)
                    
                    # Verificar duración mínima del archivo
                    try:
                        from pydub import AudioSegment
                        audio_check = AudioSegment.from_wav(wav_path)
                        duration_ms = len(audio_check)
                        print(f"[DEBUG] Whisper chunk {part_num}: {file_size} bytes, {duration_ms}ms")
                        
                        # Solo procesar si tenemos al menos 3 segundos
                        if duration_ms >= 3000:
                            whisper_result = transcribir_whisper(wav_path)
                            if whisper_result:
                                partial["whisper"] = whisper_result
                                print(f"[DEBUG] Whisper chunk result: '{whisper_result}'")
                            else:
                                print("[DEBUG] Whisper devolvió resultado vacío")
                        else:
                            print(f"[DEBUG] Audio muy corto para Whisper: {duration_ms}ms")
                            
                    except Exception as e:
                        print(f"[DEBUG] Error verificando duración: {e}")
                        
                else:
                    print(f"[DEBUG] Archivo WAV no existe: {wav_path}")
            except Exception as exc:
                print(f"[DEBUG] Error en Whisper chunk: {exc}")
                errors["whisper"] = _short_error(exc)

        payload = {"ok": True, "saved": chunk_path, "partial": partial}
        if errors:
            payload["errors"] = errors

        return Response(payload)


class RealtimeFinalizeView(APIView):
    """Devuelve las transcripciones finales a partir del audio acumulado."""

    @method_decorator(csrf_exempt)
    def dispatch(self, *args, **kwargs):
        return super().dispatch(*args, **kwargs)

    def post(self, request, *args, **kwargs):
        session_id = request.data.get("session_id") or request.POST.get("session_id")
        if not session_id:
            return Response(
                {"error": "missing session_id"}, status=status.HTTP_400_BAD_REQUEST
            )

        # Crear/obtener archivo WAV final
        try:
            wav_path = concat_session_to_wav(session_id)
        except Exception as exc:
            return Response(
                {"error": f"Error creando archivo final: {_short_error(exc)}"}, 
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

        final = {"whisper": "", "speech": ""}
        errors = {}

        # Transcribir con Whisper
        try:
            if os.path.exists(wav_path) and os.path.getsize(wav_path) > 0:
                file_size = os.path.getsize(wav_path)
                print(f"[DEBUG] Procesando Whisper final, archivo: {file_size} bytes")
                
                whisper_result = transcribir_whisper(wav_path)
                if not whisper_result:
                    print("[DEBUG] Resultado Whisper final vacío, intentando fallback...")
                    from .utils import transcribir_whisper_fallback
                    whisper_result = transcribir_whisper_fallback(wav_path)
                
                final["whisper"] = whisper_result
                print(f"[DEBUG] Whisper final result: '{whisper_result}'")
            else:
                errors["whisper"] = "Archivo de audio vacío o no encontrado"
        except Exception as exc:
            print(f"[DEBUG] Error en Whisper final: {exc}")
            errors["whisper"] = _short_error(exc)

        # Transcribir con Google Speech Recognition
        try:
            if os.path.exists(wav_path) and os.path.getsize(wav_path) > 0:
                final["speech"] = transcribir_google(wav_path)
            else:
                errors["speech"] = "Archivo de audio vacío o no encontrado"
        except Exception as exc:
            errors["speech"] = _short_error(exc)

        payload = {"session_id": session_id, "final": final}
        if errors:
            payload["ok"] = False
            payload["errors"] = errors
        else:
            payload["ok"] = True

        return Response(payload)