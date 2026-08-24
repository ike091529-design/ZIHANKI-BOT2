import discord
from discord.ext import commands, tasks
from discord import app_commands, ui
import json
import os
import asyncio
import datetime
from concurrent.futures import ThreadPoolExecutor
from cryptography.fernet import Fernet

from Kyasher import Kyash, KyashError, KyashLoginError

KYASH_DATA_FILE = "kyash_data.json"

# 暗号化キー（.env の KYASH_ENCRYPT_KEY に Fernet.generate_key().decode() の値を設定）
# 初回起動時にキーがなければ自動生成してファイルに保存
_ENCRYPT_KEY_FILE = ".kyash_key"

def _load_or_create_key() -> bytes:
    if os.path.exists(_ENCRYPT_KEY_FILE):
        with open(_ENCRYPT_KEY_FILE, "rb") as f:
            return f.read().strip()
    key = Fernet.generate_key()
    with open(_ENCRYPT_KEY_FILE, "wb") as f:
        f.write(key)
    print(f"[KyashCog] 暗号化キーを生成しました: {_ENCRYPT_KEY_FILE}")
    return key

_fernet = Fernet(_load_or_create_key())

def encrypt(value: str) -> str:
    """文字列を暗号化して base64 文字列で返す"""
    return _fernet.encrypt(value.encode()).decode()

def decrypt(value: str) -> str:
    """暗号化された base64 文字列を復号して返す"""
    return _fernet.decrypt(value.encode()).decode()

# 暗号化対象フィールド
_ENCRYPTED_FIELDS = ("access_token", "client_uuid", "installation_uuid")

def encrypt_account(acc: dict) -> dict:
    """保存前にセンシティブフィールドを暗号化"""
    result = acc.copy()
    for field in _ENCRYPTED_FIELDS:
        if field in result and result[field]:
            result[field] = encrypt(result[field])
    return result

def decrypt_account(acc: dict) -> dict:
    """読み込み後にセンシティブフィールドを復号"""
    result = acc.copy()
    for field in _ENCRYPTED_FIELDS:
        if field in result and result[field]:
            try:
                result[field] = decrypt(result[field])
            except Exception:
                pass  # 未暗号化データ（移行時）はそのまま
    return result


# ─── ユーティリティ ───────────────────────────────────────────

# Kyashログイン一時セッション（user_id → {email, password, kyash_instance}）
KYASH_TEMP_SESSIONS: dict = {}

_executor = ThreadPoolExecutor()


def load_kyash_data() -> dict:
    """ファイルから読み込み、センシティブフィールドを復号して返す"""
    if os.path.exists(KYASH_DATA_FILE):
        with open(KYASH_DATA_FILE, "r", encoding="utf-8") as f:
            try:
                raw = json.load(f)
            except json.JSONDecodeError:
                return {}
        # 各アカウントを復号
        result = {}
        for user_id, accounts in raw.items():
            result[user_id] = [decrypt_account(a) for a in accounts]
        return result
    return {}


