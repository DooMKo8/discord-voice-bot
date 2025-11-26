import discord
from discord.ext import commands
from discord import app_commands
from gtts import gTTS
import io
import os
import asyncio
import json
from dotenv import load_dotenv
import static_ffmpeg
import yt_dlp
import sys

# Ensure ffmpeg is available
static_ffmpeg.add_paths()

load_dotenv()

# Configure intents
intents = discord.Intents.default()
intents.message_content = True

bot = commands.Bot(command_prefix='!', intents=intents)

# --- Load Opus Library (Required for Voice) ---
if not discord.opus.is_loaded():
    try:
        opus_name = "libopus-0.dll"
        opus_path = opus_name
        
        # Check if running in PyInstaller
        if getattr(sys, 'frozen', False):
            # Look in the temporary folder first
            if hasattr(sys, '_MEIPASS'):
                temp_path = os.path.join(sys._MEIPASS, opus_name)
                if os.path.exists(temp_path):
                    opus_path = temp_path
            # Also check next to the executable
            else:
                 exe_path = os.path.join(os.path.dirname(sys.executable), opus_name)
                 if os.path.exists(exe_path):
                     opus_path = exe_path

        discord.opus.load_opus(opus_path)
        print(f"✅ Opus library loaded from: {opus_path}")
    except Exception as e:
        print(f"⚠️ Failed to load Opus library: {e}")
        # Fallback to system search


# Constants
ALLOWED_USERS_FILE = "allowed_users.json"
ADMIN_ID = os.getenv("ADMIN_ID")

# Store voice settings: guild_id -> voice_name
guild_settings = {}

# Store music queues: guild_id -> list of {'web_url': str, 'title': str}
music_queues = {}

# --- Persistence for Allowed Users ---
def load_allowed_users():
    if not os.path.exists(ALLOWED_USERS_FILE):
        return []
    try:
        with open(ALLOWED_USERS_FILE, 'r') as f:
            return json.load(f)
    except:
        return []

def save_allowed_users(users):
    with open(ALLOWED_USERS_FILE, 'w') as f:
        json.dump(users, f)

allowed_users = load_allowed_users()

# --- Access Control Check ---
def is_allowed(interaction: discord.Interaction) -> bool:
    if str(interaction.user.id) == ADMIN_ID:
        return True
    if interaction.user.id in allowed_users:
        return True
    return False

async def check_permissions(interaction: discord.Interaction) -> bool:
    if is_allowed(interaction):
        return True
    await interaction.response.send_message("⛔ **Доступ запрещен!** Только админ может разрешить вам пользоваться ботом.", ephemeral=True)
    return False

# Available voices (Native Russian + Multilingual)
VOICES = [
    # --- Native Russian ---
    app_commands.Choice(name="🇷🇺 Дмитрий (Native Male)", value="ru-RU-DmitryNeural"),
    app_commands.Choice(name="🇷🇺 Светлана (Native Female)", value="ru-RU-SvetlanaNeural"),
    app_commands.Choice(name="🇷🇺 Дарья (Native Female)", value="ru-RU-DariyaNeural"),
    
    # --- Multilingual Male (Speak Russian) ---
    app_commands.Choice(name="🇺🇸 Andrew (Multilingual Male)", value="en-US-AndrewMultilingualNeural"),
    app_commands.Choice(name="🇺🇸 Brian (Multilingual Male)", value="en-US-BrianMultilingualNeural"),
    app_commands.Choice(name="🇫🇷 Remy (Multilingual Male)", value="fr-FR-RemyMultilingualNeural"),
    app_commands.Choice(name="🇩🇪 Florian (Multilingual Male)", value="de-DE-FlorianMultilingualNeural"),
    app_commands.Choice(name="🇺🇸 Christopher (Multilingual Male)", value="en-US-ChristopherMultilingualNeural"),
    app_commands.Choice(name="🇺🇸 Eric (Multilingual Male)", value="en-US-EricMultilingualNeural"),
    app_commands.Choice(name="🇺🇸 Roger (Multilingual Male)", value="en-US-RogerMultilingualNeural"),
    app_commands.Choice(name="🇺🇸 Steffan (Multilingual Male)", value="en-US-SteffanMultilingualNeural"),
    app_commands.Choice(name="🇨🇳 Yunfan (Multilingual Male)", value="zh-CN-YunfanMultilingualNeural"),
    app_commands.Choice(name="🇨🇳 Yunxiao (Multilingual Male)", value="zh-CN-YunxiaoMultilingualNeural"),

    # --- Multilingual Female (Speak Russian) ---
    app_commands.Choice(name="🇺🇸 Ava (Multilingual Female)", value="en-US-AvaMultilingualNeural"),
    app_commands.Choice(name="🇺🇸 Emma (Multilingual Female)", value="en-US-EmmaMultilingualNeural"),
    app_commands.Choice(name="🇺🇸 Jenny (Multilingual Female)", value="en-US-JennyMultilingualNeural"),
    app_commands.Choice(name="🇫🇷 Vivienne (Multilingual Female)", value="fr-FR-VivienneMultilingualNeural"),
    app_commands.Choice(name="🇩🇪 Seraphina (Multilingual Female)", value="de-DE-SeraphinaMultilingualNeural"),
    app_commands.Choice(name="🇺🇸 Michelle (Multilingual Female)", value="en-US-MichelleMultilingualNeural"),
    app_commands.Choice(name="🇺🇸 Alyssa (Multilingual Female)", value="en-US-AlyssaMultilingualNeural"),
    app_commands.Choice(name="🇺🇸 Brianna (Multilingual Female)", value="en-US-BriannaMultilingualNeural"),
    app_commands.Choice(name="🇧🇷 Thalita (Multilingual Female)", value="pt-BR-ThalitaMultilingualNeural"),
    app_commands.Choice(name="🇨🇳 Xiaoxiao (Multilingual Female)", value="zh-CN-XiaoxiaoMultilingualNeural"),
]

