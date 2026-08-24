import discord
from discord.ext import commands
from discord import app_commands, ui
import json
import os
import uuid
import io
import asyncio
import datetime
import pytz
from concurrent.futures import ThreadPoolExecutor
from utils import is_allowed
import paypayu
import random
import backup_manager

# Kyasher ライブラリ（Kyasher/ フォルダが同ディレクトリに必要）
try:
    from Kyasher import Kyash, KyashError, KyashLoginError
    KYASH_AVAILABLE = True
except ImportError:
    KYASH_AVAILABLE = False
    print("[vending] Kyasherライブラリが見つかりません。Kyash決済は無効です。")

_executor = ThreadPoolExecutor()

KYASH_DATA_FILE = "kyash_data.json"

# ─── Kyash 暗号化ユーティリティ ───────────────────────────────
try:
    from cryptography.fernet import Fernet as _Fernet
    _ENCRYPT_KEY_FILE = ".kyash_key"

    def _load_or_create_key() -> bytes:
        if os.path.exists(_ENCRYPT_KEY_FILE):
            with open(_ENCRYPT_KEY_FILE, "rb") as f:
                return f.read().strip()
        key = _Fernet.generate_key()
        with open(_ENCRYPT_KEY_FILE, "wb") as f:
            f.write(key)
        return key

    _fernet = _Fernet(_load_or_create_key())
    _ENCRYPTED_FIELDS = ("access_token", "client_uuid", "installation_uuid")

    def _encrypt(value: str) -> str:
        return _fernet.encrypt(value.encode()).decode()

    def _decrypt(value: str) -> str:
        return _fernet.decrypt(value.encode()).decode()

    def _encrypt_account(acc: dict) -> dict:
        result = acc.copy()
        for field in _ENCRYPTED_FIELDS:
            if field in result and result[field]:
                result[field] = _encrypt(result[field])
        return result

    def _decrypt_account(acc: dict) -> dict:
        result = acc.copy()
        for field in _ENCRYPTED_FIELDS:
            if field in result and result[field]:
                try:
                    result[field] = _decrypt(result[field])
                except Exception:
                    pass
        return result

    _KYASH_CRYPTO = True
except ImportError:
    _KYASH_CRYPTO = False
    print("[vending] cryptographyライブラリが見つかりません。Kyashデータは暗号化されません。")
    def _encrypt_account(acc): return acc
    def _decrypt_account(acc): return acc

def load_kyash_data() -> dict:
    if os.path.exists(KYASH_DATA_FILE):
        with open(KYASH_DATA_FILE, "r", encoding="utf-8") as f:
            try:
                raw = json.load(f)
            except json.JSONDecodeError:
                return {}
        return {uid: [_decrypt_account(a) for a in accs] for uid, accs in raw.items()}
    return {}

