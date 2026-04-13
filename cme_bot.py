import requests
import os
import datetime
import time
import sys  
from datetime import timedelta
from github import Github

# ==========================================
# 配置区域
# ==========================================
GITHUB_TOKEN = os.environ.get("GH_PERSONAL_TOKEN")
GITHUB_REPO = "Curarpikt0000/cme-data-archive"

# ✅ 关键修复：优先读取 GitHub Secrets 注入的环境变量，如果没读到，则使用你的实际 Key 兜底
SCRAPER_API_KEY = os.environ.get("SCRAPER_API_KEY", "0434276aa91c62e0340dcd30819f3fbf")

DISPLAY_DATE = (datetime.datetime.now() - timedelta(days=1)).strftime('%Y-%m-%d')
GITHUB_PATH_PREFIX = f"data/{DISPLAY_DATE}/"

BASE_URL = "https://www.cmegroup.com/delivery_reports/"
METALS_FILES = [
    'MetalsIssuesAndStopsReport.pdf', 'Gold_Stocks.xls', 'Silver_stocks.xls', 
    'Copper_Stocks.xls', 'PA-PL_Stck_Rprt.xls', 'Aluminum_Stocks.xls', 
    'Zinc_Stocks.xls', 'Lead_Stocks.xls'
]

def upload_to_github(filename, content_bytes):
    """上传文件到 GitHub"""
    if not GITHUB_TOKEN:
        print("❌ 错误: 缺少 GH_PERSONAL_TOKEN")
        return False
    try:
        g = Github(GITHUB_TOKEN)
        repo = g.get_repo(GITHUB_REPO)
        target_path = GITHUB_PATH_PREFIX + filename
        try:
            contents = repo.get_contents(target_path)
            repo.update_file(contents.path, f"Update {filename} {DISPLAY_DATE}", content_bytes, contents.sha)
        except:
            repo.create_file(target_path, f"Add {filename} {DISPLAY_DATE}", content_bytes)
        print(f"✅ GitHub 提交成功: {filename}")
        return True
    except Exception as e:
        print(f"❌ GitHub 提交失败 ({filename}): {e}")
        return False

def download_with_scraperapi(filename):
    """通过 ScraperAPI 下载文件（带自动重试机制）"""
    target_url = f"{BASE_URL}{filename}"
    proxy_url = "http://api.scraperapi.com"
    params = {
        'api_key': SCRAPER_API_KEY,
        'url': target_url,
        'render': 'false', 
    }
    
    # ✅ 进阶优化：增加 3 次重试机制，防止 ScraperAPI 节点偶尔抽风
    max_retries = 3
    for attempt in range(max_retries):
        try:
            print(f"正在下载: {filename} (尝试 {attempt + 1}/{max_retries})...")
            response = requests.get(proxy_url, params=params, timeout=60)
            
            if response.status_code == 200:
                # 下载成功后立即尝试上传
                if upload_to_github(filename, response.content):
                    return True
                return False
            else:
                print(f"⚠️ 下载失败: {filename} (状态码: {response.status_code})")
                if attempt < max_retries - 1:
                    time.sleep(3) # 失败后等 3 秒再试
                    continue
                return False
        except Exception as e:
            print(f"⚠️ 请求异常 ({filename}): {e}")
            if attempt < max_retries - 1:
                time.sleep(3)
                continue
            return False

if __name__ == "__main__":
    print(f"🚀 任务启动日期: {DISPLAY_DATE}")
    
    if SCRAPER_API_KEY == "你的_SCRAPERAPI_KEY" or not SCRAPER_API_KEY:
        print("❌ 致命错误: 未检测到有效的 SCRAPER_API_KEY！")
        sys.exit(1)
        
    total_files = len(METALS_FILES)
    failed_files = []

    for fname in METALS_FILES:
        # 如果下载或上传任何一步失败，则计入失败名单
        if not download_with_scraperapi(fname):
            failed_files.append(fname)
        time.sleep(2) # 增加一点文件间的间隔，对代理更友好
        
    print(f"\n--- 任务总结 ---")
    print(f"成功: {total_files - len(failed_files)} / 失败: {len(failed_files)}")

    if failed_files:
        print(f"❌ 以下文件同步失败: {', '.join(failed_files)}")
        # 核心逻辑：如果有失败，以状态码 1 退出，这会让 GitHub Action 变红
        sys.exit(1)
    else:
        print("🎉 所有文件同步成功！")
        sys.exit(0)
