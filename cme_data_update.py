import os
import pandas as pd
import requests
import pdfplumber
import re
import yfinance as yf
import google.generativeai as genai
from datetime import datetime, timedelta

# ==========================================
# 1. 基础配置
# ==========================================
NOTION_TOKEN = os.getenv("NOTION_TOKEN")
DATABASE_ID = os.getenv("NOTION_DATABASE_ID", "2e047eb5fd3c80d89d56e2c1ad066138")
genai.configure(api_key=os.getenv("GOOGLE_API_KEY"))

HEADERS = {
    "Authorization": f"Bearer {NOTION_TOKEN}",
    "Content-Type": "application/json",
    "Notion-Version": "2022-06-28"
}

# 映射金属到 yfinance 代码
TICKER_MAP = {
    "Gold": "GC=F", "Silver": "SI=F", "Copper": "HG=F",
    "Platinum": "PL=F", "Palladium": "PA-F", "Aluminum": "ALI=F"
}

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
    try: return float(str(val).replace(',', '').strip()) if not pd.isna(val) else 0.0
    except: return 0.0

def extract_clearing_anomalies(metal_name):
    """解析 PDF 商家异动：区分 ISSUED 与 STOPPED"""
    pdf_path = "MetalsIssuesAndStopsReport.pdf"
    if not os.path.exists(pdf_path): return "PDF not found."
    extracted_data = []
    current_section = "Unknown"
    try:
        with pdfplumber.open(pdf_path) as pdf:
            for page in pdf.pages:
                text = page.extract_text()
                if not text or metal_name.upper() not in text.upper(): continue
                lines = text.split('\n')
                for line in lines:
                    if "ISSUED" in line.upper(): current_section = "Issued"
                    if "STOPPED" in line.upper(): current_section = "Stopped"
                    if re.search(r'\d+', line) and "TOTAL" not in line.upper():
                        nums = re.findall(r'\d+', line.replace(',', ''))
                        if len(nums) >= 1:
                            member_name = re.sub(r'\d.*', '', line).strip()
                            vol = int(nums[0])
                            if vol > 0 and len(member_name) > 3:
                                extracted_data.append({"name": member_name, "vol": vol, "type": current_section})
        extracted_data.sort(key=lambda x: x['vol'], reverse=True)
        top_3 = extracted_data[:3]
        if not top_3: return "No significant clearing activity."
        return " | ".join([f"{d['name']}: {d['vol']} ({d['type']})" for d in top_3])
    except Exception as e: return f"PDF Error: {str(e)}"

def get_ai_analysis(metal, price_data, inventory_change, anomalies):
    """整合所有维度数据，调用 Gemini 生成深度研判"""
    model = genai.GenerativeModel('gemini-1.5-flash')
    prompt = f"""
    作为专业金属分析师，分析当日{metal}行情：
    1. 价格：当前${price_data['price']}, 涨跌幅{price_data['change']}%。
    2. 库存变动：当日库存净变动(Net Change)为 {inventory_change}。
    3. 商家行为：CME交割通知显示：{anomalies}。
    请结合库存流向、商家接货(Stops)或出货(Issued)的逻辑，判断是否存在挤仓(Squeeze)风险或机构看涨情绪。
    用两句话简明扼要地总结。
    """
    try:
        response = model.generate_content(prompt)
        return response.text.strip()
    except: return "AI analysis failed."

def update_precise_data():
    date_str = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")
    print(f"[*] 正在处理日期为 {date_str} 的数据...")

    for metal, cfg in CELL_CONFIG.items():
        if not os.path.exists(cfg['file']): continue
        try:
            # 1. 提取库存
            try: df = pd.read_html(cfg['file'])[0]
            except: df = pd.read_excel(cfg['file'], header=None)
            reg = clean_val(df.iloc[cfg['reg'][0], cfg['reg'][1]])
            elig = clean_val(df.iloc[cfg['elig'][0], cfg['elig'][1]])
            change = clean_val(df.iloc[cfg['change'][0], cfg['change'][1]])

            # 2. 提取商家异动
            anomalies = extract_clearing_anomalies(metal)

            # 3. 获取价格数据
            ticker = TICKER_MAP.get(metal, "GC=F")
            yf_data = yf.Ticker(ticker).history(period="2d")
            price_info = {"price": 0, "change": 0}
            if len(yf_data) >= 2:
                last_price = yf_data['Close'].iloc[-1]
                prev_price = yf_data['Close'].iloc[-2]
                price_info = {"price": round(last_price, 2), "change": round(((last_price-prev_price)/prev_price)*100, 2)}

            # 4. AI 综合研判
            ai_insight = get_ai_analysis(metal, price_info, change, anomalies)

            # 5. 更新 Notion
            q_res = requests.post(f"https://api.notion.com/v1/databases/{DATABASE_ID}/query", headers=HEADERS, 
                                 json={"filter": {"and": [{"property": "Date", "date": {"equals": date_str}},
                                                         {"property": "Metal Type", "select": {"equals": metal}}]}}).json()

            if q_res.get("results"):
                pid = q_res["results"][0]["id"]
                requests.patch(f"https://api.notion.com/v1/pages/{pid}", headers=HEADERS, 
                              json={"properties": {
                                  "Total Registered": {"number": reg},
                                  "Total Eligible": {"number": elig},
                                  "Net Change": {"number": change},
                                  "JPM/Asahi etc Stock change": {"rich_text": [{"text": {"content": anomalies}}]},
                                  "Activity Note": {"rich_text": [{"text": {"content": ai_insight}}]}
                              }})
                print(f"✅ {metal} 数据与 AI 研判已完美同步。")
        except Exception as e: print(f"❌ {metal} Error: {e}")

if __name__ == "__main__":
    if not NOTION_TOKEN: print("[!] 缺失 NOTION_TOKEN")
    else: update_precise_data()