# YT-DLP Options
YTDL_OPTIONS = {
    'format': 'bestaudio/best',
    'noplaylist': True, # We handle playlists manually
    'nocheckcertificate': True,
    'ignoreerrors': False,
    'logtostderr': False,
    'quiet': True,
    'no_warnings': True,
    'default_search': 'auto',
    'source_address': '0.0.0.0',
}

FFMPEG_OPTIONS = {
    'before_options': '-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5',
    'options': '-vn',
}

ytdl = yt_dlp.YoutubeDL(YTDL_OPTIONS)

class TTSAudioSource(discord.AudioSource):
    def __init__(self, mp3_bytes):
        self.mp3_bytes = mp3_bytes
        self.ffmpeg_process = None
        self.pcm_output = None

    def read(self):
        if self.pcm_output is None:
            args = [
                'ffmpeg',
                '-i', 'pipe:0',
                '-f', 's16le',
                '-ar', '48000',
                '-ac', '2',
                '-loglevel', 'quiet',
                'pipe:1'
            ]
            
            import subprocess
            self.ffmpeg_process = subprocess.Popen(
                args,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE
            )
            
            out, err = self.ffmpeg_process.communicate(input=self.mp3_bytes.getvalue())
            self.pcm_output = io.BytesIO(out)
        
        ret = self.pcm_output.read(3840)
        if len(ret) == 0:
            return b''
        return ret

    def cleanup(self):
        if self.ffmpeg_process:
            self.ffmpeg_process.kill()

# --- Music Queue Logic ---
async def play_next(interaction: discord.Interaction):
    guild_id = interaction.guild_id
    if guild_id in music_queues and music_queues[guild_id]:
        # Get next song info
        next_song = music_queues[guild_id].pop(0)
        web_url = next_song['web_url']
        title = next_song['title']
        
        voice_client = interaction.guild.voice_client
        if not voice_client:
            return

        print(f"Resolving stream for: {title}")
        
        try:
            # Resolve stream URL just-in-time
            loop = asyncio.get_event_loop()
            data = await loop.run_in_executor(None, lambda: ytdl.extract_info(web_url, download=False))
            
            if 'entries' in data:
                data = data['entries'][0]
                
            stream_url = data['url']
            
            source = discord.FFmpegPCMAudio(stream_url, **FFMPEG_OPTIONS)
            
            # Define callback to play next after this one finishes
            def after_playing(error):
                if error:
                    print(f"Error in playback: {error}")
                # Schedule next song
                coro = play_next(interaction)
                fut = asyncio.run_coroutine_threadsafe(coro, bot.loop)
                try:
                    fut.result()
                except:
                    pass

            voice_client.play(source, after=after_playing)
            print(f"Now playing: {title}")
            
        except Exception as e:
            print(f"Error playing {title}: {e}")
            # Skip to next if failed
            await play_next(interaction)
    else:
        # Queue empty
        pass