def save_kyash_data(data: dict):
    encrypted = {uid: [_encrypt_account(a) for a in accs] for uid, accs in data.items()}
    with open(KYASH_DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(encrypted, f, indent=4, ensure_ascii=False)

async def run_in_executor(func, *args):
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(_executor, func, *args)

VENDING_DATA_FILE = "vending_data.json"
PAYPAY_DATA_FILE = "paypay_data.json"
STOCK_DIR_BASE = "stock_files"
STOCK_NOTIFICATION_DATA_FILE = "stock_notification_data.json"
STOCK_ALERT_DATA_FILE = "stock_alert_data.json"
COUPON_DATA_FILE = "coupon_data.json"
ROLE_ASSIGNMENT_DATA_FILE = "role_assignment_data.json"
CONFIG_FILE = "config.json"  # 適宜パスを調整
BOT_OWNER_ID = "1365166057924333669"  # BotオーナーのDiscord ID（文字列）

def load_config(cls):
    if os.path.exists(CONFIG_FILE):
        with open(CONFIG_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    else:
        # デフォルト設定
        default_config = {
            "allowed_user_ids": [],  # 最初は空リスト
            "log_channel_id": None,
            # 他の必要な設定があればここに
        }
        cls.save_config(default_config)
        return default_config

def load_json(file_path):
    if os.path.exists(file_path):
        with open(file_path, "r", encoding="utf-8") as f:
            try:
                return json.load(f)
            except json.JSONDecodeError:
                return {}
    return {}

def save_json(file_path, data):
    with open(file_path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=4, ensure_ascii=False)

def load_paypay_data():
    if os.path.exists(PAYPAY_DATA_FILE):
        with open(PAYPAY_DATA_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}

def load_stock_notification_data():
    if os.path.exists(STOCK_NOTIFICATION_DATA_FILE):
        with open(STOCK_NOTIFICATION_DATA_FILE, "r", encoding="utf-8") as f:
            try:
                return json.load(f)
            except json.JSONDecodeError:
                return {}
    return {}

def save_stock_notification_data(data):
    with open(STOCK_NOTIFICATION_DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=4, ensure_ascii=False)

def load_stock_alert_data():
    if os.path.exists(STOCK_ALERT_DATA_FILE):
        with open(STOCK_ALERT_DATA_FILE, "r", encoding="utf-8") as f:
            try:
                return json.load(f)
            except json.JSONDecodeError:
                return {}
    return {}

def save_stock_alert_data(data):
    with open(STOCK_ALERT_DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=4, ensure_ascii=False)

def load_coupon_data():
    if os.path.exists(COUPON_DATA_FILE):
        with open(COUPON_DATA_FILE, "r", encoding="utf-8") as f:
            try:
                return json.load(f)
            except json.JSONDecodeError:
                return {}
    return {}

def save_coupon_data(data):
    with open(COUPON_DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=4, ensure_ascii=False)

def load_role_assignment_data():
    if os.path.exists(ROLE_ASSIGNMENT_DATA_FILE):
        with open(ROLE_ASSIGNMENT_DATA_FILE, "r", encoding="utf-8") as f:
            try:
                return json.load(f)
            except json.JSONDecodeError:
                return {}
    return {}

def save_role_assignment_data(data):
    with open(ROLE_ASSIGNMENT_DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=4, ensure_ascii=False)

async def vending_machine_autocomplete(interaction: discord.Interaction, current: str) -> list[app_commands.Choice[str]]:
    vending_data = load_json(VENDING_DATA_FILE)
    user_id_str = str(interaction.user.id)
    
    user_machines = [
        (vm_id, vm_data) for vm_id, vm_data in vending_data.items() 
        if vm_data.get("owner_id") == user_id_str
    ]

    return [
        app_commands.Choice(name=vm_data.get("name", "名称未設定"), value=vm_id)
        for vm_id, vm_data in user_machines
        if current.lower() in vm_data.get("name", "").lower()
    ]
    
async def paypay_alias_autocomplete(interaction: discord.Interaction, current: str) -> list[app_commands.Choice[str]]:
    paypay_data = load_paypay_data()  # 既存の関数を利用
    user_id_str = str(interaction.user.id)
    
    accounts = paypay_data.get(user_id_str, [])
    
    return [
        app_commands.Choice(name=acc["alias"], value=acc["alias"])
        for acc in accounts
        if current.lower() in acc["alias"].lower()
    ][:25]

async def coupon_autocomplete(interaction: discord.Interaction, current: str) -> list[app_commands.Choice[str]]:
    coupon_data = load_coupon_data()
    user_id_str = str(interaction.user.id)
    
    user_coupons = [
        (coupon_code, coupon_info) for coupon_code, coupon_info in coupon_data.items()
        if coupon_info.get("owner_id") == user_id_str
    ]
    
    choices = []
    for coupon_code, coupon_info in user_coupons:
        if current.lower() in coupon_code.lower():
            discount = coupon_info.get("discount", 0)
            vending_machine_id = coupon_info.get("vending_machine_id", "")
            vending_data = load_json(VENDING_DATA_FILE)
            vm_name = vending_data.get(vending_machine_id, {}).get("name", "不明")
            choices.append(app_commands.Choice(
                name=f"{coupon_code} (-{discount}円) [{vm_name}]",
                value=coupon_code
            ))
    
    return choices[:25]

async def role_assignment_autocomplete(interaction: discord.Interaction, current: str) -> list[app_commands.Choice[str]]:
    role_data = load_role_assignment_data()
    vending_data = load_json(VENDING_DATA_FILE)
    
    choices = []
    for vm_id, role_info in role_data.items():
        if role_info.get("guild_id") == interaction.guild.id:
            vm = vending_data.get(vm_id)
            if vm and vm.get("owner_id") == str(interaction.user.id):
                vm_name = vm.get("name", "不明な自販機")
                if current.lower() in vm_name.lower():
                    choices.append(app_commands.Choice(name=vm_name, value=vm_id))
    
    return choices[:25]

async def handle_error(interaction: discord.Interaction, error: Exception, ephemeral: bool = True):
    """統一エラーハンドリング"""
    try:
        embed = discord.Embed(
            title="エラーが発生しました",
            description=f"```{str(error)}```",
            color=discord.Color.red(),
            timestamp=discord.utils.utcnow()
        )
        embed.set_footer(text="Created by @nama_0721")
        
        if interaction.response.is_done():
            await interaction.followup.send(embed=embed, ephemeral=ephemeral)
        else:
            await interaction.response.send_message(embed=embed, ephemeral=ephemeral)
    except:
        print(f"Error sending error message: {error}")

async def check_stock(interaction: discord.Interaction, products: list):
    embed = discord.Embed(
        title="在庫・販売数情報",
        color=discord.Color(0x313c48),
        timestamp=discord.utils.utcnow()
    )
    embed.set_footer(text="Created by @nama_0721")

    if not products:
        embed.description = "この自販機には商品が登録されていません。"
        await interaction.followup.send(embed=embed, ephemeral=True)
        return
    
    for product in products:
        product_name = product.get("name", "不明")
        sales_count = product.get("sales_count", 0)
        
        if product.get("infinite_stock"):
            # 無限在庫の場合
            embed.add_field(
                name=f"{product_name}", 
                value=f"```在庫数: ∞個\n販売数: {sales_count}個```", 
                inline=False
            )
        else:
            # 有限在庫の場合
            stock_file = product.get("stock_file")
            
            if not stock_file:
                embed.add_field(
                    name=f"{product_name}", 
                    value=f"```在庫数: 不明\n販売数: {sales_count}個```", 
                    inline=False
                )
                continue
                
            try:
                with open(stock_file, "r", encoding="utf-8") as file:
                    lines = [line for line in file.readlines() if line.strip()]
                    stock_count = len(lines)
                    embed.add_field(
                        name=f"{product_name}", 
                        value=f"```在庫数: {stock_count}個\n販売数: {sales_count}個```", 
                        inline=False
                    )

            except FileNotFoundError:
                embed.add_field(
                    name=f"{product_name}", 
                    value=f"```在庫数: 0個\n販売数: {sales_count}個```", 
                    inline=False
                )
            except Exception as e:
                await handle_error(interaction, e)

    await interaction.followup.send(embed=embed, ephemeral=True)


class VendingMachineCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    async def cog_load(self):
        """Cogロード時に永続化Viewを復元"""
        vending_data = load_json(VENDING_DATA_FILE)
        
        if not os.path.exists(STOCK_DIR_BASE):
            os.makedirs(STOCK_DIR_BASE)
            print(f"[VendingMachine] Created directory: {STOCK_DIR_BASE}")

        vending_data = load_json(VENDING_DATA_FILE)
        
        # 自販機パネル用Viewを復元
        for vm_id in vending_data.keys():
            view = VendingMachineCog.VendingMachineView(vm_id, self.bot)
            self.bot.add_view(view)
        
        # その他の永続化Viewも復元
        products_data = []
        for vm_data in vending_data.values():
            products_data.extend(vm_data.get("products", []))
        
        if products_data:
            # 在庫追加用View
            stock_view = VendingMachineCog.ProductSelectViewForStock(products_data)
            self.bot.add_view(stock_view)
            
            # 在庫引出用View
            withdraw_view = VendingMachineCog.WithdrawStockView(products_data, 1)
            self.bot.add_view(withdraw_view)
            
            # 在庫内容確認用View
            content_view = VendingMachineCog.ContentView(products_data)
            self.bot.add_view(content_view)

    @app_commands.command(name="自販機作成", description="自販機を作成します")
    @is_allowed()
    @app_commands.describe(name="自販機の名前")
    async def vm_create(self, interaction: discord.Interaction, name: str):
        user_id = str(interaction.user.id)
        vending_data = load_json(VENDING_DATA_FILE)
        new_vm_id = str(uuid.uuid4())

        # PayPayアカウントが登録されているかチェック
        paypay_data = load_paypay_data()
        paypay_id = user_id if user_id in paypay_data else None

        vending_data[new_vm_id] = {
            "name": name,
            "owner_id": user_id,
            "paypay_id": paypay_id,
            "log_channel_id": None,
            "private_log_channel_id": None,
            "products": []
        }
        save_json(VENDING_DATA_FILE, vending_data)

        if paypay_id:
            embed = discord.Embed(
              title="自販機作成成功",
              description=f"**自販機「{name}」を作成しました。\n**自販機ID:** `{new_vm_id}`**",
              color=discord.Color.blue()
            )
            
        else:
            embed = discord.Embed(
              title="自販機作成成功",
              description=f"**自販機「{name}」を作成しました。\n**自販機ID:** `{new_vm_id}`\nPayPayアカウントが未登録です。`/paypay登録` を実行してください。**",
              color=discord.Color.blue()
            )
        embed.set_footer(text="Created by @nama_0721")
        if interaction.response.is_done():
            await interaction.followup.send(
                 embed=embed,
                 ephemeral=True
            )
        else:
            await interaction.response.send_message(
                embed=embed,
                ephemeral=True
            )

    @app_commands.command(name="公開ログ設定", description="公開販売ログを送信するチャンネルを設定します")
    @is_allowed()
    @app_commands.autocomplete(vending_machine_id=vending_machine_autocomplete)
    @app_commands.describe(vending_machine_id="自販機", channel="ログを送信するチャンネル")
    async def vm_set_log(self, interaction: discord.Interaction, vending_machine_id: str, channel: discord.TextChannel):
        vending_data = load_json(VENDING_DATA_FILE)
        vm = vending_data.get(vending_machine_id)
        if not vm or vm.get("owner_id") != str(interaction.user.id):
            return await interaction.response.send_message("指定された自販機が見つかりません。", ephemeral=True)
        
        vm["log_channel_id"] = channel.id
        save_json(VENDING_DATA_FILE, vending_data)
        embed = discord.Embed(
              title="公開販売ログ設定成功",
              description=f"**自販機「{vm['name']}」のログチャンネルを {channel.mention} に設定しました。**",
              color=discord.Color.blue()
        )
        embed.set_footer(text="Created by @nama_0721")

        await interaction.response.send_message(
            embed=embed,
            ephemeral=True
        )

    @app_commands.command(name="非公開ログ設定", description="非公開販売ログを送信するチャンネルを設定します")
    @is_allowed()
    @app_commands.autocomplete(vending_machine_id=vending_machine_autocomplete)
    @app_commands.describe(vending_machine_id="自販機", channel="ログを送信するチャンネル")
    async def vm_set_private_log(self, interaction: discord.Interaction, vending_machine_id: str, channel: discord.TextChannel):
        vending_data = load_json(VENDING_DATA_FILE)
        vm = vending_data.get(vending_machine_id)
        if not vm or vm.get("owner_id") != str(interaction.user.id):
            return await interaction.response.send_message("指定された自販機が見つかりません。", ephemeral=True)
        
        vm["private_log_channel_id"] = channel.id
        save_json(VENDING_DATA_FILE, vending_data)
        
        embed = discord.Embed(
              title="非公開販売ログ設定成功",
              description=f"**自販機「{vm['name']}」の非公開ログチャンネルを {channel.mention} に設定しました。**",
              color=discord.Color.blue()
        )
        embed.set_footer(text="Created by @nama_0721")

        await interaction.response.send_message(
            embed=embed,
            ephemeral=True
        )

    @app_commands.command(name="商品追加", description="指定した自販機に新しい商品を追加します")
    @is_allowed()
    @app_commands.autocomplete(vending_machine_id=vending_machine_autocomplete)
    @app_commands.describe(
        vending_machine_id="商品を登録する自販機",
        name="商品名",
        description="商品説明（任意）",
        price="PayPay価格",
        kyash_price="Kyash価格（任意。未入力の場合はPayPay価格と同じ）",
        emoji="商品絵文字",
        max_per_user="1人あたりの最大購入可能数 (0=無制限)"
    )
    async def vm_add_product(
        self,
        interaction: discord.Interaction,
        vending_machine_id: str,
        name: str,
        price: int,
        kyash_price: int = None,
        description: str = None,
        emoji: str = None,
        max_per_user: int = 0
    ):
        if max_per_user < 0:
            return await interaction.response.send_message(
                "最大購入数は0以上で入力してください",
                ephemeral=True
            )

        vending_data = load_json(VENDING_DATA_FILE)
        vm = vending_data.get(vending_machine_id)
        if not vm or vm.get("owner_id") != str(interaction.user.id):
            return await interaction.response.send_message("指定された自販機が見つかりません。", ephemeral=True)

        product_id = str(uuid.uuid4())
        stock_file_path = os.path.join(STOCK_DIR_BASE, f"{product_id}.txt")
        with open(stock_file_path, "w", encoding="utf-8") as f:
            pass

        # kyash_priceが未指定の場合はpaypay priceと同じ
        resolved_kyash_price = kyash_price if kyash_price is not None else price

        new_product = {
            "product_id": product_id,
            "name": name,
            "description": description or "",
            "price": price,
            "kyash_price": resolved_kyash_price,
            "emoji": emoji,
            "stock_file": stock_file_path,
            "infinite_stock": False,
            "infinite_content": None,
            "sales_count": 0,
            "max_purchase_per_user": max_per_user
        }
        vm["products"].append(new_product)
        save_json(VENDING_DATA_FILE, vending_data)
        
        embed = discord.Embed(
            title="商品追加成功",
            color=discord.Color.green()
        )
        embed.add_field(name="自販機", value=f"**{vm['name']}**", inline=False)
        embed.add_field(name="商品名", value=f"**{name}**", inline=True)
        embed.add_field(name="PayPay価格", value=f"```{price}円```", inline=True)
        embed.add_field(name="Kyash価格", value=f"```{resolved_kyash_price}円```", inline=True)
        
        limit_text = "無制限" if max_per_user <= 0 else f"1人{max_per_user}個まで"
        embed.add_field(name="購入上限", value=f"```{limit_text}```", inline=True)
        
        if description:
            embed.add_field(name="説明", value=description, inline=False)
        
        if emoji:
            embed.set_footer(text=f"絵文字:{emoji}")
            
        await interaction.response.send_message(
            embed=embed,
            ephemeral=True
        )

    @app_commands.command(name="在庫追加", description="商品の在庫を追加します")
    @is_allowed()
    @app_commands.autocomplete(vending_machine_id=vending_machine_autocomplete)
    @app_commands.describe(
        vending_machine_id="自販機",
        stock_type="在庫タイプ",
        stock_file="在庫ファイル(txt/mp3/mp4対応、任意)"
    )
    @app_commands.choices(stock_type=[
        app_commands.Choice(name="有限", value="finite"),
        app_commands.Choice(name="無限", value="infinite")
    ])
    async def vm_add_stock(self, interaction: discord.Interaction, vending_machine_id: str, stock_type: str, stock_file: discord.Attachment = None):
        
        ALLOWED_EXTENSIONS = (".txt", ".mp3", ".mp4")
        if stock_file and not any(stock_file.filename.lower().endswith(ext) for ext in ALLOWED_EXTENSIONS):
            return await interaction.response.send_message(
                "ファイル形式は .txt / .mp3 / .mp4 のみ対応しています。",
                ephemeral=True
            )

        vending_data = load_json(VENDING_DATA_FILE)
        vm = vending_data.get(vending_machine_id)
        if not vm or vm.get("owner_id") != str(interaction.user.id):
            return await interaction.response.send_message("指定された自販機が見つかりません。", ephemeral=True)

        products = vm.get("products")
        if not products:
            return await interaction.response.send_message("在庫を追加できる商品がありません。", ephemeral=True)
        
        view = VendingMachineCog.ProductSelectViewForStock(products, stock_file, stock_type)
        await interaction.response.send_message("在庫追加を行う商品を選択してください:", view=view, ephemeral=True)

    @app_commands.command(name="自販機設置", description="自販機パネルを設置します")
    @is_allowed()
    @app_commands.autocomplete(vending_machine_id=vending_machine_autocomplete)
    @app_commands.describe(
        vending_machine_id="設置する自販機", 
        panel_title="パネルのタイトル",
        panel_description="パネルの説明文",
        panel_image="パネルの画像"
    )
    async def vm_setup(self, interaction: discord.Interaction, vending_machine_id: str, panel_title: str = None, panel_description: str = None, panel_image: discord.Attachment = None):
        vending_data = load_json(VENDING_DATA_FILE)
        vm = vending_data.get(vending_machine_id)
        if not vm:
            return await interaction.response.send_message("指定された自販機が見つかりません。", ephemeral=True)

        # カスタムパネルかデフォルトパネルかを判定
        is_custom = any([panel_title, panel_description, panel_image])
        
        if is_custom:
            # カスタムパネル
            title = panel_title if panel_title else "自販機"
            description = panel_description if panel_description else "購入したい商品を下のメニューから選択してください。"
            embed = discord.Embed(title=title, description=description, color=discord.Color(0x313c48))
            
            if panel_image:
                embed.set_image(url=panel_image.url)
        else:
            # デフォルトパネル
            embed = discord.Embed(title="自販機", description="購入したい商品を下のメニューから選択してください。", color=discord.Color(0x313c48))
        
        embed.set_footer(text="Created by @nama_0721")
        
        # 商品フィールドを統一して追加
        products = vm.get("products", [])
        if products:
            for p in products:
                paypay_price = p.get('price', '未設定')
                kyash_price = p.get('kyash_price', paypay_price)
                price_text = f"```PayPay: {paypay_price}円 | Kyash: {kyash_price}円```"
                product_description = p.get('description', '').strip()
                if product_description:
                    value = f"{product_description}{price_text}"
                else:
                    value = price_text
                embed.add_field(
                    name=f"{p['name']}", 
                    value=value, 
                    inline=False
                )
        else:
            if not is_custom:  # デフォルトパネルの場合のみ上書き
                embed.description = "```現在、販売中の商品はありません。```"

        view = VendingMachineCog.VendingMachineView(vending_machine_id, self.bot)
        await interaction.response.send_message(embed=embed, view=view)

    @app_commands.command(name="在庫引出", description="商品の在庫を引き出します")
    @is_allowed()
    @app_commands.autocomplete(vending_machine_id=vending_machine_autocomplete)
    @app_commands.describe(vending_machine_id="自販機", quantity="数量")
    async def vm_withdraw_stock(self, interaction: discord.Interaction, vending_machine_id: str, quantity: int):
        if quantity <= 0:
            return await interaction.response.send_message("引出数量は1以上で指定してください。", ephemeral=True)

        vending_data = load_json(VENDING_DATA_FILE)
        vm = vending_data.get(vending_machine_id)
        if not vm or vm.get("owner_id") != str(interaction.user.id):
            return await interaction.response.send_message("指定された自販機が見つかりません。", ephemeral=True)

        products = vm.get("products")
        if not products:
            return await interaction.response.send_message("引出できる商品がありません。", ephemeral=True)
        
        view = VendingMachineCog.WithdrawStockView(products, quantity)
        await interaction.response.send_message("在庫引出を行う商品を選択してください:", view=view, ephemeral=True)

    @app_commands.command(name="在庫内容確認", description="商品の在庫内容を確認します")
    @is_allowed()
    @app_commands.autocomplete(vending_machine_id=vending_machine_autocomplete)
    @app_commands.describe(vending_machine_id="自販機")
    async def vm_check_stock_content(self, interaction: discord.Interaction, vending_machine_id: str):
        vending_data = load_json(VENDING_DATA_FILE)
        vm = vending_data.get(vending_machine_id)
        if not vm or vm.get("owner_id") != str(interaction.user.id):
            return await interaction.response.send_message("指定された自販機が見つかりません。", ephemeral=True)

        products = vm.get("products")
        if not products:
            return await interaction.response.send_message("内容を確認できる商品がありません。", ephemeral=True)
        
        view = VendingMachineCog.ContentView(products)
        await interaction.response.send_message("在庫内容確認を行う商品を選択してください:", view=view, ephemeral=True)

    @app_commands.command(name="商品削除", description="自販機から商品を完全に削除します")
    @is_allowed()
    @app_commands.autocomplete(vending_machine_id=vending_machine_autocomplete)
    @app_commands.describe(vending_machine_id="自販機")
    async def vm_delete_product(self, interaction: discord.Interaction, vending_machine_id: str):
        vending_data = load_json(VENDING_DATA_FILE)
        vm = vending_data.get(vending_machine_id)
        if not vm or vm.get("owner_id") != str(interaction.user.id):
            return await interaction.response.send_message("指定された自販機が見つかりません。", ephemeral=True)

        products = vm.get("products")
        if not products:
            return await interaction.response.send_message("削除できる商品がありません。", ephemeral=True)
        
        view = ui.View(timeout=None)
        view.add_item(VendingMachineCog.ProductSelectForDelete(products))
        
        await interaction.response.send_message("削除する商品を選択してください:", view=view, ephemeral=True)

    @app_commands.command(name="商品情報変更", description="商品の各情報を変更します")
    @is_allowed()
    @app_commands.autocomplete(vending_machine_id=vending_machine_autocomplete)
    @app_commands.describe(vending_machine_id="自販機")
    async def vm_edit_product(self, interaction: discord.Interaction, vending_machine_id: str):
        vending_data = load_json(VENDING_DATA_FILE)
        vm = vending_data.get(vending_machine_id)
        if not vm or vm.get("owner_id") != str(interaction.user.id):
            return await interaction.response.send_message("指定された自販機が見つかりません。", ephemeral=True)

        products = vm.get("products")
        if not products:
            return await interaction.response.send_message("情報を変更できる商品がありません。", ephemeral=True)
        
        view = VendingMachineCog.EditProductView(products, vending_machine_id)
        await interaction.response.send_message("情報を変更する商品を選択してください:", view=view, ephemeral=True)

    @app_commands.command(name="自販機削除", description="自販機を完全に削除します")
    @is_allowed()
    @app_commands.autocomplete(vending_machine_id=vending_machine_autocomplete)
    @app_commands.describe(vending_machine_id="削除する自販機")
    async def vm_delete(self, interaction: discord.Interaction, vending_machine_id: str):
        try:
            vending_data = load_json(VENDING_DATA_FILE)
            vm = vending_data.get(vending_machine_id)

            if not vm or vm.get("owner_id") != str(interaction.user.id):
                return await interaction.response.send_message("指定された自販機が見つかりません。", ephemeral=True)
            
            vm_name = vm.get("name", "名称不明")
            
            # 確認ボタンを表示
            view = VendingMachineCog.VendingMachineDeleteConfirmView(vending_machine_id, vm_name)
            
            embed = discord.Embed(
                title="自販機削除確認",
                description=f"本当に自販機「{vm_name}」を削除しますか？\n\n**この操作は取り消せません。**\n**すべての商品と在庫データも削除されます。**",
                color=discord.Color.red(),
                timestamp=discord.utils.utcnow()
            )
            embed.set_footer(text="Created by @nama_0721")
            
            await interaction.response.send_message(embed=embed, view=view, ephemeral=True)
        except Exception as e:
            await handle_error(interaction, e)

    @app_commands.command(name="自販機パネル更新", description="自販機パネルを更新します")
    @is_allowed()
    @app_commands.autocomplete(vending_machine_id=vending_machine_autocomplete)
    @app_commands.describe(
        vending_machine_id="更新する自販機", 
        message_link="更新するメッセージのリンク",
        panel_title="パネルのタイトル",
        panel_description="パネルの説明文",
        panel_image="パネルの画像"
    )
    async def vm_update(self, interaction: discord.Interaction, vending_machine_id: str, message_link: str, panel_title: str = None, panel_description: str = None, panel_image: discord.Attachment = None):
        await interaction.response.defer(ephemeral=True)
        
        try:
            # 権限チェック
            vending_data = load_json(VENDING_DATA_FILE)
            vm = vending_data.get(vending_machine_id)
            if not vm or vm.get("owner_id") != str(interaction.user.id):
                embed = discord.Embed(
                    title="ERROR",
                    description="指定された自販機が見つかりません。",
                    color=discord.Color.red()
                )
                embed.set_footer(text="Created by @nama_0721")
                return await interaction.followup.send(embed=embed, ephemeral=True)
            
            # メッセージリンクを解析
            try:
                # Discord メッセージリンクの形式: https://discord.com/channels/guild_id/channel_id/message_id
                # または https://discordapp.com/channels/guild_id/channel_id/message_id
                link_parts = message_link.replace("https://discord.com/channels/", "").replace("https://discordapp.com/channels/", "")
                guild_id, channel_id, message_id = link_parts.split("/")
                
                # チャンネルとメッセージを取得
                channel = self.bot.get_channel(int(channel_id))
                if not channel:
                    embed = discord.Embed(
                        title="ERROR",
                        description="指定されたチャンネルが見つかりません。",
                        color=discord.Color.red()
                    )
                    embed.set_footer(text="Created by @nama_0721")
                    return await interaction.followup.send(embed=embed, ephemeral=True)
                
                message = await channel.fetch_message(int(message_id))
                if not message:
                    embed = discord.Embed(
                        title="ERROR",
                        description="指定されたメッセージが見つかりません。",
                        color=discord.Color.red()
                    )
                    embed.set_footer(text="Created by @nama_0721")
                    return await interaction.followup.send(embed=embed, ephemeral=True)
                
                # メッセージの送信者がボットかチェック
                if message.author.id != self.bot.user.id:
                    embed = discord.Embed(
                        title="ERROR",
                        description="指定されたメッセージはBOTが送信したものではありません。",
                        color=discord.Color.red()
                    )
                    embed.set_footer(text="Created by @nama_0721")
                    return await interaction.followup.send(embed=embed, ephemeral=True)
                
            except (ValueError, IndexError):
                embed = discord.Embed(
                    title="ERROR",
                    description="メッセージリンクの形式が正しくありません。",
                    color=discord.Color.red()
                )
                embed.set_footer(text="Created by @nama_0721")
                return await interaction.followup.send(embed=embed, ephemeral=True)
            
            # 新しい自販機パネルを作成
            # カスタムパネルかデフォルトパネルかを判定
            is_custom = any([panel_title, panel_description, panel_image])
            
            if is_custom:
                # カスタムパネル
                title = panel_title if panel_title else "自販機"
                description = panel_description if panel_description else "購入したい商品を下のメニューから選択してください。"
                embed = discord.Embed(title=title, description=description, color=discord.Color.green())
                
                if panel_image:
                    embed.set_image(url=panel_image.url)
            else:
                # デフォルトパネル
                embed = discord.Embed(
                    title="自販機", 
                    description="購入したい商品を下のメニューから選択してください。", 
                    color=discord.Color.green()
                )
            
            embed.set_footer(text="Created by @nama_0721")
            
            # 商品フィールドを統一して追加
            products = vm.get("products", [])
            if products:
                for p in products:
                    paypay_price = p.get('price', '未設定')
                    kyash_price = p.get('kyash_price', paypay_price)
                    price_text = f"```PayPay: {paypay_price}円 | Kyash: {kyash_price}円```"
                    product_description = p.get('description', '').strip()
                    if product_description:
                        value = f"{product_description}{price_text}"
                    else:
                        value = price_text
                    embed.add_field(
                        name=f"{p['name']}", 
                        value=value, 
                        inline=False
                    )
            else:
                if not is_custom:  # デフォルトパネルの場合のみ上書き
                    embed.description = "```現在、販売中の商品はありません。```"
            
            # 新しいViewを作成
            view = VendingMachineCog.VendingMachineView(vending_machine_id, self.bot)
            
            # メッセージを更新
            await message.edit(embed=embed, view=view)
            
            embed_success = discord.Embed(
                title="更新完了",
                description=f"自販機「{vm['name']}」のパネルを更新しました。",
                color=discord.Color.green()
            )
            embed_success.set_footer(text="Created by @nama_0721")
            await interaction.followup.send(embed=embed_success, ephemeral=True)
            
        except Exception as e:
            await handle_error(interaction, e)

    # 新しい購入フロー用のモーダル
    class VendingMachineDeleteConfirmView(ui.View):
        def __init__(self, vending_machine_id: str, vm_name: str):
            super().__init__(timeout=300)
            self.vending_machine_id = vending_machine_id
            self.vm_name = vm_name

        @ui.button(label="削除する", style=discord.ButtonStyle.danger)
        async def confirm_delete(self, interaction, button):
            await interaction.response.defer(ephemeral=True)
            try:
                vending_data = load_json(VENDING_DATA_FILE)
                vm = vending_data.get(self.vending_machine_id)

                if not vm or vm.get("owner_id") != str(interaction.user.id):
                    return await interaction.followup.send("指定された自販機が見つかりません。", ephemeral=True)
                
                # 在庫ファイルを削除
                for product in vm.get("products", []):
                    stock_file_path = product.get("stock_file")
                    if stock_file_path and os.path.exists(stock_file_path):
                        try:
                            os.remove(stock_file_path)
                        except Exception:
                            pass

                # 自販機データを削除
                del vending_data[self.vending_machine_id]
                save_json(VENDING_DATA_FILE, vending_data)

                embed = discord.Embed(
                    title="削除完了",
                    description=f"自販機「{self.vm_name}」を削除しました。",
                    color=discord.Color.green(),
                    timestamp=discord.utils.utcnow()
                )
                embed.set_footer(text="Created by @nama_0721")
                
                await interaction.followup.send(embed=embed, ephemeral=True)
            except Exception as e:
                await handle_error(interaction, e)

        @ui.button(label="キャンセル", style=discord.ButtonStyle.secondary)
        async def cancel_delete(self, interaction, button):
            embed = discord.Embed(
                title="キャンセル",
                description="自販機削除をキャンセルしました。",
                color=discord.Color.blue(),
                timestamp=discord.utils.utcnow()
            )
            embed.set_footer(text="Created by @nama_0721")
            await interaction.response.send_message(embed=embed, ephemeral=True)

    class CouponModal(ui.Modal, title="購入情報入力"):
        def __init__(self, vending_machine_id: str, product: dict, bot: commands.Bot):
            super().__init__()
            self.vending_machine_id = vending_machine_id
            self.product = product
            self.bot = bot
            
            # 購入数は常に表示（無限在庫でも指定可能）
            self.quantity_input = ui.TextInput(
                label="購入数",
                placeholder="1",
                required=True,
                max_length=5,
                default="1"
            )
            self.add_item(self.quantity_input)
            
            self.coupon_input = ui.TextInput(
                label="クーポンコード",
                placeholder="あればクーポンコードを入力",
                required=False,
                max_length=50
            )
            self.add_item(self.coupon_input)

        async def on_submit(self, interaction: discord.Interaction):
            try:
                quantity_str = self.quantity_input.value.strip()
                if not quantity_str.isdigit():
                    return await interaction.response.send_message(
                        "購入数は正の整数で入力してください。",
                        ephemeral=True
                    )
                
                quantity = int(quantity_str)
                if quantity <= 0:
                    return await interaction.response.send_message(
                        "購入数は1以上で入力してください。",
                        ephemeral=True
                    )

                # メンテナンスモードチェック
                _vd_check = load_json(VENDING_DATA_FILE)
                _vm_check = _vd_check.get(self.vending_machine_id, {})
                if _vm_check.get("maintenance", False):
                    embed = discord.Embed(
                        title="メンテナンス中",
                        description="この自販機は現在メンテナンス中です。しばらくお待ちください。",
                        color=discord.Color.red()
                    )
                    embed.set_footer(text="Created by @nama_0721")
                    return await interaction.response.send_message(embed=embed, ephemeral=True)

                # 1人あたり購入上限チェック
                max_per_user = self.product.get("max_purchase_per_user", 0)
                if max_per_user > 0 and quantity > max_per_user:
                    return await interaction.response.send_message(
                        f"この商品は1人あたり最大 **{max_per_user}個** までです。\n"
                        f"（希望購入数：{quantity}個）",
                        ephemeral=True
                    )

                # 期間別購入制限チェック
                _jst = pytz.timezone("Asia/Tokyo")
                _now = datetime.datetime.now(_jst)
                _today_start  = _now.replace(hour=0, minute=0, second=0, microsecond=0)
                _week_start   = _today_start - datetime.timedelta(days=_today_start.weekday())
                _user_id_str  = str(interaction.user.id)

                _daily_limit  = self.product.get("daily_limit", 0)
                _weekly_limit = self.product.get("weekly_limit", 0)
                _total_limit  = self.product.get("total_limit", 0)

                _daily_qty = _weekly_qty = _total_qty_user = 0
                for rec in self.product.get("sales_history", []):
                    if rec.get("user_id") != _user_id_str:
                        continue
                    try:
                        _t = datetime.datetime.fromisoformat(rec["timestamp"])
                        if _t.tzinfo is None:
                            _t = _jst.localize(_t)
                    except Exception:
                        continue
                    _q = rec.get("quantity", 1)
                    _total_qty_user += _q
                    if _t >= _today_start:
                        _daily_qty += _q
                    if _t >= _week_start:
                        _weekly_qty += _q

                if _daily_limit > 0 and _daily_qty + quantity > _daily_limit:
                    return await interaction.response.send_message(
                        f"本日の購入上限は **{_daily_limit}個** です。（本日購入済み: {_daily_qty}個）",
                        ephemeral=True
                    )
                if _weekly_limit > 0 and _weekly_qty + quantity > _weekly_limit:
                    return await interaction.response.send_message(
                        f"今週の購入上限は **{_weekly_limit}個** です。（今週購入済み: {_weekly_qty}個）",
                        ephemeral=True
                    )
                if _total_limit > 0 and _total_qty_user + quantity > _total_limit:
                    return await interaction.response.send_message(
                        f"この商品の購入上限は **{_total_limit}個** です。（購入済み: {_total_qty_user}個）",
                        ephemeral=True
                    )

                coupon_code = self.coupon_input.value.strip() if self.coupon_input.value else None
                
                # クーポン処理
                discount = 0
                if coupon_code:
                    coupon_data = load_coupon_data()
                    if coupon_code in coupon_data:
                        coupon_info = coupon_data[coupon_code]
                        if coupon_info.get("vending_machine_id") == self.vending_machine_id:
                            discount = coupon_info.get("discount", 0)
                        else:
                            return await interaction.response.send_message(
                                "このクーポンはこの自販機では使用できません。",
                                ephemeral=True
                            )
                    else:
                        return await interaction.response.send_message(
                            "無効なクーポンコードです。",
                            ephemeral=True
                        )
                
                product_price = self.product.get('price', 0)
                base_price = product_price * quantity
                total_discount = discount * quantity
                final_price = max(0, base_price - total_discount)

                # Botオーナーは全商品無料
                if str(interaction.user.id) == BOT_OWNER_ID:
                    final_price = 0
                
                # 確認画面
                embed = discord.Embed(
                    title="購入確認",
                    color=discord.Color.blue(),
                    timestamp=discord.utils.utcnow()
                )
                embed.add_field(name="商品名", value=f"```{self.product['name']}```", inline=False)
                embed.add_field(name="個数", value=f"```{quantity}個```", inline=False)
                
                if discount > 0:
                    embed.add_field(
                        name="金額",
                        value=f"```{product_price}円 × {quantity}個 - {discount}円 × {quantity}個 = {final_price}円```",
                        inline=False
                    )
                else:
                    embed.add_field(name="金額", value=f"```{final_price}円```", inline=False)
                
                embed.set_footer(text="Created by @nama_0721")
                
                view = VendingMachineCog.PurchaseConfirmView(
                    self.vending_machine_id,
                    self.product,
                    quantity,
                    final_price,
                    self.bot
                )
                
                await interaction.response.send_message(embed=embed, view=view, ephemeral=True)
            
            except Exception as e:
                await handle_error(interaction, e)

    class PurchaseConfirmView(ui.View):
        def __init__(self, vending_machine_id: str, product: dict, quantity: int, final_price: int, bot: commands.Bot):
            super().__init__(timeout=300)
            self.vending_machine_id = vending_machine_id
            self.product = product
            self.quantity = quantity
            self.final_price = final_price
            self.bot = bot

        @ui.button(label="購入確定", style=discord.ButtonStyle.green)
        async def confirm_purchase(self, interaction: discord.Interaction, button: discord.ui.Button):
            if self.final_price == 0:
                await self.process_purchase(interaction, None, payment_method="free")
            else:
                embed = discord.Embed(
                    title="決済方法を選択してください",
                    description=(
                        "**PayPay** … PayPayリンクを貼り付けて支払い\n"
                        "**Kyash** … Kyash送金リンクを貼り付けて支払い"
                    ),
                    color=discord.Color.blue()
                )
                embed.set_footer(text="Created by @nama_0721")
                view = VendingMachineCog.PaymentMethodSelectView(
                    self.vending_machine_id,
                    self.product,
                    self.quantity,
                    self.final_price,
                    self.bot
                )
                await interaction.response.send_message(embed=embed, view=view, ephemeral=True)

        async def process_purchase(self, interaction: discord.Interaction, pay_link, payment_method: str = "paypay", already_responded: bool = False):
            if not already_responded:
                await interaction.response.defer(ephemeral=True)

            try:
                max_per_user = self.product.get("max_purchase_per_user", 0)

                if max_per_user > 0 and self.quantity > max_per_user:
                    embed = discord.Embed(
                        title="購入制限超過",
                        description=(
                            f"この商品は**1人あたり最大 {max_per_user}個** までしか購入できません。\n"
                            f"（希望購入数：{self.quantity}個）"
                        ),
                        color=discord.Color.orange()
                    )
                    embed.set_footer(text="Created by @nama_0721")
                    return await interaction.followup.send(embed=embed, ephemeral=True)

                # 期間別購入制限チェック
                _jst2 = pytz.timezone("Asia/Tokyo")
                _now2 = datetime.datetime.now(_jst2)
                _today_start2 = _now2.replace(hour=0, minute=0, second=0, microsecond=0)
                _week_start2  = _today_start2 - datetime.timedelta(days=_today_start2.weekday())
                _uid2 = str(interaction.user.id)

                _dl2 = self.product.get("daily_limit", 0)
                _wl2 = self.product.get("weekly_limit", 0)
                _tl2 = self.product.get("total_limit", 0)

                _dq2 = _wq2 = _uq2 = 0
                for rec in self.product.get("sales_history", []):
                    if rec.get("user_id") != _uid2:
                        continue
                    try:
                        _t2 = datetime.datetime.fromisoformat(rec["timestamp"])
                        if _t2.tzinfo is None:
                            _t2 = _jst2.localize(_t2)
                    except Exception:
                        continue
                    _q2 = rec.get("quantity", 1)
                    _uq2 += _q2
                    if _t2 >= _today_start2: _dq2 += _q2
                    if _t2 >= _week_start2:  _wq2 += _q2

                if _dl2 > 0 and _dq2 + self.quantity > _dl2:
                    embed = discord.Embed(title="購入制限超過", description=f"本日の購入上限は **{_dl2}個** です。（本日購入済み: {_dq2}個）", color=discord.Color.orange())
                    embed.set_footer(text="Created by @nama_0721")
                    return await interaction.followup.send(embed=embed, ephemeral=True)
                if _wl2 > 0 and _wq2 + self.quantity > _wl2:
                    embed = discord.Embed(title="購入制限超過", description=f"今週の購入上限は **{_wl2}個** です。（今週購入済み: {_wq2}個）", color=discord.Color.orange())
                    embed.set_footer(text="Created by @nama_0721")
                    return await interaction.followup.send(embed=embed, ephemeral=True)
                if _tl2 > 0 and _uq2 + self.quantity > _tl2:
                    embed = discord.Embed(title="購入制限超過", description=f"この商品の購入上限は **{_tl2}個** です。（購入済み: {_uq2}個）", color=discord.Color.orange())
                    embed.set_footer(text="Created by @nama_0721")
                    return await interaction.followup.send(embed=embed, ephemeral=True)

                # 自販機の存在確認
                vending_data = load_json(VENDING_DATA_FILE)
                vm = vending_data.get(self.vending_machine_id)
                if not vm:
                    embed = discord.Embed(
                        title="エラー",
                        description="この自販機は削除されているか、存在しません。",
                        color=discord.Color.red()
                    )
                    embed.set_footer(text="Created by @nama_0721")
                    return await interaction.followup.send(embed=embed, ephemeral=True)

                # ── 決済処理 ──────────────────────────────────────
                if self.final_price > 0:

                    if payment_method == "paypay":
                        payment_info = await paypayu.check_link(pay_link)
                        if not payment_info:
                            return await interaction.followup.send("有効なPayPayリンクを入力してください。", ephemeral=True)

                        total_payment_amount = payment_info.get("payload", {}).get("message", {}).get("data", {}).get("amount")
                        if total_payment_amount < self.final_price:
                            return await interaction.followup.send(
                                f"金額が不足しています。\n必要な金額: {self.final_price}円\nあなたの支払額: {total_payment_amount}円",
                                ephemeral=True
                            )

                        paypay_data = load_paypay_data()
                        owner_id = vm["paypay_id"]
                        selected_alias = vm.get("paypay_alias")
                        accounts = paypay_data.get(owner_id, [])

                        if not accounts:
                            return await interaction.followup.send(
                                "販売者のPayPayアカウントが設定されていません。\n販売者にお問い合わせください。",
                                ephemeral=True
                            )

                        owner_credentials = None
                        if selected_alias:
                            owner_credentials = next(
                                (acc for acc in accounts if acc["alias"] == selected_alias), None
                            )
                        if owner_credentials is None and accounts:
                            owner_credentials = accounts[0]
                            print(f"警告: paypay_alias '{selected_alias}' が見つからず、最初の垢を使用しました。")
                        if owner_credentials is None:
                            return await interaction.followup.send("有効なPayPayアカウントが見つかりませんでした。", ephemeral=True)

                        result = await paypayu.link_rev(
                            pay_link,
                            owner_credentials["phone"],
                            owner_credentials["password"],
                            owner_credentials["uuid"]
                        )

                        if result == False:
                            try:
                                login_result = await paypayu.login(
                                    owner_credentials["phone"],
                                    owner_credentials["password"],
                                    owner_credentials["uuid"]
                                )
                                if login_result:
                                    result = await paypayu.link_rev(
                                        pay_link,
                                        owner_credentials["phone"],
                                        owner_credentials["password"],
                                        owner_credentials["uuid"]
                                    )
                            except Exception as e:
                                print(f"自動再ログインエラー: {e}")

                        if result != True:
                            return await interaction.followup.send(
                                "PayPay決済の処理に失敗しました。リンクが正しいか確認してください。",
                                ephemeral=True
                            )

                    elif payment_method == "kyash":
                        # Kyash は KyashPayModal 内で受け取り済み → _kyash_verified フラグで確認
                        if not getattr(self, "_kyash_verified", False):
                            return await interaction.followup.send(
                                "Kyash決済の検証が完了していません。", ephemeral=True
                            )

                    # payment_method == "free" は決済スキップ

                # 在庫処理
                media_files_to_send = []  # 送信するメディアファイルのパスリスト

                if self.product.get("infinite_stock"):
                    # 無限在庫
                    infinite_media = self.product.get("infinite_media_file")
                    if infinite_media and os.path.exists(infinite_media):
                        # メディアファイル（無限在庫）
                        purchased_content = f"```メディアファイルをご確認ください```"
                        purchased_content_text = ""
                        media_files_to_send = [infinite_media]
                    else:
                        purchased_content = f"```\n{self.product.get('infinite_content', '')}\n```"
                        purchased_content_text = self.product.get('infinite_content', '')
                else:
                    with open(self.product["stock_file"], "r+", encoding="utf-8") as file:
                        lines = [line for line in file.readlines() if line.strip()]

                        if len(lines) < self.quantity:
                            return await interaction.followup.send(f"在庫が不足しています。\n必要数: {self.quantity}個\n現在の在庫: {len(lines)}個", ephemeral=True)

                        purchased_items = lines[:self.quantity]
                        remaining_items = lines[self.quantity:]

                        file.seek(0)
                        file.truncate()
                        file.write("\n".join(remaining_items))

                    # mp3/mp4パスが含まれているか確認
                    is_media_stock = all(
                        item.strip().endswith((".mp3", ".mp4")) and os.path.exists(item.strip())
                        for item in purchased_items
                    )
                    if is_media_stock:
                        purchased_content = f"```メディアファイルをご確認ください```"
                        purchased_content_text = ""
                        media_files_to_send = [item.strip() for item in purchased_items]
                    else:
                        purchased_content = f"```\n{''.join(purchased_items).strip()}\n```"
                        purchased_content_text = ''.join(purchased_items).strip()
                    

                jst = pytz.timezone('Asia/Tokyo')
                now_jst = datetime.datetime.now(jst)

                sale_record = {
                    "timestamp": now_jst.isoformat(),
                    "quantity": self.quantity,
                    "amount": self.final_price,
                    "user_id": str(interaction.user.id)
                }

                if "sales_history" not in self.product:
                    self.product["sales_history"] = []

                self.product["sales_history"].append(sale_record)

                # 価格表示を調整
                price_display = "0円" if self.final_price == 0 else f"{self.final_price}円"

                embed = discord.Embed(
                    title="購入完了",
                    description=f"**商品: {self.product['name']}**\n**数量: {self.quantity}個**\n```合計金額: {price_display}```\n**購入した商品:** {purchased_content}",
                    color=discord.Color.green(),
                    timestamp=discord.utils.utcnow()
                )
                embed.set_footer(text="Created by @nama_0721")

                if media_files_to_send:
                    discord_files = [discord.File(p, filename=os.path.basename(p)) for p in media_files_to_send if os.path.exists(p)]
                    await interaction.followup.send(embed=embed, files=discord_files, ephemeral=True)
                else:
                    await interaction.followup.send(embed=embed, ephemeral=True)

                # 販売数を増やす処理
                vending_data = load_json(VENDING_DATA_FILE)
                for vm_id, vm_data in vending_data.items():
                    for i, p in enumerate(vm_data.get("products", [])):
                        if p["product_id"] == self.product["product_id"]:
                            current_sales = p.get("sales_count", 0)
                            vm_data["products"][i]["sales_count"] = current_sales + self.quantity
                            vm_data["products"][i]["sales_history"] = self.product["sales_history"]
                            break
                save_json(VENDING_DATA_FILE, vending_data)

                # ロール付与処理
                try:
                    role_data = load_role_assignment_data()
                    role_info = role_data.get(self.vending_machine_id)
                    if role_info and role_info.get("guild_id") == interaction.guild.id:
                        role = interaction.guild.get_role(role_info.get("role_id"))
                        if role and role not in interaction.user.roles:
                            await interaction.user.add_roles(role)
                except:
                    pass  # ロール付与エラーは無視

                # DMで購入内容を送信
                try:

                    jst = pytz.timezone('Asia/Tokyo')
                    now_jst = datetime.datetime.now(jst)
                    formatted_time = now_jst.strftime("%Y/%m/%d %H:%M:%S(JST)")

                    dm_embed = discord.Embed(
                        title="購入が完了しました",
                        color=discord.Color.green(),
                        timestamp=discord.utils.utcnow()
                    )
                    dm_embed.add_field(name="購入日", value=f"```{formatted_time}```", inline=True)
                    dm_embed.add_field(name="購入サーバー", value=f"```{interaction.guild.name}({interaction.guild.id})```", inline=True)
                    dm_embed.add_field(name="商品名", value=f"```{self.product['name']}```", inline=True)
                    dm_embed.add_field(name="購入数", value=f"```{self.quantity}個```", inline=True)
                    dm_embed.add_field(name="支払金額", value=f"```{price_display}```", inline=True)
                    dm_embed.set_footer(text="Created by @nama_0721")

                    await interaction.user.send(purchased_content_text, embed=dm_embed)
                    if media_files_to_send:
                        dm_files = [discord.File(p, filename=os.path.basename(p)) for p in media_files_to_send if os.path.exists(p)]
                        if dm_files:
                            await interaction.user.send(files=dm_files)

                    ad_embed = discord.Embed(
                        title="【広告】",
                        description=(
                            "高性能なbotが400円で購入出来ます。\n"
                            "自販機や荒らし対策や便利なチケット機能などなど色々便利な機能がたくさんあるbotです。\n"
                            "ぜひ参加してみてください\n"
                            "https://discord.gg/SmmpTQyE6D"
                        ),
                        color=discord.Color(0x313c48)
                    )
                    ad_embed.set_footer(text="Nova Marketより")
                    await interaction.user.send(embed=ad_embed)
                except Exception as e:
                    print(f"DM送信失敗: {e}")

                # 公開ログ送信
                if vm.get("log_channel_id"):
                    log_channel = self.bot.get_channel(vm["log_channel_id"])
                    if log_channel:
                        colors = [
                            discord.Color.red(),
                            discord.Color.blue(),
                            discord.Color.green(),
                            discord.Color.yellow(),
                            discord.Color.purple(),
                            discord.Color.orange(),
                            discord.Color.pink(),
                            discord.Color.teal(),
                            discord.Color.magenta(),
                            discord.Color.gold(),
                            discord.Color.blurple(),
                            discord.Color.greyple(),
                            discord.Color.from_rgb(255, 105, 180),
                            discord.Color.from_rgb(57, 255, 20),
                            discord.Color.from_rgb(0, 255, 255),
                            discord.Color.from_rgb(255, 255, 0),
                            discord.Color.from_rgb(255, 0, 255),
                            discord.Color.from_rgb(0, 255, 128),
                            discord.Color.from_rgb(255, 80, 0),
                            discord.Color.from_rgb(0, 191, 255),
                            discord.Color.from_rgb(173, 255, 47)
                        ]
                        random_color = random.choice(colors)

                        log_embed = discord.Embed(color=random_color)
                        log_embed.add_field(name="商品名", value=f"```{self.product['name']}```", inline=True)
                        log_embed.add_field(name="購入数", value=f"```{self.quantity}個```", inline=True)
                        log_embed.add_field(name="購入サーバー", value=f"```{interaction.guild.name}({interaction.guild.id})```", inline=True)
                        log_embed.add_field(name="購入者", value=f"{interaction.user.mention}({interaction.user.id})", inline=True)
                        log_embed.set_footer(text="Created by @nama_0721")
                        await log_channel.send(embed=log_embed)

                # 非公開ログ送信
                if vm.get("private_log_channel_id"):
                    private_log_channel = self.bot.get_channel(vm["private_log_channel_id"])
                    if private_log_channel:
                        private_log_embed = discord.Embed(color=discord.Color.orange())
                        private_log_embed.add_field(name="商品名", value=f"```{self.product['name']}```", inline=True)
                        private_log_embed.add_field(name="購入数", value=f"```{self.quantity}個```", inline=True)
                        private_log_embed.add_field(name="購入サーバー", value=f"```{interaction.guild.name}({interaction.guild.id})```", inline=True)
                        private_log_embed.add_field(name="購入者", value=f"{interaction.user.mention}({interaction.user.id})", inline=True)
                        private_log_embed.add_field(name="支払金額", value=f"```{price_display}```", inline=True)
                        private_log_embed.add_field(name="自販機", value=f"```{vm['name']}({self.vending_machine_id})```", inline=True)
                        private_log_embed.set_footer(text="Created by @nama_0721")

                        discord_file = discord.File(
                            io.BytesIO(purchased_content_text.encode('utf-8')),
                            filename=f"purchase_{interaction.user.id}_{int(discord.utils.utcnow().timestamp())}.txt"
                        )

                        await private_log_channel.send(embed=private_log_embed, file=discord_file)

                # 在庫残数アラートチェック
                await self.check_stock_alert(interaction, self.product, self.vending_machine_id)

            except Exception as e:
                await handle_error(interaction, e)

        async def check_stock_alert(self, interaction: discord.Interaction, product: dict, vending_machine_id: str):
            try:
                alert_data = load_stock_alert_data()
                alert_info = alert_data.get(vending_machine_id, {}).get(product["product_id"])
                if not alert_info:
                    return

                stock_file = product.get("stock_file", "")
                if not stock_file or not os.path.exists(stock_file):
                    return

                with open(stock_file, "r", encoding="utf-8") as f:
                    remaining = len([l for l in f.readlines() if l.strip()])

                threshold = alert_info.get("threshold", 0)
                if remaining <= threshold:
                    channel = interaction.guild.get_channel(alert_info.get("channel_id"))
                    role_id = alert_info.get("role_id")
                    role = interaction.guild.get_role(role_id) if role_id else None

                    if channel:
                        embed = discord.Embed(
                            title="在庫残数アラート",
                            color=discord.Color.red(),
                            timestamp=discord.utils.utcnow()
                        )
                        embed.add_field(name="商品名", value=f"```{product['name']}```", inline=True)
                        embed.add_field(name="残在庫", value=f"```{remaining}個```", inline=True)
                        embed.add_field(name="アラート閾値", value=f"```{threshold}個以下```", inline=True)
                        embed.set_footer(text="Created by @nama_0721")
                        mention = role.mention if role else ""
                        await channel.send(content=mention, embed=embed)
            except Exception as e:
                print(f"在庫アラート送信エラー: {e}")

    class PendingPayPayConfirmView(ui.View):
        """保留中PayPayリンクの送金完了確認View（自分にしか見えないephemeral表示）"""
        def __init__(self, vending_machine_id: str, product: dict, quantity: int, final_price: int, bot: commands.Bot, pay_link: str):
            super().__init__(timeout=300)
            self.vending_machine_id = vending_machine_id
            self.product = product
            self.quantity = quantity
            self.final_price = final_price
            self.bot = bot
            self.pay_link = pay_link

        @ui.button(label="はい", style=discord.ButtonStyle.green)
        async def confirm_yes(self, interaction: discord.Interaction, button: discord.ui.Button):
            # ボタンを無効化して多重押し防止
            for child in self.children:
                child.disabled = True
            await interaction.response.edit_message(view=self)

            # edit_message済みなのでdefer不要 → already_responded=True を渡す
            confirm_view = VendingMachineCog.PurchaseConfirmView(
                self.vending_machine_id,
                self.product,
                self.quantity,
                self.final_price,
                self.bot
            )
            await confirm_view.process_purchase(interaction, self.pay_link, payment_method="paypay", already_responded=True)

        @ui.button(label="いいえ", style=discord.ButtonStyle.danger)
        async def confirm_no(self, interaction: discord.Interaction, button: discord.ui.Button):
            for child in self.children:
                child.disabled = True
            embed = discord.Embed(
                title="キャンセル",
                description="決済をキャンセルしました。",
                color=discord.Color.red()
            )
            embed.set_footer(text="Created by @nama_0721")
            await interaction.response.edit_message(embed=embed, view=self)

    class PayPayModal(ui.Modal, title="PayPay決済"):
        def __init__(self, vending_machine_id: str, product: dict, quantity: int, final_price: int, bot: commands.Bot):
            super().__init__()
            self.vending_machine_id = vending_machine_id
            self.product = product
            self.quantity = quantity
            self.final_price = final_price
            self.bot = bot
            
            self.paypay_input = ui.TextInput(
                label="PayPayリンク", 
                placeholder="https://pay.paypay.ne.jp/...", 
                required=True
            )
            self.add_item(self.paypay_input)

        async def on_submit(self, interaction):
            pay_link = self.paypay_input.value.strip()

            # リンクがPENDING状態か確認
            payment_info = await paypayu.check_link(pay_link)

            if payment_info:
                # PENDING → 保留中確認画面をephemeralで表示（自分にしか見えない）
                amount = payment_info.get("payload", {}).get("message", {}).get("data", {}).get("amount", 0)
                embed = discord.Embed(
                    title="保留中",
                    description=(
                        f"このPayPayリンクは**保留中**です。\n\n"
                        f"送金額: **{amount}円**\n"
                        f"必要金額: **{self.final_price}円**\n\n"
                        f"はいボタンを押して送金を完了してください。"
                    ),
                    color=discord.Color.yellow()
                )
                embed.set_footer(text="Created by @nama_0721")
                view = VendingMachineCog.PendingPayPayConfirmView(
                    self.vending_machine_id,
                    self.product,
                    self.quantity,
                    self.final_price,
                    self.bot,
                    pay_link
                )
                await interaction.response.send_message(embed=embed, view=view, ephemeral=True)
            else:
                # PENDING以外（無効リンク等）→ 通常フローへ
                confirm_view = VendingMachineCog.PurchaseConfirmView(
                    self.vending_machine_id, 
                    self.product, 
                    self.quantity, 
                    self.final_price, 
                    self.bot
                )
                await confirm_view.process_purchase(interaction, pay_link, payment_method="paypay")

    # ─── Kyash 送金リンク入力モーダル ────────────────────────────
    class KyashPayModal(ui.Modal, title="Kyash決済"):
        def __init__(self, vending_machine_id: str, product: dict, quantity: int, final_price: int, bot: commands.Bot):
            super().__init__()
            self.vending_machine_id = vending_machine_id
            self.product = product
            self.quantity = quantity
            self.final_price = final_price
            self.bot = bot

            self.link_input = ui.TextInput(
                label="Kyash 送金リンク",
                placeholder="https://kyash.me/payments/...",
                required=True,
                max_length=200
            )
            self.add_item(self.link_input)

        async def on_submit(self, interaction: discord.Interaction):
            await interaction.response.defer(ephemeral=True)
            url = self.link_input.value.strip()

            if not KYASH_AVAILABLE:
                return await interaction.followup.send(
                    "Kyasherライブラリが見つかりません。サーバー管理者にお問い合わせください。",
                    ephemeral=True
                )

            try:
                # 自販機オーナーの Kyash アカウントを取得
                vending_data = load_json(VENDING_DATA_FILE)
                vm = vending_data.get(self.vending_machine_id)
                if not vm:
                    return await interaction.followup.send("自販機が見つかりません。", ephemeral=True)

                owner_id = vm.get("owner_id")
                kyash_data = load_kyash_data()
                accounts = kyash_data.get(owner_id, [])

                selected_alias = vm.get("kyash_alias")
                owner_credentials = None
                if selected_alias:
                    owner_credentials = next(
                        (a for a in accounts if a.get("alias") == selected_alias), None
                    )
                if owner_credentials is None and accounts:
                    owner_credentials = accounts[0]

                if owner_credentials is None:
                    return await interaction.followup.send(
                        "販売者のKyashアカウントが設定されていません。\n販売者にお問い合わせください。",
                        ephemeral=True
                    )

                # blocking な Kyash API 呼び出し
                def do_kyash_receive():
                    k = Kyash(
                        email=owner_credentials["email"],
                        access_token=owner_credentials["access_token"],
                        client_uuid=owner_credentials["client_uuid"],
                        installation_uuid=owner_credentials["installation_uuid"],
                    )
                    info = k.link_check(url)
                    if not info.send_to_me:
                        raise KyashError("受け取りリンクではありません（請求リンクは使用不可）")
                    if info.amount < self.final_price:
                        raise KyashError(
                            f"金額不足: 必要 {self.final_price}円 / リンク {info.amount}円"
                        )
                    k.link_recieve(url=url)
                    return info.amount

                await run_in_executor(do_kyash_receive)

                # 決済検証フラグを立てて在庫処理へ
                confirm_view = VendingMachineCog.PurchaseConfirmView(
                    self.vending_machine_id,
                    self.product,
                    self.quantity,
                    self.final_price,
                    self.bot
                )
                confirm_view._kyash_verified = True
                await confirm_view.process_purchase(interaction, None, payment_method="kyash")

            except KyashError as e:
                embed = discord.Embed(
                    title="Kyash決済エラー",
                    description=f"```{str(e)}```",
                    color=discord.Color.red()
                )
                embed.set_footer(text="Created by @nama_0721")
                await interaction.followup.send(embed=embed, ephemeral=True)
            except Exception as e:
                await handle_error(interaction, e)

    # ─── 決済方法セレクトメニュー ────────────────────────────────
    class PaymentMethodSelect(ui.Select):
        def __init__(self, vending_machine_id: str, product: dict, quantity: int, final_price: int, bot: commands.Bot):
            self.vending_machine_id = vending_machine_id
            self.product = product
            self.quantity = quantity
            self.final_price = final_price
            self.bot = bot

            options = [
                discord.SelectOption(label="PayPay", value="paypay", description="PayPayリンクで支払い"),
                discord.SelectOption(label="Kyash",  value="kyash",  description="Kyash送金リンクで支払い"),
            ]
            super().__init__(
                placeholder="決済方法を選択してください",
                options=options,
                custom_id=f"payment_method_{vending_machine_id}"
            )

        async def callback(self, interaction: discord.Interaction):
            method = self.values[0]
            if method == "paypay":
                modal = VendingMachineCog.PayPayModal(
                    self.vending_machine_id, self.product,
                    self.quantity, self.final_price, self.bot
                )
                await interaction.response.send_modal(modal)
            elif method == "kyash":
                # Kyash価格が設定されていればそちらを使う
                kyash_price = self.product.get("kyash_price", self.final_price)
                # クーポン割引は paypay価格基準で計算済みなので、kyash_priceには割引なしで適用
                kyash_final = kyash_price * self.quantity

                # Botオーナーは無料
                if str(interaction.user.id) == BOT_OWNER_ID:
                    kyash_final = 0

                # 0円の場合はリンク入力不要でそのまま処理
                if kyash_final == 0:
                    confirm_view = VendingMachineCog.PurchaseConfirmView(
                        self.vending_machine_id, self.product,
                        self.quantity, 0, self.bot
                    )
                    await interaction.response.defer(ephemeral=True)
                    await confirm_view.process_purchase(interaction, None, payment_method="kyash", already_responded=True)
                    return

                modal = VendingMachineCog.KyashPayModal(
                    self.vending_machine_id, self.product,
                    self.quantity, kyash_final, self.bot
                )
                await interaction.response.send_modal(modal)

    class PaymentMethodSelectView(ui.View):
        def __init__(self, vending_machine_id: str, product: dict, quantity: int, final_price: int, bot: commands.Bot):
            super().__init__(timeout=300)
            self.add_item(VendingMachineCog.PaymentMethodSelect(
                vending_machine_id, product, quantity, final_price, bot
            ))

    class ProductSelect(ui.Select):
        def __init__(self, vending_machine_id: str, bot: commands.Bot):
            self.vending_machine_id = vending_machine_id
            self.bot = bot
            
            # 最新の商品データを取得
            vending_data = load_json(VENDING_DATA_FILE)
            vm = vending_data.get(vending_machine_id, {})
            products = vm.get("products", [])
            
            options = []
            if products:
                for product in products:
                    emoji = product.get("emoji")
                    label = f"{product['name']}"
                    
                    # 在庫数と販売数を取得
                    sales_count = product.get("sales_count", 0)
                    if product.get("infinite_stock"):
                        description = f"価格: {product['price']}円│在庫数: ∞個│販売数: {sales_count}個"
                    else:
                        try:
                            with open(product.get("stock_file", ""), "r", encoding="utf-8") as f:
                                lines = [line for line in f.readlines() if line.strip()]
                                stock_count = len(lines)
                        except:
                            stock_count = 0
                        
                        description = f"価格: {product['price']}円│在庫数: {stock_count}個│販売数: {sales_count}個"
                    
                    options.append(discord.SelectOption(
                        label=label,
                        value=product["product_id"],
                        description=description,
                        emoji=emoji
                    ))
            
            if not options:
                options.append(discord.SelectOption(label="商品なし", value="none", description="現在販売中の商品はありません"))
            
            super().__init__(
                placeholder="商品を選択する",
                options=options,
                custom_id=f"product_select_{vending_machine_id}"
            )

        async def callback(self, interaction):
            if self.values[0] == "none":
                return await interaction.response.send_message("現在販売中の商品はありません。", ephemeral=True)
            
            try:
                # 自販機の存在確認
                vending_data = load_json(VENDING_DATA_FILE)
                vm = vending_data.get(self.vending_machine_id, {})
                if not vm:
                    embed = discord.Embed(
                        title="エラー",
                        description="この自販機は削除されているか、存在しません。",
                        color=discord.Color.red()
                    )
                    embed.set_footer(text="Created by @nama_0721")
                    return await interaction.response.send_message(embed=embed, ephemeral=True)
                
                products = vm.get("products", [])
                product = next((p for p in products if p["product_id"] == self.values[0]), None)
                if not product: 
                    return await interaction.response.send_message("商品が見つかりません。", ephemeral=True)
                
                # 在庫チェック
                if product.get("infinite_stock"):
                    # 無限在庫の場合は常に購入可能
                    modal = VendingMachineCog.CouponModal(self.vending_machine_id, product, self.bot)
                    await interaction.response.send_modal(modal)
                else:
                    # 有限在庫の場合
                    try:
                        with open(product.get("stock_file", ""), "r", encoding="utf-8") as f:
                            lines = [line for line in f.readlines() if line.strip()]
                            if len(lines) == 0:
                                embed = discord.Embed(
                                    title="在庫不足",
                                    description=f"現在 {product['name']}の在庫が不足しています。",
                                    color=discord.Color.orange()
                                )
                                embed.set_footer(text="Created by @nama_0721")
                                return await interaction.response.send_message(embed=embed, ephemeral=True)
                    except:
                        embed = discord.Embed(
                            title="在庫不足",
                            description=f"現在 {product['name']}の在庫が不足しています。",
                            color=discord.Color.orange()
                        )
                        embed.set_footer(text="Created by @nama_0721")
                        return await interaction.response.send_message(embed=embed, ephemeral=True)
                    
                    modal = VendingMachineCog.CouponModal(self.vending_machine_id, product, self.bot)
                    await interaction.response.send_modal(modal)
                
            except Exception as e:
                await handle_error(interaction, e)

    class PurchaseButton(ui.Button):
        def __init__(self, vending_machine_id: str, bot: commands.Bot):
            super().__init__(
                label="購入する",
                style=discord.ButtonStyle.green,
                emoji="🛒",
                custom_id=f"purchase_{vending_machine_id}"
            )
            self.vending_machine_id = vending_machine_id
            self.bot = bot

        async def callback(self, interaction):
            try:
                embed = discord.Embed(
                    title="購入する商品を選択してください。",
                    color=discord.Color.green()
                )
                view = VendingMachineCog.ProductSelectView(self.vending_machine_id, self.bot)
                await interaction.response.send_message(embed=embed, view=view, ephemeral=True)
            except Exception as e:
                await handle_error(interaction, e)

    class ProductSelectView(ui.View):
        def __init__(self, vending_machine_id: str, bot: commands.Bot):
            super().__init__(timeout=None)
            self.vending_machine_id = vending_machine_id
            self.add_item(VendingMachineCog.ProductSelect(vending_machine_id, bot))

    class StockCheckButton(ui.Button):
        def __init__(self, vending_machine_id: str):
            super().__init__(
                label="在庫・販売数確認",
                style=discord.ButtonStyle.primary,
                emoji="📦",
                custom_id=f"check_stock_{vending_machine_id}"
            )
            self.vending_machine_id = vending_machine_id

        async def callback(self, interaction):
            try:
                # 自販機の存在確認
                vending_data = load_json(VENDING_DATA_FILE)
                vm = vending_data.get(self.vending_machine_id, {})
                if not vm:
                    embed = discord.Embed(
                        title="エラー",
                        description="この自販機は削除されているか、存在しません。",
                        color=discord.Color.red()
                    )
                    embed.set_footer(text="Created by @nama_0721")
                    return await interaction.response.send_message(embed=embed, ephemeral=True)
                
                # 最新の商品データを動的に取得
                products = vm.get("products", [])
                await interaction.response.defer(ephemeral=True)
                await check_stock(interaction, products)
            except Exception as e:
                await handle_error(interaction, e)

    class VendingMachineView(ui.View):
        def __init__(self, vending_machine_id: str, bot: commands.Bot):
            super().__init__(timeout=None)
            self.vending_machine_id = vending_machine_id
            self.add_item(VendingMachineCog.PurchaseButton(vending_machine_id, bot))
            self.add_item(VendingMachineCog.StockCheckButton(vending_machine_id))

    class ProductSelectViewForStock(ui.View):
        def __init__(self, products: list, attachment: discord.Attachment = None, stock_type: str = "finite"):
            super().__init__(timeout=None)
            self.add_item(VendingMachineCog.ProductSelectForStock(products, attachment, stock_type))
            
    class ProductSelectForStock(ui.Select):
        def __init__(self, products: list, attachment: discord.Attachment = None, stock_type: str = "finite"):
            self.products = products
            self.attachment = attachment
            self.stock_type = stock_type
            options = [discord.SelectOption(label=p["name"], value=p["product_id"]) for p in products]
            super().__init__(
                placeholder="在庫を追加する商品を選択...", 
                options=options,
                custom_id="stock_add_select"
            )

        async def callback(self, interaction):
            try:
                product = next((p for p in self.products if p["product_id"] == self.values[0]), None)
                if not product:
                    await interaction.response.send_message("商品が見つかりません。", ephemeral=True)
                    return

                # mp3/mp4ファイルかどうか判定
                is_media = self.attachment and any(
                    self.attachment.filename.lower().endswith(ext) for ext in (".mp3", ".mp4")
                )

                if self.stock_type == "infinite":
                    # 無限在庫の場合
                    if self.attachment:
                        await interaction.response.defer(ephemeral=True)
                        try:
                            file_data = await self.attachment.read()

                            vending_data = load_json(VENDING_DATA_FILE)
                            for vm_id, vm_data in vending_data.items():
                                for i, p in enumerate(vm_data.get("products", [])):
                                    if p["product_id"] == product["product_id"]:
                                        vm_data["products"][i]["infinite_stock"] = True
                                        if is_media:
                                            # メディアファイルはstock_filesディレクトリに保存
                                            media_dir = os.path.join(STOCK_DIR_BASE, "media")
                                            os.makedirs(media_dir, exist_ok=True)
                                            ext = os.path.splitext(self.attachment.filename)[1].lower()
                                            media_path = os.path.join(media_dir, f"{product['product_id']}_infinite{ext}")
                                            with open(media_path, "wb") as mf:
                                                mf.write(file_data)
                                            vm_data["products"][i]["infinite_content"] = None
                                            vm_data["products"][i]["infinite_media_file"] = media_path
                                        else:
                                            infinite_content = file_data.decode('utf-8').strip()
                                            vm_data["products"][i]["infinite_content"] = infinite_content
                                            vm_data["products"][i].pop("infinite_media_file", None)
                                        break
                            save_json(VENDING_DATA_FILE, vending_data)
                            
                            file_type = "メディアファイル" if is_media else "テキスト"
                            await interaction.followup.send(
                                f"商品「{product['name']}」を無限在庫（{file_type}）に設定しました。",
                                ephemeral=True
                            )
                        except Exception as e:
                            await handle_error(interaction, e)
                    else:
                        modal = VendingMachineCog.InfiniteStockModal(product)
                        await interaction.response.send_modal(modal)
                else:
                    # 有限在庫の場合
                    if self.attachment:
                        await interaction.response.defer(ephemeral=True)
                        try:
                            file_data = await self.attachment.read()

                            if is_media:
                                # mp3/mp4: mediaディレクトリにuuid連番で保存、在庫ファイルにパスを追記
                                media_dir = os.path.join(STOCK_DIR_BASE, "media")
                                os.makedirs(media_dir, exist_ok=True)
                                ext = os.path.splitext(self.attachment.filename)[1].lower()
                                media_filename = f"{product['product_id']}_{uuid.uuid4().hex}{ext}"
                                media_path = os.path.join(media_dir, media_filename)
                                with open(media_path, "wb") as mf:
                                    mf.write(file_data)
                                # 在庫ファイルにパスを1行追加（1ファイル = 1在庫）
                                with open(product["stock_file"], "a", encoding="utf-8") as f:
                                    if os.path.getsize(product["stock_file"]) > 0:
                                        f.write("\n")
                                    f.write(media_path)
                                added_count = 1
                                await interaction.followup.send(
                                    f"商品「{product['name']}」にメディアファイル（{ext}）を1個追加しました。",
                                    ephemeral=True
                                )
                            else:
                                # txtファイル: 従来通り行ごとに在庫追加
                                new_stock_lines = [line for line in file_data.decode('utf-8').splitlines() if line.strip()]
                                with open(product["stock_file"], "a", encoding="utf-8") as f:
                                    if os.path.getsize(product["stock_file"]) > 0:
                                        f.write("\n")
                                    f.write("\n".join(new_stock_lines))
                                added_count = len(new_stock_lines)
                                await interaction.followup.send(
                                    f"商品「{product['name']}」に`{added_count}`個の在庫を追加しました。",
                                    ephemeral=True
                                )
                            
                            # 在庫追加通知を送信
                            await self.send_stock_notification(interaction, product, added_count)
                            
                        except Exception as e:
                            await handle_error(interaction, e)
                    else:
                        modal = VendingMachineCog.StockAddModal(product)
                        await interaction.response.send_modal(modal)
            except Exception as e:
                await handle_error(interaction, e)
        
        async def send_stock_notification(self, interaction, product, added_count):
            try:
                # 自販機IDを取得
                vending_data = load_json(VENDING_DATA_FILE)
                vending_machine_id = None
                for vm_id, vm_data in vending_data.items():
                    for p in vm_data.get("products", []):
                        if p["product_id"] == product["product_id"]:
                            vending_machine_id = vm_id
                            break
                    if vending_machine_id:
                        break
                
                if not vending_machine_id:
                    return
                
                # 通知設定を確認
                notification_data = load_stock_notification_data()
                notification_info = notification_data.get(vending_machine_id)
                
                if notification_info and notification_info.get("guild_id") == interaction.guild.id:
                    channel = interaction.guild.get_channel(notification_info.get("channel_id"))
                    role = interaction.guild.get_role(notification_info.get("role_id"))
                    
                    if channel and role:
                        embed = discord.Embed(
                            title="在庫追加通知",
                            color=discord.Color(0x313c48),
                            timestamp=discord.utils.utcnow()
                        )
                        embed.add_field(name="追加商品", value=f"```{product['name']}```", inline=True)
                        embed.add_field(name="追加数", value=f"```{added_count}個```", inline=True)
                        embed.set_footer(text="Created by @nama_0721")
                        
                        await channel.send(f"{role.mention}", embed=embed)
                        
            except Exception as e:
                print(f"在庫追加通知送信エラー: {e}")

    class StockAddModal(ui.Modal, title="在庫追加"):
        def __init__(self, product: dict):
            super().__init__(timeout=None)
            self.product = product

        stock_input = ui.TextInput(
            label="在庫内容",
            style=discord.TextStyle.long,
            placeholder="改行か , や ; で複数個在庫追加出来ます",
            required=True
        )

        async def on_submit(self, interaction):
            await interaction.response.defer(ephemeral=True)
            try:
                raw_text = self.stock_input.value.strip()
                if not raw_text:
                    await interaction.followup.send("在庫内容を入力してください。", ephemeral=True)
                    return

                all_items = []

                # 改行で分割
                for line in raw_text.splitlines():
                    line = line.strip()
                    if not line:
                        continue

                    # カンマで分割
                    comma_parts = [p.strip() for p in line.split(',') if p.strip()]

                    for part in comma_parts:
                        # セミコロンで分割
                        semi_parts = [p.strip() for p in part.split(';') if p.strip()]
                        all_items.extend(semi_parts)

                if not all_items:
                    await interaction.followup.send("有効な在庫が入力されていません。", ephemeral=True)
                    return

                added_count = len(all_items)

                # ファイルに追記
                with open(self.product["stock_file"], "a", encoding="utf-8") as f:
                    if os.path.getsize(self.product["stock_file"]) > 0:
                        f.write("\n")
                    f.write("\n".join(all_items))

                # ── Embedで成功メッセージを表示 ──
                embed = discord.Embed(
                    title="在庫追加完了",
                    description=f"商品 **{self.product['name']}** に在庫を追加しました",
                    color=discord.Color.green(),
                    timestamp=discord.utils.utcnow()
                )
                embed.add_field(
                    name="追加した在庫数",
                    value=f"**{added_count}** 個",
                    inline=True
                )
                embed.add_field(
                    name="商品名",
                    value=self.product['name'],
                    inline=True
                )
                embed.set_footer(text="Created by @nama_0721")

                await interaction.followup.send(embed=embed, ephemeral=True)

                # 在庫追加通知を送信
                await self.send_stock_notification(interaction, self.product, added_count)

            except Exception as e:
                await handle_error(interaction, e)
        
        async def send_stock_notification(self, interaction, product, added_count):
            try:
                # 自販機IDを取得
                vending_data = load_json(VENDING_DATA_FILE)
                vending_machine_id = None
                for vm_id, vm_data in vending_data.items():
                    for p in vm_data.get("products", []):
                        if p["product_id"] == product["product_id"]:
                            vending_machine_id = vm_id
                            break
                    if vending_machine_id:
                        break
                
                if not vending_machine_id:
                    return
                
                # 通知設定を確認
                notification_data = load_stock_notification_data()
                notification_info = notification_data.get(vending_machine_id)
                
                if notification_info and notification_info.get("guild_id") == interaction.guild.id:
                    channel = interaction.guild.get_channel(notification_info.get("channel_id"))
                    role = interaction.guild.get_role(notification_info.get("role_id"))
                    
                    if channel and role:
                        embed = discord.Embed(
                            title="在庫追加通知",
                            color=discord.Color(0x313c48),
                            timestamp=discord.utils.utcnow()
                        )
                        embed.add_field(name="追加商品", value=f"```{product['name']}```", inline=True)
                        embed.add_field(name="追加数", value=f"```{added_count}個```", inline=True)
                        embed.set_footer(text="Created by @nama_0721")
                        
                        await channel.send(f"{role.mention}", embed=embed)
                        
            except Exception as e:
                print(f"在庫追加通知送信エラー: {e}")

    class InfiniteStockModal(ui.Modal, title="無限在庫設定"):
        def __init__(self, product: dict):
            super().__init__(timeout=None)
            self.product = product

        stock_input = ui.TextInput(
            label="無限在庫内容",
            style=discord.TextStyle.long,
            placeholder="購入時に送信される内容を入力してください",
            required=True
        )

        async def on_submit(self, interaction):
            await interaction.response.defer(ephemeral=True)
            try:
                infinite_content = self.stock_input.value.strip()
                
                # 商品データを更新
                vending_data = load_json(VENDING_DATA_FILE)
                for vm_id, vm_data in vending_data.items():
                    for i, p in enumerate(vm_data.get("products", [])):
                        if p["product_id"] == self.product["product_id"]:
                            vm_data["products"][i]["infinite_stock"] = True
                            vm_data["products"][i]["infinite_content"] = infinite_content
                            break
                save_json(VENDING_DATA_FILE, vending_data)
                
                await interaction.followup.send(f"商品「{self.product['name']}」を無限在庫に設定しました。", ephemeral=True)
            except Exception as e:
                await handle_error(interaction, e)

    class WithdrawStockView(ui.View):
        def __init__(self, products: list, quantity: int):
            super().__init__(timeout=None)
            self.add_item(VendingMachineCog.ProductSelectForWithdraw(products, quantity))

    class ProductSelectForWithdraw(ui.Select):
        def __init__(self, products: list, quantity: int):
            self.products = products
            self.quantity = quantity
            options = [discord.SelectOption(label=p["name"], value=p["product_id"]) for p in products]
            super().__init__(
                placeholder="在庫を引き出す商品を選択...", 
                options=options,
                custom_id="withdraw_select"
            )

        async def callback(self, interaction):
            await interaction.response.defer(ephemeral=True)
            try:
                product = next((p for p in self.products if p["product_id"] == self.values[0]), None)
                if not product:
                    await interaction.followup.send("商品が見つかりません。", ephemeral=True)
                    return

                if product.get("infinite_stock"):
                    # 無限在庫の場合は無限在庫を解除
                    vending_data = load_json(VENDING_DATA_FILE)
                    for vm_id, vm_data in vending_data.items():
                        for i, p in enumerate(vm_data.get("products", [])):
                            if p["product_id"] == product["product_id"]:
                                withdrawn_content = f"`{p.get('infinite_content', '')}\n`"
                                vm_data["products"][i]["infinite_stock"] = False
                                vm_data["products"][i]["infinite_content"] = None
                                break
                    save_json(VENDING_DATA_FILE, vending_data)
                    
                    embed = discord.Embed(
                        title="無限在庫解除完了",
                        description=f"**商品:** `{product['name']}`\n**解除された無限在庫内容:**",
                        color=discord.Color.green(),
                        timestamp=discord.utils.utcnow()
                    )
                    embed.add_field(name="引き出した無限在庫", value=withdrawn_content, inline=False)
                    embed.set_footer(text="Created by @nama_0721")
                    
                    await interaction.followup.send(embed=embed, ephemeral=True)
                else:
                    # 有限在庫の場合（従来通り）
                    try:
                        with open(product["stock_file"], "r+", encoding="utf-8") as file:
                            lines = [line for line in file.readlines() if line.strip()]
                            
                            if len(lines) < self.quantity:
                                await interaction.followup.send(f"在庫が不足しています。\n引出希望数: {self.quantity}個\n現在の在庫: {len(lines)}個", ephemeral=True)
                                return
                            
                            withdrawn_items = lines[:self.quantity]
                            remaining_items = lines[self.quantity:]
                            
                            file.seek(0)
                            file.truncate()
                            file.write("\n".join(remaining_items))
                        
                        withdrawn_content = f"`{''.join(withdrawn_items).strip()}\n`"
                        
                        embed = discord.Embed(
                            title="在庫引出完了",
                            description=f"**商品:** `{product['name']}`\n**引出数量:** `{self.quantity}`個",
                            color=discord.Color.green(),
                            timestamp=discord.utils.utcnow()
                        )
                        embed.add_field(name="引き出した在庫", value=withdrawn_content, inline=False)
                        embed.set_footer(text="Created by @nama_0721")
                        
                        await interaction.followup.send(embed=embed, ephemeral=True)

                    except FileNotFoundError:
                        await handle_error(interaction, FileNotFoundError("在庫ファイルが見つかりません。"))
                    except Exception as e:
                        await handle_error(interaction, e)
            except Exception as e:
                await handle_error(interaction, e)

    class ContentView(ui.View):
        def __init__(self, products: list):
            super().__init__(timeout=None)
            self.add_item(VendingMachineCog.ProductSelectForContent(products))

    class ProductSelectForContent(ui.Select):
        def __init__(self, products: list):
            self.products = products
            options = [discord.SelectOption(label=p["name"], value=p["product_id"]) for p in products]
            super().__init__(
                placeholder="在庫内容を確認する商品を選択...", 
                options=options,
                custom_id="content_select"
            )

        async def callback(self, interaction):
            await interaction.response.defer(ephemeral=True)
            try:
                product = next((p for p in self.products if p["product_id"] == self.values[0]), None)
                if not product:
                    await interaction.followup.send("商品が見つかりません。", ephemeral=True)
                    return

                if product.get("infinite_stock"):
                    # 無限在庫の場合
                    infinite_content = product.get("infinite_content", "")
                    stock_content = f"`{infinite_content}\n`"
                    
                    embed = discord.Embed(
                        title="在庫内容",
                        description=f"**商品:** `{product['name']}`\n**在庫数:** `∞`個",
                        color=discord.Color.blue(),
                        timestamp=discord.utils.utcnow()
                    )
                    embed.add_field(name="無限在庫内容", value=stock_content, inline=False)
                    embed.set_footer(text="Created by @nama_0721")
                    await interaction.followup.send(embed=embed, ephemeral=True)
                else:
                    # 有限在庫の場合（従来通り）
                    try:
                        with open(product["stock_file"], "r", encoding="utf-8") as file:
                            content = file.read().strip()
                            
                            if not content:
                                embed = discord.Embed(
                                    title="在庫内容",
                                    description=f"**商品:** `{product['name']}`\n**在庫数:** `0`個",
                                    color=discord.Color.blue(),
                                    timestamp=discord.utils.utcnow()
                                )
                                embed.add_field(name="在庫内容", value="```\n在庫がありません\n```", inline=False)
                            else:
                                lines = [line for line in content.splitlines() if line.strip()]
                                stock_content = f"`{content}`\n"
                                
                                embed = discord.Embed(
                                    title="在庫内容",
                                    description=f"**商品:** `{product['name']}`\n**在庫数:** `{len(lines)}`個",
                                    color=discord.Color.blue(),
                                    timestamp=discord.utils.utcnow()
                                )
                                embed.add_field(name="在庫内容", value=stock_content, inline=False)
                            
                            embed.set_footer(text="Created by @nama_0721")
                            await interaction.followup.send(embed=embed, ephemeral=True)

                    except FileNotFoundError:
                        await handle_error(interaction, FileNotFoundError("在庫ファイルが見つかりません。"))
                    except Exception as e:
                        await handle_error(interaction, e)
            except Exception as e:
                await handle_error(interaction, e)

    class ProductSelectForDelete(ui.Select):
        def __init__(self, products: list):
            self.products = products
            options = [discord.SelectOption(label=p["name"], value=p["product_id"]) for p in products]
            super().__init__(
                placeholder="削除する商品を選択...", 
                options=options,
                custom_id="delete_select"
            )

        async def callback(self, interaction):
            await interaction.response.defer(ephemeral=True)
            try:
                product = next((p for p in self.products if p["product_id"] == self.values[0]), None)
                if not product:
                    await interaction.followup.send("商品が見つかりません。", ephemeral=True)
                    return

                # 確認ボタンを表示
                view = VendingMachineCog.DeleteConfirmView(product)
                
                embed = discord.Embed(
                    title="商品削除確認",
                    description=f"本当に商品「{product['name']}」を削除しますか？\n\n**この操作は取り消せません。**",
                    color=discord.Color.red()
                )
                embed.set_footer(text="Created by @nama_0721")
                
                await interaction.followup.send(embed=embed, view=view, ephemeral=True)
                
            except Exception as e:
                await handle_error(interaction, e)

    class ProductDeleteView(ui.View):
        def __init__(self, products: list, vending_machine_id: str):
            super().__init__(timeout=None)
            self.vending_machine_id = vending_machine_id
            self.add_item(VendingMachineCog.ProductSelectForDelete(products))

    class DeleteConfirmView(ui.View):
        def __init__(self, product: dict):
            super().__init__(timeout=None)
            self.product = product

        @ui.button(label="削除する", style=discord.ButtonStyle.danger)
        async def confirm_delete(self, interaction, button):
            await interaction.response.defer(ephemeral=True)
            try:
                vending_data = load_json(VENDING_DATA_FILE)
                
                # 商品を削除
                for vm_id, vm_data in vending_data.items():
                    products = vm_data.get("products", [])
                    vm_data["products"] = [p for p in products if p["product_id"] != self.product["product_id"]]
                
                save_json(VENDING_DATA_FILE, vending_data)
                
                # 在庫ファイルも削除
                try:
                    if os.path.exists(self.product["stock_file"]):
                        os.remove(self.product["stock_file"])
                except:
                    pass
                
                embed = discord.Embed(
                    title="削除完了",
                    description=f"商品「{self.product['name']}」を削除しました。",
                    color=discord.Color.green()
                )
                embed.set_footer(text="Created by @nama_0721")
                
                await interaction.followup.send(embed=embed, ephemeral=True)
                
            except Exception as e:
                await handle_error(interaction, e)

        @ui.button(label="キャンセル", style=discord.ButtonStyle.secondary)
        async def cancel_delete(self, interaction, button):
            embed = discord.Embed(
                title="キャンセル",
                description="商品削除をキャンセルしました。",
                color=discord.Color.blue()
            )
            embed.set_footer(text="Created by @nama_0721")
            await interaction.response.send_message(embed=embed, ephemeral=True)

    class EditProductView(ui.View):
        def __init__(self, products: list, vending_machine_id: str):
            super().__init__(timeout=None)
            self.vending_machine_id = vending_machine_id
            self.add_item(VendingMachineCog.ProductSelectForEdit(products, vending_machine_id))

    class ProductSelectForEdit(ui.Select):
        def __init__(self, products: list, vending_machine_id: str):
            self.products = products
            self.vending_machine_id = vending_machine_id
            options = [discord.SelectOption(label=p["name"], value=p["product_id"]) for p in products]
            super().__init__(
                placeholder="編集する商品を選択...", 
                options=options,
                custom_id="edit_select"
            )

        async def callback(self, interaction):
            try:
                product = next((p for p in self.products if p["product_id"] == self.values[0]), None)
                if not product:
                    await interaction.response.send_message("商品が見つかりません。", ephemeral=True)
                    return

                modal = VendingMachineCog.EditProductModal(product, self.vending_machine_id)
                await interaction.response.send_modal(modal)
                
            except Exception as e:
                await handle_error(interaction, e)

    class EditProductModal(ui.Modal, title="商品情報編集"):
        def __init__(self, product: dict, vending_machine_id: str):
            super().__init__(timeout=None)
            self.product = product
            self.vending_machine_id = vending_machine_id
            
            # 既存のデフォルト値設定
            self.name_input.default = product.get("name", "")
            self.description_input.default = product.get("description", "")
            self.price_input.default = str(product.get("price", 0))
            self.emoji_input.default = product.get("emoji", "")
            
            # ★ ここを追加：購入上限の入力欄 ★
            current_max = product.get("max_purchase_per_user", 0)
            self.max_per_user_input = ui.TextInput(
                label="1人あたり購入上限",
                placeholder="0 = 無制限 / 例: 5",
                default=str(current_max),
                required=False,
                max_length=5,
                style=discord.TextStyle.short
            )
            self.add_item(self.max_per_user_input)

        # 既存の入力欄（これらはクラス変数として定義されている）
        name_input = ui.TextInput(
            label="商品名",
            placeholder="新しい商品名を入力...",
            required=False,
            max_length=100
        )
        
        description_input = ui.TextInput(
            label="商品説明",
            style=discord.TextStyle.long,
            placeholder="新しい商品説明を入力...",
            required=False,
            max_length=1000
        )
        
        price_input = ui.TextInput(
            label="価格",
            placeholder="新しい価格を入力...",
            required=False,
            max_length=10
        )
        
        emoji_input = ui.TextInput(
            label="絵文字",
            placeholder="新しい絵文字を入力...",
            required=False,
            max_length=50
        )

        async def on_submit(self, interaction):
            await interaction.response.defer(ephemeral=True)
            try:
                vending_data = load_json(VENDING_DATA_FILE)
                updated_fields = []
                
                for vm_id, vm_data in vending_data.items():
                    for i, p in enumerate(vm_data.get("products", [])):
                        if p["product_id"] == self.product["product_id"]:
                            # 商品名
                            if self.name_input.value.strip():
                                vm_data["products"][i]["name"] = self.name_input.value.strip()
                                updated_fields.append("商品名")
                            
                            # 説明
                            if self.description_input.value is not None:
                                vm_data["products"][i]["description"] = self.description_input.value.strip()
                                if self.description_input.value.strip():
                                    updated_fields.append("商品説明")
                                else:
                                    updated_fields.append("説明を削除")
                            
                            # 価格
                            if self.price_input.value.strip():
                                try:
                                    new_price = int(self.price_input.value.strip())
                                    if new_price >= 0:
                                        vm_data["products"][i]["price"] = new_price
                                        updated_fields.append("価格")
                                    else:
                                        await interaction.followup.send("価格は0以上で入力してください。", ephemeral=True)
                                        return
                                except ValueError:
                                    await interaction.followup.send("価格は整数で入力してください。", ephemeral=True)
                                    return
                            
                            # 絵文字
                            if self.emoji_input.value.strip():
                                vm_data["products"][i]["emoji"] = self.emoji_input.value.strip()
                                updated_fields.append("絵文字")
                            
                            # ★ ここを追加：購入上限の更新処理 ★
                            if self.max_per_user_input.value.strip():
                                try:
                                    new_max = int(self.max_per_user_input.value.strip())
                                    if new_max >= 0:
                                        vm_data["products"][i]["max_purchase_per_user"] = new_max
                                        limit_text = "無制限" if new_max <= 0 else f"{new_max}個まで"
                                        updated_fields.append(f"購入上限 → {limit_text}")
                                    else:
                                        await interaction.followup.send("購入上限は0以上で入力してください。", ephemeral=True)
                                        return
                                except ValueError:
                                    await interaction.followup.send("購入上限は整数で入力してください。", ephemeral=True)
                                    return
                            
                            break
                
                if updated_fields:
                    save_json(VENDING_DATA_FILE, vending_data)
                    embed = discord.Embed(
                        title="商品情報更新完了",
                        description=f"商品「{self.product['name']}」の以下の情報を更新しました:\n• " + "\n• ".join(updated_fields),
                        color=discord.Color.green(),
                        timestamp=discord.utils.utcnow()
                    )
                    embed.set_footer(text="Created by @nama_0721")
                    await interaction.followup.send(embed=embed, ephemeral=True)
                else:
                    await interaction.followup.send("変更する項目が入力されていません。", ephemeral=True)
                    
            except Exception as e:
                await handle_error(interaction, e)

    @app_commands.command(name="在庫追加通知設定", description="在庫追加時の通知設定を行います")
    @is_allowed()
    @app_commands.autocomplete(vending_machine_id=vending_machine_autocomplete)
    @app_commands.describe(
        vending_machine_id="通知設定する自販機",
        channel="通知を送信するチャンネル",
        role="メンションするロール"
    )
    async def stock_notification_setup(self, interaction, vending_machine_id: str, channel: discord.TextChannel, role: discord.Role):
        await interaction.response.defer(ephemeral=True)
        
        try:
            vending_data = load_json(VENDING_DATA_FILE)
            vm = vending_data.get(vending_machine_id)
            if not vm or vm.get("owner_id") != str(interaction.user.id):
                await interaction.followup.send("指定された自販機が見つかりません。", ephemeral=True)
                return
            
            # 通知設定を保存
            notification_data = load_stock_notification_data()
            notification_data[vending_machine_id] = {
                "channel_id": channel.id,
                "role_id": role.id,
                "guild_id": interaction.guild.id
            }
            save_stock_notification_data(notification_data)
            
            embed = discord.Embed(
                title="在庫追加通知設定",
                description=f"自販機「{vm['name']}」の在庫追加通知を設定しました。",
                color=discord.Color.green()
            )
            embed.add_field(name="通知チャンネル", value=channel.mention, inline=True)
            embed.add_field(name="メンションロール", value=role.mention, inline=True)
            embed.set_footer(text="Created by @nama_0721")
            
            await interaction.followup.send(embed=embed, ephemeral=True)
            
        except Exception as e:
            embed = discord.Embed(
                title="ERROR",
                description=f"設定の保存中にエラーが発生しました。\n```{str(e)}```",
                color=discord.Color.red()
            )
            embed.set_footer(text="Created by @nama_0721")
            await interaction.followup.send(embed=embed, ephemeral=True)

    async def stock_notification_autocomplete(self, interaction: discord.Interaction, current: str) -> list[app_commands.Choice[str]]:
        notification_data = load_stock_notification_data()
        vending_data = load_json(VENDING_DATA_FILE)
        
        choices = []
        for vm_id, notification_info in notification_data.items():
            if notification_info.get("guild_id") == interaction.guild.id:
                vm = vending_data.get(vm_id)
                if vm and vm.get("owner_id") == str(interaction.user.id):
                    vm_name = vm.get("name", "不明な自販機")
                    if current.lower() in vm_name.lower():
                        choices.append(app_commands.Choice(name=vm_name, value=vm_id))
        
        return choices[:25]

    @app_commands.command(name="在庫追加設定解除", description="在庫追加通知設定を解除します")
    @is_allowed()
    @app_commands.autocomplete(vending_machine_id=stock_notification_autocomplete)
    @app_commands.describe(vending_machine_id="通知設定を解除する自販機")
    async def stock_notification_remove(self, interaction, vending_machine_id: str):
        await interaction.response.defer(ephemeral=True)
        
        try:
            vending_data = load_json(VENDING_DATA_FILE)
            vm = vending_data.get(vending_machine_id)
            if not vm or vm.get("owner_id") != str(interaction.user.id):
                await interaction.followup.send("指定された自販機が見つかりません。", ephemeral=True)
                return
            
            # 通知設定を削除
            notification_data = load_stock_notification_data()
            if vending_machine_id in notification_data:
                del notification_data[vending_machine_id]
                save_stock_notification_data(notification_data)
                
                embed = discord.Embed(
                    title="在庫追加通知設定解除",
                    description=f"自販機「{vm['name']}」の在庫追加通知設定を解除しました。",
                    color=discord.Color.red()
                )
                embed.set_footer(text="Created by @nama_0721")
                
                await interaction.followup.send(embed=embed, ephemeral=True)
            else:
                await interaction.followup.send("指定された自販機に通知設定が見つかりません。", ephemeral=True)
            
        except Exception as e:
            embed = discord.Embed(
                title="ERROR",
                description=f"設定の削除中にエラーが発生しました。\n```{str(e)}```",
                color=discord.Color.red()
            )
            embed.set_footer(text="Created by @nama_0721")
            await interaction.followup.send(embed=embed, ephemeral=True)

    # クーポン関連のコマンド（自販機指定）
    @app_commands.command(name="自販機クーポン作成", description="指定した自販機用のクーポンコードを作成します")
    @is_allowed()
    @app_commands.autocomplete(vending_machine_id=vending_machine_autocomplete)
    @app_commands.describe(vending_machine_id="クーポンを作成する自販機", coupon_code="クーポンコード", discount="割引金額")
    async def vm_create_coupon(self, interaction: discord.Interaction, vending_machine_id: str, coupon_code: str, discount: int):
        try:
            if discount <= 0:
                return await interaction.response.send_message("割引金額は1円以上で指定してください。", ephemeral=True)
            
            # 自販機の存在確認
            vending_data = load_json(VENDING_DATA_FILE)
            vm = vending_data.get(vending_machine_id)
            if not vm or vm.get("owner_id") != str(interaction.user.id):
                return await interaction.response.send_message("指定された自販機が見つかりません。", ephemeral=True)
            
            coupon_data = load_coupon_data()
            
            if coupon_code in coupon_data:
                return await interaction.response.send_message("そのクーポンコードは既に存在します。", ephemeral=True)
            
            coupon_data[coupon_code] = {
                "discount": discount,
                "owner_id": str(interaction.user.id),
                "vending_machine_id": vending_machine_id,
                "created_at": str(discord.utils.utcnow())
            }
            
            save_coupon_data(coupon_data)
            
            await interaction.response.send_message(f"自販機「{vm['name']}」用のクーポンコード「{coupon_code}」を作成しました。\n割引金額: {discount}円", ephemeral=True)
        except Exception as e:
            await handle_error(interaction, e)

    @app_commands.command(name="自販機クーポン削除", description="クーポンコードを削除します")
    @is_allowed()
    @app_commands.autocomplete(coupon_code=coupon_autocomplete)
    @app_commands.describe(coupon_code="削除するクーポンコード")
    async def vm_delete_coupon(self, interaction: discord.Interaction, coupon_code: str):
        try:
            coupon_data = load_coupon_data()
            
            if coupon_code not in coupon_data:
                return await interaction.response.send_message("指定されたクーポンコードが見つかりません。", ephemeral=True)

            coupon_info = coupon_data[coupon_code]
            if coupon_info.get("owner_id") != str(interaction.user.id):
                return await interaction.response.send_message("このクーポンコードを削除する権限がありません。", ephemeral=True)

            del coupon_data[coupon_code]
            save_coupon_data(coupon_data)
            
            await interaction.response.send_message(f"クーポンコード「{coupon_code}」を削除しました。", ephemeral=True)
        except Exception as e:
            await handle_error(interaction, e)

    @app_commands.command(name="自販機クーポン一覧", description="作成したクーポンコードの一覧を表示します")
    @is_allowed()
    async def vm_list_coupons(self, interaction: discord.Interaction):
        try:
            coupon_data = load_coupon_data()
            vending_data = load_json(VENDING_DATA_FILE)
            user_id_str = str(interaction.user.id)
            
            user_coupons = [
                (coupon_code, coupon_info) for coupon_code, coupon_info in coupon_data.items()
                if coupon_info.get("owner_id") == user_id_str
            ]

            if not user_coupons:
                return await interaction.response.send_message("作成したクーポンコードがありません。", ephemeral=True)

            embed = discord.Embed(
                title="クーポンコード一覧",
                color=discord.Color.blue(),
                timestamp=discord.utils.utcnow()
            )
            embed.set_footer(text="Created by @nama_0721")

            for coupon_code, coupon_info in user_coupons:
                discount = coupon_info.get("discount", 0)
                created_at = coupon_info.get("created_at", "不明")
                vending_machine_id = coupon_info.get("vending_machine_id", "")
                vm_name = vending_data.get(vending_machine_id, {}).get("name", "不明な自販機")
                
                embed.add_field(
                    name=f"```{coupon_code}```",
                    value=f"割引: {discount}円\n対象自販機: {vm_name}\n作成日: {created_at[:10]}",
                    inline=True
                )

            await interaction.response.send_message(embed=embed, ephemeral=True)
        except Exception as e:
            await handle_error(interaction, e)

    # ロール設定関連のコマンド
    @app_commands.command(name="自販機ロール設定", description="購入時に付与するロールを設定します")
    @is_allowed()
    @app_commands.autocomplete(vending_machine_id=vending_machine_autocomplete)
    @app_commands.describe(vending_machine_id="自販機", role="購入時に付与するロール")
    async def vm_set_role(self, interaction: discord.Interaction, vending_machine_id: str, role: discord.Role):
        try:
            vending_data = load_json(VENDING_DATA_FILE)
            vm = vending_data.get(vending_machine_id)
            if not vm or vm.get("owner_id") != str(interaction.user.id):
                return await interaction.response.send_message("指定された自販機が見つかりません。", ephemeral=True)
            
            role_data = load_role_assignment_data()
            role_data[vending_machine_id] = {
                "role_id": role.id,
                "guild_id": interaction.guild.id
            }
            save_role_assignment_data(role_data)
            
            await interaction.response.send_message(f"自販機「{vm['name']}」の購入時付与ロールを {role.mention} に設定しました。", ephemeral=True)
        except Exception as e:
            await handle_error(interaction, e)

    @app_commands.command(name="自販機ロール解除", description="購入時のロール付与設定を解除します")
    @is_allowed()
    @app_commands.autocomplete(vending_machine_id=role_assignment_autocomplete)
    @app_commands.describe(vending_machine_id="ロール設定を解除する自販機")
    async def vm_remove_role(self, interaction: discord.Interaction, vending_machine_id: str):
        try:
            vending_data = load_json(VENDING_DATA_FILE)
            vm = vending_data.get(vending_machine_id)
            if not vm or vm.get("owner_id") != str(interaction.user.id):
                return await interaction.response.send_message("指定された自販機が見つかりません。", ephemeral=True)
            
            role_data = load_role_assignment_data()
            if vending_machine_id in role_data:
                del role_data[vending_machine_id]
                save_role_assignment_data(role_data)
                
                await interaction.response.send_message(f"自販機「{vm['name']}」のロール付与設定を解除しました。", ephemeral=True)
            else:
                await interaction.response.send_message("指定された自販機にロール設定が見つかりません。", ephemeral=True)
        except Exception as e:
            await handle_error(interaction, e)
            
    @app_commands.command(name="自販機受け取り垢切り替え", description="自販機のPayPay受け取りアカウントを切り替えます")
    @is_allowed()
    @app_commands.autocomplete(
        vending_machine_id=vending_machine_autocomplete,
        alias=paypay_alias_autocomplete
    )
    @app_commands.describe(
        vending_machine_id="対象の自販機",
        alias="切り替え先のPayPayアカウント（アカウント名）"
    )
    async def vm_switch_paypay_alias(self, interaction: discord.Interaction, vending_machine_id: str, alias: str):
        await interaction.response.defer(ephemeral=True)
        
        vending_data = load_json(VENDING_DATA_FILE)
        vm = vending_data.get(vending_machine_id)
        
        # 自販機が存在し、かつ自分がオーナーかチェック
        if not vm or vm.get("owner_id") != str(interaction.user.id):
            embed = discord.Embed(
                title="エラー",
                description="指定された自販機が見つからないか、あなたの所有自販機ではありません。",
                color=discord.Color.red()
            )
            await interaction.followup.send(embed=embed, ephemeral=True)
            return
        
        # 指定したaliasが本当に自分のPayPayアカウントにあるか確認
        paypay_data = load_paypay_data()
        user_id_str = str(interaction.user.id)
        accounts = paypay_data.get(user_id_str, [])
        
        if not any(acc["alias"] == alias for acc in accounts):
            embed = discord.Embed(
                title="エラー",
                description=f"「{alias}」という名前のPayPayアカウントは登録されていません。",
                color=discord.Color.red()
            )
            await interaction.followup.send(embed=embed, ephemeral=True)
            return
        
        # 切り替え実行
        vm["paypay_alias"] = alias
        # paypay_id はユーザーIDのままでOK（複数垢でもユーザー単位で管理）
        
        save_json(VENDING_DATA_FILE, vending_data)
        
        embed = discord.Embed(
            title="受け取りアカウント切り替え成功",
            description="paypay受け取りするアカウントの変更を完了しました。",
            color=discord.Color.green()
        )
        embed.add_field(name="自販機", value=vm.get("name", "名称未設定"), inline=False)
        embed.add_field(name="新しい受け取りアカウント", value=f"**{alias}**", inline=False)
        embed.set_footer(text="Created by @nama_0721")
        
        await interaction.followup.send(embed=embed, ephemeral=True)

    @app_commands.command(name="自販機kyash受け取り垢切り替え", description="自販機のKyash受け取りアカウントを切り替えます")
    @is_allowed()
    @app_commands.autocomplete(vending_machine_id=vending_machine_autocomplete)
    @app_commands.describe(
        vending_machine_id="対象の自販機",
        alias="切り替え先のKyashアカウント名"
    )
    async def vm_switch_kyash_alias(self, interaction: discord.Interaction, vending_machine_id: str, alias: str):
        await interaction.response.defer(ephemeral=True)

        vending_data = load_json(VENDING_DATA_FILE)
        vm = vending_data.get(vending_machine_id)

        if not vm or vm.get("owner_id") != str(interaction.user.id):
            embed = discord.Embed(
                title="エラー",
                description="指定された自販機が見つからないか、あなたの所有自販機ではありません。",
                color=discord.Color.red()
            )
            return await interaction.followup.send(embed=embed, ephemeral=True)

        accounts = load_kyash_data().get(str(interaction.user.id), [])
        if not any(a["alias"] == alias for a in accounts):
            embed = discord.Embed(
                title="エラー",
                description=f"「{alias}」というKyashアカウントは登録されていません。",
                color=discord.Color.red()
            )
            return await interaction.followup.send(embed=embed, ephemeral=True)

        vm["kyash_alias"] = alias
        save_json(VENDING_DATA_FILE, vending_data)

        embed = discord.Embed(
            title="Kyash受け取りアカウント切り替え成功",
            description="Kyash受け取りするアカウントの変更を完了しました。",
            color=discord.Color.green()
        )
        embed.add_field(name="自販機", value=vm.get("name", "名称未設定"), inline=False)
        embed.add_field(name="新しい受け取りアカウント", value=f"**{alias}**", inline=False)
        embed.set_footer(text="Created by @nama_0721")
        await interaction.followup.send(embed=embed, ephemeral=True)

    @vm_switch_kyash_alias.autocomplete("alias")
    async def kyash_vending_alias_ac(self, interaction: discord.Interaction, current: str):
        accounts = load_kyash_data().get(str(interaction.user.id), [])
        return [
            app_commands.Choice(name=a["alias"], value=a["alias"])
            for a in accounts if current.lower() in a["alias"].lower()
        ][:25]

    @app_commands.command(name="売上確認", description="指定した自販機の売上を確認します")
    @is_allowed()
    @app_commands.autocomplete(vending_machine_id=vending_machine_autocomplete)
    @app_commands.describe(vending_machine_id="確認する自販機")
    async def vm_sales_check(self, interaction: discord.Interaction, vending_machine_id: str):
        await interaction.response.defer(ephemeral=True)

        try:
            vending_data = load_json(VENDING_DATA_FILE)
            vm = vending_data.get(vending_machine_id)

            if not vm or vm.get("owner_id") != str(interaction.user.id):
                return await interaction.followup.send(
                    embed=discord.Embed(
                        title="エラー",
                        description="自販機が見つからないか、あなたの所有自販機ではありません。",
                        color=discord.Color.red()
                    ),
                    ephemeral=True
                )

            from collections import defaultdict

            jst = pytz.timezone('Asia/Tokyo')
            now_jst = datetime.datetime.now(jst)
            one_month_ago = now_jst - datetime.timedelta(days=30)

            # 集計用変数
            total_revenue = 0
            total_quantity = 0
            monthly_revenue = 0
            monthly_quantity = 0
            sale_timestamps = []

            # 商品別集計
            product_stats = defaultdict(lambda: {
                "name": "",
                "total_revenue": 0,
                "total_quantity": 0,
                "monthly_revenue": 0,
                "monthly_quantity": 0
            })

            for product in vm.get("products", []):
                prod_id = product["product_id"]
                prod_name = product.get("name", "名称不明")
                price = product.get("price", 0)
                history = product.get("sales_history", [])

                stats = product_stats[prod_id]
                stats["name"] = prod_name

                for record in history:
                    try:
                        sale_time = datetime.datetime.fromisoformat(record["timestamp"])
                    except:
                        continue

                    amount = record.get("amount", 0)
                    qty = record.get("quantity", 1)

                    # 全体集計
                    total_revenue += amount
                    total_quantity += qty
                    sale_timestamps.append(sale_time)

                    # 商品別全体
                    stats["total_revenue"] += amount
                    stats["total_quantity"] += qty

                    # 月間
                    if sale_time >= one_month_ago:
                        monthly_revenue += amount
                        monthly_quantity += qty
                        stats["monthly_revenue"] += amount
                        stats["monthly_quantity"] += qty

            # 平均売上計算
            if sale_timestamps:
                first_sale = min(sale_timestamps)
                last_sale = max(sale_timestamps)
                days_active = (last_sale - first_sale).days + 1
                if days_active < 1:
                    days_active = 1
                avg_daily = total_revenue / days_active
            else:
                days_active = 0
                avg_daily = 0

            # 商品別を売上降順でソート
            sorted_products = sorted(
                product_stats.values(),
                key=lambda x: x["total_revenue"],
                reverse=True
            )

            # Embed作成
            embed = discord.Embed(
                title="売上確認（商品別内訳付き）",
                description=f"**自販機：{vm.get('name', '名称未設定')}**",
                color=discord.Color.gold(),
                timestamp=discord.utils.utcnow()
            )
            embed.set_footer(text="Created by @nama_0721")

            # 全体サマリー
            embed.add_field(
                name="合計売上（全期間）",
                value=f"```合計 {total_revenue:,} 円  /  {total_quantity} 個```",
                inline=False
            )

            embed.add_field(
                name="過去30日間の売上",
                value=f"```合計 {monthly_revenue:,} 円  /  {monthly_quantity} 個```",
                inline=False
            )

            embed.add_field(
                name="1日平均売上",
                value=f"```約 {int(avg_daily):,} 円 / 日  （稼働 {days_active} 日）```",
                inline=False
            )

            # 商品別内訳
            if sorted_products:
                inner_text = ""
                displayed = 0
                others_count = 0
                others_revenue = 0
                others_qty = 0

                for stats in sorted_products:
                    if displayed < 10:
                        inner_text += f"• {stats['name']}\n"
                        inner_text += f"　全期間: {stats['total_revenue']:,}円 ({stats['total_quantity']}個)\n"
                        if stats["monthly_revenue"] > 0:
                            inner_text += f"　過去30日: {stats['monthly_revenue']:,}円 ({stats['monthly_quantity']}個)\n"
                        inner_text += "\n"
                        displayed += 1
                    else:
                        others_count += 1
                        others_revenue += stats["total_revenue"]
                        others_qty += stats["total_quantity"]

                if others_count > 0:
                    inner_text += f"他 {others_count} 商品\n"
                    inner_text += f"　合計: {others_revenue:,}円 ({others_qty}個)"

                embed.add_field(
                    name="商品別売上内訳（全期間降順）",
                    value=f"```{inner_text if inner_text else 'データなし'}```",
                    inline=False
                )
            else:
                embed.add_field(
                    name="商品別売上内訳",
                    value="```まだ売上がありません```",
                    inline=False
                )

            # 注意書き
            if not sale_timestamps:
                embed.add_field(name="補足", value="この自販機にはまだ売上記録がありません。", inline=False)
            elif days_active < 7:
                embed.add_field(name="注意", value="稼働日数が少ないため、平均値は参考程度です。", inline=False)

            await interaction.followup.send(embed=embed, ephemeral=True)

        except Exception as e:
            await handle_error(interaction, e)

    # ─── 自販機一覧 ──────────────────────────────────────────────────

    @app_commands.command(name="自販機一覧", description="自分が所有している自販機の一覧を表示します")
    @is_allowed()
    async def vm_list(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        try:
            vending_data = load_json(VENDING_DATA_FILE)
            user_id = str(interaction.user.id)
            my_vms = [(vm_id, vm) for vm_id, vm in vending_data.items() if vm.get("owner_id") == user_id]

            if not my_vms:
                embed = discord.Embed(
                    title="自販機一覧",
                    description="所有している自販機はありません。",
                    color=discord.Color(0x313c48)
                )
                embed.set_footer(text="Created by @nama_0721")
                return await interaction.followup.send(embed=embed, ephemeral=True)

            embed = discord.Embed(
                title="自販機一覧",
                description=f"所有自販機数：**{len(my_vms)}台**",
                color=discord.Color(0x313c48),
                timestamp=discord.utils.utcnow()
            )

            for vm_id, vm in my_vms:
                products = vm.get("products", [])
                total_sales = sum(p.get("sales_count", 0) for p in products)
                total_rev   = sum(
                    sum(r.get("amount", 0) for r in p.get("sales_history", []))
                    for p in products
                )
                log_ch = f"<#{vm['log_channel_id']}>" if vm.get("log_channel_id") else "未設定"
                embed.add_field(
                    name=vm.get("name", "名称未設定"),
                    value=(
                        f"```"
                        f"商品数  : {len(products)} 種\n"
                        f"総販売数: {total_sales} 個\n"
                        f"累計売上: {total_rev:,} 円"
                        f"```"
                        f"ログ: {log_ch}"
                    ),
                    inline=False
                )

            embed.set_footer(text="Created by @nama_0721")
            await interaction.followup.send(embed=embed, ephemeral=True)

        except Exception as e:
            await handle_error(interaction, e)

    # ─── 購入制限設定 ────────────────────────────────────────────────

    @app_commands.command(name="購入制限設定", description="商品ごとに期間別の購入上限を設定します")
    @is_allowed()
    @app_commands.autocomplete(vending_machine_id=vending_machine_autocomplete)
    @app_commands.describe(
        vending_machine_id="設定する自販機",
        daily_limit="1日あたりの購入上限（0=無制限）",
        weekly_limit="1週間あたりの購入上限（0=無制限）",
        total_limit="全期間の購入上限（0=無制限）"
    )
    async def vm_purchase_limit(
        self,
        interaction: discord.Interaction,
        vending_machine_id: str,
        daily_limit: int = 0,
        weekly_limit: int = 0,
        total_limit: int = 0
    ):
        await interaction.response.defer(ephemeral=True)
        try:
            vending_data = load_json(VENDING_DATA_FILE)
            vm = vending_data.get(vending_machine_id)

            if not vm or vm.get("owner_id") != str(interaction.user.id):
                embed = discord.Embed(title="エラー", description="指定された自販機が見つかりません。", color=discord.Color.red())
                embed.set_footer(text="Created by @nama_0721")
                return await interaction.followup.send(embed=embed, ephemeral=True)

            products = vm.get("products", [])
            if not products:
                embed = discord.Embed(title="エラー", description="この自販機には商品が登録されていません。", color=discord.Color.red())
                embed.set_footer(text="Created by @nama_0721")
                return await interaction.followup.send(embed=embed, ephemeral=True)

            # 全商品に適用
            for i, p in enumerate(products):
                vm["products"][i]["daily_limit"]   = daily_limit
                vm["products"][i]["weekly_limit"]  = weekly_limit
                vm["products"][i]["total_limit"]   = total_limit

            save_json(VENDING_DATA_FILE, vending_data)

            def fmt_limit(v): return "無制限" if v <= 0 else f"{v}個まで"

            embed = discord.Embed(
                title="購入制限設定",
                description=f"自販機「{vm['name']}」の全商品に購入制限を設定しました。",
                color=discord.Color.green()
            )
            embed.add_field(name="1日あたり",   value=f"```{fmt_limit(daily_limit)}```",  inline=True)
            embed.add_field(name="1週間あたり", value=f"```{fmt_limit(weekly_limit)}```", inline=True)
            embed.add_field(name="全期間",       value=f"```{fmt_limit(total_limit)}```",  inline=True)
            embed.set_footer(text="Created by @nama_0721")
            await interaction.followup.send(embed=embed, ephemeral=True)

        except Exception as e:
            await handle_error(interaction, e)

    # ─── 売上リセット ────────────────────────────────────────────────

    @app_commands.command(name="売上リセット", description="自販機の売上履歴をリセットします")
    @is_allowed()
    @app_commands.autocomplete(vending_machine_id=vending_machine_autocomplete)
    @app_commands.describe(vending_machine_id="リセットする自販機")
    async def vm_sales_reset(self, interaction: discord.Interaction, vending_machine_id: str):
        try:
            vending_data = load_json(VENDING_DATA_FILE)
            vm = vending_data.get(vending_machine_id)

            if not vm or vm.get("owner_id") != str(interaction.user.id):
                embed = discord.Embed(title="エラー", description="指定された自販機が見つかりません。", color=discord.Color.red())
                embed.set_footer(text="Created by @nama_0721")
                return await interaction.response.send_message(embed=embed, ephemeral=True)

            products = vm.get("products", [])
            total_rev = sum(
                sum(r.get("amount", 0) for r in p.get("sales_history", []))
                for p in products
            )
            total_qty = sum(p.get("sales_count", 0) for p in products)

            embed = discord.Embed(
                title="売上リセット確認",
                description=(
                    f"自販機「{vm['name']}」の売上履歴を本当にリセットしますか？\n"
                    f"この操作は**取り消せません。**\n\n"
                    f"```現在の累計売上: {total_rev:,} 円 / {total_qty} 個```"
                ),
                color=discord.Color.red()
            )
            embed.set_footer(text="Created by @nama_0721")
            view = VendingMachineCog.SalesResetConfirmView(vending_machine_id, vm.get("name", ""))
            await interaction.response.send_message(embed=embed, view=view, ephemeral=True)

        except Exception as e:
            await handle_error(interaction, e)

    class SalesResetConfirmView(ui.View):
        def __init__(self, vending_machine_id: str, vm_name: str):
            super().__init__(timeout=60)
            self.vending_machine_id = vending_machine_id
            self.vm_name = vm_name

        @ui.button(label="リセットする", style=discord.ButtonStyle.danger)
        async def confirm(self, interaction: discord.Interaction, button: ui.Button):
            try:
                vending_data = load_json(VENDING_DATA_FILE)
                vm = vending_data.get(self.vending_machine_id)
                if vm:
                    for i in range(len(vm.get("products", []))):
                        vm["products"][i]["sales_count"]   = 0
                        vm["products"][i]["sales_history"] = []
                    save_json(VENDING_DATA_FILE, vending_data)

                embed = discord.Embed(
                    title="売上リセット完了",
                    description=f"自販機「{self.vm_name}」の売上履歴をリセットしました。",
                    color=discord.Color.green()
                )
                embed.set_footer(text="Created by @nama_0721")
                self.stop()
                await interaction.response.send_message(embed=embed, ephemeral=True)
            except Exception as e:
                await handle_error(interaction, e)

        @ui.button(label="キャンセル", style=discord.ButtonStyle.secondary)
        async def cancel(self, interaction: discord.Interaction, button: ui.Button):
            embed = discord.Embed(
                title="キャンセル",
                description="売上リセットをキャンセルしました。",
                color=discord.Color(0x313c48)
            )
            embed.set_footer(text="Created by @nama_0721")
            self.stop()
            await interaction.response.send_message(embed=embed, ephemeral=True)

    # ─── 在庫残数アラート設定 ────────────────────────────────────────

    @app_commands.command(name="在庫残数アラート設定", description="在庫が指定数以下になったら通知します")
    @is_allowed()
    @app_commands.autocomplete(vending_machine_id=vending_machine_autocomplete)
    @app_commands.describe(
        vending_machine_id="設定する自販機",
        threshold="この個数以下になったら通知（例: 3）",
        channel="通知を送るチャンネル",
        role="メンションするロール（任意）"
    )
    async def vm_stock_alert_setup(
        self,
        interaction: discord.Interaction,
        vending_machine_id: str,
        threshold: int,
        channel: discord.TextChannel,
        role: discord.Role = None
    ):
        await interaction.response.defer(ephemeral=True)
        try:
            vending_data = load_json(VENDING_DATA_FILE)
            vm = vending_data.get(vending_machine_id)
            if not vm or vm.get("owner_id") != str(interaction.user.id):
                embed = discord.Embed(title="エラー", description="指定された自販機が見つかりません。", color=discord.Color.red())
                embed.set_footer(text="Created by @nama_0721")
                return await interaction.followup.send(embed=embed, ephemeral=True)

            products = vm.get("products", [])
            if not products:
                embed = discord.Embed(title="エラー", description="この自販機には商品が登録されていません。", color=discord.Color.red())
                embed.set_footer(text="Created by @nama_0721")
                return await interaction.followup.send(embed=embed, ephemeral=True)

            # 全商品にアラート設定
            alert_data = load_stock_alert_data()
            if vending_machine_id not in alert_data:
                alert_data[vending_machine_id] = {}

            for product in products:
                alert_data[vending_machine_id][product["product_id"]] = {
                    "threshold": threshold,
                    "channel_id": channel.id,
                    "role_id": role.id if role else None,
                    "guild_id": interaction.guild.id
                }
            save_stock_alert_data(alert_data)

            embed = discord.Embed(
                title="在庫残数アラート設定",
                description=f"自販機「{vm['name']}」の全商品にアラートを設定しました。",
                color=discord.Color.green()
            )
            embed.add_field(name="閾値", value=f"```{threshold}個以下で通知```", inline=True)
            embed.add_field(name="通知チャンネル", value=channel.mention, inline=True)
            if role:
                embed.add_field(name="メンションロール", value=role.mention, inline=True)
            embed.set_footer(text="Created by @nama_0721")
            await interaction.followup.send(embed=embed, ephemeral=True)

        except Exception as e:
            await handle_error(interaction, e)

    @app_commands.command(name="在庫残数アラート解除", description="在庫残数アラートを解除します")
    @is_allowed()
    @app_commands.autocomplete(vending_machine_id=vending_machine_autocomplete)
    @app_commands.describe(vending_machine_id="解除する自販機")
    async def vm_stock_alert_remove(self, interaction: discord.Interaction, vending_machine_id: str):
        await interaction.response.defer(ephemeral=True)
        try:
            vending_data = load_json(VENDING_DATA_FILE)
            vm = vending_data.get(vending_machine_id)
            if not vm or vm.get("owner_id") != str(interaction.user.id):
                embed = discord.Embed(title="エラー", description="指定された自販機が見つかりません。", color=discord.Color.red())
                embed.set_footer(text="Created by @nama_0721")
                return await interaction.followup.send(embed=embed, ephemeral=True)

            alert_data = load_stock_alert_data()
            if vending_machine_id in alert_data:
                del alert_data[vending_machine_id]
                save_stock_alert_data(alert_data)

            embed = discord.Embed(
                title="在庫残数アラート解除",
                description=f"自販機「{vm['name']}」のアラート設定を解除しました。",
                color=discord.Color.red()
            )
            embed.set_footer(text="Created by @nama_0721")
            await interaction.followup.send(embed=embed, ephemeral=True)

        except Exception as e:
            await handle_error(interaction, e)

    # ─── ランダム配送確認 ────────────────────────────────────────────

    @app_commands.command(name="ランダム配送確認", description="ランダム配送がONになっている商品を確認します")
    @is_allowed()
    @app_commands.autocomplete(vending_machine_id=vending_machine_autocomplete)
    @app_commands.describe(vending_machine_id="確認する自販機")
    async def vm_random_delivery_check(self, interaction: discord.Interaction, vending_machine_id: str):
        await interaction.response.defer(ephemeral=True)
        try:
            vending_data = load_json(VENDING_DATA_FILE)
            vm = vending_data.get(vending_machine_id)
            if not vm or vm.get("owner_id") != str(interaction.user.id):
                embed = discord.Embed(title="エラー", description="指定された自販機が見つかりません。", color=discord.Color.red())
                embed.set_footer(text="Created by @nama_0721")
                return await interaction.followup.send(embed=embed, ephemeral=True)

            products = vm.get("products", [])
            on_products = [p for p in products if p.get("random_delivery")]
            off_products = [p for p in products if not p.get("random_delivery")]

            embed = discord.Embed(
                title="ランダム配送確認",
                description=f"自販機「{vm['name']}」のランダム配送設定一覧",
                color=discord.Color(0x313c48)
            )

            if on_products:
                embed.add_field(
                    name="ON",
                    value="\n".join(f"・{p['name']}" for p in on_products),
                    inline=False
                )
            else:
                embed.add_field(name="ON", value="なし", inline=False)

            if off_products:
                embed.add_field(
                    name="OFF",
                    value="\n".join(f"・{p['name']}" for p in off_products),
                    inline=False
                )
            else:
                embed.add_field(name="OFF", value="なし", inline=False)

            embed.set_footer(text="Created by @nama_0721")
            await interaction.followup.send(embed=embed, ephemeral=True)

        except Exception as e:
            await handle_error(interaction, e)

    # ─── 商品並び替え ────────────────────────────────────────────────

    @app_commands.command(name="商品並び替え", description="自販機パネルに表示する商品の順番を変更します")
    @is_allowed()
    @app_commands.autocomplete(vending_machine_id=vending_machine_autocomplete)
    @app_commands.describe(vending_machine_id="並び替える自販機")
    async def vm_reorder_products(self, interaction: discord.Interaction, vending_machine_id: str):
        try:
            vending_data = load_json(VENDING_DATA_FILE)
            vm = vending_data.get(vending_machine_id)
            if not vm or vm.get("owner_id") != str(interaction.user.id):
                embed = discord.Embed(title="エラー", description="指定された自販機が見つかりません。", color=discord.Color.red())
                embed.set_footer(text="Created by @nama_0721")
                return await interaction.response.send_message(embed=embed, ephemeral=True)

            products = vm.get("products", [])
            if len(products) < 2:
                embed = discord.Embed(title="エラー", description="並び替えには2つ以上の商品が必要です。", color=discord.Color.red())
                embed.set_footer(text="Created by @nama_0721")
                return await interaction.response.send_message(embed=embed, ephemeral=True)

            current_order = "\n".join(f"{i+1}. {p['name']}" for i, p in enumerate(products))
            embed = discord.Embed(
                title="商品並び替え",
                description=f"**現在の順番**\n```{current_order}```\n移動させたい商品を選んでください。",
                color=discord.Color(0x313c48)
            )
            embed.set_footer(text="Created by @nama_0721")

            view = VendingMachineCog.ReorderSelectView(products, vending_machine_id)
            await interaction.response.send_message(embed=embed, view=view, ephemeral=True)

        except Exception as e:
            await handle_error(interaction, e)

    class ReorderSelectView(ui.View):
        def __init__(self, products: list, vending_machine_id: str):
            super().__init__(timeout=180)
            self.add_item(VendingMachineCog.ReorderPickTargetSelect(products, vending_machine_id))

    class ReorderPickTargetSelect(ui.Select):
        """移動させる商品を選ぶ"""
        def __init__(self, products: list, vending_machine_id: str):
            self.products = products
            self.vending_machine_id = vending_machine_id
            options = [
                discord.SelectOption(label=f"{i+1}. {p['name']}", value=p["product_id"])
                for i, p in enumerate(products)
            ]
            super().__init__(placeholder="移動する商品を選択...", options=options)

        async def callback(self, interaction: discord.Interaction):
            try:
                target_id = self.values[0]
                target_idx = next(i for i, p in enumerate(self.products) if p["product_id"] == target_id)

                view = VendingMachineCog.ReorderPickDestView(self.products, self.vending_machine_id, target_idx)
                current_order = "\n".join(f"{i+1}. {p['name']}" for i, p in enumerate(self.products))
                embed = discord.Embed(
                    title="商品並び替え",
                    description=f"**現在の順番**\n```{current_order}```\n「{self.products[target_idx]['name']}」をどこに移動しますか？",
                    color=discord.Color(0x313c48)
                )
                embed.set_footer(text="Created by @nama_0721")
                await interaction.response.send_message(embed=embed, view=view, ephemeral=True)
            except Exception as e:
                await handle_error(interaction, e)

    class ReorderPickDestView(ui.View):
        def __init__(self, products: list, vending_machine_id: str, target_idx: int):
            super().__init__(timeout=180)
            self.add_item(VendingMachineCog.ReorderPickDestSelect(products, vending_machine_id, target_idx))

    class ReorderPickDestSelect(ui.Select):
        """移動先の位置を選ぶ"""
        def __init__(self, products: list, vending_machine_id: str, target_idx: int):
            self.products = products
            self.vending_machine_id = vending_machine_id
            self.target_idx = target_idx
            options = [
                discord.SelectOption(
                    label=f"{i+1}番目の位置へ移動",
                    value=str(i),
                    description=f"現在: {p['name']}" if i != target_idx else "（現在の位置）"
                )
                for i, p in enumerate(products)
                if i != target_idx
            ]
            super().__init__(placeholder="移動先を選択...", options=options)

        async def callback(self, interaction: discord.Interaction):
            try:
                dest_idx = int(self.values[0])
                new_products = self.products.copy()
                target = new_products.pop(self.target_idx)
                new_products.insert(dest_idx, target)

                vending_data = load_json(VENDING_DATA_FILE)
                vm = vending_data.get(self.vending_machine_id)
                if vm:
                    vm["products"] = new_products
                    save_json(VENDING_DATA_FILE, vending_data)

                new_order = "\n".join(f"{i+1}. {p['name']}" for i, p in enumerate(new_products))
                embed = discord.Embed(
                    title="商品並び替え完了",
                    description=f"順番を変更しました。\n```{new_order}```\n※ パネルに反映するには `/自販機パネル更新` を実行してください。",
                    color=discord.Color.green()
                )
                embed.set_footer(text="Created by @nama_0721")
                await interaction.response.send_message(embed=embed, ephemeral=True)

            except Exception as e:
                await handle_error(interaction, e)

    # ─── ランダム配送 ────────────────────────────────────────────

    @app_commands.command(name="ランダム配送", description="自販機のランダム配送設定を行います")
    @app_commands.default_permissions(administrator=True)
    @app_commands.autocomplete(vending_machine_id=vending_machine_autocomplete)
    @app_commands.describe(vending_machine_id="設定する自販機")
    async def vm_random_delivery(self, interaction: discord.Interaction, vending_machine_id: str):
        try:
            vending_data = load_json(VENDING_DATA_FILE)
            vm = vending_data.get(vending_machine_id)

            if not vm or vm.get("owner_id") != str(interaction.user.id):
                embed = discord.Embed(
                    title="エラー",
                    description="指定された自販機が見つかりません。",
                    color=discord.Color.red()
                )
                embed.set_footer(text="Created by @nama_0721")
                return await interaction.response.send_message(embed=embed, ephemeral=True)

            products = vm.get("products", [])
            if not products:
                embed = discord.Embed(
                    title="エラー",
                    description="この自販機には商品が登録されていません。",
                    color=discord.Color.red()
                )
                embed.set_footer(text="Created by @nama_0721")
                return await interaction.response.send_message(embed=embed, ephemeral=True)

            embed = discord.Embed(
                title="ランダム配送パネル",
                description="下のボタンからまとめて編集か1つ編集か選んでください。",
                color=discord.Color(0x313c48)
            )
            embed.set_footer(text="Created by @nama_0721")

            view = VendingMachineCog.RandomDeliveryPanelView(products, vending_machine_id)
            await interaction.response.send_message(embed=embed, view=view, ephemeral=True)

        except Exception as e:
            await handle_error(interaction, e)

    class RandomDeliveryPanelView(ui.View):
        def __init__(self, products: list, vending_machine_id: str):
            super().__init__(timeout=180)
            self.products = products
            self.vending_machine_id = vending_machine_id

        @ui.button(label="1つ編集", style=discord.ButtonStyle.primary)
        async def single_edit(self, interaction: discord.Interaction, button: ui.Button):
            try:
                view = VendingMachineCog.RandomDeliverySingleView(
                    self.products, self.vending_machine_id
                )
                await interaction.response.send_message(
                    "設定する商品を選択してください：",
                    view=view,
                    ephemeral=True
                )
            except Exception as e:
                await handle_error(interaction, e)

        @ui.button(label="まとめて編集", style=discord.ButtonStyle.secondary)
        async def bulk_edit(self, interaction: discord.Interaction, button: ui.Button):
            try:
                vending_data = load_json(VENDING_DATA_FILE)
                vm = vending_data.get(self.vending_machine_id)
                if vm:
                    for product in vm.get("products", []):
                        product["random_delivery"] = True
                    save_json(VENDING_DATA_FILE, vending_data)

                embed = discord.Embed(
                    title="全ての商品をランダム配送の設定に完了しました",
                    color=discord.Color.green()
                )
                embed.set_footer(text="Created by @nama_0721")
                await interaction.response.send_message(embed=embed, ephemeral=True)
            except Exception as e:
                await handle_error(interaction, e)

    class RandomDeliverySingleView(ui.View):
        def __init__(self, products: list, vending_machine_id: str):
            super().__init__(timeout=180)
            self.add_item(VendingMachineCog.RandomDeliveryProductSelect(products, vending_machine_id))

    class RandomDeliveryProductSelect(ui.Select):
        def __init__(self, products: list, vending_machine_id: str):
            self.products = products
            self.vending_machine_id = vending_machine_id
            options = [
                discord.SelectOption(
                    label=p["name"],
                    value=p["product_id"],
                    description=f"PayPay: {p.get('price', '未設定')}円 | Kyash: {p.get('kyash_price', p.get('price', '未設定'))}円"
                )
                for p in products
            ]
            super().__init__(
                placeholder="商品を選択...",
                options=options,
                custom_id="random_delivery_product_select"
            )

        async def callback(self, interaction: discord.Interaction):
            try:
                product_id = self.values[0]
                vending_data = load_json(VENDING_DATA_FILE)
                vm = vending_data.get(self.vending_machine_id)

                product_name = "不明"
                if vm:
                    for product in vm.get("products", []):
                        if product["product_id"] == product_id:
                            product["random_delivery"] = True
                            product_name = product.get("name", "不明")
                            break
                    save_json(VENDING_DATA_FILE, vending_data)

                embed = discord.Embed(
                    title="ランダム配送設定",
                    description=f"ランダム配送設定完了しました。\n**商品：{product_name}**",
                    color=discord.Color.green()
                )
                embed.set_footer(text="Created by @nama_0721")
                await interaction.response.send_message(embed=embed, ephemeral=True)

            except Exception as e:
                await handle_error(interaction, e)

    # ─── メンテナンスモード ──────────────────────────────────────────

    @app_commands.command(name="メンテナンスモード", description="自販機の購入を一時停止/再開します")
    @is_allowed()
    @app_commands.autocomplete(vending_machine_id=vending_machine_autocomplete)
    @app_commands.describe(vending_machine_id="対象の自販機")
    async def vm_maintenance(self, interaction: discord.Interaction, vending_machine_id: str):
        await interaction.response.defer(ephemeral=True)
        try:
            vending_data = load_json(VENDING_DATA_FILE)
            vm = vending_data.get(vending_machine_id)
            if not vm or vm.get("owner_id") != str(interaction.user.id):
                embed = discord.Embed(title="エラー", description="指定された自販機が見つかりません。", color=discord.Color.red())
                embed.set_footer(text="Created by @nama_0721")
                return await interaction.followup.send(embed=embed, ephemeral=True)

            current = vm.get("maintenance", False)
            vm["maintenance"] = not current
            save_json(VENDING_DATA_FILE, vending_data)

            if vm["maintenance"]:
                embed = discord.Embed(
                    title="メンテナンスモード ON",
                    description=f"自販機「{vm['name']}」の購入を**一時停止**しました。\n再開するには再度このコマンドを実行してください。",
                    color=discord.Color.red()
                )
            else:
                embed = discord.Embed(
                    title="メンテナンスモード OFF",
                    description=f"自販機「{vm['name']}」の購入を**再開**しました。",
                    color=discord.Color.green()
                )
            embed.set_footer(text="Created by @nama_0721")
            await interaction.followup.send(embed=embed, ephemeral=True)

        except Exception as e:
            await handle_error(interaction, e)

    # ─── バージョン管理システム ──────────────────────────────────────

    #@app_commands.command(name="バージョン更新", description="新しいバージョンをリリースし全サーバーに通知します（Botオーナー専用）")
    async def vm_release_version(self, interaction: discord.Interaction):
        try:
            if str(interaction.user.id) != BOT_OWNER_ID:
                embed = discord.Embed(
                    title="エラー",
                    description="このコマンドはBotオーナーのみ使用できます。",
                    color=discord.Color.red()
                )
                embed.set_footer(text="Created by @nama_0721")
                return await interaction.response.send_message(embed=embed, ephemeral=True)

            await interaction.response.send_modal(VendingMachineCog.VersionReleaseModal(self.bot))

        except Exception as e:
            await handle_error(interaction, e)

    #@app_commands.command(name="バージョン確認", description="現在のバージョンと最新パッチノートを確認します")
    async def vm_check_version(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        try:
            version_data = load_version_data()
            history = version_data.get("history", [])

            if not history:
                embed = discord.Embed(
                    title="バージョン確認",
                    description="まだバージョン情報がありません。",
                    color=discord.Color(0x313c48)
                )
                embed.set_footer(text="Created by @nama_0721")
                return await interaction.followup.send(embed=embed, ephemeral=True)

            latest = history[-1]
            embed = discord.Embed(
                title=f"現在のバージョン：{latest['version']}",
                color=discord.Color(0x313c48),
                timestamp=datetime.datetime.fromisoformat(latest["released_at"])
            )
            if latest.get("new_features"):
                embed.add_field(name="新機能", value=f"```{latest['new_features']}```", inline=False)
            if latest.get("fixes"):
                embed.add_field(name="修正", value=f"```{latest['fixes']}```", inline=False)
            if latest.get("bug_fixes"):
                embed.add_field(name="バグ修正", value=f"```{latest['bug_fixes']}```", inline=False)

            if len(history) > 1:
                prev_versions = "\n".join(
                    f"・{h['version']}  {h['released_at'][:10]}"
                    for h in reversed(history[:-1][-5:])
                )
                embed.add_field(name="過去のバージョン", value=f"```{prev_versions}```", inline=False)

            embed.set_footer(text="Created by @nama_0721")
            await interaction.followup.send(embed=embed, ephemeral=True)

        except Exception as e:
            await handle_error(interaction, e)

    class VersionReleaseModal(ui.Modal, title="バージョンリリース"):
        version_input = ui.TextInput(
            label="バージョン番号",
            placeholder="例: v1.2.0",
            max_length=20,
            required=True
        )
        new_features_input = ui.TextInput(
            label="新機能",
            placeholder="追加した機能を入力（なければ空白）",
            style=discord.TextStyle.paragraph,
            required=False,
            max_length=500
        )
        fixes_input = ui.TextInput(
            label="修正",
            placeholder="改善・変更内容を入力（なければ空白）",
            style=discord.TextStyle.paragraph,
            required=False,
            max_length=500
        )
        bug_fixes_input = ui.TextInput(
            label="バグ修正",
            placeholder="修正したバグを入力（なければ空白）",
            style=discord.TextStyle.paragraph,
            required=False,
            max_length=500
        )

        def __init__(self, bot):
            super().__init__()
            self.bot = bot

        async def on_submit(self, interaction: discord.Interaction):
            await interaction.response.defer(ephemeral=True)
            try:
                jst = pytz.timezone("Asia/Tokyo")
                now_jst = datetime.datetime.now(jst)

                # 入力を箇条書きに整形
                def format_notes(raw: str) -> str:
                    if not raw:
                        return ""
                    lines = [l.strip() for l in raw.replace("、", "\n").replace(",", "\n").splitlines() if l.strip()]
                    return "\n".join(f"・{l.lstrip('・').strip()}" for l in lines)

                raw_features = self.new_features_input.value.strip()
                raw_fixes    = self.fixes_input.value.strip()
                raw_bugs     = self.bug_fixes_input.value.strip()

                gen_features = format_notes(raw_features)
                gen_fixes    = format_notes(raw_fixes)
                gen_bugs     = format_notes(raw_bugs)

                version_data = load_version_data()
                if "history" not in version_data:
                    version_data["history"] = []

                record = {
                    "version":      self.version_input.value.strip(),
                    "new_features": gen_features,
                    "fixes":        gen_fixes,
                    "bug_fixes":    gen_bugs,
                    "released_at":  now_jst.isoformat(),
                    "released_by":  str(interaction.user.id)
                }
                version_data["history"].append(record)
                save_version_data(version_data)

                # 通知embed
                notify_embed = discord.Embed(
                    title=f"アップデート {record['version']} がリリースされました",
                    color=discord.Color(0x313c48),
                    timestamp=now_jst
                )
                if record["new_features"]:
                    notify_embed.add_field(name="新機能",   value=f"```{record['new_features']}```", inline=False)
                if record["fixes"]:
                    notify_embed.add_field(name="修正",     value=f"```{record['fixes']}```",        inline=False)
                if record["bug_fixes"]:
                    notify_embed.add_field(name="バグ修正", value=f"```{record['bug_fixes']}```",    inline=False)
                notify_embed.set_footer(text="Created by @nama_0721")

                # 固定チャンネルに送信
                FIXED_UPDATE_CHANNEL_ID = 1502880074087534662

                target_channel_ids = {FIXED_UPDATE_CHANNEL_ID}

                success = 0
                failed = 0
                for channel_id in target_channel_ids:
                    try:
                        ch = self.bot.get_channel(channel_id)
                        if ch:
                            await ch.send(embed=notify_embed)
                            success += 1
                        else:
                            failed += 1
                    except Exception:
                        failed += 1

                result_embed = discord.Embed(
                    title="リリース完了",
                    description=f"**{record['version']}** をリリースしました。",
                    color=discord.Color.green()
                )
                result_embed.add_field(
                    name="通知送信",
                    value=f"```成功: {success} サーバー\n失敗: {failed} サーバー```",
                    inline=False
                )
                result_embed.set_footer(text="Created by @nama_0721")
                await interaction.followup.send(embed=result_embed, ephemeral=True)

            except Exception as e:
                await handle_error(interaction, e)


VERSION_DATA_FILE = "version_data.json"

def load_version_data():
    if os.path.exists(VERSION_DATA_FILE):
        with open(VERSION_DATA_FILE, "r", encoding="utf-8") as f:
            try:
                return json.load(f)
            except json.JSONDecodeError:
                return {}
    return {}

def save_version_data(data):
    with open(VERSION_DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=4, ensure_ascii=False)


async def setup(bot):
    await bot.add_cog(VendingMachineCog(bot))