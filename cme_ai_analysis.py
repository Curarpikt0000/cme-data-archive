import os, requests, yfinance as yf
from datetime import datetime, timedelta

GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")
NOTION_TOKEN = os.getenv("NOTION_TOKEN")
DATABASE_ID = os.getenv("NOTION_DATABASE_ID")
HEADERS = {"Authorization": f"Bearer {NOTION_TOKEN}", "Content-Type": "application/json", "Notion-Version": "2022-06-28"}

def call_gemini_rest(prompt):
    # 使用 2026 稳定版接口与模型名称
    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent?key={GOOGLE_API_KEY}"
    payload = {"contents": [{"parts": [{"text": prompt}]}]}
    try:
        res = requests.post(url, json=payload, timeout=20)
        if res.status_code == 200:
            return res.json()['candidates'][0]['content']['parts'][0]['text']
        else:
            print(f"❌ API 404/Error: {res.text}")
            return None
    except Exception as e:
        print(f"❌ 请求崩溃: {e}")
        return None

def run_analysis():
    if not GOOGLE_API_KEY:
        print("❌ 错误: GOOGLE_API_KEY 为空")
        return

    date_str = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")
    tickers = {"Gold": "GC=F", "Silver": "SI=F", "Platinum": "PL=F", "Copper": "HG=F"}

    for metal, sym in tickers.items():
        try:
            # 修复 Series format 报错
            hist = yf.download(sym, period="5d", progress=False)
            if hist.empty: continue
            price = hist['Close'].iloc[-1].item()
            change = (price - hist['Close'].iloc[-2].item()) / hist['Close'].iloc[-2].item() * 100
            
            # 查询事实数据
            res = requests.post(f"https://api.notion.com/v1/databases/{DATABASE_ID}/query", headers=HEADERS,
                json={"filter": {"and": [{"property": "Date", "date": {"equals": date_str}},
                                       {"property": "Metal Type", "select": {"equals": metal}}]}}).json()
            
            if not res.get("results"): continue
            page = res["results"][0]
            dealer_info = page["properties"]["JPM/Asahi etc Stock change"]["rich_text"][0]["plain_text"]
            
            prompt = f"分析 {metal} ({date_str}): 价格 {price:.2f} ({change:+.2f}%), 交割Facts: {dealer_info}. 请给2句深度研判。"
            analysis = call_gemini_rest(prompt)
            
            if analysis:
                requests.patch(f"https://api.notion.com/v1/pages/{page['id']}", headers=HEADERS,
                    json={"properties": {"Activity Note": {"rich_text": [{"text": {"content": analysis}}]}}})
                print(f"✅ {metal} AI 分析同步成功")
        except Exception as e: print(f"❌ {metal} 出错: {e}")

if __name__ == "__main__":
    run_analysis()