@bot.event
async def on_ready():
    print(f'Logged in as {bot.user} (ID: {bot.user.id})')
    try:
        synced = await bot.tree.sync()
        print(f'Synced {len(synced)} commands globally')
    except Exception as e:
        print(f'Failed to sync commands: {e}')
    print('------')

@bot.tree.command(name="setvoice", description="Выбрать голос озвучки (20+ вариантов)")
@app_commands.describe(voice="Выберите голос из списка")
@app_commands.choices(voice=VOICES)
async def setvoice(interaction: discord.Interaction, voice: app_commands.Choice[str]):
    if not await check_permissions(interaction): return

    guild_settings[interaction.guild_id] = voice.value
    await interaction.response.send_message(f"✅ Голос изменен на: **{voice.name}**", ephemeral=True)

@bot.tree.command(name="say", description="Озвучить текст в голосовом канале")
@app_commands.describe(text="Текст для озвучки")
async def say(interaction: discord.Interaction, text: str):
    if not await check_permissions(interaction): return

    if not interaction.user.voice:
        await interaction.response.send_message("Вы не в голосовом канале! ❌", ephemeral=True)
        return

    await interaction.response.defer(ephemeral=True)

    channel = interaction.user.voice.channel
    voice_client = interaction.guild.voice_client

    if voice_client:
        if voice_client.channel != channel:
            await voice_client.move_to(channel)
    else:
        voice_client = await channel.connect()

    try:
        # Debug: Check ffmpeg
        import shutil
        import traceback
        if not shutil.which("ffmpeg"):
            print("❌ CRITICAL: ffmpeg not found in PATH!")
            await interaction.followup.send("Ошибка: ffmpeg не найден в системе.", ephemeral=True)
            return

        # Get selected voice or default
        voice = guild_settings.get(interaction.guild_id, "ru-RU-DmitryNeural")
        
        print(f"🎤 Generating TTS with gTTS, text: '{text[:50]}...'")
        
        # Generate TTS with gTTS (Google Text-to-Speech)
        try:
            # gTTS uses language codes, not voice names
            lang = 'ru'  # Default to Russian
            
            # Create TTS in executor (gTTS is blocking)
            loop = asyncio.get_event_loop()
            
            def generate_tts():
                tts = gTTS(text=text, lang=lang, slow=False)
                fp = io.BytesIO()
                tts.write_to_fp(fp)
                fp.seek(0)
                return fp
            
            mp3_fp = await loop.run_in_executor(None, generate_tts)
            
            print(f"✅ Generated audio, size: {mp3_fp.tell()} bytes")
            
            if mp3_fp.tell() == 0:
                raise Exception("No audio data generated")
                
            mp3_fp.seek(0)
            
        except Exception as tts_error:
            print(f"❌ TTS Error: {tts_error}")
            traceback.print_exc()
            await interaction.followup.send(f"Ошибка генерации речи: {tts_error}", ephemeral=True)
            return
        
        source = TTSAudioSource(mp3_fp)
        
        if voice_client.is_playing():
            voice_client.stop()
            
        voice_client.play(source, after=lambda e: print(f'Player error: {e}') if e else None)
        await interaction.followup.send("✅ Озвучено", ephemeral=True)
        
    except Exception as e:
        traceback.print_exc()
        await interaction.followup.send(f"Ошибка ({type(e).__name__}): {e}", ephemeral=True)

