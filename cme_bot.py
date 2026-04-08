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

# 动态日期：如果今天没出，可以手动调整 timedelta 补录
# 建议保持为 1，即抓取昨天的数据（CME 报表通常滞后一天）
DISPLAY_DATE = (datetime.datetime.now() - timedelta(days=1)).strftime('%Y-%m-%d')
GITHUB_PATH_PREFIX = f"data/{DISPLAY_DATE}/"

BASE_URL = "https://www.cmegroup.com/delivery_reports/"
DELIVERY_PDF_NAME = "MetalsIssuesAndStopsReport.pdf"

# 统一文件名（修复大小写问题）
METALS_FILES = [
    'Gold_Stocks.xls', 'Silver_stocks.xls', 'Copper_Stocks.xls', 
    'PA-PL_Stck_Rprt.xls', 'Aluminum_Stocks.xls', 'Zinc_Stocks.xls', 'Lead_Stocks.xls'
]

def upload_to_github(filename, content_bytes):
    if not GITHUB_TOKEN:
        print("❌ 错误: 缺少 GITHUB_TOKEN")
        return
    try:
        g = Github(GITHUB_TOKEN)
        repo = g.get_repo(GITHUB_REPO)
        target_path = GITHUB_PATH_PREFIX + filename
        
        try:
            # 尝试更新现有文件
            contents = repo.get_contents(target_path)
            repo.update_file(contents.path, f"Update {filename} for {DISPLAY_DATE}", content_bytes, contents.sha)
            print(f"✅ 已更新: {target_path}")
        except:
            # 创建新文件
            repo.create_file(target_path, f"Add {filename} for {DISPLAY_DATE}", content_bytes)
            print(f"✅ 已新增: {target_path}")
    except Exception as e:
        print(f"❌ GitHub 提交失败 {filename}: {e}")

def download_file(filename):
    url = f"{BASE_URL}{filename}"
    # 模拟真实浏览器，防止被 CME 屏蔽
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,.*/*;q=0.8',
        'Referer': 'https://www.cmegroup.com/clearing/operations-and-financial-services/delivery-reports.html'
    }
    
    try:
        print(f"正在尝试下载: {url}")
        r = requests.get(url, headers=headers, timeout=30)
        
        if r.status_code == 200:
            # 确保本地目录存在
            os.makedirs(os.path.dirname(GITHUB_PATH_PREFIX), exist_ok=True)
            local_path = os.path.join(os.path.dirname(GITHUB_PATH_PREFIX), filename)
            
            with open(local_path, 'wb') as f:
                f.write(r.content)
            
            # 上传到 GitHub
            upload_to_github(filename, r.content)
            return True
        else:
            print(f"⚠️ 下载失败: {filename} (HTTP状态码: {r.status_code})")
            return False
    except Exception as e:
        print(f"❌ 下载异常 {filename}: {e}")
        return False

if __name__ == "__main__":
    print(f"🚀 任务启动日期: {DISPLAY_DATE}")
    
    # 下载 PDF
    pdf_success = download_file(DELIVERY_PDF_NAME)
    
    # 下载各金属 XLS
    success_count = 0
    for fname in METALS_FILES:
        if download_file(fname):
            success_count += 1
        time.sleep(2)  # 稍微停顿防止被频率限制
        
    print(f"--- 任务结束: 成功同步 {success_count} 个文件 ---")
