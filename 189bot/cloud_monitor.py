import asyncio
import re
import os
import sqlite3
import aiohttp
import sys
import traceback
import time
import logging
from logging.handlers import TimedRotatingFileHandler
from urllib.parse import urlparse
from datetime import datetime, timezone, timedelta

# Telegram 库
from telethon import TelegramClient
from telethon.sessions import StringSession
from telethon.tl.types import MessageEntityTextUrl
from telethon.tl.functions.messages import ImportChatInviteRequest
from telethon.tl.functions.channels import JoinChannelRequest
from telethon.errors import ChannelPrivateError

# 导入配置管理器
import config_manager
# 在这里定义 CONFIG，但先将其设为 None，直到 load_global_config 被调用
CONFIG = None

# 占位符，将在 load_global_config() 中初始化
API_ID = 0
API_HASH = ''
STRING_SESSION = ''
ALIST_URL = ''
ALIST_KEY = ''
ENABLE_189 = True
ENABLE_UC = False
ENABLE_123 = False
ENABLE_115 = False
SAVE_PATH = '/app/data'
LOOP_SWITCH = 2
MONITOR_INTERVAL_HOURS = 3
MAX_CONCURRENT_REQUESTS = 10
MONITOR_LIMIT = 3000
MONITOR_DAYS = 365
SMART_STOP_COUNT = 50
DB_RETENTION_DAYS = 30
CHANNEL_URLS = []
EXCLUDE_KEYWORDS = []
API_CONFIGS = []
ENABLE_PROXY = False
PROXY_URL = "socks5://192.168.2.1:7891"


def load_global_config():
    """在脚本启动时调用此函数，延迟加载配置并初始化全局变量。"""
    global CONFIG
    try:
        CONFIG = config_manager.load_config()
    except Exception as e:
        print(f"FATAL: Failed to load configuration: {e}")
        sys.exit(1)
    
    # --- 1. Telegram 配置 ---
    global API_ID, API_HASH, STRING_SESSION
    API_ID = CONFIG['TELEGRAM'].get('API_ID', 0)
    API_HASH = CONFIG['TELEGRAM'].get('API_HASH', '')
    STRING_SESSION = CONFIG['TELEGRAM'].get('STRING_SESSION', '')

    # --- 2. Alist-TVBox 接口配置 ---
    global ALIST_URL, ALIST_KEY
    ALIST_URL = CONFIG['ALIST'].get('URL', '')
    ALIST_KEY = CONFIG['ALIST'].get('KEY', '')

    # --- 3. 云盘抓取开关 ---
    global ENABLE_189, ENABLE_UC, ENABLE_123, ENABLE_115
    ENABLE_189 = CONFIG['DRIVE_SWITCHES'].get('ENABLE_189', True)
    ENABLE_UC = CONFIG['DRIVE_SWITCHES'].get('ENABLE_UC', False)
    ENABLE_123 = CONFIG['DRIVE_SWITCHES'].get('ENABLE_123', False)
    ENABLE_115 = CONFIG['DRIVE_SWITCHES'].get('ENABLE_115', False)


    # --- 4. 运行环境与扫描配置 ---
    global SAVE_PATH, LOOP_SWITCH, MONITOR_INTERVAL_HOURS, MAX_CONCURRENT_REQUESTS, MONITOR_LIMIT, MONITOR_DAYS, SMART_STOP_COUNT, DB_RETENTION_DAYS
    SAVE_PATH = CONFIG['MONITORING'].get('SAVE_PATH', '/app/data')
    LOOP_SWITCH = CONFIG['MONITORING'].get('LOOP_SWITCH', 2)
    MONITOR_INTERVAL_HOURS = CONFIG['MONITORING'].get('MONITOR_INTERVAL_HOURS', 3)
    MAX_CONCURRENT_REQUESTS = CONFIG['MONITORING'].get('MAX_CONCURRENT_REQUESTS', 10)
    MONITOR_LIMIT = CONFIG['MONITORING'].get('MONITOR_LIMIT', 3000)
    MONITOR_DAYS = CONFIG['MONITORING'].get('MONITOR_DAYS', 365)
    SMART_STOP_COUNT = CONFIG['MONITORING'].get('SMART_STOP_COUNT', 50)
    DB_RETENTION_DAYS = CONFIG['MONITORING'].get('DB_RETENTION_DAYS', 30)

    # --- 5. 监控频道列表 ---
    global CHANNEL_URLS
    CHANNEL_URLS = CONFIG['MONITORING'].get('CHANNEL_URLS', [])

    # --- 6. 全局关键词过滤 ---
    global EXCLUDE_KEYWORDS
    EXCLUDE_KEYWORDS = CONFIG['FILTERING'].get('EXCLUDE_KEYWORDS', [])
    if not EXCLUDE_KEYWORDS:
        EXCLUDE_KEYWORDS = ['小程序', '预告', '书籍', '电子书', '课程', '教程', '写真', 'MP3', '音乐']

    # --- 7. 分类抓取规则 ---
    global API_CONFIGS
    API_CONFIGS = CONFIG['RULES'].get('API_CONFIGS', [])
    if not API_CONFIGS:
        API_CONFIGS = [
            {'name': "Default (默认)", 'folder_prefix': "", 'priority_keywords': [], 'required_keywords': [], 'optional_keywords': [], 'excluded_keywords': [], 'try_join': True}
        ]

    # --- 8. 代理配置 ---
    global ENABLE_PROXY, PROXY_URL
    ENABLE_PROXY = CONFIG['PROXY'].get('ENABLE_PROXY', False)
    PROXY_URL = CONFIG['PROXY'].get('PROXY_URL', "socks5://192.168.2.1:7891")


