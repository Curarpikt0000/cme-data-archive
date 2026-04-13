import os
import re
import requests
import pdfplumber
import pandas as pd
from datetime import datetime, timedelta

# --- 配置 ---
NOTION_TOKEN = os.getenv("NOTION_TOKEN")
DATABASE_ID = os.getenv("NOTION_DATABASE_ID") # 已修改为读取环境变量
HEADERS = {"Authorization": f"Bearer {NOTION_TOKEN}", "Content-Type": "application/json", "Notion-Version": "2022-06-28"}

# 做市商名单
MARKET_MAKERS = ['JPMORGAN', 'CITI', 'HSBC', 'SCOTIA', 'BOFA', 'WELLS', 'STONEX']
# CME OI 产品 ID
OI_CONFIG = {
    "Gold": 437, "Silver": 450, "Copper": 446, "Platinum": 462, 
    "Palladium": 464, "Aluminum": 8416, "Zinc": 8417, "Lead": 8418
}

def get_cme_oi(product_id, date_str):
    """从 CME 网站抓取 Open Interest"""
    try:
        cme_date = date_str.replace("-", "")
        url = f"https://www.cmegroup.com/CmeWS/mvc/Volume/Details/F/{product_id}/{cme_date}/P"
        r = requests.get(url, headers={'User-Agent': 'Mozilla/5.0'}, timeout=15)
        data = r.json()
        if 'items' in data:
            oi_list = [int(str(i.get('openInterest', 0)).replace(',', '')) for i in data['items'] if i.get('openInterest')]
            return max(oi_list) if oi_list else 0
    except: return 0
    return 0

def download_pdf_from_github(date_str, filename="MetalsIssuesAndStopsReport.pdf"):
    """从自己的 GitHub 仓库下载当日归档的 PDF"""
    print(f"正在从云端拉取 {filename} ...")
    url = f"https://raw.githubusercontent.com/Curarpikt0000/cme-data-archive/main/data/{date_str}/{filename}"
    try:
        res = requests.get(url, timeout=30)
        if res.status_code == 200:
            with open(filename, 'wb') as f:
                f.write(res.content)
            return True
    except Exception as e:
        print(f"拉取 PDF 失败: {e}")
    return False

def parse_delivery_report(metal_name, date_str):
    """解析 PDF 查找做市商异动"""
    pdf_path = "MetalsIssuesAndStopsReport.pdf"
    
    # 增加逻辑：如果本地没有，去 GitHub 拉取
    if not os.path.exists(pdf_path): 
        if not download_pdf_from_github(date_str, pdf_path):
            return ""
            
    details = []
    try:
        with pdfplumber.open(pdf_path) as pdf:
            search_key = metal_name.upper()
            for page in pdf.pages:
                text = page.extract_text()
                if not text or search_key not in text: continue
                
                lines = text.split('\n')
                for line in lines:
                    if any(mm in line.upper() for mm in MARKET_MAKERS):
                        clean_line = re.sub(r'\s+', ' ', line).strip()
                        details.append(f"🚚 {clean_line}")
    except: pass
    return "\n".join(list(set(details))[:15])

def generate_activity_note(metal, change_val, delivery_txt):
    """根据数据生成逻辑分析"""
    note = "⚖️ Neutral"
    if change_val < 0: note = "📉 Drawdown (去库)"
    elif change_val > 0: note = "📦 Inflow (累库)"
    
    if "JPMORGAN" in delivery_txt:
        if "Stop" in delivery_txt or "接货" in delivery_txt:
            note += " | JPM 强力接货"
    return note

def run_analysis():
    date_str = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")
    
    for metal, pid in OI_CONFIG.items():
        print(f"Analyzing {metal}...")
        oi_val = get_cme_oi(pid, date_str)
        delivery_detail = parse_delivery_report(metal, date_str) # 传入日期以便下载
        
        query_res = requests.post(f"https://api.notion.com/v1/databases/{DATABASE_ID}/query", headers=HEADERS, 
                                 json={"filter": {"and": [{"property": "Date", "date": {"equals": date_str}},
                                                        {"property": "Metal Type", "select": {"equals": metal}}]}}).json()
        
        if query_res.get("results"):
            page = query_res["results"][0]
            pid_notion = page["id"]
            net_change = page["properties"].get("Net Change", {}).get("number") or 0
            
            activity_note = generate_activity_note(metal, net_change, delivery_detail)
            
            update_data = {
                "properties": {
                    "OI (Open Interest)": {"number": oi_val},
                    "JPM/Asahi etc Stock change": {"rich_text": [{"text": {"content": delivery_detail[:2000]}}]},
                    "Activity Note": {"rich_text": [{"text": {"content": activity_note}}]}
                }
            }
            requests.patch(f"https://api.notion.com/v1/pages/{pid_notion}", headers=HEADERS, json=update_data)
            print(f"✅ {metal} Analysis Updated.")

if __name__ == "__main__":
    run_analysis()
