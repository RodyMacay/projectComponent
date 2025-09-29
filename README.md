# Proyecto ASR con Whisper

Este proyecto implementa un sistema de **Reconocimiento Automático del Habla (ASR)** utilizando **Whisper** de Hugging Face, ajustado para español.

---

## 📂 Estructura del repositorio

- `app/` → Código fuente del proyecto (Django / API / scripts de entrenamiento).
- `notebooks/` → Experimentos y pruebas.
- `requirements.txt` → Dependencias necesarias.
- `README.md` → Este documento.

⚠️ **Nota importante:**  
El modelo entrenado **no está incluido en este repositorio** porque excede el límite de GitHub (100 MB).  

---

## 🔗 Descargar el modelo

El modelo se encuentra disponible en Google Drive en el siguiente enlace:  

👉 [Descargar modelo desde Google Drive](https://drive.google.com/drive/folders/1cUVf9HYi13Y2XrJ1ORcNd0xbiQ6_3zKB?usp=sharing)

Dentro encontrarás la carpeta `whisper-asr-model-V2` con los archivos:

- `config.json`  
- `pytorch_model.bin` / `model.safetensors`  
- `tokenizer.json`  
- Otros archivos de configuración del modelo.

---

## 🚀 Cómo usar el modelo

1. Descarga la carpeta completa desde Google Drive.  
2. Colócala en la raíz del proyecto, quedando así:

