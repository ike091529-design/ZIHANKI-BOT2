# backup_manager.py
import json
import shutil
import time
import hashlib
from datetime import datetime, timedelta
from pathlib import Path
import threading

# ──────────────────────────────────────────────
# 設定
# ──────────────────────────────────────────────
VENDING_DATA_FILE = Path("vending_data.json")
BACKUP_DIR = Path("backups/vending_data")
BACKUP_DIR.mkdir(parents=True, exist_ok=True)

# 1日1回の強制バックアップ時刻（例: 毎日午前5時）
DAILY_BACKUP_HOUR   = 5
DAILY_BACKUP_MINUTE = 0

# チェック間隔（秒）
CHECK_INTERVAL = 30

# グローバル変数
_last_hash          = None
_last_backup_time   = 0
_last_daily_check   = None
lock = threading.Lock()


def get_latest_backup() -> Path | None:
    """最新のバックアップファイルを返す"""
    backups = sorted(BACKUP_DIR.glob("vending_data_*.json"), reverse=True)
    return backups[0] if backups else None


def compute_file_hash(file_path: Path) -> str:
    """ファイル内容のSHA256ハッシュを計算（変更検知用）"""
    if not file_path.exists() or file_path.stat().st_size == 0:
        return ""
    hasher = hashlib.sha256()
    with open(file_path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            hasher.update(chunk)
    return hasher.hexdigest()


def should_do_daily_backup() -> bool:
    """今日まだ1日1回のバックアップをしていないか"""
    global _last_daily_check
    now = datetime.now()
    today_start = now.replace(hour=DAILY_BACKUP_HOUR, minute=DAILY_BACKUP_MINUTE, second=0, microsecond=0)
    
    if now < today_start:
        today_start -= timedelta(days=1)
    
    if _last_daily_check is None or _last_daily_check < today_start:
        _last_daily_check = now
        return True
    return False


def create_backup(reason: str = "定期/変更検知"):
    """バックアップを作成し、1個前のものを削除"""
    global _last_backup_time
    with lock:
        if not VENDING_DATA_FILE.exists() or VENDING_DATA_FILE.stat().st_size == 0:
            return
        
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_path = BACKUP_DIR / f"vending_data_{timestamp}.json"
        
        try:
            shutil.copy2(VENDING_DATA_FILE, backup_path)
            _last_backup_time = time.time()
            print(f"[バックアップ] {backup_path.name} 作成（理由: {reason}）")
            
            # 1個前のバックアップを削除（最新2個だけ残す）
            delete_previous_backup()
            
        except Exception as e:
            print(f"[バックアップ失敗] {e}")


def delete_previous_backup():
    """最新のバックアップ以外で、一番新しいものを残して1個前のものを削除"""
    backups = sorted(
        BACKUP_DIR.glob("vending_data_*.json"),
        key=lambda p: p.stat().st_mtime,
        reverse=True
    )
    
    # 2個以上ある場合に、最新の次（インデックス1）のものを削除
    if len(backups) >= 2:
        to_delete = backups[1]
        try:
            to_delete.unlink()
            print(f"[自動削除] 1個前のバックアップを削除: {to_delete.name}")
        except Exception as e:
            print(f"[削除失敗] {to_delete.name} を削除できませんでした: {e}")


def restore_if_needed():
    """ファイルが存在しない・空・壊れている場合に最新バックアップから復元"""
    with lock:
        need_restore = False

        if not VENDING_DATA_FILE.exists():
            need_restore = True
        else:
            try:
                with open(VENDING_DATA_FILE, "r", encoding="utf-8") as f:
                    data = json.load(f)
                if not isinstance(data, dict):
                    need_restore = True
            except (json.JSONDecodeError, Exception):
                need_restore = True

        if need_restore:
            latest = get_latest_backup()
            if latest:
                try:
                    shutil.copy2(latest, VENDING_DATA_FILE)
                    print(f"[自動復元] {latest.name} から vending_data.json に復元しました")
                except Exception as e:
                    print(f"[復元失敗] {e} → 空ファイルで初期化")
                    with open(VENDING_DATA_FILE, "w", encoding="utf-8") as f:
                        json.dump({}, f, ensure_ascii=False, indent=2)
            else:
                print("[復元] バックアップが存在しない → 空ファイルを作成")
                with open(VENDING_DATA_FILE, "w", encoding="utf-8") as f:
                    json.dump({}, f, ensure_ascii=False, indent=2)


def check_and_backup():
    global _last_hash
    
    current_hash = compute_file_hash(VENDING_DATA_FILE)
    
    # 内容が変わっていたらバックアップ
    if current_hash and current_hash != _last_hash:
        _last_hash = current_hash
        create_backup("内容変更検知")
    
    # 1日1回は必ずバックアップ
    if should_do_daily_backup():
        create_backup("1日1回保証")


def start_backup_thread():
    def loop():
        while True:
            try:
                restore_if_needed()     # 起動時＆定期的に復元チェック
                check_and_backup()      # 変更チェック＋1日1回保証
            except Exception as e:
                print(f"[BackupMonitor エラー] {e}")
            time.sleep(CHECK_INTERVAL)

    thread = threading.Thread(target=loop, daemon=True, name="BackupMonitor")
    thread.start()
    print(f"[BackupManager] {CHECK_INTERVAL}秒間隔でバックアップ監視を開始しました")


# モジュール読み込み時に自動でスレッド開始
start_backup_thread()