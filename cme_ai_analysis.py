import os
import requests
import yfinance as yf
import google.generativeai as genai
from datetime import datetime, timedelta

NOTION_TOKEN = os.getenv("NOTION_TOKEN")
DATABASE_ID = os.getenv("NOTION_DATABASE_ID", "2e047eb5fd3c80d89d56e2c1ad066138")
genai.configure(api_key=os.getenv("GOOGLE_API_KEY"))
HEADERS = {"Authorization": f"Bearer {NOTION_TOKEN}", "Content-Type": "application/json", "Notion-Version": "2022-06-28"}

def get_market_analysis():
    date_str = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")
    model = genai.GenerativeModel('gemini-1.5-flash')
    tickers = {"Gold": "GC=F", "Silver": "SI=F", "Platinum": "PL=F"}

    for metal, ticker in tickers.items():
        # 1. 健壮的价格抓取逻辑
        try:
            data = yf.download(ticker, period="5d")
            if len(data) < 2: 
                p_change = "Data Insufficient"
            else:
                # 修复 IndexError
                p_change = f"{((data['Close'].iloc[-1] - data['Close'].iloc[-2]) / data['Close'].iloc[-2] * 100):.2f}%"
        except: p_change = "Price Error"

        # 2. 从 Notion 获取 Step 3 刚刚填入的库存和商家异动
        q_res = requests.post(f"https://api.notion.com/v1/databases/{DATABASE_ID}/query", headers=HEADERS, 
                             json={"filter": {"and": [{"property": "Date", "date": {"equals": date_str}},
                                                     {"property": "Metal Type", "select": {"equals": metal}}]}}).json()
        
        if not q_res.get("results"): continue
        props = q_res["results"][0]["properties"]
        pid = q_res["results"][0]["id"]

        net_change = props["Net Change"]["number"]
        # 获取 Step 3 提取的商家详情
        dealer_act = props["JPM/Asahi etc Stock change"]["rich_text"][0]["text"]["content"] if props["JPM/Asahi etc Stock change"]["rich_text"] else "None"

        # 3. AI 深度综合分析
        prompt = f"""
        请根据以下{metal}数据进行分析：
        - 价格变动：{p_change}
        - 库存净变动：{net_change}
        - 关键商家行为：{dealer_act}
        结合库存流向和商家交割(Issues/Stops)情况，判断今日市场情绪。
        分析要简明扼要，直接指出是否有挤仓风险。
        """
        
        try:
            response = model.generate_content(prompt)
            ai_text = response.text
            
            # 4. 写入 Activity Note，修正 Name 属性
            requests.patch(f"https://api.notion.com/v1/pages/{pid}", headers=HEADERS, 
                          json={"properties": {
                              "Name": {"title": [{"text": {"content": f"AI Insight: {metal} {date_str}"}}]},
                              "Activity Note": {"rich_text": [{"text": {"content": ai_text}}]}
                          }})
            print(f"✅ {metal} AI 分析同步成功")
        except:
            # 记录失败状态到 Notion
            requests.patch(f"https://api.notion.com/v1/pages/{pid}", headers=HEADERS, 
                          json={"properties": {"Activity Note": {"rich_text": [{"text": {"content": "AI analysis failed."}}]}}})

if __name__ == "__main__":
    get_market_analysis()
