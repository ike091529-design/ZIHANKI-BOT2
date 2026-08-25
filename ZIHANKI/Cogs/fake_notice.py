import json
import logging
import os
import random
import urllib.request
import discord
from discord import app_commands
from discord.ext import commands, tasks

logger = logging.getLogger("discord")
DATA_FILE = "fake_notice_settings.json"


# ──── Gist データ通信 ────
def load_from_gist():
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
            if DATA_FILE in result.get("files", {}):
                return json.loads(result["files"][DATA_FILE]["content"])
            return {}
    except Exception as e:
        logger.error(f"Gist Load Error (FakeNotice): {e}")
        return {}


def save_to_gist(data):
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
            DATA_FILE: {"content": json.dumps(data, ensure_ascii=False, indent=4)}
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
        logger.error(f"Gist Save Error (FakeNotice): {e}")
        return False


# ──── モーダル1: 基本設定 ────
class BasicConfigModal(discord.ui.Modal, title="基本動作設定"):
    interval_input = discord.ui.TextInput(
        label="送信間隔（秒）", placeholder="例: 20", required=True, max_length=5
    )
    win_rate_input = discord.ui.TextInput(
        label="当たり確率（%）",
        placeholder="例: 80 (0〜100の数値)",
        required=True,
        max_length=3,
    )

    def __init__(self, cog):
        super().__init__()
        self.cog = cog
        self.interval_input.default = str(self.cog.interval_seconds)
        self.win_rate_input.default = str(self.cog.win_rate)

    async def on_submit(self, interaction: discord.Interaction):
        try:
            interval = int(self.interval_input.value)
            win_rate = float(self.win_rate_input.value)
            if interval < 5 or not (0 <= win_rate <= 100):
                raise ValueError()
        except ValueError:
            await interaction.response.send_message(
                "⚠️ 間隔は5秒以上の整数、確率は0〜100の数値で指定してください。",
                ephemeral=True,
            )
            return

        self.cog.interval_seconds = interval
        self.cog.win_rate = win_rate
        self.cog.save_settings()
        self.cog.restart_task()

        await interaction.response.send_message(
            f"✅ 基本設定を変更しました！\n- 送信間隔: **{interval}秒**\n- 当たり確率: **{win_rate}%**",
            ephemeral=True,
        )


