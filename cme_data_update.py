import os
import pandas as pd
import requests
import pdfplumber
import re
from datetime import datetime, timedelta

NOTION_TOKEN = os.getenv("NOTION_TOKEN")
DATABASE_ID = "2e047eb5fd3c80d89d56e2c1ad066138"
HEADERS = {"Authorization": f"Bearer {NOTION_TOKEN}", "Content-Type": "application/json", "Notion-Version": "2022-06-28"}

# 精确坐标配置 (Excel 行号-1, 列号H=7, F=5)
CELL_CONFIG = {
    "Lead":      {"file": "Lead_Stocks.xls",      "reg": (92, 7), "elig": (93, 7), "change": (92, 5)},
    "Zinc":      {"file": "Zinc_Stocks.xls",      "reg": (82, 7), "elig": (83, 7), "change": (82, 5)},
    "Platinum":  {"file": "PA-PL_Stck_Rprt.xls",  "reg": (71, 7), "elig": (72, 7), "change": (71, 5)},
    "Palladium": {"file": "PA-PL_Stck_Rprt.xls",  "reg": (140, 7), "elig": (141, 7), "change": (140, 5)},
    "Copper":    {"file": "Copper_Stocks.xls",    "reg": (47, 7), "elig": (48, 7), "change": (47, 5)},
    "Silver":    {"file": "Silver_stocks.xls",    "reg": (72, 7), "elig": (73, 7), "change": (72, 5)},
    "Gold":      {"file": "Gold_Stocks.xls",      "reg": (121, 7), "elig": (123, 7), "change": (121, 5)}
}

def clean_val(val):
    try:
        return float(str(val).replace(',', '').strip()) if not pd.isna(val) else 0.0
    except: return 0.0

def update_precise_data():
    date_str = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")
    
    for metal, cfg in CELL_CONFIG.items():
        if not os.path.exists(cfg['file']): continue
        try:
            # 兼容 HTML 格式的 XLS
            try: df = pd.read_html(cfg['file'])[0]
            except: df = pd.read_excel(cfg['file'], header=None)

            reg = clean_val(df.iloc[cfg['reg'][0], cfg['reg'][1]])
            elig = clean_val(df.iloc[cfg['elig'][0], cfg['elig'][1]])
            change = clean_val(df.iloc[cfg['change'][0], cfg['change'][1]])
            total = reg + elig
            ratio = round(reg / total, 4) if total > 0 else 0

            # 查找并更新 Notion
            q_res = requests.post(f"https://api.notion.com/v1/databases/{DATABASE_ID}/query", headers=HEADERS, 
                                 json={"filter": {"and": [{"property": "Date", "date": {"equals": date_str}},
                                                        {"property": "Metal Type", "select": {"equals": metal}}]}}).json()
            if q_res.get("results"):
                pid = q_res["results"][0]["id"]
                requests.patch(f"https://api.notion.com/v1/pages/{pid}", headers=HEADERS, 
                              json={"properties": {
                                  "Total Registered": {"number": reg}, "Total Eligible": {"number": elig},
                                  "Combined Total": {"number": total}, "Net Change": {"number": change},
                                  "Reg/Total Ratio": {"number": ratio}
                              }})
                print(f"✅ {metal} Data Patched.")
        except Exception as e: print(f"❌ {metal} Error: {e}")

if __name__ == "__main__":
    update_precise_data()
