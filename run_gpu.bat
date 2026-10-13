@echo off
cd /d D:\Project\ComfyUI
D:\Project\ComfyUI\.venv\Scripts\python.exe main.py --lowvram --reserve-vram 1.5 --fast fp16_accumulation --fp8_e4m3fn-text-enc --fp8_e5m2-unet --disable-async-offload --enable-manager
