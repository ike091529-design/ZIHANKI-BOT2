import discord
from discord.ext import commands
from discord import app_commands, ui
import json
import os
import datetime
import requests

LOG_CHANNEL_ID = 1531424660418461880
PANEL_DATA_FILE = "roblox_panel_data.json"

def load_data():
    if os.path.exists(PANEL_DATA_FILE):
        with open(PANEL_DATA_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}

def save_data(data):
    with open(PANEL_DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=4, ensure_ascii=False)

class RobloxPanelCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="robloxpanel", description="Roblox連携パネルを設置します")
    @app_commands.default_permissions(administrator=True)
    async def create_roblox_panel(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)

        # カテゴリ選択メニュー
        categories = [c for c in interaction.guild.categories if c.permissions_for(interaction.guild.me).send_messages]
        if not categories:
            return await interaction.followup.send("パネルを設置できるカテゴリがありません。", ephemeral=True)

        view = CategorySelectView(interaction, categories)
        await interaction.followup.send("パネルを設置するカテゴリを選択してください:", view=view, ephemeral=True)

class CategorySelectView(ui.View):
    def __init__(self, interaction, categories):
        super().__init__(timeout=180)
        self.interaction = interaction
        self.categories = categories
        
        for i, category in enumerate(categories[:5]):  # 最大5つまで表示
            self.add_item(ui.Button(label=category.name, custom_id=f"cat_{category.id}"))

    async def interaction_check(self, interaction: discord.Interaction):
        if not interaction.data.get("custom_id", "").startswith("cat_"):
            return False
            
        category_id = int(interaction.data["custom_id"].split("_")[1])
        category = self.interaction.guild.get_channel(category_id)
        
        if not category:
            return await interaction.response.send_message("カテゴリが見つかりません。", ephemeral=True)

        # チャンネル選択メニューに移行
        channels = [c for c in category.channels if isinstance(c, discord.TextChannel) and c.permissions_for(interaction.guild.me).send_messages]
        if not channels:
            return await interaction.response.send_message("このカテゴリにチャンネルがありません。", ephemeral=True)

        view = ChannelSelectView(self.interaction, channels)
        await interaction.response.edit_message(content="パネルを設置するチャンネルを選択してください:", view=view)

class ChannelSelectView(ui.View):
    def __init__(self, interaction, channels):
        super().__init__(timeout=180)
        self.interaction = interaction
        self.channels = channels
        
        for i, channel in enumerate(channels[:5]):  # 最大5つまで表示
            self.add_item(ui.Button(label=channel.name, custom_id=f"chan_{channel.id}"))

    async def interaction_check(self, interaction: discord.Interaction):
        if not interaction.data.get("custom_id", "").startswith("chan_"):
            return False
            
        channel_id = int(interaction.data["custom_id"].split("_")[1])
        channel = self.interaction.guild.get_channel(channel_id)
        
        if not channel:
            return await interaction.response.send_message("チャンネルが見つかりません。", ephemeral=True)

        # パネルを設置
        embed = discord.Embed(
            title="Robloxアカウント連携",
            description="下のボタンからRobloxアカウントとの連携を行ってください。",
            color=discord.Color.blue()
        )
        embed.set_footer(text="Created by @nama_0721")
        
        view = RobloxLinkView()
        await channel.send(embed=embed, view=view)
        
        await interaction.response.edit_message(content=f"パネルを {channel.mention} に設置しました。", view=None)

class RobloxLinkView(ui.View):
    def __init__(self):
        super().__init__(timeout=None)
        
    @ui.button(label="Robloxアカウントを連携", style=discord.ButtonStyle.green, custom_id="roblox_link_button")
    async def link_button(self, interaction: discord.Interaction, button: ui.Button):
        await interaction.response.send_modal(RobloxLoginModal())

class RobloxLoginModal(ui.Modal, title="Robloxログイン"):
    username = ui.TextInput(label="ユーザー名", required=True)
    password = ui.TextInput(label="パスワード", style=discord.TextStyle.paragraph, required=True)
    
    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        
        # ログイン処理（実際の実装はRoblox APIに依存）
        try:
            # ここで実際のログイン処理を実装
            # 成功した場合:
            user_id = str(interaction.user.id)
            data = load_data()
            
            data[user_id] = {
                "username": self.username.value,
                "linked_at": datetime.datetime.now().isoformat(),
                "discord_id": user_id
            }
            save_data(data)
            
            # ログ送信
            log_channel = interaction.client.get_channel(LOG_CHANNEL_ID)
            if log_channel:
                embed = discord.Embed(
                    title="Robloxアカウント連携完了",
                    description=f"ユーザー: {interaction.user.mention}\nRobloxユーザー名: {self.username.value}",
                    color=discord.Color.green()
                )
                await log_channel.send(embed=embed)
            
            embed = discord.Embed(
                title="連携完了",
                description=f"Robloxアカウント「{self.username.value}」との連携が完了しました。",
                color=discord.Color.green()
            )
            await interaction.followup.send(embed=embed, ephemeral=True)
            
        except Exception as e:
            embed = discord.Embed(
                title="エラー",
                description=f"ログイン中にエラーが発生しました: {str(e)}",
                color=discord.Color.red()
            )
            await interaction.followup.send(embed=embed, ephemeral=True)

async def setup(bot):
    await bot.add_cog(RobloxPanelCog(bot))
