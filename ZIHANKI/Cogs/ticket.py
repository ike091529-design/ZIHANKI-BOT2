import discord
from discord import app_commands
from discord.ext import commands

# ──── 要件入力用モーダル ────
class TicketReasonModal(discord.ui.Modal, title="チケット作成 - 要件入力"):
    reason_input = discord.ui.TextInput(
        label="お問い合わせ・要件",
        style=discord.TextStyle.paragraph,
        placeholder="お問い合わせ内容やご要件を詳しくご記入ください。",
        required=True,
        max_length=1000
    )

    def __init__(self, target_category: discord.CategoryChannel):
        super().__init__()
        self.target_category = target_category

    async def on_submit(self, interaction: discord.Interaction):
        guild = interaction.guild
        user = interaction.user

        # 👑Owner ロールを取得
        owner_role = discord.utils.get(guild.roles, name="👑Owner")

        # パーミッション（権限）の構築
        overwrites = {
            guild.default_role: discord.PermissionOverwrite(read_messages=False), # 全員非表示
            user: discord.PermissionOverwrite(read_messages=True, send_messages=True, attach_files=True), # 作成者のみ表示
            guild.me: discord.PermissionOverwrite(read_messages=True, send_messages=True, manage_channels=True) # Bot自身
        }

        # 👑Owner ロールが存在する場合は閲覧権限を追加
        if owner_role:
            overwrites[owner_role] = discord.PermissionOverwrite(read_messages=True, send_messages=True, attach_files=True)

        # チケットチャンネルの作成
        channel_name = f"ticket-{user.name}"
        ticket_channel = await guild.create_text_channel(
            name=channel_name,
            category=self.target_category,
            overwrites=overwrites,
            topic=f"作成者: {user.mention} (ID: {user.id})"
        )

        # 案内メッセージの埋め込みを作成
        embed = discord.Embed(
            title="🎟️ チケットが作成されました",
            description=f"{user.mention} 様、お問い合わせありがとうございます。\nスタッフからの返信をお待ちください。",
            color=discord.Color.green()
        )
        embed.add_field(name="📌 ご要件", value=self.reason_input.value, inline=False)
        if not owner_role:
            embed.add_field(name="⚠️ 注意", value="`👑Owner` ロールが見つからなかったため、作成者とBotのみ閲覧可能です。", inline=False)

        # チケット操作View（閉じるボタン）を送信
        await ticket_channel.send(content=f"{user.mention} {owner_role.mention if owner_role else ''}", embed=embed, view=TicketControlView())

        # モーダル送信者への完了通知
        await interaction.response.send_message(f"チケットを作成しました: {ticket_channel.mention}", ephemeral=True)

# ──── チケット作成パネル用 View ────
class TicketCreateView(discord.ui.View):
    def __init__(self, target_category: discord.CategoryChannel):
        super().__init__(timeout=None)
        self.target_category = target_category

    @discord.ui.button(label="🎟️ チケットを作成する", style=discord.ButtonStyle.primary, custom_id="ticket_create_btn")
    async def create_ticket(self, interaction: discord.Interaction, button: discord.ui.Button):
        # モーダルを表示して要件を入力させる
        await interaction.response.send_modal(TicketReasonModal(target_category=self.target_category))

# ──── チケットチャンネル内操作用 View（閉じるボタン） ────
class TicketControlView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="🔒 チケットを閉じる", style=discord.ButtonStyle.danger, custom_id="ticket_close_btn")
    async def close_ticket(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_message("このチケットは5秒後に削除されます...", ephemeral=False)
        import asyncio
        await asyncio.sleep(5)
        await interaction.channel.delete(reason="チケットクローズ")

# ──── Ticket Cog 本体 ────
class Ticket(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="ticket", description="チケット作成パネルを指定したチャンネルに設置します")
    @app_commands.describe(
        category="チケットチャンネルが作成されるカテゴリー",
        target_channel="チケットパネルを送信するチャンネル"
    )
    @app_commands.checks.has_permissions(administrator=True)
    async def ticket_setup(
        self,
        interaction: discord.Interaction,
        category: discord.CategoryChannel,
        target_channel: discord.TextChannel
    ):
        embed = discord.Embed(
            title="🎫 サポートチケット",
            description="下の「チケットを作成する」ボタンを押すと、専用のお問い合わせチャンネルが作成されます。",
            color=discord.Color.blue()
        )
        
        # 指定されたチャンネルへパネルを送信
        await target_channel.send(embed=embed, view=TicketCreateView(target_category=category))
        
        # コマンド実行者へ完了通知（自分だけに表示）
        await interaction.response.send_message(
            f"✅ {target_channel.mention} にチケットパネルを設置しました！（作成先カテゴリー: **{category.name}**）",
            ephemeral=True
        )

async def setup(bot):
    await bot.add_cog(Ticket(bot))
