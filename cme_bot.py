import requests
import os
import datetime
from datetime import timedelta
import time
import warnings
import re
import pdfplumber
import pandas as pd
from github import Github

warnings.filterwarnings('ignore')

# ==========================================
# 1. 配置区域 (从 GitHub Secrets 读取)
# ==========================================
# 这里的名字必须和你在 GitHub Settings 里设置的一模一样
NOTION_TOKEN = os.environ.get("NOTION_TOKEN")
GITHUB_TOKEN = os.environ.get("GH_PERSONAL_TOKEN")

# 这里填你的 Database ID
DATABASE_ID = "2e047eb5fd3c80d89d56e2c1ad066138" 

# ⚠️ 【这里已经修改为你指定的名字】 ⚠️
# 请确保你在 GitHub 上真的创建了一个叫 "cme-data-archive" 的仓库
GITHUB_REPO = "ChaosJin/cme-data-archive"  

# ==========================================
# 以下逻辑不需要动
# ==========================================
TARGET_DATE = (datetime.datetime.now() - timedelta(days=1)).strftime('%Y%m%d')
DISPLAY_DATE = (datetime.datetime.now() - timedelta(days=1)).strftime('%Y-%m-%d')
GITHUB_Path_PREFIX = f"data/{DISPLAY_DATE}/"

TARGET_FIRMS = [
    'JPMORGAN', 'HSBC', 'CITI', 'SCOTIA', 'MANFRA', 'BRINK', 
    'ASAHI', 'MTB', 'LOOMIS', 'MALCA', 'STONEX', 'IBK', 
    'GLORY', 'MAREX', 'WELLS', 'MORGAN STANLEY', 'BOFA'
]

BASE_URL = "https://www.cmegroup.com/delivery_reports/"
DELIVERY_PDF_NAME = "MetalsIssuesAndStopsReport.pdf"

METALS_CONFIG = {
    'Gold':      {'id': 437,  'search_key': 'GOLD',      'file': 'Gold_Stocks.xls'},
    'Silver':    {'id': 450,  'search_key': 'SILVER',    'file': 'Silver_stocks.xls'}, 
    'Copper':    {'id': 446,  'search_key': 'COPPER',    'file': 'Copper_Stocks.xls'},
    'Platinum':  {'id': 462,  'search_key': 'PLATINUM',  'file': 'PA-PL_Stck_Rprt.xls'},
    'Palladium': {'id': 464,  'search_key': 'PALLADIUM', 'file': 'PA-PL_Stck_Rprt.xls'},
    'Aluminum':  {'id': 8416, 'search_key': 'ALUMINUM',  'file': 'Aluminum_Stocks.xls'},
    'Zinc':      {'id': 8417, 'search_key': 'ZINC',      'file': 'Zinc_Stocks.xls'},
    'Lead':      {'id': 8418, 'search_key': 'LEAD',      'file': 'Lead_Stocks.xls'}
}

# --- 功能模块 ---
def upload_to_github_and_get_link(filename, content_bytes):
    if not GITHUB_TOKEN: return ""
    try:
        g = Github(GITHUB_TOKEN)
        repo = g.get_repo(GITHUB_REPO)
        target_path = GITHUB_Path_PREFIX + filename
        try:
            contents = repo.get_contents(target_path)
            repo.update_file(contents.path, f"Update {filename}", content_bytes, contents.sha)
        except:
            repo.create_file(target_path, f"Add {filename}", content_bytes)
        return f"https://raw.githubusercontent.com/{GITHUB_REPO}/main/{target_path}"
    except Exception as e:
        print(f"GitHub Error: {e}")
        return ""

def download_and_store(filename):
    url = BASE_URL + filename
    try:
        headers = {'User-Agent': 'Mozilla/5.0'}
        r = requests.get(url, headers=headers, timeout=30)
        if r.status_code == 200:
            # 这里的 wb 模式对于二进制上传至关重要
            with open(filename, 'wb') as f: f.write(r.content)
            return upload_to_github_and_get_link(filename, r.content)
    except: pass
    return None

def fetch_daily_files_flow():
    print("Step 1: Downloading & Archiving...")
    pdf_url = download_and_store(DELIVERY_PDF_NAME)
    file_urls = {DELIVERY_PDF_NAME: pdf_url}
    downloaded = set()
    for m, conf in METALS_CONFIG.items():
        fname = conf['file']
        if fname not in downloaded:
            url = download_and_store(fname)
            file_urls[fname] = url
            downloaded.add(fname)
            downloaded.add(fname) # 防止重复下载
    return file_urls

