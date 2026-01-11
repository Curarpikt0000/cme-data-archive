import os
import pandas as pd
import requests
import pdfplumber
import re
from datetime import datetime, timedelta

# ==========================================
# 1. 基础配置 (从环境变量读取，确保安全性)
# ==========================================
NOTION_TOKEN = os.getenv("NOTION_TOKEN")
DATABASE_ID = os.getenv("NOTION_DATABASE_ID") # 移除硬编码，改用环境变量
HEADERS = {
    "Authorization": f"Bearer {NOTION_TOKEN}", 
    "Content-Type": "application/json", 
    "Notion-Version": "2022-06-28"
}

# 8 种金属的精确坐标配置 (基于 Excel 索引：行号-1, H列=7, F列=5)
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
    """数值清洗"""
    try:
        return float(str(val).replace(',', '').strip()) if not pd.isna(val) else 0.0
    except: return 0.0

def extract_jpm_activity(metal_name):
    """
    
    从 MetalsIssuesAndStopsReport.pdf 提取 JPM/Asahi 的变动详情
    """
    pdf_path = "MetalsIssuesAndStopsReport.pdf"
    if not os.path.exists(pdf_path):
        return "No Delivery PDF found."
    
    activity_summary = []
    try:
        with pdfplumber.open(pdf_path) as pdf:
            for page in pdf.pages:
                text = page.extract_text()
                if not text: continue
                
                # 模糊匹配 JPM, ASAHI, BRINKS 的变动行
                # 寻找包含金属名称和关键机构名称的行
                lines = text.split('\n')
                for line in lines:
                    if metal_name.upper() in line.upper():
                        if any(k in line.upper() for k in ["JPM", "ASAHI", "BRINK", "HSBC"]):
                            activity_summary.append(line.strip())
        
        return "\n".join(activity_summary[:3]) if activity_summary else "No major clearing activity."
    except Exception as e:
        return f"PDF Error: {str(e)}"

def get_oi_from_excel(filename):
    """尝试从 Excel 的末尾行提取总持仓量 (OI)"""
    try:
        df = pd.read_excel(filename)
        # 逻辑：OI 通常在表格最后一行的某个特定位置，这里作为演示提取
        return clean_val(df.iloc[-1, 7]) # 假设在 H 列最后
    except:
        return 0

def update_precise_data():
    """主更新逻辑"""
    # 获取交易日日期 (昨日)
    date_str = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")
    print(f"[*] 启动针对 {date_str} 的库存精准更新流程...")
    
    for metal, cfg in CELL_CONFIG.items():
        if not os.path.exists(cfg['file']):
            print(f"[!] 缺失文件: {cfg['file']}，跳过 {metal}")
            continue
            
        try:
            # 读取数据
            try: df = pd.read_html(cfg['file'])[0]
            except: df = pd.read_excel(cfg['file'], header=None)

            reg = clean_val(df.iloc[cfg['reg'][0], cfg['reg'][1]])
            elig = clean_val(df.iloc[cfg['elig'][0], cfg['elig'][1]])
            change = clean_val(df.iloc[cfg['change'][0], cfg['change'][1]])
            total = reg + elig
            ratio = round(reg / total, 4) if total > 0 else 0
            
            # 新增：提取 PDF 详情和 OI
            jpm_detail = extract_jpm_activity(metal)
            oi_val = get_oi_from_excel(cfg['file'])

            # 3. 查找并更新 Notion
            query_url = f"https://api.notion.com/v1/databases/{DATABASE_ID}/query"
            q_res = requests.post(query_url, headers=HEADERS, 
                                 json={"filter": {"and": [
                                     {"property": "Date", "date": {"equals": date_str}},
                                     {"property": "Metal Type", "select": {"equals": metal}}
                                 ]}}).json()

            if q_res.get("results"):
                pid = q_res["results"][0]["id"]
                update_url = f"https://api.notion.com/v1/pages/{pid}"
                
                # 补全所有缺失字段的 Patch
                requests.patch(update_url, headers=HEADERS, 
                              json={"properties": {
                                  "Total Registered": {"number": reg},
                                  "Total Eligible": {"number": elig},
                                  "Combined Total": {"number": total},
                                  "Net Change": {"number": change},
                                  "Reg/Total Ratio": {"number": ratio},
                                  "JPM/Asahi etc Stock change": {"rich_text": [{"text": {"content": jpm_detail}}]},
                                  "OI (Open Interest)": {"number": oi_val}
                              }})
                print(f"✅ {metal} 数据已完美更新 (含 JPM 详情)。")
            else:
                print(f"[?] Notion 中未找到 {date_str} 的 {metal} 记录，请检查 Step 2 是否运行成功。")
                
        except Exception as e:
            print(f"❌ {metal} 处理出错: {e}")

if __name__ == "__main__":
    if not DATABASE_ID:
        print("[!] 致命错误: 未在环境变量中找到 NOTION_DATABASE_ID")
    else:
        update_precise_data()
