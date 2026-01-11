import requests
import os
import datetime
from datetime import timedelta
from github import Github

# ==========================================
# 配置区域
# ==========================================
GITHUB_TOKEN = os.environ.get("GH_PERSONAL_TOKEN")
GITHUB_REPO = "Curarpikt0000/cme-data-archive"

TARGET_DATE = (datetime.datetime.now() - timedelta(days=1)).strftime('%Y%m%d')
DISPLAY_DATE = (datetime.datetime.now() - timedelta(days=1)).strftime('%Y-%m-%d')
GITHUB_Path_PREFIX = f"data/{DISPLAY_DATE}/"

BASE_URL = "https://www.cmegroup.com/delivery_reports/"
DELIVERY_PDF_NAME = "MetalsIssuesAndStopsReport.pdf"

# 只需要文件名列表
METALS_FILES = [
    'Gold_Stocks.xls', 'Silver_stocks.xls', 'Copper_Stocks.xls', 
    'PA-PL_Stck_Rprt.xls', 'Aluminum_Stocks.xls', 'Zinc_Stocks.xls', 'Lead_Stocks.xls'
]

def upload_to_github(filename, content_bytes):
    if not GITHUB_TOKEN: return
    try:
        g = Github(GITHUB_TOKEN)
        repo = g.get_repo(GITHUB_REPO)
        target_path = GITHUB_Path_PREFIX + filename
        try:
            contents = repo.get_contents(target_path)
            repo.update_file(contents.path, f"Update {filename}", content_bytes, contents.sha)
        except:
            repo.create_file(target_path, f"Add {filename}", content_bytes)
        print(f"Successfully uploaded {filename} to GitHub.")
    except Exception as e:
        print(f"GitHub Error for {filename}: {e}")

def download_file(filename):
    url = BASE_URL + filename
    try:
        headers = {'User-Agent': 'Mozilla/5.0'}
        r = requests.get(url, headers=headers, timeout=30)
        if r.status_code == 200:
            # 本地保存供后续脚本读取，同时上传GitHub
            os.makedirs(os.path.dirname(GITHUB_Path_PREFIX), exist_ok=True)
            with open(filename, 'wb') as f: f.write(r.content)
            upload_to_github(filename, r.content)
    except Exception as e:
        print(f"Download Error for {filename}: {e}")

if __name__ == "__main__":
    print(f"🚀 Starting Download for {DISPLAY_DATE}")
    download_file(DELIVERY_PDF_NAME)
    for fname in METALS_FILES:
        download_file(fname)
