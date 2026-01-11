import os, requests, yfinance as yf
from datetime import datetime, timedelta

GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")
NOTION_TOKEN = os.getenv("NOTION_TOKEN")
DATABASE_ID = os.getenv("NOTION_DATABASE_ID")

def call_gemini_rest(prompt):
    """使用原生 REST API 访问 v1 稳定版接口"""
    url = f"https://generativelanguage.googleapis.com/v1/models/gemini-1.5-flash:generateContent?key={GOOGLE_API_KEY}"
    payload = {"contents": [{"parts": [{"text": prompt}]}]}
    res = requests.post(url, json=payload)
    if res.status_code == 200:
        return res.json()['candidates'][0]['content']['parts'][0]['text']
    else:
        print(f"❌ API 报错: {res.status_code} - {res.text}")
        return None

def run_analysis():
    date_str = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")
    tickers = {"Gold": "GC=F", "Silver": "SI=F", "Platinum": "PL=F", "Copper": "HG=F"}
    headers = {"Authorization": f"Bearer {NOTION_TOKEN}", "Content-Type": "application/json", "Notion-Version": "2022-06-28"}

    for metal, sym in tickers.items():
        try:
            hist = yf.download(sym, period="5d", progress=False)
            if hist.empty: continue
            last_p = hist['Close'].iloc[-1].item() # 修复 Series 格式化报错
            prev_p = hist['Close'].iloc[-2].item()
            change = (last_p - prev_p) / prev_p * 100
            
            q = requests.post(f"https://api.notion.com/v1/databases/{DATABASE_ID}/query", headers=headers,
                json={"filter": {"and": [{"property": "Date", "date": {"equals": date_str}},
                                       {"property": "Metal Type", "select": {"equals": metal}}]}}).json()
            if not q.get("results"): continue
            
            # 读取 Step 3 刚刚写入的事实数据
            dealer_info = q["results"][0]["properties"]["JPM/Asahi etc Stock change"]["rich_text"][0]["plain_text"]
            
            prompt = f"分析 {metal} ({date_str}): 价格 {last_p:.2f} ({change:+.2f}%), 异动 facts: {dealer_info}. 请给 2 句深度博弈研判。"
            analysis = call_gemini_rest(prompt)
            
            if analysis:
                requests.patch(f"https://api.notion.com/v1/pages/{q['results'][0]['id']}", headers=headers,
                    json={"properties": {"Activity Note": {"rich_text": [{"text": {"content": analysis}}]}}})
                print(f"✅ {metal} AI 深度研判成功")
        except Exception as e: print(f"❌ {metal} 处理出错: {e}")

if __name__ == "__main__": run_analysis()
