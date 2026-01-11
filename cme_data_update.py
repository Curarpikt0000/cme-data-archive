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

# 8 种金属的精准坐标配置
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
# 2. 核心功能函数
# ==========================================

def clean_val(val):
    """数值清洗逻辑"""
    try:
        return float(str(val).replace(',', '').strip()) if not pd.isna(val) else 0.0
    except: return 0.0

def extract_clearing_anomalies(metal_name):
    """
   
    精准解析 PDF 中的做市商异动：区分 ISSUED (卖出) 与 STOPPED (接货)
    """
    pdf_path = "MetalsIssuesAndStopsReport.pdf"
    if not os.path.exists(pdf_path):
        return "PDF not found."

    extracted_data = []
    current_section = "Unknown" # 用于跟踪当前是 ISSUED 还是 STOPPED 区域

    try:
        with pdfplumber.open(pdf_path) as pdf:
            for page in pdf.pages:
                text = page.extract_text()
                if not text or metal_name.upper() not in text.upper():
                    continue
                
                lines = text.split('\n')
                for line in lines:
                    # 识别区域上下文
                    if "ISSUED" in line.upper(): current_section = "Issued"
                    if "STOPPED" in line.upper(): current_section = "Stopped"

                    # 排除汇总行，提取机构数据行
                    if re.search(r'\d+', line) and "TOTAL" not in line.upper():
                        # 清洗逗号并提取所有数值
                        nums = re.findall(r'\d+', line.replace(',', ''))
                        if len(nums) >= 1:
                            # 提取行首的机构名称
                            member_name = re.sub(r'\d.*', '', line).strip()
                            vol = int(nums[0]) # 获取成交量
                            if vol > 0 and len(member_name) > 3:
                                extracted_data.append({
                                    "name": member_name, 
                                    "vol": vol, 
                                    "type": current_section
                                })
        
        # 按成交量降序排列并格式化输出
        extracted_data.sort(key=lambda x: x['vol'], reverse=True)
        top_3 = extracted_data[:3]
        
        if not top_3:
            return "No significant clearing activity detected."
        
        return " | ".join([f"{d['name']}: {d['vol']} ({d['type']})" for d in top_3])

    except Exception as e:
        return f"PDF Error: {str(e)}"

def update_precise_data():
    """主更新逻辑：Excel 库存 + PDF 异动"""
    date_str = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")
    print(f"[*] 正在处理日期为 {date_str} 的金属数据...")

    for metal, cfg in CELL_CONFIG.items():
        if not os.path.exists(cfg['file']):
            print(f"[!] 缺失文件: {cfg['file']}")
            continue
        
        try:
            # 1. 提取 Excel 库存数据
            try: df = pd.read_html(cfg['file'])[0]
            except: df = pd.read_excel(cfg['file'], header=None)

            reg = clean_val(df.iloc[cfg['reg'][0], cfg['reg'][1]])
            elig = clean_val(df.iloc[cfg['elig'][0], cfg['elig'][1]])
            change = clean_val(df.iloc[cfg['change'][0], cfg['change'][1]])
            
            # 2. 提取 PDF 异动详情
            anomalies = extract_clearing_anomalies(metal)

            # 3. 在 Notion 数据库中查询对应行
            query_url = f"https://api.notion.com/v1/databases/{DATABASE_ID}/query"
            q_res = requests.post(query_url, headers=HEADERS, 
                                 json={"filter": {"and": [
                                     {"property": "Date", "date": {"equals": date_str}},
                                     {"property": "Metal Type", "select": {"equals": metal}}
                                 ]}}).json()

            if q_res.get("results"):
                pid = q_res["results"][0]["id"]
                update_url = f"https://api.notion.com/v1/pages/{pid}"
                
                # 4. 执行更新 (Patch)
                requests.patch(update_url, headers=HEADERS, 
                              json={"properties": {
                                  "Total Registered": {"number": reg},
                                  "Total Eligible": {"number": elig},
                                  "Net Change": {"number": change},
                                  "JPM/Asahi etc Stock change": {"rich_text": [{"text": {"content": anomalies}}]}
                              }})
                print(f"✅ {metal} 数据已完美更新 (含 {anomalies})。")
            else:
                print(f"[?] Notion 中未找到 {date_str} 的 {metal} 记录。")
                
        except Exception as e:
            print(f"❌ {metal} 处理出错: {e}")

if __name__ == "__main__":
    if not NOTION_TOKEN:
        print("[!] 缺失 NOTION_TOKEN 环境变量。")
    else:
        update_precise_data()
