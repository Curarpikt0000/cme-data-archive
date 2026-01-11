import os, requests, yfinance as yf
from google import genai
from datetime import datetime, timedelta

GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")
NOTION_TOKEN = os.getenv("NOTION_TOKEN")
DATABASE_ID = os.getenv("NOTION_DATABASE_ID")

def get_ai_analysis():
    if not GOOGLE_API_KEY: return
    client = genai.Client(api_key=GOOGLE_API_KEY)
    
    date_str = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")
    tickers = {"Gold": "GC=F", "Silver": "SI=F", "Platinum": "PL=F", "Copper": "HG=F"}
    headers = {"Authorization": f"Bearer {NOTION_TOKEN}", "Content-Type": "application/json", "Notion-Version": "2022-06-28"}

    for metal, sym in tickers.items():
        try:
            hist = yf.download(sym, period="5d", progress=False)
            if hist.empty: continue
            closes = hist['Close'].values.flatten()
            curr, prev = float(closes[-1]), float(closes[-2])
            p_info = f"Price {curr:.2f} ({(curr-prev)/prev*100:+.2f}%)"

            q = requests.post(f"https://api.notion.com/v1/databases/{DATABASE_ID}/query", headers=headers,
                json={"filter": {"and": [{"property": "Date", "date": {"equals": date_str}},
                                       {"property": "Metal Type", "select": {"equals": metal}}]}}).json()
            
            if not q.get("results"): continue
            page = q["results"][0]
            # 读取由 Step 3 写入的 AI 详细结论
            dealer_info = page["properties"].get("JPM/Asahi etc Stock change", {}).get("rich_text", [{}])[0].get("plain_text", "None")

            prompt = f"分析 {metal} {date_str}: 行情 {p_info}，详细变动: {dealer_info}。请据此给出两句深度的市场博弈研判。"
            
            response = client.models.generate_content(
                model='gemini-1.5-flash',
                contents=prompt
            )
            
            requests.patch(f"https://api.notion.com/v1/pages/{page['id']}", headers=headers,
                json={"properties": {
                    "Name": {"title": [{"text": {"content": f"AI Insight: {metal} {date_str}"}}]},
                    "Activity Note": {"rich_text": [{"text": {"content": response.text}}]}
                }})
            print(f"✅ {metal} 深度研判同步成功")
        except Exception as e: print(f"❌ {metal} 出错: {e}")

if __name__ == "__main__": get_ai_analysis()
