from flask import Flask, render_template, request, jsonify, redirect, url_for
import config_manager
import subprocess
import sys
import threading
import os
import signal
import json
import traceback

app = Flask(__name__)
monitor_process = None

# --- 辅助函数 ---

def run_monitor_script():
    """在后台线程中运行云盘监控脚本。"""
    global monitor_process
    
    # 确保在启动前加载最新的配置
    current_config = config_manager.load_config()
    print("加载最新配置成功，准备启动监控脚本...")

    try:
        # 使用 os.setsid 确保进程组能被统一杀死
        monitor_process = subprocess.Popen([sys.executable, 'cloud_monitor.py'],
                                           stdout=subprocess.PIPE,
                                           stderr=subprocess.STDOUT,
                                           bufsize=1,
                                           universal_newlines=True,
                                           preexec_fn=os.setsid)

        print(f"监控脚本已启动，PID: {monitor_process.pid}")
        # 实时打印监控脚本的输出
        for line in iter(monitor_process.stdout.readline, ''):
            print(f"[MONITOR LOG] {line.strip()}")
            
        monitor_process.wait()
        print("监控脚本已结束。")
    except Exception as e:
        print(f"启动监控脚本失败: {e}", file=sys.stderr)
    finally:
        monitor_process = None


def parse_keywords(text):
    """将多行文本转换为关键词列表，并去除空行。"""
    if not text:
        return []
    # 过滤掉空格或空字符串
    return [k.strip() for k in text.split('\n') if k.strip()]

# --- Flask 路由 ---

@app.route('/')
def index():
    """渲染前端配置页面，并加载当前配置。"""
    # 确保每次访问页面都加载最新的配置
    current_config = config_manager.load_config()
    is_running = monitor_process is not None and monitor_process.poll() is None
    
    return render_template('config_form.html', config=current_config, is_running=is_running)

@app.route('/api/config', methods=['POST'])
def update_config():
    """接收前端提交的配置数据并保存。"""
    data = request.json
    
    if not data:
        return jsonify({"success": False, "message": "保存失败: 接收到空数据。"}), 400

    try:
        # 1. 基础配置项和数字类型转换
        data['TELEGRAM']['API_ID'] = int(data['TELEGRAM']['API_ID'])
        data['MONITORING']['LOOP_SWITCH'] = int(data['MONITORING']['LOOP_SWITCH'])
        # 使用 float 确保循环间隔支持小数
        data['MONITORING']['MONITOR_INTERVAL_HOURS'] = float(data['MONITORING']['MONITOR_INTERVAL_HOURS'])
        
        # ✅ 全局扫描参数类型转换 (新增/修正)
        data['MONITORING']['MONITOR_LIMIT'] = int(data['MONITORING']['MONITOR_LIMIT'])
        data['MONITORING']['MONITOR_DAYS'] = int(data['MONITORING']['MONITOR_DAYS'])
        data['MONITORING']['SMART_STOP_COUNT'] = int(data['MONITORING']['SMART_STOP_COUNT'])
        data['MONITORING']['DB_RETENTION_DAYS'] = int(data['MONITORING']['DB_RETENTION_DAYS']) 

        # 2. 关键词列表解析 (从 TEXT 字段解析到列表)
        
        # 2.1 全局频道列表
        data['MONITORING']['CHANNEL_URLS'] = parse_keywords(data['MONITORING'].get('CHANNEL_URLS_TEXT', ''))
        data['MONITORING'].pop('CHANNEL_URLS_TEXT', None) # 清理 TEXT 字段

        # 2.2 全局排除关键词
        data['FILTERING']['EXCLUDE_KEYWORDS'] = parse_keywords(data['FILTERING'].get('EXCLUDE_KEYWORDS_TEXT', ''))
        data['FILTERING'].pop('EXCLUDE_KEYWORDS_TEXT', None) # 清理 TEXT 字段

        # 2.3 复杂的 API_CONFIGS 规则列表
        if 'RULES' in data and 'API_CONFIGS' in data['RULES']:
            for rule in data['RULES']['API_CONFIGS']:
                
                # 关键词处理：从 TEXT 字段转换为列表 (无 _text 后缀)
                rule['priority_keywords'] = parse_keywords(rule.get('priority_keywords_text', ''))
                rule['required_keywords'] = parse_keywords(rule.get('required_keywords_text', '')) 
                rule['optional_keywords'] = parse_keywords(rule.get('optional_keywords_text', ''))
                rule['excluded_keywords'] = parse_keywords(rule.get('excluded_keywords_text', ''))
                
                # ❗❗❗ 清理前端提交的原始文本字段，确保 config.json 只存储列表
                rule.pop('priority_keywords_text', None)
                rule.pop('required_keywords_text', None)
                rule.pop('optional_keywords_text', None)
                rule.pop('excluded_keywords_text', None)
                
                # 布尔值处理 (try_join 必须处理字符串 'on' 或布尔值 True)
                rule['try_join'] = rule.get('try_join', False) in (True, 'true', 'on')
        
        # 3. 调用 config_manager 保存配置
        config_manager.save_config(data)
        return jsonify({"success": True, "message": "配置已成功保存！"})
    
    except ValueError as e:
        return jsonify({"success": False, "message": f"保存失败: 数字/布尔类型转换错误。请检查输入: {str(e)}"}), 400
    except Exception as e:
        print(f"配置保存失败: {traceback.format_exc()}", file=sys.stderr)
        return jsonify({"success": False, "message": f"保存失败: 内部错误: {str(e)}"}), 500

@app.route('/api/monitor/start', methods=['POST'])
def start_monitor():
    """启动监控脚本。"""
    global monitor_process
    if monitor_process and monitor_process.poll() is None:
        return jsonify({"success": False, "message": "监控已在运行中。"})

    current_config = config_manager.load_config()
    # 简单检查核心配置是否缺失
    if not all([current_config['TELEGRAM']['API_ID'], current_config['TELEGRAM']['API_HASH'], current_config['TELEGRAM']['STRING_SESSION'], current_config['ALIST']['URL']]):
        return jsonify({"success": False, "message": "启动失败: 核心 Telegram/Alist 配置不完整，请先保存配置！"})

    thread = threading.Thread(target=run_monitor_script)
    thread.daemon = True
    thread.start()

    return jsonify({"success": True, "message": "监控脚本已在后台启动。"})

@app.route('/api/monitor/stop', methods=['POST'])
def stop_monitor():
    """停止监控脚本。"""
    global monitor_process
    if monitor_process and monitor_process.poll() is None:
        try:
            # 杀死进程组，确保所有子进程都被终止
            os.killpg(os.getpgid(monitor_process.pid), signal.SIGTERM)
            monitor_process.wait(timeout=5)
            monitor_process = None
            return jsonify({"success": True, "message": "监控脚本已停止。"})
        except Exception as e:
            # 如果终止失败，尝试再次设置 monitor_process 为 None 以重置状态
            monitor_process = None 
            return jsonify({"success": False, "message": f"停止脚本失败: {str(e)}"})
    return jsonify({"success": False, "message": "监控脚本未运行。"})


if __name__ == '__main__':
    # 确保数据目录存在
    data_dir = os.path.join(os.path.dirname(__file__), 'data')
    os.makedirs(data_dir, exist_ok=True)

    # 检查并创建初始 config.json，确保文件存在
    if not os.path.exists(config_manager.CONFIG_FILE):
        config_manager.save_config(config_manager.load_config())

    # 启动 Flask Web 服务
    app.run(host='0.0.0.0', port=5000, debug=False)
