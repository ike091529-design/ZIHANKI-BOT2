import os
import discord
from discord.ext import commands
from discord.gateway import DiscordWebSocket
from dotenv import load_dotenv
import logging

# ────────── Koyeb / PaaS ヘルスチェック対応 ──────────
from keep_alive import keep_alive
keep_alive()

# バックアップマネージャー（自動監視スレッド）の導入
try:
    import backup_manager
except ImportError:
    pass
# ───────────────────────────────────────────────────

logger = logging.getLogger('discord')
logger.setLevel(logging.INFO)

handler = logging.StreamHandler()
handler.setFormatter(logging.Formatter('%(asctime)s:%(levelname)s:%(name)s: %(message)s'))
logger.addHandler(handler)

load_dotenv()
token = os.getenv('TOKEN')
if not token:
    raise ValueError("TOKENが見つかりません。.envファイルまたは環境変数にTOKENを設定してください！")

intents = discord.Intents.all()

def mobile_patch():
    original_identify = DiscordWebSocket.identify
    
    async def patched_identify(self):
        payload = {
            'op': DiscordWebSocket.IDENTIFY,
            'd': {
                'token': self.token,
                'properties': {
                    '$os': 'Android',              
                    '$browser': 'Discord Android',
                    '$device': 'Discord Android',
                    '$referrer': '',
                    '$referring_domain': ''
                },
                'compress': True,
                'large_threshold': 250,
                'presence': {
                    'status': 'idle',
                    'since': 0,
                    'activities': [],
                    'afk': False
                },
                'intents': intents.value
            }
        }
        
        if self.shard_id is not None and self.shard_count is not None:
            payload['d']['shard'] = [self.shard_id, self.shard_count]
        
        await self.send_as_json(payload)
        logger.info("Mobile identify payload sent（スマホ表示パッチ適用済み）")

    DiscordWebSocket.identify = patched_identify

# パッチを即座に適用
mobile_patch()

class MyBot(commands.Bot):
    def __init__(self):
        super().__init__(
            command_prefix=commands.when_mentioned,
            intents=intents,
            help_command=None,
        )

bot = MyBot()

# Cogs読み込み
async def load_cogs():
    cog_path = "./Cogs"
    if not os.path.exists(cog_path):
        logger.warning(f"Cogsフォルダが見つかりません: {cog_path}")
        return

    for filename in os.listdir(cog_path):
        if filename.endswith(".py") and filename != "__init__.py":
            cog_name = filename[:-3]
            try:
                await bot.load_extension(f"Cogs.{cog_name}")
                logger.info(f"Loaded cog: {cog_name}")
            except Exception as e:
                logger.error(f"Failed to load cog {cog_name}: {e}")

    # スラッシュコマンド同期
    try:
        synced = await bot.tree.sync()
        logger.info(f"Command tree synced globally. ({len(synced)} commands)")
    except Exception as e:
        logger.error(f"Failed to sync command tree: {e}")

bot.setup_hook = load_cogs

# on_readyイベント
@bot.event
async def on_ready():
    if not hasattr(bot, '_already_ready_once'):
        logger.info(f'Bot起動完了！ログイン中: {bot.user} (ID: {bot.user.id})')
        bot._already_ready_once = True

        # カスタムアクティビティ
        activity = discord.CustomActivity(name="Created By MAKIKUSA")
        await bot.change_presence(status=discord.Status.idle, activity=activity)
    else:
        logger.info(f'Reconnected: {bot.user}')

if __name__ == "__main__":
    logger.info("Starting Bot...")
    bot.run(token, log_handler=None)