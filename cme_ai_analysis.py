import os
import requests
import yfinance as yf
import google.generativeai as genai
from datetime import datetime, timedelta

NOTION_TOKEN = os.getenv("NOTION_TOKEN")
DATABASE_ID = os.getenv("NOTION_DATABASE_ID", "2e047eb5fd3c80d89d56e2c1ad066138")
genai.configure(api_key=os.getenv("GOOGLE_API_KEY"))
HEADERS = {"Authorization": f"Bearer {NOTION_TOKEN}", "Content-Type": "application/json", "Notion-Version": "2022-06-28"}

def analyze():
    date_str = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")
    model = genai.GenerativeModel('gemini-1.5-flash')
    tickers = {"Gold": "GC=F", "Silver": "SI=F", "Platinum": "PL=F", "Palladium": "PA=F", "Copper": "HG=F"}

    for metal, sym in tickers.items():
        # 1. 获取价格，增加数据长度检查
        try:
            data = yf.download(sym, period="5d")
            if len(data) < 2: p_str = "Price info insufficient"
            else:
                change = (data['Close'].iloc[-1] - data['Close'].iloc[-2]) / data['Close'].iloc[-2] * 100
                p_str = f"Price {data['Close'].iloc[-1]:.2f} ({change:+.2f}%)"
        except: p_str = "Price fetch failed"

        # 2. 从 Notion 获取 Step 3 刚刚填入的交割异动和库存变动
        q_res = requests.post(f"https://api.notion.com/v1/databases/{DATABASE_ID}/query", headers=HEADERS, 
                             json={"filter": {"and": [{"property": "Date", "date": {"equals": date_str}},
                                                     {"property": "Metal Type", "select": {"equals": metal}}]}}).json()
        if not q_res.get("results"): continue
        props = q_res["results"][0]["properties"]
        pid = q_res["results"][0]["id"]
        
        net_chg = props["Net Change"]["number"]
        dealers = props["JPM/Asahi etc Stock change"]["rich_text"][0]["text"]["content"] if props["JPM/Asahi etc Stock change"]["rich_text"] else "None"

        # 3. 构造深度分析 Prompt
        prompt = f"""
        Analyze {metal} market for {date_str}:
        - Market Data: {p_str}
        - Inventory Change: {net_chg}
        - Top 3 Dealer Activity: {dealers}
        结合库存流向和大机构接货/出货行为，判断是否存在潜在的挤仓(Squeeze)风险或显著的机构情绪变化。
        请给出两句简明扼要的深度分析结论。
        """
        
        try:
            response = model.generate_content(prompt)
            ai_text = response.text.strip()
            # 修正属性名
            requests.patch(f"https://api.notion.com/v1/pages/{pid}", headers=HEADERS, 
                          json={"properties": {
                              "Name": {"title": [{"text": {"content": f"AI Insight: {metal} {date_str}"}}]},
                              "Activity Note": {"rich_text": [{"text": {"content": ai_text}}]}
                          }})
            print(f"✅ {metal} AI Sync success.")
        except Exception as e: print(f"❌ {metal} AI failed: {e}")

if __name__ == "__main__":
    analyze()
