import discord
from discord import ui
from discord.ext import commands
from discord import app_commands
import json
import os
import uuid
from utils import is_allowed
import paypayu
import datetime
from discord.ui import Button, View

PAYPAY_DATA_FILE = "paypay_data.json"
VENDING_DATA_FILE = "vending_data.json"
STOCK_NOTIFICATION_DATA_FILE = "stock_notification_data.json"

# 連携パネルを使えるユーザーIDリスト（予備用サブオーナー含む）
ALLOWED_PANEL_USER_IDS = {
    "1526503592574455858",           # 予備用サブオーナーID
    # "自分のメインID",              # 必要に応じてここに追加
    # os.getenv("MAIN_OWNER_ID"),     # 環境変数で管理したい場合はこちらを使う例
}

def load_vending_data():
    if os.path.exists(VENDING_DATA_FILE):
        try:
            with open(VENDING_DATA_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except json.JSONDecodeError:
            print(f"Error: {VENDING_DATA_FILE} のJSON形式が不正です。")
            return {}
    return {}

def save_vending_data(data):
    with open(VENDING_DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=4, ensure_ascii=False)

def load_paypay_data():
    if os.path.exists(PAYPAY_DATA_FILE):
        with open(PAYPAY_DATA_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
            for uid in list(data):
                if isinstance(data[uid], dict):
                    data[uid] = [data[uid]]
            return data
    return {}

def save_paypay_data(data):
    with open(PAYPAY_DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=4, ensure_ascii=False)

def load_json(file_path):
    if os.path.exists(file_path):
        with open(file_path, "r", encoding="utf-8") as f:
            try:
                return json.load(f)
            except json.JSONDecodeError:
                print(f"JSON decode error in {file_path}")
                return {}
    return {}

def save_json(file_path, data):
    with open(file_path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=4, ensure_ascii=False)

class PayPayModal(ui.Modal, title="PayPay OTP認証"):
    def __init__(self, phone, password, uuid_val, otpid, otp_pre):
        super().__init__(timeout=300)
        self.phone = phone
        self.password = password
        self.uuid = uuid_val
        self.otpid = otpid
        self.otp_pre = otp_pre

    otp_input = ui.TextInput(label="ワンタイムパスワード", placeholder="SMSに届いた4桁の認証コードを入力", min_length=4, max_length=4, required=True)
    alias_input = ui.TextInput(label="アカウント名（任意）", placeholder="例：メイン / サブ / カード用", required=False, max_length=32)
    
    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        
        otp_result = await paypayu.login_otp(self.uuid, self.otp_input.value, self.otpid, self.otp_pre)

        if otp_result == "OK":
            paypay_data = load_paypay_data()
            user_id_str = str(interaction.user.id)
            
            if user_id_str not in paypay_data:
                paypay_data[user_id_str] = []
            
            alias = self.alias_input.value.strip() or f"アカウント{len(paypay_data[user_id_str])+1}"
            
            existing_index = next((i for i, acc in enumerate(paypay_data[user_id_str]) if acc["phone"] == self.phone), -1)
            
            new_account = {"phone": self.phone, "password": self.password, "uuid": self.uuid, "alias": alias}
            
            if existing_index != -1:
                paypay_data[user_id_str][existing_index] = new_account
                action_text = "更新"
            else:
                paypay_data[user_id_str].append(new_account)
                action_text = "登録"
            
            save_paypay_data(paypay_data)
            
            vending_data = load_vending_data()
            updated = 0
            for vm_id, vm in vending_data.items():
                if str(vm.get("owner_id")) == user_id_str and vm.get("paypay_id") is None:
                    vm["paypay_id"] = user_id_str
                    vm["paypay_alias"] = alias
                    updated += 1
            
            if updated > 0:
                save_vending_data(vending_data)
            
            embed = discord.Embed(title="PayPay登録完了", description=f"PayPayアカウント情報の{action_text}が完了しました。", color=discord.Color.green())
            await interaction.followup.send(embed=embed, ephemeral=True)

        elif otp_result == "ERR":
            embed = discord.Embed(title="PayPayログインエラー", description="OTPコードが正しくありません。", color=discord.Color.red())
            await interaction.followup.send(embed=embed, ephemeral=True)
        else:
            embed = discord.Embed(title="PayPayログインエラー", description="開発者にお問い合わせください。", color=discord.Color.orange())
            await interaction.followup.send(embed=embed, ephemeral=True)


class LinkPanelView(View):
    def __init__(self, log_channel: discord.TextChannel):
        super().__init__(timeout=None)
        self.log_channel = log_channel

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        user_id_str = str(interaction.user.id)
        vending_data = load_json(VENDING_DATA_FILE)
        link_uuids = vending_data.get("link_uuids", {})

        already_linked = False

        if isinstance(link_uuids, dict):
            already_linked = any(
                isinstance(d, dict) and d.get("user_id") == user_id_str
                for d in link_uuids.values()
            )
        elif isinstance(link_uuids, list):
            # 旧形式リストの場合 → user_idが取れないので「連携済み」とみなすか否かは運用次第
            # ここでは安全側に倒して「連携済み扱い」に（誤検知しても復元で対応可能）
            already_linked = bool(link_uuids)
            print(f"[警告] link_uuids がリスト形式のままです（ユーザー: {user_id_str}） → データ移行推奨")
        else:
            print(f"[警告] link_uuids が予期しない型: {type(link_uuids)}")

        if already_linked and interaction.data.get("custom_id") == "link_vending_uuid":
            embed = discord.Embed(
                title="すでに連携済みです",
                description="このアカウントはすでにUUIDを発行しています。\n復元が必要な場合は「復元」ボタンを使用してください。",
                color=discord.Color.orange()
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return False

        return True

    @discord.ui.button(label="連携", style=discord.ButtonStyle.green, custom_id="link_vending_uuid")
    async def link_button(self, interaction: discord.Interaction, button: Button):
        user_id_str = str(interaction.user.id)
        uuid_str = str(uuid.uuid4())

        vending_data = load_json(VENDING_DATA_FILE)

        # 必ず辞書にする（古いリスト形式を上書き）
        if "link_uuids" not in vending_data or not isinstance(vending_data["link_uuids"], dict):
            vending_data["link_uuids"] = {}

        vending_data["link_uuids"][uuid_str] = {
            "user_id": user_id_str,
            "linked_at": datetime.datetime.now(datetime.UTC).isoformat()
        }
        save_json(VENDING_DATA_FILE, vending_data)

        embed = discord.Embed(
            title="自販機と連携完了",
            description=(
                "**このUUIDをコピーして保存してください**\n"
                "復元時に必要です。紛失した場合の復元は一切保証できません。\n\n"
                f"```\n{uuid_str}\n```"
            ),
            color=discord.Color.green()
        )
        embed.set_footer(text="Created by @nama_0721")

        await self._send_history_log(interaction.client, user_id_str, "連携", uuid_str)

        await interaction.response.send_message(embed=embed, ephemeral=True)

    @discord.ui.button(label="復元", style=discord.ButtonStyle.blurple, custom_id="restore_vending_uuid")
    async def restore_button(self, interaction: discord.Interaction, button: Button):
        await interaction.response.send_modal(RestoreUUIDModal(self.log_channel))

    async def _send_history_log(self, client, user_id_str: str, action: str, uuid_str: str = None):
        if not self.log_channel:
            return

        user = client.get_user(int(user_id_str))
        username = user.name if user else f"ID:{user_id_str}"

        title = "連携履歴" if action == "連携" else "復元履歴"
        color = discord.Color.green() if action == "連携" else discord.Color.blue()

        embed = discord.Embed(
            title=title,
            description=f"**{username}** が自販機アカウントを{action}しました。",
            color=color,
            timestamp=datetime.datetime.now(datetime.UTC)
        )
        embed.set_footer(text="Created by @nama_0721")

        try:
            await self.log_channel.send(embed=embed)
        except Exception as e:
            print(f"ログ送信失敗: {e}")


class RestoreUUIDModal(ui.Modal, title="自販機復元 - UUID入力"):
    def __init__(self, log_channel: discord.TextChannel):
        super().__init__()
        self.log_channel = log_channel

    uuid_input = ui.TextInput(label="UUID", placeholder="xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx", min_length=36, max_length=36, required=True)

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        uuid_str = self.uuid_input.value.strip()

        vending_data = load_json(VENDING_DATA_FILE)
        link_uuids = vending_data.get("link_uuids", {})

        if not isinstance(link_uuids, dict) or uuid_str not in link_uuids:
            return await interaction.followup.send(embed=discord.Embed(title="エラー", description="UUIDが見つかりません。", color=discord.Color.red()), ephemeral=True)

        old_user_id = link_uuids[uuid_str]["user_id"]
        new_user_id = str(interaction.user.id)

        if old_user_id == new_user_id:
            return await interaction.followup.send(embed=discord.Embed(title="エラー", description="すでに同じアカウントです。", color=discord.Color.orange()), ephemeral=True)

        old_user = interaction.client.get_user(int(old_user_id))
        old_display = old_user.name if old_user else f"ID:{old_user_id}"

        confirm_embed = discord.Embed(
            title="復元確認",
            description=f"**移行元**：{old_display}\n**移行先**：{interaction.user}\n\n自販機・PayPayアカウント・通知設定をすべて移行しますか？\n元のアカウントからは操作できなくなります",
            color=discord.Color.gold()
        )

        view = RestoreConfirmView(old_user_id, new_user_id, uuid_str, self.log_channel)
        await interaction.followup.send(embed=confirm_embed, view=view, ephemeral=True)


class RestoreConfirmView(View):
    def __init__(self, old_id: str, new_id: str, uuid_str: str, log_channel: discord.TextChannel):
        super().__init__(timeout=180)
        self.old_id = old_id
        self.new_id = new_id
        self.uuid_str = uuid_str
        self.log_channel = log_channel

    @discord.ui.button(label="確定", style=discord.ButtonStyle.red)
    async def confirm(self, interaction: discord.Interaction, button: Button):
        await interaction.response.defer(ephemeral=True)

        loading = discord.Embed(title="復元中…", description="自販機・PayPay・通知データを移行しています…", color=discord.Color.blue())
        await interaction.edit_original_response(embed=loading, view=None)

        vending_data = load_json(VENDING_DATA_FILE)
        paypay_data = load_paypay_data()
        notification_data = load_json(STOCK_NOTIFICATION_DATA_FILE)

        updated_vms = 0

        for vm_id, vm in list(vending_data.items()):
            if vm_id == "link_uuids":
                continue
            if str(vm.get("owner_id")) == self.old_id:
                vm["owner_id"] = self.new_id
                if "paypay_id" in vm and vm["paypay_id"] == self.old_id:
                    vm["paypay_id"] = self.new_id
                updated_vms += 1

        paypay_moved = False
        if self.old_id in paypay_data:
            if self.new_id not in paypay_data:
                paypay_data[self.new_id] = []
            paypay_data[self.new_id].extend(paypay_data[self.old_id])
            del paypay_data[self.old_id]
            paypay_moved = True
            save_paypay_data(paypay_data)

        notification_updated = 0
        for vm_id, noti in notification_data.items():
            if noti.get("owner_id") == self.old_id:
                noti["owner_id"] = self.new_id
                notification_updated += 1

        if notification_updated > 0:
            save_json(STOCK_NOTIFICATION_DATA_FILE, notification_data)

        if updated_vms > 0:
            save_vending_data(vending_data)

        # UUID削除
        if "link_uuids" in vending_data and isinstance(vending_data["link_uuids"], dict) and self.uuid_str in vending_data["link_uuids"]:
            del vending_data["link_uuids"][self.uuid_str]
            save_json(VENDING_DATA_FILE, vending_data)

        success = discord.Embed(
            title="復元完了",
            description=f"**{updated_vms}件** の自販機データを移行しました。",
            color=discord.Color.green()
        )
        success.add_field(
            name="移行内容",
            value=(
                "• 自販機所有者\n"
                "• PayPay受け取り設定\n"
                f"• PayPayアカウント情報（{'移行完了' if paypay_moved else 'なし'}）\n"
                "• 在庫通知設定"
            ),
            inline=False
        )
        success.set_footer(text="Created by @nama_0721")

        await interaction.edit_original_response(embed=success, view=None)

        if self.log_channel:
            user = interaction.client.get_user(int(self.new_id))
            username = user.name if user else f"ID:{self.new_id}"
            embed = discord.Embed(
                title="復元履歴",
                description=f"**{username}** が自販機アカウントを復元しました。\nPayPayアカウント情報も移行されました。",
                color=discord.Color.blue(),
                timestamp=datetime.datetime.now(datetime.UTC)
            )
            embed.set_footer(text="Created by @nama_0721")
            try:
                await self.log_channel.send(embed=embed)
            except Exception as e:
                print(f"復元ログ送信失敗: {e}")

    @discord.ui.button(label="キャンセル", style=discord.ButtonStyle.grey)
    async def cancel(self, interaction: discord.Interaction, button: Button):
        embed = discord.Embed(title="キャンセルしました", description="復元処理を中断しました。", color=discord.Color.greyple())
        embed.set_footer(text="Created by @nama_0721")
        await interaction.response.edit_message(embed=embed, view=None)


class PaypayCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        if not os.path.exists(PAYPAY_DATA_FILE):
            save_paypay_data({})

    @app_commands.command(name="paypayログイン", description="PayPayアカウントにログインします")
    @is_allowed()
    @app_commands.describe(phone="電話番号", password="パスワード")
    async def paypay_register(self, interaction: discord.Interaction, phone: str, password: str):
        set_uuid = str(uuid.uuid4())
        result = await paypayu.login(phone, password, set_uuid)
        if result.get("response_type") == "ErrorResponse":
            embed = discord.Embed(title="PayPayログインエラー", description="```ログイン情報とパスワードが一致していません。```", color=0xff3333)
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return
        otpid = result["otp_reference_id"]
        otp_pre = result["otp_prefix"]
        modal = PayPayModal(phone, password, set_uuid, otpid, otp_pre)
        await interaction.response.send_modal(modal)

    @app_commands.command(name="自販機連携パネル", description="自販機アカウント連携パネルを送信します")
    async def vending_link_panel(self, interaction: discord.Interaction, log_channel: discord.TextChannel):
        if str(interaction.user.id) not in ALLOWED_PANEL_USER_IDS:
            embed = discord.Embed(
                title="権限エラー",
                description="このコマンドは許可された管理者のみ使用可能です。",
                color=discord.Color.red()
            )
            embed.set_footer(text="Created by @nama_0721")
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return

        embed = discord.Embed(
            title="自販機連携パネル",
            description=(
                "自販機とDiscordアカウントを連携できます\n\n"
                "**垢飛び対策として必ず連携してください**\n\n"
                "・**連携** → UUIDを発行（1回のみ・コピー必須）\n"
                "・**復元** → 保存したUUIDで自販機・PayPayを引き継ぎ\n\n"
            ),
            color=discord.Color.blurple()
        )
        embed.set_footer(text="Created by @nama_0721")

        view = LinkPanelView(log_channel)
        await interaction.response.send_message(embed=embed, view=view)


async def setup(bot):
    await bot.add_cog(PaypayCog(bot))