import discord


class MediaButtons(discord.ui.View):
    """A persistent-safe view containing only external media links."""

    def __init__(self, web_url: str):
        super().__init__(timeout=300)
        self.add_item(discord.ui.Button(label="Open in Jellyfin", url=web_url, emoji="▶️"))