@bot.tree.command(name="play", description="Включить музыку (YouTube, SoundCloud, Spotify плейлисты)")
@app_commands.describe(url="Ссылка на трек или плейлист")
async def play(interaction: discord.Interaction, url: str):
    if not await check_permissions(interaction): return

    if not interaction.user.voice:
        await interaction.response.send_message("Вы не в голосовом канале! ❌", ephemeral=True)
        return

    await interaction.response.defer(ephemeral=True)

    channel = interaction.user.voice.channel
    voice_client = interaction.guild.voice_client

    if voice_client:
        if voice_client.channel != channel:
            await voice_client.move_to(channel)
    else:
        voice_client = await channel.connect()

    try:
        loop = asyncio.get_event_loop()
        
        # Use extract_flat to get playlist items quickly without downloading
        # For Spotify, yt-dlp might not support it well directly, but let's try standard extraction first
        # If it's a playlist, 'entries' will be present
        ytdl_opts = {
            'extract_flat': 'in_playlist',
            'quiet': True,
            'default_search': 'auto',
            'ignoreerrors': True,
        }
        
        with yt_dlp.YoutubeDL(ytdl_opts) as ydl:
            data = await loop.run_in_executor(None, lambda: ydl.extract_info(url, download=False))

        if 'entries' in data:
            # It's a playlist
            entries = list(data['entries'])
            added_count = 0
            
            if interaction.guild_id not in music_queues:
                music_queues[interaction.guild_id] = []
                
            for entry in entries:
                if entry:
                    title = entry.get('title', 'Unknown Track')
                    web_url = entry.get('url')
                    # For some extractors, url might be missing or different, handle accordingly
                    if not web_url:
                        web_url = entry.get('webpage_url')
                    
                    if web_url:
                        music_queues[interaction.guild_id].append({'web_url': web_url, 'title': title})
                        added_count += 1
            
            await interaction.followup.send(f"📚 **Плейлист добавлен!** ({added_count} треков)", ephemeral=True)
            
        else:
            # Single track
            title = data.get('title', 'Unknown')
            web_url = data.get('webpage_url', url) # fallback to input url if needed
            
            if interaction.guild_id not in music_queues:
                music_queues[interaction.guild_id] = []
                
            music_queues[interaction.guild_id].append({'web_url': web_url, 'title': title})
            await interaction.followup.send(f"🎵 **Добавлено в очередь:** {title}", ephemeral=True)

        # If nothing is playing, start the queue
        if not voice_client.is_playing():
            await play_next(interaction)
        
    except Exception as e:
        await interaction.followup.send(f"Ошибка при обработке ссылки: {str(e)}", ephemeral=True)

@bot.tree.command(name="skip", description="Пропустить текущий трек")
async def skip(interaction: discord.Interaction):
    if not await check_permissions(interaction): return

    if interaction.guild.voice_client and interaction.guild.voice_client.is_playing():
        interaction.guild.voice_client.stop() # This triggers 'after' callback which calls play_next
        await interaction.response.send_message("⏭️ Трек пропущен.", ephemeral=True)
    else:
        await interaction.response.send_message("Сейчас ничего не играет.", ephemeral=True)

@bot.tree.command(name="queue", description="Показать очередь воспроизведения")
async def queue(interaction: discord.Interaction):
    if not await check_permissions(interaction): return
    
    q = music_queues.get(interaction.guild_id, [])
    
    if not q:
        await interaction.response.send_message("📂 Очередь пуста.", ephemeral=True)
        return
        
    embed = discord.Embed(title="📂 Музыкальная очередь", color=0x3498db)
    
    desc = ""
    for i, song in enumerate(q[:10], 1): # Show max 10
        desc += f"**{i}.** {song['title']}\n"
        
    if len(q) > 10:
        desc += f"\n*...и еще {len(q) - 10} треков*"
        
    embed.description = desc
    await interaction.response.send_message(embed=embed, ephemeral=True)

@bot.tree.command(name="stop", description="Остановить воспроизведение и очистить очередь")
async def stop(interaction: discord.Interaction):
    if not await check_permissions(interaction): return

    # Clear queue
    if interaction.guild_id in music_queues:
        music_queues[interaction.guild_id] = []

    if interaction.guild.voice_client and interaction.guild.voice_client.is_playing():
        interaction.guild.voice_client.stop()
        await interaction.response.send_message("⏹️ Остановлено и очередь очищена.", ephemeral=True)
    else:
        await interaction.response.send_message("Сейчас ничего не играет.", ephemeral=True)

@bot.tree.command(name="leave", description="Выгнать бота из голосового канала")
async def leave(interaction: discord.Interaction):
    if not await check_permissions(interaction): return

    if interaction.guild.voice_client:
        # Clear queue on leave
        if interaction.guild_id in music_queues:
            music_queues[interaction.guild_id] = []
            
        await interaction.guild.voice_client.disconnect()
        await interaction.response.send_message("Отключился. 👋")
    else:
        await interaction.response.send_message("Я не в канале.", ephemeral=True)