# ==============================================================================
# ====== 📊 仪表盘 UI 模块 (Dashboard UI Module) ================================
# ==============================================================================

class Dashboard:
    """负责控制台表格输出，像素级对齐 (总宽80字符)"""
    
    # 列宽配置: Channel/Project(16) | Progress(13) | Found(13) | Added(13) | Time(13)
    HEADER_FMT = "{:<16} | {:>13} | {:>13} | {:>13} | {:>13}"
    ROW_FMT    = "{:<16} | {:>13} | {:>13} | {:>13} | {:>13}"
    
    @staticmethod
    def print_header():
        print("="*80)
        print(Dashboard.HEADER_FMT.format("Channel/Project", "Progress", "Found", "Added", "Time"))
        print("-" * 80)

    @staticmethod
    def print_channel_frame(channel_name, total, current, stats, start_time, is_final=False):
        """绘制信息"""
        # 计算耗时
        duration_str = "-"
        if start_time:
            elapsed = datetime.now() - start_time
            mm, ss = divmod(elapsed.seconds, 60)
            duration_str = f"{mm:02d}m {ss:02d}s"
        
        # 截断频道名
        safe_name = channel_name[:16]

        # 进度字符串处理
        progress_str = "-"
        if isinstance(total, int) and isinstance(current, int):
            if total == -1: 
                progress_str = "-"
            else:
                progress_str = f"{current}/{total}"
        elif isinstance(total, str): 
            progress_str = total
        
        # 计算总数
        total_found = sum(s['found'] for s in stats.values() if isinstance(s, dict))
        total_added = sum(s['added'] for s in stats.values() if isinstance(s, dict))

        # --- 第1行: 频道总览 ---
        line1 = Dashboard.ROW_FMT.format(safe_name, progress_str[:13], str(total_found), str(total_added), duration_str)
        
        # 动态生成规则行
        rule_lines = [line1]
        
        # 确保 API_CONFIGS 已经加载
        global API_CONFIGS
        configs_to_iterate = API_CONFIGS if API_CONFIGS else [{'name': "Default"}] # 容错
        
        for idx, cfg in enumerate(configs_to_iterate):
            if idx in stats and isinstance(stats[idx], dict):
                s_found = stats[idx]['found']
                s_added = stats[idx]['added']
                line_rule = Dashboard.ROW_FMT.format(f"  |_ {cfg['name'][:12]}", "-", str(s_found), str(s_added), "-")
                rule_lines.append(line_rule)
        
        # 确保 "special" 统计单独打印 (如果存在)
        if 'special' in stats and isinstance(stats['special'], dict):
            sp_found = stats['special']['found']
            sp_added = stats['special']['added']
            if sp_found > 0 or sp_added > 0:
                 line_special = Dashboard.ROW_FMT.format("  |_ Priority", "-", str(sp_found), str(sp_added), "-")
                 rule_lines.append(line_special)

        # 打印并处理光标回退
        print("\r" + "\n".join(rule_lines) + "\033[K", end="")
        
        # 回退光标到起始位置
        if not is_final:
            for _ in range(len(rule_lines) - 1):
                 sys.stdout.write("\033[F")
            sys.stdout.write("\033[F\033[K")
            sys.stdout.flush()
        else:
            print() # 完成时换行

