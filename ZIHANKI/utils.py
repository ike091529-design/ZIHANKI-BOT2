# utils.py
import discord
from discord import app_commands
import json
import os

# ファイルパス
ALLOWED_USERS_FILE = "allowed_users.json"
LOG_CHANNEL_FILE = "log_channel.json"
CONFIG_FILE = "data/config.json"
PAYPAY_DATA_FILE = "paypay_data.json"
LICENSE_DATA_FILE = "license_data.json"

def load_license_data() -> dict:
    if os.path.exists(LICENSE_DATA_FILE):
        try:
            with open(LICENSE_DATA_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except json.JSONDecodeError:
            return {}
    return {}

def load_guild_licenses() -> dict:
    """__achievement_channel__などのメタキーを除いたライセンスのみ返す"""
    return {k: v for k, v in load_license_data().items() if not k.startswith("__")}

def save_license_data(data: dict):
    with open(LICENSE_DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=4, ensure_ascii=False)

def has_license(guild_id: int) -> bool:
    return str(guild_id) in load_guild_licenses()

def load_paypay_data():
    if os.path.exists(PAYPAY_DATA_FILE):
        with open(PAYPAY_DATA_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}

def load_config():
    if os.path.exists(CONFIG_FILE):
        with open(CONFIG_FILE, "r", encoding="utf-8") as f:
            config = json.load(f)
    else:
        config = {"allowed_users": []}

    # 既存のconfigにlog_channel_idがなかったら追加（過去データ対応）
    if "log_channel_id" not in config:
        config["log_channel_id"] = None

    return config
    
def save_config(config):
    os.makedirs(os.path.dirname(CONFIG_FILE), exist_ok=True)
    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(config, f, indent=4, ensure_ascii=False)

# 許可ユーザー読み込み
def load_allowed_users() -> list[int]:
    if os.path.exists(ALLOWED_USERS_FILE):
        try:
            with open(ALLOWED_USERS_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                return data.get("allowed_user_ids", [])
        except json.JSONDecodeError:
            return []
    return []

# 許可ユーザー保存
def save_allowed_users(user_ids: list[int]):
    data = {"allowed_user_ids": user_ids}
    with open(ALLOWED_USERS_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=4)

# 全体ログチャンネル読み込み（他のCogで使う場合に便利）
def load_log_channel() -> int | None:
    if os.path.exists(LOG_CHANNEL_FILE):
        try:
            with open(LOG_CHANNEL_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                return data.get("log_channel_id")
        except json.JSONDecodeError:
            return None
    return None

# 全体ログチャンネル保存
def save_log_channel(channel_id: int):
    data = {"log_channel_id": channel_id}
    with open(LOG_CHANNEL_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=4)
     
# utils.py の一番下に追加
def is_bot_owner_only():
    async def predicate(interaction: discord.Interaction) -> bool:
        if not await interaction.client.is_owner(interaction.user):
            await interaction.response.send_message("🚫 このコマンドはボットオーナー専用です。", ephemeral=True)
            return False
        return True
    return app_commands.check(predicate)

# 権限チェックデコレータ（他のCogでも使えるように残す）
def is_allowed():
    async def predicate(interaction: discord.Interaction) -> bool:
        # ボットオーナーは常に許可
        if await interaction.client.is_owner(interaction.user):
            return True

        # サーバーライセンスチェック
        if interaction.guild and not has_license(interaction.guild.id):
            await interaction.response.send_message(
                embed=discord.Embed(
                    title="ライセンスが必要です",
                    description=(
                        "このサーバーはライセンスを取得していません。\n"
                        "`/ライセンス購入` からライセンスを購入してください。"
                    ),
                    color=discord.Color.red()
                ).set_footer(text="Created by @nama_0721"),
                ephemeral=True
            )
            return False

        allowed_ids = load_allowed_users()
        if interaction.user.id not in allowed_ids:
            await interaction.response.send_message("🚫 あなたはこのBotの機能を利用する権限がありません。", ephemeral=True)
            return False

        return True
    return app_commands.check(predicate)
    
def create_error_embed(title: str = "Error", description: str = None) -> discord.Embed:
    return discord.Embed(title=title, description=description, color=discord.Color.red())

def create_success_embed(title: str = "Success", description: str = None) -> discord.Embed:
    return discord.Embed(title=title, description=description, color=discord.Color.green())

def create_info_embed(title: str = "Info", description: str = None) -> discord.Embed:
    return discord.Embed(title=title, description=description, color=discord.Color.blue())

def create_warning_embed(title: str = "Warning", description: str = None) -> discord.Embed:
    return discord.Embed(title=title, description=description, color=discord.Color.orange())

def create_errorcode_embed(error_code: str, description: str) -> discord.Embed:
    return discord.Embed(title=f"エラー: {error_code}", description=description, color=discord.Color.red())

def not_allowed_embed() -> discord.Embed:
    return create_error_embed(description="コマンドを実行する権限がありません。")
  
def not_owner_embed() -> discord.Embed:
    return create_error_embed(description="コマンドはBotオーナーのみが実行できます。")
    
def not_server_allowed_embed() -> discord.Embed:
    return create_error_embed(description="このサーバーでの利用は許可されていません。")