def parse_stock_data_robust(metal_name, config):
    filename = config['file']
    stats = {'Registered': 0.0, 'Eligible': 0.0, 'Total': 0.0, 'NetChange': 0.0, 'Ratio': 0.0, 'Firm_Moves': []}
    if not os.path.exists(filename): return stats
    try:
        # 使用 latin-1 忽略 0xd0 错误
        with open(filename, 'rb') as f:
            content = f.read().decode('latin-1', errors='ignore').upper()
            raw_text = re.sub(r'<[^>]+>', ' ', content)
        
        reg_match = re.search(r'TOTAL\s+REGISTERED.*?(\d{1,3}(?:,\d{3})*|\d+)', raw_text, re.DOTALL)
        if reg_match: stats['Registered'] = float(reg_match.group(1).replace(',', ''))
        
        elig_match = re.search(r'TOTAL\s+ELIGIBLE.*?(\d{1,3}(?:,\d{3})*|\d+)', raw_text, re.DOTALL)
        if elig_match: stats['Eligible'] = float(elig_match.group(1).replace(',', ''))
        
        stats['Total'] = stats['Registered'] + stats['Eligible']
        if stats['Total'] > 0: stats['Ratio'] = round(stats['Registered'] / stats['Total'], 4)
        
        change_matches = re.findall(r'NET\s+CHANGE.*?(-?\d{1,3}(?:,\d{3})*)', raw_text, re.DOTALL)
        for m in change_matches:
            try:
                val = float(m.replace(',', ''))
                # 过滤异常大的数值
                if abs(val) < stats['Total']: 
                    stats['NetChange'] = val; break
            except: continue
            
        for line in raw_text.split('\n'):
            for firm in TARGET_FIRMS:
                if firm in line and "TOTAL" not in line and any(c.isdigit() for c in line):
                    clean = re.sub(r'\s+', ' ', line).strip()
                    idx = clean.find(firm)
                    stats['Firm_Moves'].append(clean[idx:][:50])
        stats['Firm_Moves'] = sorted(list(set(stats['Firm_Moves'])))
    except: pass
    return stats

def parse_delivery_pdf(metal_key):
    if not os.path.exists(DELIVERY_PDF_NAME): return 0, ""
    jpm_net = 0; lines = []
    try:
        with pdfplumber.open(DELIVERY_PDF_NAME) as pdf:
            for page in pdf.pages:
                text = page.extract_text()
                if not text or metal_key not in text.upper(): continue
                for row in text.split('\n'):
                    if "JP" in row.upper() and "MORGAN" in row.upper() and " H " in row.upper():
                        nums = re.findall(r'(\d{1,3}(?:,\d{3})*)', row)
                        if len(nums)>=2: jpm_net += (int(nums[-1].replace(',','')) - int(nums[-2].replace(',','')))
                    for firm in TARGET_FIRMS:
                        if firm in row.upper() and (" H " in row.upper() or " C " in row.upper()):
                            lines.append(f"🚚 {row.strip()}")
    except: pass
    return jpm_net, "\n".join(list(set(lines)))

def get_oi_data(pid):
    try:
        url = f"https://www.cmegroup.com/CmeWS/mvc/Volume/Details/F/{pid}/{TARGET_DATE}/P"
        r = requests.get(url, headers={'User-Agent': 'Mozilla/5.0'})
        data = r.json()
        if 'items' in data:
             df = pd.DataFrame(data['items'])
             df['openInterest'] = pd.to_numeric(df['openInterest'].astype(str).str.replace(',', ''), errors='coerce')
             return df['openInterest'].max()
    except: pass
    return 0

def push_to_notion(metal, stats, delivery_txt, jpm_net, oi_val, stock_url, delivery_url):
    moves_txt = "\n".join(stats['Firm_Moves'][:8]) 
    if delivery_txt: moves_txt += "\n\n" + delivery_txt
    if not moves_txt: moves_txt = "No significant changes"
    
    note = "⚖️ Normal"
    if stats['NetChange'] < 0: note = "📉 Drawdown (去库)"
    if stats['NetChange'] > 0: note = "📦 Inflow (累库)"
    if jpm_net > 0: note += " | JPM Stopped (接货)"
    if jpm_net < 0: note += " | JPM Issued (交货)"

    # 这里会使用 GitHub 返回的 Raw URL
    stock_file = [{"name": f"{metal}.xls", "type": "external", "external": {"url": stock_url}}] if stock_url else []
    del_file = [{"name": "Delivery.pdf", "type": "external", "external": {"url": delivery_url}}] if delivery_url else []

    props = {
        "Name": {"title": [{"text": {"content": f"{metal} - {DISPLAY_DATE}"}}]},
        "Date": {"date": {"start": DISPLAY_DATE}},
        "Metal Type": {"select": {"name": metal}},
        "Total Registered": {"number": stats['Registered']},
        "Total Eligible":   {"number": stats['Eligible']},
        "Combined Total":   {"number": stats['Total']},
        "Net Change":       {"number": stats['NetChange']},
        "Reg/Total Ratio":  {"number": stats['Ratio']},
        "OI (Open Interest)": {"number": oi_val},
        "Activity Note":    {"rich_text": [{"text": {"content": note}}]},
        "JPM/Asahi etc Stock change": {"rich_text": [{"text": {"content": moves_txt[:2000]}}]},
        "Stock File": {"files": stock_file},
        "Delivery Notice": {"files": del_file}
    }
    
    requests.post("https://api.notion.com/v1/pages", json={"parent": {"database_id": DATABASE_ID}, "properties": props}, headers={
        "Authorization": f"Bearer {NOTION_TOKEN}", "Content-Type": "application/json", "Notion-Version": "2022-06-28"
    })
    print(f"✅ {metal} Done")

if __name__ == "__main__":
    print(f"🚀 Running for {DISPLAY_DATE}")
    print(f"📂 Target Repo: {GITHUB_REPO}") # 打印一下确认
    file_urls = fetch_daily_files_flow()
    delivery_url = file_urls.get(DELIVERY_PDF_NAME, "")
    for metal, config in METALS_CONFIG.items():
        print(f"Processing {metal}...")
        stock_stats = parse_stock_data_robust(metal, config)
        jpm_net, del_txt = parse_delivery_pdf(config['search_key'])
        oi_val = get_oi_data(config['id'])
        stock_url = file_urls.get(config['file'], "")
        push_to_notion(metal, stock_stats, del_txt, jpm_net, oi_val, stock_url, delivery_url)
