from setuptools import setup, find_packages

setup(
    name="MyWhisper",
    version="1.0.0",
    description="Local voice-to-text for Windows using OpenAI Whisper",
    author="MyWhisper",
    packages=find_packages(),
    python_requires=">=3.10",
    install_requires=[
        "faster-whisper>=1.0.3",
        "PyQt6>=6.6.0",
        "sounddevice>=0.4.6",
        "numpy>=1.24.0",
        "pynput>=1.7.6",
        "pyperclip>=1.8.2",
        "pyautogui>=0.9.54",
    ],
    entry_points={
        "console_scripts": [
            "mywhisper=src.main:main",
        ],
    },
)
