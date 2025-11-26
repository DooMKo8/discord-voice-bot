import PyInstaller.__main__
import os

# Ensure we are in the right directory
os.chdir(os.path.dirname(os.path.abspath(__file__)))

PyInstaller.__main__.run([
    'main.py',
    '--name=DiscordVoiceBot',
    '--onefile',
    '--clean',
    # Hidden imports that might be missed
    '--hidden-import=engineio.async_drivers.aiohttp',
    '--hidden-import=discord',
    '--hidden-import=edge_tts',
    '--hidden-import=yt_dlp',
    # Include Opus DLL
    '--add-data=libopus-0.dll;.',
    # Exclude unnecessary heavy modules if any (optional)
])