# ==============================================================================
# ====== 💻 核心逻辑代码 (Core Logic) ===========================================
# ==============================================================================

RE_ACCESS_CODE = re.compile(r'(?:密码|提取码|验证码|访问码|分享密码|密钥|pwd|password|share_pwd|pass_code|#)[=:：\s]*([a-zA-Z0-9]{4,6})(?![a-zA-Z0-9])', re.IGNORECASE)
RE_URL_PARAM_CODE = re.compile(r'[?&](?:pwd|password|access_code|code|sharepwd)=([a-zA-Z0-9]{4,6})', re.IGNORECASE)
RE_TIANYI = re.compile(r'(?:https?://)?cloud\.189\.cn/t/([a-zA-Z0-9]{12})\b', re.IGNORECASE)
RE_UC = re.compile(r'drive\.uc\.cn/s/([a-zA-Z0-9\-_]+)([^#]*)?(#*/list/share/([^\?\-]+))?', re.IGNORECASE)
RE_123 = re.compile(r'(?:https?://)?(?:www\.)?(?:123[\d]*|pan\.123)\.com/s/([a-zA-Z0-9\-_]+)', re.IGNORECASE)
RE_115 = re.compile(r'(?:https?://)?(?:www\.)?(?:115cdn\.com|115\.com)/s/([a-zA-Z0-9]+)', re.IGNORECASE)


