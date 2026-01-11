import os, requests, yfinance as yf, google.generativeai as genai
from datetime import datetime, timedelta

GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")
NOTION_TOKEN = os.getenv("NOTION_TOKEN")
DATABASE_ID = os.getenv("NOTION_DATABASE_ID")

def get_ai_analysis():
    if not GOOGLE_API_KEY: return
    
    # 修复：明确配置并使用标准模型名称
    genai.configure(api_key=GOOGLE_API_KEY)
    model = genai.GenerativeModel('gemini-1.5-flash')
    
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
            # 获取刚刚 Step 3 写入的 AI 提取数据
            dealers_rt = page["properties"].get("JPM/Asahi etc Stock change", {}).get("rich_text", [])
            dealers = dealers_rt[0].get("plain_text", "None") if dealers_rt else "None"

            # 研判逻辑
            prompt = f"分析 {metal} {date_str}: 价格 {p_info}, 做市商变动明细: {dealers}。请提供2句深度市场情绪研判。"
            response = model.generate_content(prompt)
            
            requests.patch(f"https://api.notion.com/v1/pages/{page['id']}", headers=headers,
                json={"properties": {
                    "Name": {"title": [{"text": {"content": f"AI Insight: {metal} {date_str}"}}]},
                    "Activity Note": {"rich_text": [{"text": {"content": response.text}}]}
                }})
            print(f"✅ {metal} AI 深度研判同步成功")
        except Exception as e:
            print(f"❌ {metal} 分析出错: {e}")

if __name__ == "__main__":
    get_ai_analysis()
