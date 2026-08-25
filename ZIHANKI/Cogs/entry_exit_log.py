import json
import logging
import os
import urllib.request
import discord
from discord import app_commands
from discord.ext import commands

logger = logging.getLogger("discord")

# Gist上の保存用ファイル名
LOG_SETTING_FILE = "log_settings.json"


# ──── Gist 通信関数 ────
def load_from_gist(filename):
    gist_id = os.getenv("GIST_ID")
    github_token = os.getenv("GITHUB_TOKEN")
    if not gist_id or not github_token:
        return {}
    url = f"https://api.github.com/gists/{gist_id}"
    headers = {"Authorization": f"token {github_token}"}
    req = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(req) as response:
            result = json.loads(response.read().decode("utf-8"))
            if filename in result.get("files", {}):
                return json.loads(result["files"][filename]["content"])
            return {}
    except Exception as e:
        logger.error(f"Gist Load Error: {e}")
        return {}


def save_to_gist(filename, data):
    gist_id = os.getenv("GIST_ID")
    github_token = os.getenv("GITHUB_TOKEN")
    if not gist_id or not github_token:
        return False
    url = f"https://api.github.com/gists/{gist_id}"
    headers = {
        "Authorization": f"token {github_token}",
        "Accept": "application/vnd.github.v3+json",
    }
    payload = {
        "files": {
            filename: {"content": json.dumps(data, ensure_ascii=False, indent=4)}
        }
    }
    req = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers=headers,
        method="PATCH",
    )
    try:
        with urllib.request.urlopen(req) as response:
            return response.status == 200
    except Exception as e:
        logger.error(f"Gist Save Error: {e}")
        return False


# ──── Cog 本体 ────
class EntryExitLog(commands.Cog):

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.settings = load_from_gist(LOG_SETTING_FILE) or {}

    def save_settings(self):
        save_to_gist(LOG_SETTING_FILE, self.settings)

    @app_commands.command(
        name="出入りログ",
        description="メンバーの参加・退出ログを送信するチャンネルを設定します",
    )
    @app_commands.describe(channel="ログを送信するテキストチャンネル")
    @app_commands.checks.has_permissions(administrator=True)
    async def set_log_channel(
        self, interaction: discord.Interaction, channel: discord.TextChannel
    ):
        guild_id = str(interaction.guild_id)

        if guild_id not in self.settings:
            self.settings[guild_id] = {}

        self.settings[guild_id]["log_channel_id"] = channel.id
        self.save_settings()

        embed = discord.Embed(
            title="出入りログ設定完了",
            description=f"出入りログの送信先を {channel.mention} に設定しました！",
            color=discord.Color.green(),
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @set_log_channel.error
    async def set_log_channel_error(
        self, interaction: discord.Interaction, error: app_commands.AppCommandError
    ):
        if isinstance(error, app_commands.MissingPermissions):
            await interaction.response.send_message(
                "このコマンドを実行するには管理者権限が必要です。", ephemeral=True
            )

    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member):
        guild_id = str(member.guild.id)
        channel_id = self.settings.get(guild_id, {}).get("log_channel_id")

        if not channel_id:
            return

        channel = member.guild.get_channel(channel_id)
        if channel:
            embed = discord.Embed(
                title="📥 メンバー参加",
                description=f"{member.mention} (`{member.name}`) がサーバーに参加しました。",
                color=discord.Color.blue(),
            )
            embed.set_thumbnail(url=member.display_avatar.url)
            embed.set_footer(text=f"ID: {member.id}")
            await channel.send(embed=embed)

    @commands.Cog.listener()
    async def on_member_remove(self, member: discord.Member):
        guild_id = str(member.guild.id)
        channel_id = self.settings.get(guild_id, {}).get("log_channel_id")

        if not channel_id:
            return

        channel = member.guild.get_channel(channel_id)
        if channel:
            embed = discord.Embed(
                title="📤 メンバー脱退",
                description=f"**{member.name}** がサーバーから退出しました。",
                color=discord.Color.red(),
            )
            embed.set_thumbnail(url=member.display_avatar.url)
            embed.set_footer(text=f"ID: {member.id}")
            await channel.send(embed=embed)


async def setup(bot: commands.Bot):
    await bot.add_cog(EntryExitLog(bot))