class SQLiteManager:
    """SQLite 数据库管理器，用于存储已处理的消息和已推送的链接。"""
    
    def __init__(self, db_path):
        # 使用全局配置 DB_RETENTION_DAYS 和 SAVE_PATH
        if db_path and not os.path.exists(db_path):
            try: os.makedirs(db_path, exist_ok=True)
            except: pass
        self.db_file = os.path.join(db_path, "189api.db") if db_path else "189api.db"
        self.conn = sqlite3.connect(self.db_file, check_same_thread=False)
        self.cursor = self.conn.cursor()
        self._init_db()
        self._migrate_db() 

    def _init_db(self):
        try:
            self.cursor.execute('''CREATE TABLE IF NOT EXISTS processed_msgs
                             (channel_id TEXT, msg_id INTEGER, api_index INTEGER, 
                              PRIMARY KEY (channel_id, msg_id, api_index))''')
            self.cursor.execute('''CREATE TABLE IF NOT EXISTS sent_links
                             (link TEXT, api_index INTEGER, 
                              PRIMARY KEY (link, api_index))''')
            self.conn.commit()
        except Exception as e:
            print(f"DB Error: {e}")

    def _migrate_db(self):
        try:
            self.cursor.execute("PRAGMA table_info(processed_msgs)")
            columns = [info[1] for info in self.cursor.fetchall()]
            if 'timestamp' not in columns:
                self.cursor.execute("ALTER TABLE processed_msgs ADD COLUMN timestamp REAL DEFAULT 0")
                self.conn.commit()
        except: pass

    def cleanup_old_records(self, days=DB_RETENTION_DAYS): # 使用全局配置 DB_RETENTION_DAYS
        try:
            cutoff = time.time() - (days * 86400)
            self.cursor.execute("DELETE FROM processed_msgs WHERE timestamp > 0 AND timestamp < ?", (cutoff,))
            self.conn.commit()
        except: pass

    def close(self):
        if self.conn: self.conn.close()

    def is_msg_processed(self, channel_id, msg_id):
        try:
            self.cursor.execute("SELECT 1 FROM processed_msgs WHERE channel_id=? AND msg_id=? LIMIT 1", (channel_id, msg_id))
            return self.cursor.fetchone() is not None
        except: return False

    def is_link_sent(self, link, api_index):
        try:
            self.cursor.execute("SELECT 1 FROM sent_links WHERE link=? AND api_index=?", (link, api_index))
            return self.cursor.fetchone() is not None
        except: return False

    def add_link(self, link, api_index):
        try:
            self.cursor.execute("INSERT OR IGNORE INTO sent_links VALUES (?,?)", (link, api_index))
            self.conn.commit()
        except: pass
            
    def bulk_add_msgs(self, data_list):
        if not data_list: return
        try:
            self.cursor.executemany("INSERT OR IGNORE INTO processed_msgs (channel_id, msg_id, api_index, timestamp) VALUES (?,?,?,?)", data_list)
            self.conn.commit()
        except: pass


class StringCleaner:
    """字符串清理工具，用于提取标题和过滤垃圾信息。"""
    
    # 仅用于"丢弃整行"的关键词 (绝对垃圾)
    JUNK_KEYWORDS = [
        "福利", "频道", "关注", "置顶", "推荐", "via", "转自", "来源", "投稿", "小编", "整理", "失效", "补档",
        "禁言", "通知", "更新", "日更", "公众号", "加入", "点击", "领取"
    ]
    AD_PATTERNS = [
        r'天翼云盘.*资源分享', r'via\s*🤖編號\s*9527', r'🏷?\s*标签\s*：.*', r'[🏷#]\s*\w+',
        r'UC网盘.*分享', r'资源编号：\d+', r'123网盘.*分享', r'https?://\S+', 
        r'[a-zA-Z0-9]+\.(cn|com|net)/\S+'
    ]

    @staticmethod
    def clean(text):
        if not text: return ""
        for p in StringCleaner.AD_PATTERNS:
            text = re.sub(p, '', text, flags=re.IGNORECASE)
        text = re.sub(r'https?://\S+', '', text)
        text = re.sub(r'[@#]\S+', '', text)
        # 移除 Emoji
        text = re.sub(r'[\U00010000-\U0010ffff]', '', text) 
        # 保留技术符号 (& + / _)
        text = re.sub(r'[^\u4e00-\u9fa5a-zA-Z0-9,，.。!！?？:：《》()（）【】\+\-\s\u3000&/_]', ' ', text)
        return text.strip()[:195]

    @staticmethod
    def is_junk_line(line):
        line = line.strip()
        if len(line) < 2: return True
        for kw in StringCleaner.JUNK_KEYWORDS:
            if kw in line: return True
        if re.match(r'^[\d\s\.\-\*]+$', line): return True
        return False

def get_channel_id(url):
    return re.sub(r'[^\w\-]', '_', re.sub(r'https?://', '', url))[:50]