def save_kyash_data(data: dict):
    """センシティブフィールドを暗号化してファイルに保存"""
    encrypted = {}
    for user_id, accounts in data.items():
        encrypted[user_id] = [encrypt_account(a) for a in accounts]
    with open(KYASH_DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(encrypted, f, indent=4, ensure_ascii=False)


async def run_in_executor(func, *args):
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(_executor, func, *args)


# ─── Cog ─────────────────────────────────────────────────────

class KyashCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.auto_refresh.start()

    def cog_unload(self):
        self.auto_refresh.cancel()

    # ════════════════════════════════════════════════════════
    # 20日ごと自動トークン更新タスク
    # ════════════════════════════════════════════════════════

    @tasks.loop(hours=24 * 20)
    async def auto_refresh(self):
        """20日ごとに全アカウントのアクセストークンを再取得する"""
        kyash_data = load_kyash_data()  # 復号済みデータ
        updated = 0
        failed = 0

        for user_id, accounts in kyash_data.items():
            for i, acc in enumerate(accounts):
                try:
                    def do_relogin(a=acc):
                        # client_uuid + installation_uuid 指定でOTPスキップ再ログイン
                        k = Kyash(
                            email=a["email"],
                            password=a["password"],
                            client_uuid=a["client_uuid"],
                            installation_uuid=a["installation_uuid"],
                        )
                        return k

                    k = await run_in_executor(do_relogin)
                    # 復号済みデータを更新（save_kyash_data が再暗号化する）
                    kyash_data[user_id][i]["access_token"] = k.access_token
                    kyash_data[user_id][i]["last_refresh"] = datetime.datetime.now().isoformat()
                    updated += 1
                    await asyncio.sleep(1)  # レート制限対策

                except Exception as e:
                    print(f"[KyashCog] トークン更新失敗 user={user_id} alias={acc.get('alias')}: {e}")
                    failed += 1

        save_kyash_data(kyash_data)  # 暗号化して保存
        print(f"[KyashCog] トークン自動更新完了: 成功={updated} 失敗={failed}")

    @auto_refresh.before_loop
    async def before_auto_refresh(self):
        await self.bot.wait_until_ready()

    # ════════════════════════════════════════════════════════
    # OTP モーダル
    # ════════════════════════════════════════════════════════

    class KyashOTPModal(ui.Modal, title="Kyash OTP認証"):
        def __init__(self, alias: str):
            super().__init__()
            self.alias = alias
            self.otp_input = ui.TextInput(
                label="OTPコード（6桁）",
                placeholder="SMSに届いた6桁のコードを入力",
                min_length=6,
                max_length=6,
                required=True
            )
            self.add_item(self.otp_input)

        async def on_submit(self, interaction: discord.Interaction):
            await interaction.response.defer(ephemeral=True)
            user_id = str(interaction.user.id)

            session = KYASH_TEMP_SESSIONS.get(interaction.user.id)
            if not session:
                return await interaction.followup.send(
                    "セッションが期限切れです。もう一度 `/kyashログイン` を実行してください。",
                    ephemeral=True
                )

            try:
                kyash = session["kyash"]

                def do_login():
                    kyash.login(self.otp_input.value.strip())

                await run_in_executor(do_login)

                kyash_data = load_kyash_data()
                user_accounts = kyash_data.get(user_id, [])
                # 同 alias があれば上書き
                user_accounts = [a for a in user_accounts if a.get("alias") != self.alias]
                user_accounts.append({
                    "alias": self.alias,
                    "email": session["email"],
                    "password": session["password"],
                    # 以下3フィールドは save_kyash_data 内で暗号化される
                    "access_token": kyash.access_token,
                    "client_uuid": kyash.client_uuid,
                    "installation_uuid": kyash.installation_uuid,
                    "last_refresh": datetime.datetime.now().isoformat(),
                })
                kyash_data[user_id] = user_accounts
                save_kyash_data(kyash_data)

                KYASH_TEMP_SESSIONS.pop(interaction.user.id, None)

                embed = discord.Embed(
                    title="登録成功",
                    description="Kyashの登録に成功しました",
                    color=discord.Color.green(),
                    timestamp=discord.utils.utcnow()
                )
                embed.add_field(name="アカウント名", value=f"**{self.alias}**", inline=True)
                embed.add_field(name="メールアドレス / 電話番号", value=f"`{session['email']}`", inline=True)
                embed.set_footer(text="Created by @nama_0721")
                await interaction.followup.send(embed=embed, ephemeral=True)

            except KyashLoginError as e:
                embed = discord.Embed(title="OTP認証失敗", description=f"```{str(e)}```", color=discord.Color.red())
                embed.set_footer(text="Created by @nama_0721")
                await interaction.followup.send(embed=embed, ephemeral=True)
            except Exception as e:
                embed = discord.Embed(title="エラー", description=f"```{str(e)}```", color=discord.Color.red())
                embed.set_footer(text="Created by @nama_0721")
                await interaction.followup.send(embed=embed, ephemeral=True)

    # ════════════════════════════════════════════════════════
    # OTP ボタン View
    # ════════════════════════════════════════════════════════

    class KyashOTPButtonView(ui.View):
        def __init__(self, alias: str, user_id: str):
            super().__init__(timeout=300)
            self.alias = alias
            self.user_id = user_id

        @ui.button(label="OTPを入力する", style=discord.ButtonStyle.green)
        async def open_otp_modal(self, interaction: discord.Interaction, button: discord.ui.Button):
            if str(interaction.user.id) != self.user_id:
                return await interaction.response.send_message(
                    "このボタンはあなたのものではありません。", ephemeral=True
                )
            modal = KyashCog.KyashOTPModal(self.alias)
            await interaction.response.send_modal(modal)

    # ════════════════════════════════════════════════════════
    # スラッシュコマンド
    # ════════════════════════════════════════════════════════

    @app_commands.command(name="kyashログイン", description="Kyashアカウントを登録します（管理者専用）")
    @app_commands.default_permissions(administrator=True)
    @app_commands.describe(
        email_or_phone="Kyashに登録したメールアドレスまたは電話番号",
        password="Kyashのパスワード",
        alias="アカウント管理用の名前（例: メイン）"
    )
    async def kyash_login(self, interaction: discord.Interaction, email_or_phone: str, password: str, alias: str = "メイン"):
        await interaction.response.defer(ephemeral=True)

        try:
            def do_init():
                return Kyash(email=email_or_phone, password=password)

            kyash = await run_in_executor(do_init)

            KYASH_TEMP_SESSIONS[interaction.user.id] = {
                "email": email_or_phone,
                "password": password,
                "kyash": kyash,
            }

            embed = discord.Embed(
                title="OTPを送信しました",
                description="登録したメールアドレスまたはSMSに**6桁のOTPコード**が届きました。\n下のボタンを押してOTPを入力してください。",
                color=discord.Color.blue()
            )
            embed.set_footer(text="Created by @nama_0721")
            view = KyashCog.KyashOTPButtonView(alias, str(interaction.user.id))
            await interaction.followup.send(embed=embed, view=view, ephemeral=True)

        except KyashLoginError as e:
            embed = discord.Embed(title="ログインエラー", description=f"```{str(e)}```", color=discord.Color.red())
            embed.set_footer(text="Created by @nama_0721")
            await interaction.followup.send(embed=embed, ephemeral=True)
        except Exception as e:
            embed = discord.Embed(title="エラー", description=f"```{str(e)}```", color=discord.Color.red())
            embed.set_footer(text="Created by @nama_0721")
            await interaction.followup.send(embed=embed, ephemeral=True)

    @app_commands.command(name="kyashアカウント一覧", description="登録済みKyashアカウントを確認します（管理者専用）")
    @app_commands.default_permissions(administrator=True)
    async def kyash_list(self, interaction: discord.Interaction):
        user_id = str(interaction.user.id)
        accounts = load_kyash_data().get(user_id, [])

        if not accounts:
            return await interaction.response.send_message(
                "登録済みのKyashアカウントがありません。`/kyashログイン` で登録してください。",
                ephemeral=True
            )

        embed = discord.Embed(
            title="登録済み Kyash アカウント一覧",
            color=discord.Color.blue(),
            timestamp=discord.utils.utcnow()
        )
        for acc in accounts:
            last = acc.get("last_refresh", "不明")[:10] if acc.get("last_refresh") else "不明"
            embed.add_field(
                name=acc.get("alias", "名称不明"),
                value=f"メール/電話: `{acc.get('email', '不明')}`\n最終更新: `{last}`",
                inline=False
            )
        embed.set_footer(text="Created by @nama_0721")
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @app_commands.command(name="kyashアカウント削除", description="登録済みKyashアカウントを削除します（管理者専用）")
    @app_commands.default_permissions(administrator=True)
    @app_commands.describe(alias="削除するアカウント名")
    async def kyash_delete(self, interaction: discord.Interaction, alias: str):
        user_id = str(interaction.user.id)
        kyash_data = load_kyash_data()
        accounts = kyash_data.get(user_id, [])
        new_accounts = [a for a in accounts if a.get("alias") != alias]
        if len(new_accounts) == len(accounts):
            return await interaction.response.send_message(
                f"「{alias}」というアカウントが見つかりません。", ephemeral=True
            )
        kyash_data[user_id] = new_accounts
        save_kyash_data(kyash_data)
        embed = discord.Embed(
            title="削除完了",
            description=f"Kyashアカウント「**{alias}**」を削除しました。",
            color=discord.Color.red()
        )
        embed.set_footer(text="Created by @nama_0721")
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @kyash_delete.autocomplete("alias")
    async def kyash_alias_ac(self, interaction: discord.Interaction, current: str):
        user_id = str(interaction.user.id)
        accounts = load_kyash_data().get(user_id, [])
        return [
            app_commands.Choice(name=a["alias"], value=a["alias"])
            for a in accounts if current.lower() in a["alias"].lower()
        ][:25]


async def setup(bot: commands.Bot):
    await bot.add_cog(KyashCog(bot))
