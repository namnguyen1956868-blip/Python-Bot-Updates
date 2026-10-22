"""Official Discord bot listener, supports text, embeds and webhook posts."""
import os
import re
from urllib.parse import urlparse

URL_PATTERN = re.compile(r'https?://[^\s<>]+', re.IGNORECASE)


def listen(events, channel_id):
    token = os.environ.get('PYTHON_BOT_DISCORD_TOKEN', '').strip()
    if not token:
        events.put(('discord_state', 'Thiếu PYTHON_BOT_DISCORD_TOKEN. Xem README_DISCORD.txt'))
        return
    try:
        import discord
    except ImportError:
        events.put(('discord_state', 'Chưa cài discord.py: py -m pip install discord.py'))
        return

    intents = discord.Intents.default()
    intents.message_content = True
    client = discord.Client(intents=intents)

    @client.event
    async def on_ready():
        events.put(('discord_state', f'Đã kết nối: {client.user} | Kênh {channel_id}'))

    @client.event
    async def on_message(message):
        # Skip only OUR OWN messages, not messages from other notification bots.
        if client.user and message.author.id == client.user.id:
            return
        if str(message.channel.id) != channel_id:
            return
        parts = [message.content or '']
        for embed in message.embeds:
            if embed.url:
                parts.append(embed.url)
            if embed.title:
                parts.append(embed.title)
            if embed.description:
                parts.append(embed.description)
            for field in embed.fields:
                parts.extend((field.name or '', field.value or ''))
        unique = set()
        for found in URL_PATTERN.findall('\n'.join(parts)):
            url = found.rstrip('.,;:!?)\"\'')
            parsed = urlparse(url)
            if parsed.scheme in ('http', 'https') and parsed.hostname and url not in unique:
                unique.add(url)
                events.put(('discord_url', url, channel_id))
        events.put(('discord_signal', channel_id))

    try:
        events.put(('discord_state', 'Đang kết nối Discord...'))
        client.run(token, log_handler=None, reconnect=True)
    except Exception as exc:
        events.put(('discord_state', 'Lỗi Discord: ' + str(exc)[:180]))
