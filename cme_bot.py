import requests
import os
import datetime
import time
from datetime import timedelta
from github import Github

# ==========================================
# 配置区域
# ==========================================
GITHUB_TOKEN = os.environ.get("GH_PERSONAL_TOKEN")
GITHUB_REPO = "Curarpikt0000/cme-data-archive"
# 在此处填入你截图中的 API Key
SCRAPER_API_KEY = "0434276aa91c62e0340dcd30819f3fbf" 

DISPLAY_DATE = (datetime.datetime.now() - timedelta(days=1)).strftime('%Y-%m-%d')
GITHUB_PATH_PREFIX = f"data/{DISPLAY_DATE}/"

BASE_URL = "https://www.cmegroup.com/delivery_reports/"
METALS_FILES = [
    'MetalsIssuesAndStopsReport.pdf', 'Gold_Stocks.xls', 'Silver_stocks.xls', 
    'Copper_Stocks.xls', 'PA-PL_Stck_Rprt.xls', 'Aluminum_Stocks.xls', 
    'Zinc_Stocks.xls', 'Lead_Stocks.xls'
]

def upload_to_github(filename, content_bytes):
    if not GITHUB_TOKEN: return
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
    except Exception as e:
        print(f"❌ GitHub 提交失败: {e}")

def download_with_scraperapi(filename):
    target_url = f"{BASE_URL}{filename}"
    
    # ScraperAPI 的请求格式
    proxy_url = "http://api.scraperapi.com"
    params = {
        'api_key': SCRAPER_API_KEY,
        'url': target_url,
        'render': 'false', # 如果还是 403，可以改为 'true' (但更贵)
    }
    
    try:
        print(f"正在通过 ScraperAPI 下载: {filename}...")
        # 注意：这里直接传 params，ScraperAPI 会负责转发请求
        response = requests.get(proxy_url, params=params, timeout=60)
        
        if response.status_code == 200:
            upload_to_github(filename, response.content)
            return True
        else:
            print(f"❌ ScraperAPI 返回错误: {response.status_code}")
            return False
    except Exception as e:
        print(f"❌ 请求异常: {e}")
        return False

if __name__ == "__main__":
    print(f"🚀 任务启动日期: {DISPLAY_DATE}")
    
    success_count = 0
    for fname in METALS_FILES:
        if download_with_scraperapi(fname):
            success_count += 1
        time.sleep(1) # 即使有代理，也建议稍微停顿
        
    print(f"--- 任务结束: 成功同步 {success_count} 个文件 ---")
