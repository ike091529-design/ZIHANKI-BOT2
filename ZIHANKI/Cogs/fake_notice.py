import random
import asyncio
import discord
import discord.ui
from discord import app_commands
from discord.ext import commands, tasks

# ──── 情報変更モーダル ────
class ConfigModal(discord.ui.Modal, title="実績データの設定変更"):
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
        self.product_name_input.default = self.cog.product_name
        self.win_msg_input.default = self.cog.win_text
        self.lose_msg_input.default = self.cog.lose_text

    async def on_submit(self, interaction: discord.Interaction):
        self.cog.product_name = self.product_name_input.value
        self.cog.win_text = self.win_msg_input.value
        self.cog.lose_text = self.lose_msg_input.value
        
        await interaction.response.send_message("✅ 設定を変更しました！次回送信分から反映されます。", ephemeral=True)

# ──── 管理パネル View（本人限定） ────
class ControlPanelView(discord.ui.View):
    def __init__(self, cog, original_user_id: int):
        super().__init__(timeout=None)
        self.cog = cog
        self.original_user_id = original_user_id

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.original_user_id:
            await interaction.response.send_message("⚠️ この操作パネルを実行した本人しか操作できません。", ephemeral=True)
            return False
        return True

    @discord.ui.button(label="⏹️ Stop", style=discord.ButtonStyle.danger, custom_id="bot_panel_stop")
    async def stop_loop(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not self.cog.send_notice_task.is_running():
            await interaction.response.send_message("⚠️ すでに停止しています。", ephemeral=True)
            return
        self.cog.send_notice_task.cancel()
        await interaction.response.send_message("🛑 自動送信を停止しました。", ephemeral=True)

    @discord.ui.button(label="▶️ 再開", style=discord.ButtonStyle.success, custom_id="bot_panel_resume")
    async def resume_loop(self, interaction: discord.Interaction, button: discord.ui.Button):
        if self.cog.send_notice_task.is_running():
            await interaction.response.send_message("⚠️ すでに稼働中です。", ephemeral=True)
            return
        if not self.cog.target_channel:
            await interaction.response.send_message("⚠️ 送信先チャンネルが設定されていません。", ephemeral=True)
            return
        self.cog.send_notice_task.start()
        await interaction.response.send_message("▶️ 自動送信を再開しました。", ephemeral=True)

    @discord.ui.button(label="⚙️ 情報変更", style=discord.ButtonStyle.secondary, custom_id="bot_panel_config")
    async def change_config(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(ConfigModal(self.cog))

    @discord.ui.select(
        cls=discord.ui.ChannelSelect,
        channel_types=[discord.ChannelType.text],
        placeholder="送信先チャンネルを変更...",
        custom_id="bot_panel_channel_select"
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
        
        # 設定の初期値
        self.product_name = "ぺいぺい2分の1で倍"
        self.win_text = "当たり"
        self.lose_text = "ハズレ"
        self.item_count = "1個"

    def cog_unload(self):
        if self.send_notice_task.is_running():
            self.send_notice_task.cancel()

    # 20秒間隔の自動送信処理
    @tasks.loop(seconds=20)
    async def send_notice_task(self):
        if not self.target_channel or not self.target_guild:
            return

        try:
            # サーバーからメンバーを取得（Bot以外）
            members = [m for m in self.target_guild.members if not m.bot]
            if members:
                buyer_mention = random.choice(members).mention
            else:
                buyer_mention = "@匿名"

            # 80% 当たり / 20% ハズレ
            result_text = self.win_text if random.random() < 0.8 else self.lose_text

            # Embed デザインの構築
            embed = discord.Embed(color=0x3498db)
            embed.add_field(name="購入商品名", value=f"` {self.product_name} `", inline=False)
            embed.add_field(name="購入数", value=f"` {self.item_count} `", inline=False)
            embed.add_field(name="購入サーバー", value=f"` {self.target_guild.name} `", inline=False)
            embed.add_field(name="購入者", value=buyer_mention, inline=False)
            embed.add_field(name="\u200b", value=result_text, inline=False)

            await self.target_channel.send(content="📢📢**購入のお知らせ**📢📢", embed=embed)
        except Exception as e:
            print(f"[実績送信エラー]: {e}")

    # スラッシュコマンド `/bot`
    @app_commands.command(name="bot", description="実績メールの自動送信を開始・管理します")
    @app_commands.describe(
        category="カテゴリ指定",
        channel="実績メールを送信するチャンネル"
    )
    @app_commands.checks.has_permissions(administrator=True)
    async def run_bot_cmd(
        self,
        interaction: discord.Interaction,
        category: discord.CategoryChannel,
        channel: discord.TextChannel
    ):
        self.target_channel = channel
        self.target_guild = interaction.guild

        # 送信タスクを開始（動作中ならリスタート）
        if self.send_notice_task.is_running():
            self.send_notice_task.restart()
        else:
            self.send_notice_task.start()

        # コマンド実行した本人だけに表示される（ephemeral=True）管理パネル
        panel_embed = discord.Embed(
            title="🛠️ 実績自動送信 コントロールパネル",
            description=(
                f"**現在の設定:**\n"
                f"- **送信先:** {channel.mention} (カテゴリ: `{category.name}`)\n"
                f"- **商品名:** `{self.product_name}`\n"
                f"- **送信間隔:** 20秒\n\n"
                f"下のボタンやメニューから設定を変更・操作できます。"
            ),
            color=discord.Color.gold()
        )

        await interaction.response.send_message(
            embed=panel_embed,
            view=ControlPanelView(self, interaction.user.id),
            ephemeral=True
        )

async def setup(bot):
    await bot.add_cog(FakeNotice(bot))