@bot.tree.command(name="help", description="Показать список команд и голосов")
async def help(interaction: discord.Interaction):
    if not await check_permissions(interaction): return

    embed = discord.Embed(title="🤖 VoiceBot Help", description="Я умею озвучивать текст и играть музыку!", color=0x3498db)
    
    embed.add_field(name="🗣️ Озвучка", value=(
        "`/say <текст>` - Озвучить текст\n"
        "`/setvoice` - Выбрать голос (20+ вариантов)"
    ), inline=False)

    embed.add_field(name="🎵 Музыка", value=(
        "`/play <url>` - Играть (или добавить в очередь)\n"
        "`/skip` - Пропустить трек\n"
        "`/queue` - Показать очередь\n"
        "`/stop` - Остановить и очистить"
    ), inline=False)
    
    embed.add_field(name="⚙️ Управление", value=(
        "`/leave` - Выгнать бота\n"
        "`/admin` - Управление доступом (Только Админ)"
    ), inline=False)
    
    embed.set_footer(text="Powered by Edge-TTS & YT-DLP")
    
    await interaction.response.send_message(embed=embed, ephemeral=True)

# --- Admin Commands ---
@bot.command(name="sync", help="Синхронизировать команды (Только Админ)")
async def sync_commands(ctx):
    if str(ctx.author.id) == ADMIN_ID:
        try:
            synced = await bot.tree.sync()
            await ctx.send(f"✅ Синхронизировано {len(synced)} команд глобально.")
        except Exception as e:
            await ctx.send(f"❌ Ошибка: {e}")
    else:
        await ctx.send("⛔ Доступ запрещен.")

admin_group = app_commands.Group(name="admin", description="Управление доступом к боту")
bot.tree.add_command(admin_group)

@admin_group.command(name="add", description="Добавить пользователя в белый список")
@app_commands.describe(user="Пользователь")
async def admin_add(interaction: discord.Interaction, user: discord.User):
    if str(interaction.user.id) != ADMIN_ID:
        await interaction.response.send_message("⛔ Вы не Админ!", ephemeral=True)
        return
    
    if user.id not in allowed_users:
        allowed_users.append(user.id)
        save_allowed_users(allowed_users)
        await interaction.response.send_message(f"✅ Пользователь {user.mention} добавлен в белый список.", ephemeral=True)
    else:
        await interaction.response.send_message(f"ℹ️ Пользователь {user.mention} уже в списке.", ephemeral=True)

@admin_group.command(name="remove", description="Удалить пользователя из белого списка")
@app_commands.describe(user="Пользователь")
async def admin_remove(interaction: discord.Interaction, user: discord.User):
    if str(interaction.user.id) != ADMIN_ID:
        await interaction.response.send_message("⛔ Вы не Админ!", ephemeral=True)
        return
    
    if user.id in allowed_users:
        allowed_users.remove(user.id)
        save_allowed_users(allowed_users)
        await interaction.response.send_message(f"✅ Пользователь {user.mention} удален из белого списка.", ephemeral=True)
    else:
        await interaction.response.send_message(f"ℹ️ Пользователя {user.mention} нет в списке.", ephemeral=True)

@admin_group.command(name="list", description="Показать белый список")
async def admin_list(interaction: discord.Interaction):
    if str(interaction.user.id) != ADMIN_ID:
        await interaction.response.send_message("⛔ Вы не Админ!", ephemeral=True)
        return
    
    if not allowed_users:
        await interaction.response.send_message("Список пуст (только Админ имеет доступ).", ephemeral=True)
        return
    
    # Format list
    msg = "**Белый список:**\n"
    for uid in allowed_users:
        msg += f"<@{uid}>\n"
    
    await interaction.response.send_message(msg, ephemeral=True)

# --- Keep-Alive Server for Render ---
from http.server import HTTPServer, BaseHTTPRequestHandler
import threading

class KeepAliveHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"Bot is running")

def run_server():
    port = int(os.getenv("PORT", 8080))
    server = HTTPServer(('0.0.0.0', port), KeepAliveHandler)
    print(f"Starting keep-alive server on port {port}")
    server.serve_forever()

def start_keep_alive():
    t = threading.Thread(target=run_server)
    t.daemon = True
    t.start()

if __name__ == "__main__":
    token = os.getenv("DISCORD_TOKEN")
    if not token:
        print("Error: DISCORD_TOKEN not found.")
    else:
        # Start the dummy web server for Render
        start_keep_alive()
        bot.run(token)
