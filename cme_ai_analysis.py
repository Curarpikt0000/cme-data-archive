import os
import requests
import yfinance as yf
import google.generativeai as genai
from datetime import datetime, timedelta

# 配置
NOTION_TOKEN = os.getenv("NOTION_TOKEN")
DATABASE_ID = os.getenv("NOTION_DATABASE_ID", "2e047eb5fd3c80d89d56e2c1ad066138")
genai.configure(api_key=os.getenv("GOOGLE_API_KEY"))
HEADERS = {"Authorization": f"Bearer {NOTION_TOKEN}", "Content-Type": "application/json", "Notion-Version": "2022-06-28"}

def get_market_analysis():
    date_str = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")
    model = genai.GenerativeModel('gemini-pro')
    tickers = {"Gold": "GC=F", "Silver": "SI=F", "Platinum": "PL=F"}

    for metal, ticker in tickers.items():
        # 1. 获取价格数据
        data = yf.download(ticker, period="2d")
        if data.empty: continue
        price_change = ((data['Close'].iloc[-1] - data['Close'].iloc[-2]) / data['Close'].iloc[-2]) * 100

        # 2. 从 Notion 获取 Step 3 填入的库存和商家信息
        q_res = requests.post(f"https://api.notion.com/v1/databases/{DATABASE_ID}/query", headers=HEADERS, 
                             json={"filter": {"and": [{"property": "Date", "date": {"equals": date_str}},
                                                     {"property": "Metal Type", "select": {"equals": metal}}]}}).json()
        
        if not q_res.get("results"): continue
        page = q_res["results"][0]
        pid = page["id"]
        
        # 提取 Step 3 的成果
        net_change = page["properties"]["Net Change"]["number"]
        dealer_act = page["properties"]["JPM/Asahi etc Stock change"]["rich_text"][0]["text"]["content"]

        # 3. 构造深度分析 Prompt (逻辑链条)
        prompt = f"""
        作为专业贵金属分析师，请根据以下数据对 {metal} 进行点评：
        - 价格变动：{price_change:.2f}%
        - 库存净变动 (Net Change)：{net_change}
        - 做市商交割活动：{dealer_act}
        - 当前背景：2026年宏观环境。
        分析逻辑：结合库存流出、大机构(如JPM)是接货还是出货，判断是否存在挤仓风险或机构看涨情绪。
        请给出两句话的深度分析。
        """
        
        try:
            response = model.generate_content(prompt)
            analysis_text = response.text
            
            # 4. 回传分析至 Activity Note
            requests.patch(f"https://api.notion.com/v1/pages/{pid}", headers=HEADERS, 
                          json={"properties": {
                              "Name": {"title": [{"text": {"content": f"Deep Insight: {metal} {date_str}"}}]},
                              "Activity Note": {"rich_text": [{"text": {"content": analysis_text}}]}
                          }})
            print(f"✅ {metal} 深度 AI 分析已完成")
        except Exception as e: print(f"❌ AI Error: {e}")

if __name__ == "__main__":
    get_market_analysis()
