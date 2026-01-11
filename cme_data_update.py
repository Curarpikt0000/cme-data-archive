import os
import pandas as pd
import requests
import pdfplumber
import re
from datetime import datetime, timedelta

# ==========================================
# 1. 基础配置 (从环境变量读取)
# ==========================================
NOTION_TOKEN = os.getenv("NOTION_TOKEN")
DATABASE_ID = os.getenv("NOTION_DATABASE_ID", "2e047eb5fd3c80d89d56e2c1ad066138")
HEADERS = {
    "Authorization": f"Bearer {NOTION_TOKEN}", 
    "Content-Type": "application/json", 
    "Notion-Version": "2022-06-28"
}

# 金属精确坐标配置
CELL_CONFIG = {
    "Lead":      {"file": "Lead_Stocks.xls",      "reg": (92, 7),  "elig": (93, 7),  "change": (94, 5)},
    "Zinc":      {"file": "Zinc_Stocks.xls",      "reg": (82, 7),  "elig": (83, 7),  "change": (84, 5)},
    "Aluminum":  {"file": "Aluminum_Stocks.xls",  "reg": (77, 7),  "elig": (78, 7),  "change": (79, 5)},
    "Platinum":  {"file": "PA-PL_Stck_Rprt.xls",  "reg": (71, 7),  "elig": (72, 7),  "change": (73, 5)},
    "Palladium": {"file": "PA-PL_Stck_Rprt.xls",  "reg": (140, 7), "elig": (141, 7), "change": (142, 5)},
    "Copper":    {"file": "Copper_Stocks.xls",    "reg": (47, 7),  "elig": (48, 7),  "change": (49, 5)},
    "Silver":    {"file": "Silver_stocks.xls",    "reg": (72, 7),  "elig": (73, 7),  "change": (74, 5)},
    "Gold":      {"file": "Gold_Stocks.xls",      "reg": (121, 7), "elig": (123, 7), "change": (124, 5)}
}

# ==========================================
# 2. PDF 解析逻辑 (获取 JPM/Asahi 详情)
# ==========================================

def extract_jpm_data(metal_name):
    """ 解析 Delivery Notice PDF"""
    pdf_path = "MetalsIssuesAndStopsReport.pdf"
    if not os.path.exists(pdf_path): return "No PDF file found."
    
    details = []
    try:
        with pdfplumber.open(pdf_path) as pdf:
            for page in pdf.pages:
                text = page.extract_text()
                if not text: continue
                # 寻找包含金属和关键银行的行
                for line in text.split('\n'):
                    if metal_name.upper() in line.upper() and any(k in line.upper() for k in ["JPM", "ASAHI", "BRINK", "HSBC"]):
                        details.append(line.strip())
        return "\n".join(details[:3]) if details else "No clearing activity detected."
    except Exception as e:
        return f"Error parsing PDF: {e}"

# ==========================================
# 3. 主逻辑
# ==========================================

def clean_val(val):
    try: return float(str(val).replace(',', '').strip()) if not pd.isna(val) else 0.0
    except: return 0.0

def update_precise_data():
    date_str = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")
    print(f"[*] Starting update for {date_str}")
    
    for metal, cfg in CELL_CONFIG.items():
        if not os.path.exists(cfg['file']): continue
        try:
            # 1. 提取库存数据
            try: df = pd.read_html(cfg['file'])[0]
            except: df = pd.read_excel(cfg['file'], header=None)

            reg = clean_val(df.iloc[cfg['reg'][0], cfg['reg'][1]])
            elig = clean_val(df.iloc[cfg['elig'][0], cfg['elig'][1]])
            change = clean_val(df.iloc[cfg['change'][0], cfg['change'][1]])
            
            # 2. 提取 PDF 变动详情
            jpm_info = extract_jpm_data(metal)

            # 3. 查询 Notion
            q_res = requests.post(f"https://api.notion.com/v1/databases/{DATABASE_ID}/query", headers=HEADERS, 
                                 json={"filter": {"and": [{"property": "Date", "date": {"equals": date_str}},
                                                         {"property": "Metal Type", "select": {"equals": metal}}]}}).json()
            
            if q_res.get("results"):
                pid = q_res["results"][0]["id"]
                # 关键修复：加入 'JPM/Asahi etc Stock change' 属性
                requests.patch(f"https://api.notion.com/v1/pages/{pid}", headers=HEADERS, 
                              json={"properties": {
                                  "Total Registered": {"number": reg},
                                  "Total Eligible": {"number": elig},
                                  "Net Change": {"number": change},
                                  "JPM/Asahi etc Stock change": {"rich_text": [{"text": {"content": jpm_info}}]}
                              }})
                print(f"✅ {metal} Data Patched (with JPM Info).")
        except Exception as e:
            print(f"❌ {metal} Error: {e}")

if __name__ == "__main__":
    update_precise_data()