# ──── モーダル2: 固定モード設定 ────
class FixedConfigModal(discord.ui.Modal, title="固定モード用の商品設定"):
    product_name_input = discord.ui.TextInput(
        label="固定商品名", required=True, max_length=100
    )
    win_msg_input = discord.ui.TextInput(
        label="当たりの時のテキスト", required=True, max_length=50
    )
    lose_msg_input = discord.ui.TextInput(
        label="ハズレの時のテキスト", required=True, max_length=50
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
        self.cog.save_settings()

        await interaction.response.send_message(
            f"✅ 固定モード用の設定を変更しました！\n- 商品名: `{self.cog.product_name}`",
            ephemeral=True,
        )


# ──── モーダル3: 商品追加 ────
class AddProductModal(discord.ui.Modal, title="新しい商品を登録"):
    name_input = discord.ui.TextInput(
        label="商品名", placeholder="例: 高級寿司セット", required=True, max_length=100
    )
    win_msg_input = discord.ui.TextInput(
        label="当たりの時のテキスト", default="当たり", required=True, max_length=50
    )
    lose_msg_input = discord.ui.TextInput(
        label="ハズレの時のテキスト", default="ハズレ", required=True, max_length=50
    )

    def __init__(self, cog):
        super().__init__()
        self.cog = cog

    async def on_submit(self, interaction: discord.Interaction):
        new_prod = {
            "name": self.name_input.value,
            "win_text": self.win_msg_input.value,
            "lose_text": self.lose_msg_input.value,
        }
        self.cog.products.append(new_prod)
        self.cog.save_settings()
        await interaction.response.send_message(
            f"✅ 商品 **`{self.name_input.value}`** を追加しました！", ephemeral=True
        )


# ──── View: 商品削除 ────
class ProductDeleteView(discord.ui.View):

    def __init__(self, cog):
        super().__init__(timeout=60)
        self.cog = cog

        options = [
            discord.SelectOption(label=p["name"][:100], value=str(idx))
            for idx, p in enumerate(self.cog.products)
        ]

        if options:
            select = discord.ui.Select(
                placeholder="削除する商品を選択...", options=options[:25]
            )
            select.callback = self.select_callback
            self.add_item(select)

    async def select_callback(self, interaction: discord.Interaction):
        idx = int(interaction.data["values"][0])
        if 0 <= idx < len(self.cog.products):
            removed = self.cog.products.pop(idx)
            self.cog.save_settings()
            await interaction.response.send_message(
                f"🗑️ **`{removed['name']}`** を削除しました。", ephemeral=True
            )
        else:
            await interaction.response.send_message(
                "⚠️ エラーが発生しました。", ephemeral=True
            )


# ──── View: コントロールパネル ────
class ControlPanelView(discord.ui.View):

    def __init__(self, cog, original_user_id: int):
        super().__init__(timeout=None)
        self.cog = cog
        self.original_user_id = original_user_id

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.original_user_id:
            await interaction.response.send_message(
                "⚠️ この操作パネルを実行した本人しか操作できません。", ephemeral=True
            )
            return False
        return True

    @discord.ui.button(
        label="⏹️ Stop",
        style=discord.ButtonStyle.danger,
        custom_id="bot_panel_stop",
        row=0,
    )
    async def stop_loop(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ):
        if not self.cog.send_notice_task.is_running():
            await interaction.response.send_message(
                "⚠️ すでに停止しています。", ephemeral=True
            )
            return
        self.cog.send_notice_task.cancel()
        await interaction.response.send_message(
            "🛑 自動送信を停止しました。", ephemeral=True
        )

    @discord.ui.button(
        label="▶️ 再開",
        style=discord.ButtonStyle.success,
        custom_id="bot_panel_resume",
        row=0,
    )
    async def resume_loop(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ):
        if self.cog.send_notice_task.is_running():
            await interaction.response.send_message(
                "⚠️ すでに稼働中です。", ephemeral=True
            )
            return
        if not self.cog.target_channel_id:
            await interaction.response.send_message(
                "⚠️ 送信先チャンネルが設定されていません。", ephemeral=True
            )
            return
        self.cog.restart_task()
        await interaction.response.send_message(
            "▶️ 自動送信を再開しました。", ephemeral=True
        )

    @discord.ui.button(
        label="⚙️ 基本設定",
        style=discord.ButtonStyle.secondary,
        custom_id="bot_panel_basic_config",
        row=0,
    )
    async def change_basic_config(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ):
        await interaction.response.send_modal(BasicConfigModal(self.cog))

    @discord.ui.button(
        label="📝 固定商品設定",
        style=discord.ButtonStyle.secondary,
        custom_id="bot_panel_fixed_config",
        row=0,
    )
    async def change_fixed_config(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ):
        await interaction.response.send_modal(FixedConfigModal(self.cog))

    @discord.ui.button(
        label="🔀 モード切替",
        style=discord.ButtonStyle.primary,
        custom_id="bot_panel_mode",
        row=1,
    )
    async def toggle_mode(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ):
        if self.cog.mode == "random":
            self.cog.mode = "fixed"
            mode_text = "固定モード (指定の単一商品を送信)"
        else:
            self.cog.mode = "random"
            mode_text = "ランダムモード (登録商品からランダム送信)"

        self.cog.save_settings()
        await interaction.response.send_message(
            f"🔄 **{mode_text}** に切り替えました。", ephemeral=True
        )

    @discord.ui.button(
        label="📦 商品追加",
        style=discord.ButtonStyle.success,
        custom_id="bot_panel_add_prod",
        row=1,
    )
    async def add_product(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ):
        await interaction.response.send_modal(AddProductModal(self.cog))

    @discord.ui.button(
        label="🗑️ 商品削除",
        style=discord.ButtonStyle.danger,
        custom_id="bot_panel_del_prod",
        row=1,
    )
    async def delete_product(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ):
        if not self.cog.products:
            await interaction.response.send_message(
                "⚠️ 登録されている商品がありません。", ephemeral=True
            )
            return
        await interaction.response.send_message(
            "削除したい商品を選択してください:",
            view=ProductDeleteView(self.cog),
            ephemeral=True,
        )

    @discord.ui.select(
        cls=discord.ui.ChannelSelect,
        channel_types=[discord.ChannelType.text],
        placeholder="送信先チャンネルを変更...",
        custom_id="bot_panel_channel_select",
        row=2,
    )
    async def select_channel(
        self, interaction: discord.Interaction, select: discord.ui.ChannelSelect
    ):
        selected_channel = select.values[0]
        self.cog.target_channel_id = selected_channel.id
        self.cog.target_guild_id = interaction.guild_id
        self.cog.save_settings()
        await interaction.response.send_message(
            f"📢 送信先を {selected_channel.mention} に変更しました。", ephemeral=True
        )


# ──── Cog 本体 ────
class FakeNotice(commands.Cog):

    def __init__(self, bot):
        self.bot = bot
        self.target_channel_id = None
        self.target_guild_id = None

        # 初期値
        self.interval_seconds = 20
        self.win_rate = 80.0
        self.mode = "random"
        self.product_name = "ぺいぺい2分の1で倍"
        self.win_text = "当たり"
        self.lose_text = "ハズレ"
        self.item_count = "1個"
        self.products = [
            {"name": "ぺいぺい2分の1で倍", "win_text": "当たり", "lose_text": "ハズレ"},
            {
                "name": "限定ロール権限",
                "win_text": "当選！",
                "lose_text": "残念！次もチャレンジ！",
            },
            {
                "name": "アマギフ1,000円分",
                "win_text": "アタリ！コード送信完了",
                "lose_text": "ハズレ",
            },
        ]

        # Gistから設定読み込み
        saved_data = load_from_gist()
        if saved_data:
            self.target_channel_id = saved_data.get("target_channel_id")
            self.target_guild_id = saved_data.get("target_guild_id")
            self.interval_seconds = saved_data.get("interval_seconds", 20)
            self.win_rate = saved_data.get("win_rate", 80.0)
            self.mode = saved_data.get("mode", "random")
            self.product_name = saved_data.get("product_name", "ぺいぺい2分の1で倍")
            self.win_text = saved_data.get("win_text", "当たり")
            self.lose_text = saved_data.get("lose_text", "ハズレ")
            self.products = saved_data.get("products", self.products)

    def save_settings(self):
        data = {
            "target_channel_id": self.target_channel_id,
            "target_guild_id": self.target_guild_id,
            "interval_seconds": self.interval_seconds,
            "win_rate": self.win_rate,
            "mode": self.mode,
            "product_name": self.product_name,
            "win_text": self.win_text,
            "lose_text": self.lose_text,
            "products": self.products,
        }
        save_to_gist(data)

    def cog_unload(self):
        if self.send_notice_task.is_running():
            self.send_notice_task.cancel()

    def restart_task(self):
        if self.send_notice_task.is_running():
            self.send_notice_task.cancel()

        self.send_notice_task.change_interval(seconds=self.interval_seconds)
        self.send_notice_task.start()

    @tasks.loop(seconds=20)
    async def send_notice_task(self):
        if not self.target_channel_id or not self.target_guild_id:
            return

        guild = self.bot.get_guild(self.target_guild_id)
        if not guild:
            return

        channel = guild.get_channel(self.target_channel_id)
        if not channel:
            return

        try:
            members = [m for m in guild.members if not m.bot]
            buyer_mention = random.choice(members).mention if members else "@匿名"

            if self.mode == "random" and self.products:
                selected_prod = random.choice(self.products)
                prod_name = selected_prod["name"]
                win_txt = selected_prod["win_text"]
                lose_txt = selected_prod["lose_text"]
            else:
                prod_name = self.product_name
                win_txt = self.win_text
                lose_txt = self.lose_text

            is_win = random.uniform(0, 100) < self.win_rate
            result_text = win_txt if is_win else lose_txt

            embed = discord.Embed(color=0x3498db)
            embed.add_field(
                name="購入商品名", value=f"` {prod_name} `", inline=False
            )
            embed.add_field(
                name="購入数", value=f"` {self.item_count} `", inline=False
            )
            embed.add_field(
                name="購入サーバー", value=f"` {guild.name} `", inline=False
            )
            embed.add_field(name="購入者", value=buyer_mention, inline=False)
            embed.add_field(name="\u200b", value=result_text, inline=False)

            await channel.send(
                content="📢📢**購入のお知らせ**📢📢", embed=embed
            )
        except Exception as e:
            logger.error(f"[実績送信エラー]: {e}")

    @app_commands.command(
        name="bot", description="実績メールの自動送信を開始・管理します"
    )
    @app_commands.describe(
        category="カテゴリ指定", channel="実績メールを送信するチャンネル"
    )
    @app_commands.checks.has_permissions(administrator=True)
    async def run_bot_cmd(
        self,
        interaction: discord.Interaction,
        category: discord.CategoryChannel,
        channel: discord.TextChannel,
    ):
        self.target_channel_id = channel.id
        self.target_guild_id = interaction.guild_id
        self.save_settings()

        self.restart_task()

        panel_embed = discord.Embed(
            title="🛠️ 実績自動送信 コントロールパネル",
            description=(
                f"**現在の設定:**\n"
                f"- **送信先:** {channel.mention} (カテゴリ: `{category.name}`)\n"
                f"- **現在のモード:** `{self.mode.upper()}`\n"
                f"- **送信間隔:** `{self.interval_seconds}` 秒\n"
                f"- **当たり確率:** `{self.win_rate}` %\n"
                f"- **登録済み商品数:** `{len(self.products)}` 個\n\n"
                f"下のボタンやメニューから設定変更・商品の管理が行えます。"
            ),
            color=discord.Color.gold(),
        )

        await interaction.response.send_message(
            embed=panel_embed,
            view=ControlPanelView(self, interaction.user.id),
            ephemeral=True,
        )


async def setup(bot):
    await bot.add_cog(FakeNotice(bot))
