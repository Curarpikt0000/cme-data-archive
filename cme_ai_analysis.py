import os, requests, yfinance as yf
from google import genai
from datetime import datetime, timedelta

GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")
NOTION_TOKEN = os.getenv("NOTION_TOKEN")
DATABASE_ID = os.getenv("NOTION_DATABASE_ID")

def run_step_4():
    if not GOOGLE_API_KEY: return
    client = genai.Client(api_key=GOOGLE_API_KEY)
    
    date_str = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")
    tickers = {"Gold": "GC=F", "Silver": "SI=F", "Platinum": "PL=F", "Copper": "HG=F"}
    headers = {"Authorization": f"Bearer {NOTION_TOKEN}", "Content-Type": "application/json", "Notion-Version": "2022-06-28"}

    for metal, sym in tickers.items():
        try:
            # 价格抓取与处理
            hist = yf.download(sym, period="5d", progress=False)
            if hist.empty: continue
            closes = hist['Close'].values.flatten()
            curr, prev = float(closes[-1]), float(closes[-2])
            p_info = f"Price {curr:.2f} ({(curr-prev)/prev*100:+.2f}%)"

            # 查询 Notion
            q = requests.post(f"https://api.notion.com/v1/databases/{DATABASE_ID}/query", headers=headers,
                json={"filter": {"and": [{"property": "Date", "date": {"equals": date_str}},
                                       {"property": "Metal Type", "select": {"equals": metal}}]}}).json()
            
            if not q.get("results"): continue
            page = q["results"][0]
            # 获取 Step 3 刚刚写入的异动结论
            dealer_info = page["properties"].get("JPM/Asahi etc Stock change", {}).get("rich_text", [{}])[0].get("plain_text", "None")

            prompt = f"分析 {metal} ({date_str}): 行情{p_info}, 交割异动事实:{dealer_info}. 请提供两句极其深度且不废话的博弈研判。"
            
            # 使用新版 SDK 解决 404 问题
            response = client.models.generate_content(model='gemini-1.5-flash', contents=prompt)
            
            requests.patch(f"https://api.notion.com/v1/pages/{page['id']}", headers=headers,
                json={"properties": {
                    "Name": {"title": [{"text": {"content": f"AI Insight: {metal} {date_str}"}}]},
                    "Activity Note": {"rich_text": [{"text": {"content": response.text}}]}
                }})
            print(f"✅ {metal} 深度研判成功")
        except Exception as e:
            print(f"❌ {metal} 处理失败: {e}")

if __name__ == "__main__":
    run_step_4()
