import os
import discord
from discord import app_commands
from discord.ext import commands
import logging
from utils import load_from_gist, save_to_gist

logger = logging.getLogger('discord')

# Gist上の保存用ファイル名
LOG_SETTING_FILE = "log_settings.json"

class EntryExitLog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        # 起動時にGistから設定データを読み込む
        self.settings = load_from_gist(LOG_SETTING_FILE) or {}

    def save_settings(self):
        """設定をGistへ保存"""
        save_to_gist(LOG_SETTING_FILE, self.settings)

    # ──────────────────────────────────────────
    # /出入りログ コマンド（管理権限が必要）
    # ──────────────────────────────────────────
    @app_commands.command(name="出入りログ", description="メンバーの参加・退出ログを送信するチャンネルを設定します")
    @app_commands.describe(channel="ログを送信するテキストチャンネル")
    @app_commands.checks.has_permissions(administrator=True)
    async def set_log_channel(self, interaction: discord.Interaction, channel: discord.TextChannel):
        guild_id = str(interaction.guild_id)
        
        # ギルドごとの設定を更新
        if guild_id not in self.settings:
            self.settings[guild_id] = {}
        
        self.settings[guild_id]["log_channel_id"] = channel.id
        self.save_settings()

        embed = discord.Embed(
            title="出入りログ設定完了",
            description=f"出入りログの送信先を {channel.mention} に設定しました！",
            color=discord.Color.green()
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @set_log_channel.error
    async def set_log_channel_error(self, interaction: discord.Interaction, error: app_commands.AppCommandError):
        if isinstance(error, app_commands.MissingPermissions):
            await interaction.response.send_message("このコマンドを実行するには管理者権限が必要です。", ephemeral=True)

    # ──────────────────────────────────────────
    # 参加イベント (On Member Join)
    # ──────────────────────────────────────────
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
                color=discord.Color.blue()
            )
            embed.set_thumbnail(url=member.display_avatar.url)
            embed.set_footer(text=f"ID: {member.id}")
            await channel.send(embed=embed)

    # ──────────────────────────────────────────
    # 退出イベント (On Member Remove)
    # ──────────────────────────────────────────
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
                color=discord.Color.red()
            )
            embed.set_thumbnail(url=member.display_avatar.url)
            embed.set_footer(text=f"ID: {member.id}")
            await channel.send(embed=embed)

async def setup(bot: commands.Bot):
    await bot.add_cog(EntryExitLog(bot))