class CloudMonitor:
    def __init__(self):
        # 此时全局配置变量应该已经被 load_global_config() 初始化
        self.db = SQLiteManager(SAVE_PATH) 
        self.client = None
        self.sem = asyncio.Semaphore(MAX_CONCURRENT_REQUESTS) 
        self.session_sent_links = set()
        self._init_logging()

    def _init_logging(self):
        if SAVE_PATH and not os.path.exists(SAVE_PATH): 
            try: os.makedirs(SAVE_PATH, exist_ok=True)
            except: pass
        log_file = os.path.join(SAVE_PATH, "189api_error.log") if SAVE_PATH else "189api_error.log"
        self.logger = logging.getLogger('189api')
        self.logger.setLevel(logging.ERROR)
        if not self.logger.handlers:
            handler = TimedRotatingFileHandler(log_file, when='midnight', interval=1, backupCount=30, encoding='utf-8')
            formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
            handler.setFormatter(formatter)
            self.logger.addHandler(handler)

    async def start(self):
        self.db.cleanup_old_records(DB_RETENTION_DAYS) 
        
        proxy_params = None
        if ENABLE_PROXY: 
            try:
                import socks
                parsed = urlparse(PROXY_URL) 
                if 'socks5' in parsed.scheme: p_type = socks.SOCKS5
                elif 'socks4' in parsed.scheme: p_type = socks.SOCKS4
                else: p_type = socks.HTTP
                proxy_params = (p_type, parsed.hostname, parsed.port, True, parsed.username, parsed.password)
            except Exception as e: 
                print("Proxy Config Error")
                self.logger.error(f"Proxy Config Error: {e}")
                return
        
        try:
            client_params = {'session': StringSession(STRING_SESSION), 'api_id': API_ID, 'api_hash': API_HASH}
            if proxy_params: client_params['proxy'] = proxy_params
            self.client = TelegramClient(**client_params)
            await self.client.start()
        except Exception as e:
            print(f"Connect Failed: {e}")
            self.logger.error(f"Telegram Connect Failed: {e}")
            self.db.close()
            return

        try:
            async with aiohttp.ClientSession() as session:
                if LOOP_SWITCH == 1: 
                    while True:
                        self.session_sent_links.clear() 
                        await self.run_cycle(session)
                        await asyncio.sleep(MONITOR_INTERVAL_HOURS * 3600) 
                else:
                    await self.run_cycle(session)
        finally:
            await self.client.disconnect()
            self.db.close()

    async def run_cycle(self, session):
        Dashboard.print_header()
        for channel_url in CHANNEL_URLS: 
            try:
                await self.process_channel_unified(session, channel_url)
                print("-" * 80)
            except Exception as e:
                print(f"\n❌ {channel_url} Error: {e}")
                self.logger.error(f"Run Cycle Error for {channel_url}: {traceback.format_exc()}")
                print("-" * 80)

    async def process_channel_unified(self, session, channel_url):
        channel_name = channel_url.split('/')[-1]
        channel_id = get_channel_id(channel_url)
        
        # 初始化统计数据
        stats = {idx: {'found': 0, 'added': 0} for idx in range(len(API_CONFIGS))}
        stats['special'] = {'found': 0, 'added': 0}

        start_time = datetime.now()
        Dashboard.print_channel_frame(channel_name, 0, 0, stats, start_time)

        try:
            any_try_join = any(cfg.get('try_join', False) for cfg in API_CONFIGS) 
            entity = await self.get_entity_safe(channel_url, any_try_join)
            
            if not entity:
                Dashboard.print_channel_frame(channel_name, -1, -1, stats, start_time, is_final=True)
                self.logger.error(f"Channel not found or cannot join: {channel_url}")
                return

            # --- Phase 1: Standard Scan ---
            min_date = datetime.now(timezone.utc) - timedelta(days=MONITOR_DAYS) 
            messages = []
            fetch_count = 0
            consecutive_old_count = 0 
            
            try:
                async for msg in self.client.iter_messages(entity, limit=MONITOR_LIMIT): 
                    if msg.date < min_date: break
                    
                    if self.db.is_msg_processed(channel_id, msg.id):
                        consecutive_old_count += 1
                        if consecutive_old_count >= SMART_STOP_COUNT: break 
                    else:
                        consecutive_old_count = 0

                    messages.append(msg)
                    fetch_count += 1
                    if fetch_count % 50 == 0:
                        Dashboard.print_channel_frame(channel_name, MONITOR_LIMIT, fetch_count, stats, start_time)
                        
            except ChannelPrivateError: 
                self.logger.error(f"Access Denied (Private) for channel: {channel_url}")
            
            if messages:
                await self._process_message_batch(session, messages, channel_name, channel_id, stats, start_time)

            # --- Phase 2: Priority Search ---
            Dashboard.print_channel_frame(channel_name, MONITOR_LIMIT, fetch_count, stats, start_time)

            for api_idx, cfg in enumerate(API_CONFIGS): 
                priorities = cfg.get('priority_keywords', [])
                if not priorities: continue
                
                for keyword in priorities:
                    search_msgs = []
                    try:
                        async for msg in self.client.iter_messages(entity, search=keyword, limit=500):
                            search_msgs.append(msg)
                    except Exception as e:
                        self.logger.error(f"Search Error '{keyword}': {e}")
                    
                    if search_msgs:
                        await self._process_message_batch(
                            session, search_msgs, channel_name, channel_id, stats, start_time, 
                            restrict_to_api_idx=api_idx
                        )

            Dashboard.print_channel_frame(channel_name, MONITOR_LIMIT, fetch_count, stats, start_time, is_final=True)

        except Exception as e:
            self.logger.error(f"Process Channel Error {channel_name}: {traceback.format_exc()}")
            Dashboard.print_channel_frame(channel_name, -1, -1, stats, start_time, is_final=True)

    async def _process_message_batch(self, session, messages, channel_name, channel_id, stats, start_time, restrict_to_api_idx=None):
        tasks = []
        msgs_to_save = []
        now_ts = time.time()
        
        current_idx = 0
        total_len = len(messages)

        for msg in messages:
            current_idx += 1
            if current_idx % 20 == 0:
                Dashboard.print_channel_frame(channel_name, total_len, current_idx, stats, start_time)

            if not msg.text: continue

            is_spam = False
            for kw in EXCLUDE_KEYWORDS: 
                if kw in msg.text: 
                    is_spam = True; break
            if is_spam: continue

            cloud_infos = self.extract_links(msg)
            if not cloud_infos: continue
            
            msgs_to_save.append((channel_id, msg.id, 0, now_ts))

            for info in cloud_infos:
                matched_rule = False 
                
                # 遍历所有配置的 API 规则
                for api_idx, api_cfg in enumerate(API_CONFIGS): 
                    if restrict_to_api_idx is not None and api_idx != restrict_to_api_idx:
                        continue
                    if matched_rule: break
                    
                    # 避免重复推送
                    if (info['link'], api_idx) in self.session_sent_links:
                        matched_rule = True; break

                    if self.db.is_link_sent(info['link'], api_idx): 
                        matched_rule = True; break

                    # 检查关键词是否匹配当前规则
                    is_priority_hit = self.check_api_keywords(msg.text, api_cfg)
                    if not is_priority_hit: continue

                    # 检查排除词
                    check_content = info['desc']
                    if not self.check_api_excludes(check_content, api_cfg): continue

                    matched_rule = True
                    stats[api_idx]['found'] += 1
                    
                    # 检查是否为 'special' 命中
                    priority_kws = api_cfg.get('priority_keywords', [])
                    is_special_hit = False
                    if priority_kws and any(k in msg.text for k in priority_kws):
                        stats['special']['found'] += 1
                        is_special_hit = True

                    # 构建任务名称和 payload
                    task_name = self.build_task_name(info, api_cfg.get('folder_prefix', ''))
                    payload = {
                        "path": task_name, "shareId": info['code'],
                        "folderId": "", "password": info['pwd'] or "", "type": info['type_id']
                    }
                    
                    self.session_sent_links.add((info['link'], api_idx))
                    tasks.append(self.push_wrapper(session, payload, info, msg.id, api_idx, is_special_hit, channel_name, total_len, current_idx, stats, start_time))
        
        if tasks:
            Dashboard.print_channel_frame(channel_name, total_len, total_len, stats, start_time)
            await asyncio.gather(*tasks)
        
        # 批量保存已处理的消息 ID
        self.db.bulk_add_msgs(msgs_to_save)

    async def push_wrapper(self, session, payload, info, msg_id, api_idx, is_special_hit, channel_name, total, current, stats, start_time):
        success, resp = await self.send_to_api(session, payload)
        if success:
            stats[api_idx]['added'] += 1
            if is_special_hit:
                stats['special']['added'] += 1
            self.db.add_link(info['link'], api_idx)
            Dashboard.print_channel_frame(channel_name, total, current, stats, start_time)
        elif resp != "Exists":
            self.logger.error(f"Push Failed [{resp}] for {info['desc']}: {info['link']}")

    async def send_to_api(self, session, payload):
        async with self.sem: 
            headers = {"x-api-key": ALIST_KEY, "Content-Type": "application/json", "Authorization": ALIST_KEY}
            for attempt in range(3): 
                try:
                    async with session.post(ALIST_URL, json=payload, headers=headers, timeout=20) as resp:
                        if resp.status == 200: return True, ""
                        if resp.status == 400: return False, "Exists" 
                        if resp.status >= 500: 
                            await asyncio.sleep(1); continue
                        return False, f"HTTP {resp.status}"
                except Exception as e:
                    if attempt == 2:
                        self.logger.error(f"API Network Error: {e}")
                    if attempt < 2: await asyncio.sleep(1)
                    else: return False, "NetErr"
            return False, "MaxRetries"

    async def get_entity_safe(self, url, try_join):
        try: return await self.client.get_entity(url)
        except:
            if '+' in url and try_join:
                try:
                    await self.client(ImportChatInviteRequest(url.split('+')[-1]))
                    return await self.client.get_entity(url)
                except Exception as e:
                    self.logger.error(f"Join Channel Failed {url}: {e}")
                    pass
            return None

    def check_api_excludes(self, text, cfg):
        local_exclude = cfg.get('excluded_keywords', [])
        if local_exclude:
            for kw in local_exclude:
                if re.match(r'^[a-zA-Z0-9]+$', kw):
                    if re.search(rf'\b{re.escape(kw)}\b', text, re.IGNORECASE): return False
                else:
                    if kw in text: return False
        return True

    def check_api_keywords(self, text, cfg):
        priority = cfg.get('priority_keywords', [])
        hit_priority = False
        if priority and any(k in text for k in priority):
            hit_priority = True
        
        req = cfg.get('required_keywords', [])
        if not hit_priority:
            if req and not all(k in text for k in req): return False
        
        opt = cfg.get('optional_keywords', [])
        if opt and not any(k in text for k in opt): return False
        return True

    def extract_links(self, msg):
        results = []
        text = msg.message.replace('%EF%BC%88', '(').replace('%EF%BC%89', ')')
        
        smart_title = "Untitled"
        lines = [line.strip() for line in text.split('\n') if line.strip()]
        name_marker = re.search(r'(?:资源|文件)?(?:名称|名|片名|Title)[：:]\s*(.+)', text)
        if name_marker:
            smart_title = StringCleaner.clean(name_marker.group(1))
        else:
            for line in lines:
                if StringCleaner.is_junk_line(line): continue
                cleaned = StringCleaner.clean(line)
                if len(cleaned) > 2: 
                    smart_title = cleaned; break

        m_pwd = RE_ACCESS_CODE.search(text)
        global_pwd = m_pwd.group(1) if m_pwd else None
        
        patterns = []
        if ENABLE_189: patterns.append((RE_TIANYI, 'tianyi', 9, "https://cloud.189.cn/t/")) 
        if ENABLE_UC:  patterns.append((RE_UC, 'uc', 7, "https://drive.uc.cn/s/")) 
        if ENABLE_123: patterns.append((RE_123, '123', 3, "https://www.123865.com/s/")) 
        if ENABLE_115: patterns.append((RE_115, '115', 8, "https://115cdn.com/s/"))


        items = []
        for p, ctype, cid, prefix in patterns:
            for m in p.finditer(text):
                items.append({'code': m.group(1), 'type': ctype, 'tid': cid, 'prefix': prefix, 'ent': False, 'm': m})
        if msg.entities:
            for ent in msg.entities:
                if isinstance(ent, MessageEntityTextUrl):
                    for p, ctype, cid, prefix in patterns:
                        m = p.search(ent.url)
                        if m:
                            items.append({'code': m.group(1), 'type': ctype, 'tid': cid, 'prefix': prefix, 'ent': True, 'desc': text[ent.offset:ent.offset+ent.length], 'url': ent.url})

        unique_codes = set(item['code'] for item in items)
        is_multi_link = len(unique_codes) > 1
        
        if is_multi_link:
            base_title = re.sub(r'(?i)\b(?:4K|1080[Pp]?|2160[Pp]?|SDR|HDR\d*\+?|DV|Dolby\s*Vision)(?:[\s&/+\\]+(?:4K|1080[Pp]?|2160[Pp]?|SDR|HDR\d*\+?|DV|Dolby\s*Vision))*\b', '', smart_title)
            base_title = re.sub(r'\s+', ' ', base_title).strip()
        else:
            base_title = smart_title

        seen = set()
        for it in items:
            if it['code'] in seen: continue
            seen.add(it['code'])
            
            pwd = global_pwd
            url_check = it.get('url', it.get('m').group(0) if not it.get('ent') else "")
            url_pwd = RE_URL_PARAM_CODE.search(url_check)
            if url_pwd: pwd = url_pwd.group(1)

            local_desc = ""
            if it.get('ent'):
                d = StringCleaner.clean(it['desc'])
                if len(d) > 1: local_desc = d
            else:
                start = it['m'].start()
                context = text[:start]
                prev_lines = context.split('\n')
                for i in range(len(prev_lines) - 1, -1, -1):
                    line = prev_lines[i].strip()
                    if not line: continue
                    cleaned_line = StringCleaner.clean(line)
                    if not cleaned_line or StringCleaner.is_junk_line(cleaned_line): continue
                    
                    if is_multi_link:
                        local_desc = cleaned_line
                        break
                    else:
                        if smart_title not in cleaned_line and cleaned_line not in smart_title:
                             local_desc = cleaned_line
                        break

            if is_multi_link:
                final_desc = f"{base_title} {local_desc}" if local_desc else base_title
            else:
                final_desc = smart_title

            results.append({
                'type': it['type'], 'type_id': it['tid'], 'code': it['code'],
                'link': f"{it['prefix']}{it['code']}", 'pwd': pwd, 
                'desc': final_desc
            })
        return results

    def build_task_name(self, info, prefix):
        return f"{prefix}{info['desc']}_{info['code'][-4:]}"[:200]

if __name__ == '__main__':
    # Step 1: 在启动主逻辑前，先加载配置并初始化所有全局变量
    load_global_config() 
    
    if LOOP_SWITCH != 1:
        if not all([API_ID, API_HASH, STRING_SESSION, ALIST_URL, ALIST_KEY, CHANNEL_URLS]):
            print("FATAL: 核心配置（API/Alist/Session/频道列表）不完整，请检查 config.json。")
            sys.exit(1)
            
    monitor = CloudMonitor()
    try: 
        asyncio.run(monitor.start())
    except KeyboardInterrupt: 
        print("\nStopped by user")
    except Exception as e:
        print(f"FATAL ERROR: {traceback.format_exc()}")
        monitor.logger.error(f"Monitor Crashed: {traceback.format_exc()}")
