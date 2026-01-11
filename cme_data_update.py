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

# 映射金属到 yfinance 交易代码 (覆盖全部 8 种金属)
TICKER_MAP = {
    "Gold": "GC=F", 
    "Silver": "SI=F", 
    "Copper": "HG=F",
    "Platinum": "PL=F", 
    "Palladium": "PA=F", 
    "Aluminum": "ALI=F",
    "Zinc": "ZN=F",
    "Lead": "LED=F"
}

# 8 种金属的精确坐标配置 (严格保留 Excel 行号与列号逻辑)
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
# 2. 核心分析与提取函数
# ==========================================

def clean_val(val):
    """清理 Excel 中的逗号并转换为浮点数"""
    try: 
        return float(str(val).replace(',', '').strip()) if not pd.isna(val) else 0.0
    except: 
        return 0.0

def extract_clearing_anomalies(metal_name):
    """精准解析 PDF 商家异动：区分 ISSUED (卖出) 与 STOPPED (接货)"""
    pdf_path = "MetalsIssuesAndStopsReport.pdf"
    if not os.path.exists(pdf_path): 
        return "PDF not found."
    
    extracted_data = []
    current_section = "Unknown"
    
    try:
        with pdfplumber.open(pdf_path) as pdf:
            for page in pdf.pages:
                text = page.extract_text()
                if not text or metal_name.upper() not in text.upper(): 
                    continue
                
                lines = text.split('\n')
                for line in lines:
                    # 识别当前属于哪个板块
                    if "ISSUED" in line.upper(): current_section = "Issued"
                    elif "STOPPED" in line.upper(): current_section = "Stopped"
                    
                    # 排除汇总行 (TOTAL)，寻找包含数值的机构行
                    if re.search(r'\d+', line) and "TOTAL" not in line.upper():
                        # 清理数据并寻找数值
                        nums = re.findall(r'\d+', line.replace(',', ''))
                        if len(nums) >= 1:
                            # 提取行首的商家名称
                            member_name = re.sub(r'\d.*', '', line).strip()
                            vol = int(nums[0])
                            # 仅保留有效的商家名称和成交量
                            if vol > 0 and len(member_name) > 3:
                                extracted_data.append({"name": member_name, "vol": vol, "type": current_section})
        
        # 按成交量降序排列并取前三名
        extracted_data.sort(key=lambda x: x['vol'], reverse=True)
        top_3 = extracted_data[:3]
        
        if not top_3: 
            return "No significant clearing activity detected."
            
        return " | ".join([f"{d['name']}: {d['vol']} ({d['type']})" for d in top_3])
    except Exception as e: 
        return f"PDF Error: {str(e)}"

def get_ai_analysis(metal, price_data, inventory_change, anomalies):
    """整合库存、价格与商家行为，调用 Gemini 1.5 生成深度研判"""
    model = genai.GenerativeModel('gemini-1.5-flash')
    
    prompt = f"""
    作为大宗商品专业金属分析师，请根据以下最新数据对 {metal} 进行深度研判：
    1. 价格数据：当前收盘价 ${price_data['price']}, 较上一交易日涨跌幅为 {price_data['change']}%。
    2. 库存数据：当日库存净变动 (Net Change) 为 {inventory_change}。
    3. 做市商异动：CME 交割通知 (Delivery Notice) 显示活跃商家为：{anomalies}。
    
    请分析逻辑：结合库存净变动的正负情况，判断这些做市商是在“接货 (Stops)”进行仓位锁定，还是在“出货 (Issued)”。
    重点指出是否存在潜在的挤仓 (Squeeze) 风险或明显的机构看涨情绪。
    请用简明扼要的两句话总结，直接给出结论。
    """
    
    try:
        response = model.generate_content(prompt)
        return response.text.strip()
    except: 
        return "AI analysis failed."

# ==========================================
# 3. 主程序流程
# ==========================================

def update_precise_data():
    # 获取日期 (通常分析昨日报告数据)
    date_str = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")
    print(f"[*] 正在执行 {date_str} 的全金属分析流水线...")

    for metal, cfg in CELL_CONFIG.items():
        if not os.path.exists(cfg['file']):
            print(f"[!] 缺失文件 {cfg['file']}，跳过 {metal}")
            continue
            
        try:
            # 1. 提取 Excel 库存变动数据
            try: 
                df = pd.read_html(cfg['file'])[0]
            except: 
                df = pd.read_excel(cfg['file'], header=None)
                
            reg = clean_val(df.iloc[cfg['reg'][0], cfg['reg'][1]])
            elig = clean_val(df.iloc[cfg['elig'][0], cfg['elig'][1]])
            change = clean_val(df.iloc[cfg['change'][0], cfg['change'][1]])

            # 2. 提取 PDF 做市商商家异动
            anomalies = extract_clearing_anomalies(metal)

            # 3. 获取 Yahoo Finance 价格数据
            ticker_symbol = TICKER_MAP.get(metal, "GC=F")
            ticker = yf.Ticker(ticker_symbol)
            yf_history = ticker.history(period="2d")
            
            price_info = {"price": 0, "change": 0}
            if len(yf_history) >= 2:
                last_price = yf_history['Close'].iloc[-1]
                prev_price = yf_history['Close'].iloc[-2]
                pct_change = ((last_price - prev_price) / prev_price) * 100
                price_info = {
                    "price
