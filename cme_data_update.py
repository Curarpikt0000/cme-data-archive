import os
import pandas as pd
import requests
from datetime import datetime, timedelta

# --- 配置 ---
NOTION_TOKEN = os.getenv("NOTION_TOKEN")
DATABASE_ID = "2e047eb5fd3c80d89d56e2c1ad066138"
HEADERS = {
    "Authorization": f"Bearer {NOTION_TOKEN}",
    "Content-Type": "application/json",
    "Notion-Version": "2022-06-28"
}

# 单元格坐标映射 (Excel 1-based -> Python 0-based)
# H列是索引7, F列是索引5
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
    """清理非数字字符并转为浮点数"""
    try:
        if pd.isna(val): return 0.0
        return float(str(val).replace(',', '').strip())
    except:
        return 0.0

def update_notion_data():
    # 使用昨天日期（与你下载文件的日期对齐）
    date_str = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")
    
    for metal, cfg in CELL_CONFIG.items():
        file_path = f"data/{date_str}/{cfg['file']}"
        
        if not os.path.exists(file_path):
            print(f"⚠️ 文件不存在: {file_path}")
            continue

        try:
            # CME 的 xls 有时其实是 HTML，pandas 的 read_html 比 read_excel 更鲁棒
            try:
                df_list = pd.read_html(file_path)
                df = df_list[0]
            except:
                df = pd.read_excel(file_path, header=None)

            # 提取数据
            reg_val = clean_val(df.iloc[cfg['reg'][0], cfg['reg'][1]])
            elig_val = clean_val(df.iloc[cfg['elig'][0], cfg['elig'][1]])
            change_val = clean_val(df.iloc[cfg['change'][0], cfg['change'][1]])
            
            total = reg_val + elig_val
            ratio = round(reg_val / total, 4) if total > 0 else 0

            # 1. 查找 Notion 中的对应行
            query_url = f"https://api.notion.com/v1/databases/{DATABASE_ID}/query"
            query_data = {
                "filter": {
                    "and": [
                        {"property": "Date", "date": {"equals": date_str}},
                        {"property": "Metal Type", "select": {"equals": metal}}
                    ]
                }
            }
            res = requests.post(query_url, headers=HEADERS, json=query_data).json()

            if res.get("results"):
                page_id = res["results"][0]["id"]
                # 2. 更新数值列
                patch_data = {
                    "properties": {
                        "Total Registered": {"number": reg_val},
                        "Total Eligible": {"number": elig_val},
                        "Combined Total": {"number": total},
                        "Net Change": {"number": change_val},
                        "Reg/Total Ratio": {"number": ratio}
                    }
                }
                requests.patch(f"https://api.notion.com/v1/pages/{page_id}", headers=HEADERS, json=patch_data)
                print(f"✅ {metal} 数据已精确更新")

        except Exception as e:
            print(f"❌ 处理 {metal} 出错: {e}")

if __name__ == "__main__":
    update_notion_data()
