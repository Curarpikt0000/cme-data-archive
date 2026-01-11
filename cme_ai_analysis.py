import os
import re
import requests
import pdfplumber
import yfinance as yf
import google.generativeai as genai
from datetime import datetime, timedelta

# --- 配置 ---
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
NOTION_TOKEN = os.getenv("NOTION_TOKEN")
DATABASE_ID = "2e047eb5fd3c80d89d56e2c1ad066138"
HEADERS = {"Authorization": f"Bearer {NOTION_TOKEN}", "Content-Type": "application/json", "Notion-Version": "2022-06-28"}

genai.configure(api_key=GEMINI_API_KEY)
model = genai.GenerativeModel('gemini-1.5-flash')

# 对应雅虎财经行情代码
TICKER_MAP = {
    "Gold": "GC=F", "Silver": "SI=F", "Copper": "HG=F",
    "Platinum": "PL=F", "Palladium": "PA=F", 
    "Aluminum": "ALI=F", "Zinc": "ZNC=F", "Lead": "LED=F"
}

# CME OI 产品 ID
OI_CONFIG = {"Gold": 437, "Silver": 450, "Copper": 446, "Platinum": 462, "Palladium": 464, "Aluminum": 8416, "Zinc": 8417, "Lead": 8418}

def get_market_data(metal):
    """获取价格和OI"""
    price_info = "价格暂无"
    oi_val = 0
    date_str = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")
    
    # 1. 抓取价格
    try:
        data = yf.Ticker(TICKER_MAP[metal]).history(period="2d")
        if len(data) >= 2:
            change = ((data['Close'].iloc[-1] - data['Close'].iloc[-2]) / data['Close'].iloc[-2]) * 100
            price_info = f"收盘: {data['Close'].iloc[-1]:.2f}, 涨跌: {change:+.2f}%"
    except: pass

    # 2. 抓取 OI
    try:
        cme_date = date_str.replace("-", "")
        url = f"https://www.cmegroup.com/CmeWS/mvc/Volume/Details/F/{OI_CONFIG[metal]}/{cme_date}/P"
        r = requests.get(url, headers={'User-Agent': 'Mozilla/5.0'}, timeout=10)
        items = r.json().get('items', [])
        oi_val = sum([int(str(i.get('openInterest', 0)).replace(',', '')) for i in items if i.get('openInterest')])
    except: pass
    
    return price_info, oi_val

def parse_pdf_mm(metal):
    """提取做市商异动明细"""
    details = []
    if os.path.exists("MetalsIssuesAndStopsReport.pdf"):
        with pdfplumber.open("MetalsIssuesAndStopsReport.pdf") as pdf:
            for page in pdf.pages:
                text = page.extract_text()
                if text and metal.upper() in text.upper():
                    for line in text.split('\n'):
                        if any(mm in line.upper() for mm in ['JPMORGAN', 'CITI', 'HSBC', 'BOFA', 'WELLS', 'STONEX']):
                            details.append(line.strip())
    return "\n".join(list(set(details))[:10])

def run_ai_analysis():
    date_str = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")
    
    for metal in TICKER_MAP.keys():
        print(f"🤖 AI Analyzing {metal}...")
        price_txt, oi_val = get_market_data(metal)
        mm_detail = parse_pdf_mm(metal)
        
        # 从 Notion 读取库存背景 (Step 3 填好的)
        q = requests.post(f"https://api.notion.com/v1/databases/{DATABASE_ID}/query", headers=HEADERS, 
                         json={"filter": {"and": [{"property": "Date", "date": {"equals": date_str}},
                                                {"property": "Metal Type", "select": {"equals": metal}}]}}).json()
        
        if q.get("results"):
            page = q["results"][0]
            props = page["properties"]
            net_change = props["Net Change"]["number"] or 0
            ratio = props["Reg/Total Ratio"]["number"] or 0
            
            # 喂给 Gemini 的 Prompt
            prompt = f"""
            你是顶级商品分析师。请分析CME {metal} 今日行情：
            1. 库存变动: {net_change} (注册占比: {ratio:.2%})
            2. 行情: {price_txt}，持仓量 (OI): {oi_val}
            3. 做市商交收明细: {mm_detail}
            
            请输出50字内的犀利分析，判断主力意图（如看涨逼仓、高位派发、筑底接货）。使用表情符号。
            """
            try:
                ai_note = model.generate_content(prompt).text.strip()
            except: ai_note = "AI 分析生成失败"

            # 更新回 Notion
            requests.patch(f"https://api.notion.com/v1/pages/{page['id']}", headers=HEADERS, json={
                "properties": {
                    "OI (Open Interest)": {"number": oi_val},
                    "JPM/Asahi etc Stock change": {"rich_text": [{"text": {"content": mm_detail[:2000]}}]},
                    "Activity Note": {"rich_text": [{"text": {"content": ai_note}}]}
                }
            })
            print(f"✅ {metal} AI Note Done.")

if __name__ == "__main__":
    run_ai_analysis()
