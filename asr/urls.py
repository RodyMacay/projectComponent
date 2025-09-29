from django.urls import path

from asr.views import ASRSpeechRecognitionView, ASRWhisperView, CompareASRView, RecordView, UploadView, RealtimeChunkView, RealtimeFinalizeView

urlpatterns = [
    # Templates
    path("upload/", UploadView.as_view(), name="upload"),
    path("record/", RecordView.as_view(), name="record"),

    # APIs
    path("whisper/", ASRWhisperView.as_view(), name="api-whisper"),
    path("speechrec/", ASRSpeechRecognitionView.as_view(), name="api-speechrec"),
    path("compare/", CompareASRView.as_view(), name="api-compare"),
    
    path("realtime_chunk/", RealtimeChunkView.as_view(), name="api-realtime-chunk"),
    path("realtime_finalize/", RealtimeFinalizeView.as_view(), name="api-realtime-finalize"),
    
]
