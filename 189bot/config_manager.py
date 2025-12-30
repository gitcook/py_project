import json
import os

# 定义配置文件的路径
# 确保与 SAVE_PATH 保持一致，位于 /app/data 目录下
DATA_DIR = os.path.join(os.path.dirname(__file__), 'data')
CONFIG_FILE = os.path.join(DATA_DIR, 'config.json')

def load_config():
    """从 config.json 文件加载配置，如果不存在则返回默认结构。"""
    
    # 辅助函数：递归更新字典，源字典(source)的值覆盖目标字典(target)的值
    def deep_update(target, source):
        """
        递归更新字典。
        'source' (文件配置) 中的值覆盖 'target' (默认配置) 中的值。
        """
        for k, v in source.items():
            if k in target and isinstance(target[k], dict) and isinstance(v, dict):
                deep_update(target[k], v) # 递归处理子字典
            else:
                target[k] = v # 覆盖或添加非字典值
                
    # 返回一个包含默认结构体的配置
    default_config = {
        "TELEGRAM": {"API_ID": 0, "API_HASH": "", "STRING_SESSION": ""},
        "ALIST": {"URL": "", "KEY": ""},
        "MONITORING": {
            "SAVE_PATH": "/app/data", 
            "LOOP_SWITCH": 2, 
            "MONITOR_INTERVAL_HOURS": 3, 
            "CHANNEL_URLS": [], 
            "MAX_CONCURRENT_REQUESTS": 10, 
            "MONITOR_LIMIT": 3000, 
            "MONITOR_DAYS": 365, 
            "SMART_STOP_COUNT": 50, 
            "DB_RETENTION_DAYS": 30
        },
        "DRIVE_SWITCHES": {"ENABLE_189": True, "ENABLE_UC": False, "ENABLE_123": False},
        "FILTERING": {"EXCLUDE_KEYWORDS": ['小程序', '预告', '预感', '盈利', '即可观看', '书籍', '电子书', '图书', '丛书', '期刊','app','软件', '破解版','解锁','专业版','高级版','最新版','食谱', '免安装', '免广告','安卓', 'Android', '课程', '作品', '教程', '教学', '全书', '名著', 'mobi', 'MOBI', 'epub','任天堂','PC','单机游戏', 'pdf', 'PDF', 'PPT', '抽奖', '完整版', '有声书','读者','文学', '写作', '节课', '套装', '话术', '纯净版', '日历', 'txt', 'MP3','网赚', 'mp3', 'WAV', 'CD', '音乐', '专辑', '模板', '书中', '读物', '入门', '零基础', '常识', '电商', '小红书','JPG','短视频','工作总结', '哈哈哈哈哈', '写真','抖音', '资料', '华为', '短剧', '纪录片', '记录片', '纪录', '纪实', '学习', '付费', '小学', '初中','数学', '语文', '唐诗','魔法坏女巫','车载','DJ','合并', '演唱会', '综艺']}, 
        "RULES": {
            "API_CONFIGS": [
                {
                    'name': "TV Show (剧集)", 
                    'folder_prefix': "剧集/",
                    'priority_keywords': ["权力的游戏", "绝命毒师"], 
                    'required_keywords': [], 
                    'optional_keywords': ["季", "集", "EP", "S0", "美剧", "英剧", "日剧", "韩剧"], 
                    'excluded_keywords': ["P5", "Profile 5", "DVP5"], 
                    'try_join': True
                },
                {
                    'name': "Movies (电影)", 
                    'folder_prefix': "电影/",
                    'priority_keywords': [],
                    'required_keywords': [], 
                    'optional_keywords': ["原盘", "REMUX", "4K", "HDR","简中", "简英", "简繁", "双语", "HD", "60 FPS" ],
                    'excluded_keywords': ["枪版", "抢先版", "TS", "TC", "1080", "1080p", "S0", "EP", "更至", "完结"],
                    'try_join': True
                }
            ]
        }, 
        "PROXY": {"ENABLE_PROXY": False, "PROXY_URL": "socks5://192.168.2.1:7891"}
    }
    
    # 检查配置文件是否存在
    if not os.path.exists(CONFIG_FILE):
        return default_config
        
    try:
        with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
            # 1. 从文件加载现有配置
            current_config = json.load(f) 
            
            # 2. 从默认配置的副本开始，作为最终结果
            final_config = default_config.copy()
            
            # 3. **关键步骤：** 使用文件配置递归更新默认配置
            #    这样文件中的值会覆盖默认值，同时保留默认配置中新增的键
            deep_update(final_config, current_config)
            
            return final_config
            
    except json.JSONDecodeError:
        print("警告: config.json 文件格式错误，将使用默认配置。")
        return default_config

def save_config(new_config):
    """将新配置保存到 config.json 文件。"""
    # 确保保存路径存在
    os.makedirs(os.path.dirname(CONFIG_FILE), exist_ok=True)
    with open(CONFIG_FILE, 'w', encoding='utf-8') as f:
        json.dump(new_config, f, indent=4, ensure_ascii=False)
