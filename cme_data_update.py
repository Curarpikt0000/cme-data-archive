import os
import pandas as pd
import requests
import pdfplumber
import re
from datetime import datetime, timedelta

# 基础配置
NOTION_TOKEN = os.getenv("NOTION_TOKEN")
DATABASE_ID = os.getenv("NOTION_DATABASE_ID", "2e047eb5fd3c80d89d56e2c1ad066138")
HEADERS = {"Authorization": f"Bearer {NOTION_TOKEN}", "Content-Type": "application/json", "Notion-Version": "2022-06-28"}

# 金属坐标配置
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

def clean_val(val):
    try: return float(str(val).replace(',', '').strip()) if not pd.isna(val) else 0.0
    except: return 0.0

def extract_top_3_dealers(metal_name):
    """解析 PDF 提取成交量前三的商家"""
    pdf_path = "MetalsIssuesAndStopsReport.pdf"
    if not os.path.exists(pdf_path): return "PDF Missing"
    extracted = []
    current_type = "Unknown"
    # 核心商家列表
    DEALERS = ["J.P. MORGAN", "HSBC", "ASAHI", "BRINK'S", "SCOTIA", "BOFA", "MANFRA", "MTB"]

    try:
        with pdfplumber.open(pdf_path) as pdf:
            for page in pdf.pages:
                text = page.extract_text()
                if not text or metal_name.upper() not in text.upper(): continue
                lines = text.split('\n')
                for line in lines:
                    if "ISSUED" in line.upper(): current_type = "Issued"
                    elif "STOPPED" in line.upper(): current_type = "Stopped"
                    for d in DEALERS:
                        if d in line.upper():
                            nums = re.findall(r'\d+', line.replace(',', ''))
                            if nums:
                                vol = int(nums[0])
                                extracted.append({"name": d, "vol": vol, "type": current_type})
        extracted.sort(key=lambda x: x['vol'], reverse=True)
        top_3 = extracted[:3]
        return " | ".join([f"{x['name']}: {x['vol']} ({x['type']})" for x in top_3]) if top_3 else "No significant activity."
    except Exception as e: return f"PDF Error: {e}"

def update_precise_data():
    date_str = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")
    for metal, cfg in CELL_CONFIG.items():
        if not os.path.exists(cfg['file']): continue
        try:
            try: df = pd.read_html(cfg['file'])[0]
            except: df = pd.read_excel(cfg['file'], header=None)
            reg = clean_val(df.iloc[cfg['reg'][0], cfg['reg'][1]])
            elig = clean_val(df.iloc[cfg['elig'][0], cfg['elig'][1]])
            change = clean_val(df.iloc[cfg['change'][0], cfg['change'][1]])
            anomalies = extract_top_3_dealers(metal)

            q_res = requests.post(f"https://api.notion.com/v1/databases/{DATABASE_ID}/query", headers=HEADERS, 
                                 json={"filter": {"and": [{"property": "Date", "date": {"equals": date_str}},
                                                         {"property": "Metal Type", "select": {"equals": metal}}]}}).json()
            if q_res.get("results"):
                pid = q_res["results"][0]["id"]
                requests.patch(f"https://api.notion.com/v1/pages/{pid}", headers=HEADERS, 
                              json={"properties": {
                                  "Total Registered": {"number": reg}, "Total Eligible": {"number": elig},
                                  "Net Change": {"number": change},
                                  "JPM/Asahi etc Stock change": {"rich_text": [{"text": {"content": anomalies}}]}
                              }})
                print(f"✅ {metal} 库存与 Top 3 商家更新成功")
        except Exception as e: print(f"❌ {metal} 错误: {e}")

if __name__ == "__main__":
    update_precise_data()
