import os
import re
import requests
import pdfplumber
import yfinance as yf
import google.generativeai as genai
import pandas as pd
from datetime import datetime, timedelta

# --- 配置 (请确保 GitHub Secrets 中已添加相关变量) ---
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
NOTION_TOKEN = os.getenv("NOTION_TOKEN")
DATABASE_ID = "2e047eb5fd3c80d89d56e2c1ad066138"
HEADERS = {"Authorization": f"Bearer {NOTION_TOKEN}", "Content-Type": "application/json", "Notion-Version": "2022-06-28"}

# 初始化 Gemini
genai.configure(api_key=GEMINI_API_KEY)
model = genai.GenerativeModel('gemini-1.5-flash')

# 雅虎财经代码与 CME 产品 ID 映射
ASSET_CONFIG = {
    "Gold":      {"ticker": "GC=F",  "pid": 437},
    "Silver":    {"ticker": "SI=F",  "pid": 450},
    "Copper":    {"ticker": "HG=F",  "pid": 446},
    "Platinum":  {"ticker": "PL=F",  "pid": 462},
    "Palladium": {"ticker": "PA=F",  "pid": 464},
    "Aluminum":  {"ticker": "ALI=F", "pid": 8416},
    "Zinc":      {"ticker": "ZNC=F", "pid": 8417},
    "Lead":      {"ticker": "LED=F", "pid": 8418}
}

def get_market_context(metal):
    """获取价格趋势和持仓量 OI"""
    price_info = "价格暂无"
    oi_val = 0
    date_str = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")
    config = ASSET_CONFIG[metal]
    
    # 1. 抓取行情 (2天数据计算涨跌幅)
    try:
        ticker = yf.Ticker(config['ticker'])
        hist = ticker.history(period="3d") # 周末运行建议取3天
        if len(hist) >= 2:
            last_close = hist['Close'].iloc[-1]
            prev_close = hist['Close'].iloc[-2]
            change = ((last_close - prev_close) / prev_close) * 100
            price_info = f"最新价格: {last_close:.2f}, 涨跌: {change:+.2f}%"
    except: price_info = "价格同步失败"

    # 2. 抓取 CME 官方 OI
    try:
        cme_date = date_str.replace("-", "")
        url = f"https://www.cmegroup.com/CmeWS/mvc/Volume/Details/F/{config['pid']}/{cme_date}/P"
        r = requests.get(url, headers={'User-Agent': 'Mozilla/5.0'}, timeout=10)
        items = r.json().get('items', [])
        oi_val = sum([int(str(i.get('openInterest', 0)).replace(',', '')) for i in items if i.get('openInterest')])
    except: pass
    
    return price_info, oi_val

def parse_mm_activity(metal):
    """从 PDF 提取做市商具体交收行"""
    details = []
    pdf_path = "MetalsIssuesAndStopsReport.pdf"
    if os.path.exists(pdf_path):
        try:
            with pdfplumber.open(pdf_path) as pdf:
                for page in pdf.pages:
                    text = page.extract_text()
                    if text and metal.upper() in text.upper():
                        for line in text.split('\n'):
                            if any(mm in line.upper() for mm in ['JPMORGAN', 'CITI', 'HSBC', 'BOFA', 'WELLS', 'STONEX']):
                                details.append(line.strip())
        except: pass
    return "\n".join(list(set(details))[:10])

def run_smart_analysis():
    # 使用昨天日期（与前序步骤数据对齐）
    date_str = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")
    
    for metal in ASSET_CONFIG.keys():
        print(f"🔍 正在智能分析: {metal}")
        price_txt, oi_val = get_market_context(metal)
        mm_detail = parse_mm_activity(metal)
        
        # 检索 Notion 数据获取库存背景
        q = requests.post(f"https://api.notion.com/v1/databases/{DATABASE_ID}/query", headers=HEADERS, 
                         json={"filter": {"and": [{"property": "Date", "date": {"equals": date_str}},
                                                {"property": "Metal Type", "select": {"equals": metal}}]}}).json()
        
        if q.get("results"):
            page = q["results"][0]
            props = page["properties"]
            net_chg = props["Net Change"]["number"] or 0
            ratio = props.get("Reg/Total Ratio", {}).get("number", 0)
            
            # 构造 AI 提示词
            prompt = f"""
            任务：作为大宗商品专家，分析CME {metal} 行情。
            已知数据：
            - 库存变动: {net_chg} (注册仓单占比: {ratio:.2%})
            - 市场行情: {price_txt}，持仓量 (OI): {oi_val}
            - 做市商交收明细: {mm_detail if mm_detail else '无显著变动'}
            
            要求：请结合“量价库存”逻辑，分析主力意图（如看涨逼仓、空头回补、主力吸筹）。
            输出：50字内，口吻专业，包含表情符号。
            """
            
            try:
                ai_response = model.generate_content(prompt).text.strip()
            except: ai_response = "AI 研报生成超时"

            # 写回 Notion
            patch_data = {
                "properties": {
                    "OI (Open Interest)": {"number": oi_val},
                    "JPM/Asahi etc Stock change": {"rich_text": [{"text": {"content": mm_detail[:2000]}}]},
                    "Activity Note": {"rich_text": [{"text": {"content": ai_response}}]}
                }
            }
            requests.patch(f"https://api.notion.com/v1/pages/{page['id']}", headers=HEADERS, json=patch_data)
            print(f"✅ {metal} 分析完成并写回 Notion")

if __name__ == "__main__":
    run_smart_analysis()
