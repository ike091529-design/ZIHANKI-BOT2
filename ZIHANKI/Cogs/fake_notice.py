import random
import asyncio
import discord
import discord.ui
from discord import app_commands
from discord.ext import commands, tasks

# ──── 設定変更用モーダル ────
class ConfigModal(discord.ui.Modal, title="実績送信データの設定変更"):
    product_name_input = discord.ui.TextInput(
        label="購入商品名",
        default="ぺいぺい2分の1で倍",
        required=True,
        max_length=100
    )
    win_msg_input = discord.ui.TextInput(
        label="当たりの時のテキスト",
        default="当たり",
        required=True,
        max_length=50
    )
    lose_msg_input = discord.ui.TextInput(
        label="ハズレの時のテキスト",
        default="ハズレ",
        required=True,
        max_length=50
    )

    def __init__(self, cog):
        super().__init__()
        self.cog = cog
        # 現在の設定値をデフォルト値に設定
        self.product_name_input.default = self.cog.product_name
        self.win_msg_input.default = self.cog.win_text
        self.lose_msg_input.default = self.cog.lose_text

    async def on_submit(self, interaction: discord.Interaction):
        self.cog.product_name = self.product_name_input.value
        self.cog.win_text = self.win_msg_input.value
        self.cog.lose_text = self.lose_msg_input.value
        await interaction.response.send_message("✅ 実績送信の設定を変更しました！", ephemeral=True)

# ──── 管理用パネル View ────
class ControlPanelView(discord.ui.View):
    def __init__(self, cog):
        super().__init__(timeout=None)
        self.cog = cog

    @discord.ui.button(label="⏹️ Stop", style=discord.ButtonStyle.danger, custom_id="fn_stop_btn")
    async def stop_loop(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not self.cog.send_notice_task.is_running():
            await interaction.response.send_message("⚠️ すでに停止しています。", ephemeral=True)
            return
        self.cog.send_notice_task.cancel()
        await interaction.response.send_message("🛑 20秒間隔の自動送信を停止しました。", ephemeral=True)

    @discord.ui.button(label="▶️ 再開", style=discord.ButtonStyle.success, custom_id="fn_start_btn")
    async def resume_loop(self, interaction: discord.Interaction, button: discord.ui.Button):
        if self.cog.send_notice_task.is_running():
            await interaction.response.send_message("⚠️ すでに稼働中です。", ephemeral=True)
            return
        if not self.cog.target_channel:
            await interaction.response.send_message("⚠️ 送信先チャンネルが設定されていません。", ephemeral=True)
            return
        self.cog.send_notice_task.start()
        await interaction.response.send_message("▶️ 自動送信を再開しました。", ephemeral=True)

    @discord.ui.button(label="⚙️ 情報変更", style=discord.ButtonStyle.secondary, custom_id="fn_config_btn")
    async def change_config(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(ConfigModal(self.cog))

    @discord.ui.select(
        cls=discord.ui.ChannelSelect,
        channel_types=[discord.ChannelType.text],
        placeholder="送信先チャンネルの変更...",
        custom_id="fn_channel_select"
    )
    async def select_channel(self, interaction: discord.Interaction, select: discord.ui.ChannelSelect):
        selected_channel = select.values[0]
        self.cog.target_channel = selected_channel
        await interaction.response.send_message(f"📢 送信先を {selected_channel.mention} に変更しました。", ephemeral=True)

# ──── Cog 本体 ────
class FakeNotice(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.target_channel = None
        self.target_guild = None
        
        # 可変データ
        self.product_name = "ぺいぺい2分の1で倍"
        self.win_text = "当たり"
        self.lose_text = "ハズレ"
        
        # 固定データ
        self.item_count = "1個"

    # 20秒おきの自動送信ループ
    @tasks.loop(seconds=20)
    async def send_notice_task(self):
        if not self.target_channel or not self.target_guild:
            return

        # サーバーメンバーからランダムに1人選出 (Bot除外)
        members = [m for m in self.target_guild.members if not m.bot]
        if not members:
            buyer_mention = "@匿名"
        else:
            buyer = random.choice(members)
            buyer_mention = buyer.mention

        # 当たり判定 (80% 当たり / 20% ハズレ)
        result_text = self.win_text if random.random() < 0.8 else self.lose_text

        # スクリーンショット通りのデザイン構築
        embed = discord.Embed(color=0x3498db)
        
        embed.add_field(name="購入商品名", value=f"` {self.product_name} `", inline=False)
        embed.add_field(name="購入数", value=f"` {self.item_count} `", inline=False)
        embed.add_field(name="購入サーバー", value=f"` {self.target_guild.name} `", inline=False)
        embed.add_field(name="購入者", value=buyer_mention, inline=False)
        embed.add_field(name="\u200b", value=result_text, inline=False) # ラベルなしで下部に表示

        try:
            await self.target_channel.send(content="📢📢**購入のお知らせ**📢📢", embed=embed)
        except Exception as e:
            print(f"実績メール送信エラー: {e}")

    @app_commands.command(name="bot_start", description="実績メールの20秒間隔自動送信を開始します")
    @app_commands.describe(
        category="カテゴリ指定",
        channel="実績メールを送信するチャンネル"
    )
    @app_commands.checks.has_permissions(administrator=True)
    async def bot_start(
        self,
        interaction: discord.Interaction,
        category: discord.CategoryChannel,
        channel: discord.TextChannel
    ):
        self.target_channel = channel
        self.target_guild = interaction.guild

        # タスク開始
        if self.send_notice_task.is_running():
            self.send_notice_task.restart()
        else:
            self.send_notice_task.start()

        # 実行した本人だけに表示される管理パネル（ephemeral=True）
        panel_embed = discord.Embed(
            title="🛠️ 実績自動送信 コントロールパネル",
            description=(
                f"**現在の設定:**\n"
                f"- **送信先:** {channel.mention} (カテゴリ: `{category.name}`)\n"
                f"- **商品名:** `{self.product_name}`\n"
                f"- **送信間隔:** 20秒\n\n"
                f"以下のボタン・メニューから各種設定を変更・停止できます。"
            ),
            color=discord.Color.gold()
        )

        await interaction.response.send_message(
            embed=panel_embed,
            view=ControlPanelView(self),
            ephemeral=True
        )

async def setup(bot):
    await bot.add_cog(FakeNotice(bot))
