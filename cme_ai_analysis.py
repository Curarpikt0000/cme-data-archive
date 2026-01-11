import os, requests, yfinance as yf, time
from datetime import datetime, timedelta

GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")
NOTION_TOKEN = os.getenv("NOTION_TOKEN")
DATABASE_ID = os.getenv("NOTION_DATABASE_ID")
HEADERS = {"Authorization": f"Bearer {NOTION_TOKEN}", "Content-Type": "application/json", "Notion-Version": "2022-06-28"}

def call_gemini_rest_consolidated(full_prompt):
    """一次性发送所有数据，节省 API 配额"""
    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent?key={GOOGLE_API_KEY}"
    payload = {"contents": [{"parts": [{"text": full_prompt}]}]}
    
    for attempt in range(3): # 增加重试逻辑
        res = requests.post(url, json=payload, timeout=30)
        if res.status_code == 200:
            return res.json()['candidates'][0]['content']['parts'][0]['text']
        elif res.status_code == 429:
            print(f"⚠️ 配额限制，等待 60 秒后重试...")
            time.sleep(60)
        else:
            print(f"❌ API 错误: {res.text}")
            break
    return None

def run_analysis():
    date_str = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")
    tickers = {"Gold": "GC=F", "Silver": "SI=F", "Platinum": "PL=F", "Copper": "HG=F"}
    
    market_context = []
    notion_pages = {}

    # 1. 预先收集所有行情和事实数据
    for metal, sym in tickers.items():
        try:
            hist = yf.download(sym, period="5d", progress=False)
            if hist.empty: continue
            price = hist['Close'].iloc[-1].item()
            change = (price - hist['Close'].iloc[-2].item()) / hist['Close'].iloc[-2].item() * 100
            
            res = requests.post(f"https://api.notion.com/v1/databases/{DATABASE_ID}/query", headers=HEADERS,
                json={"filter": {"and": [{"property": "Date", "date": {"equals": date_str}},
                                       {"property": "Metal Type", "select": {"equals": metal}}]}}).json()
            
            if res.get("results"):
                page = res["results"][0]
                notion_pages[metal] = page["id"]
                dealer_info = page["properties"]["JPM/Asahi etc Stock change"]["rich_text"][0]["plain_text"]
                market_context.append(f"--- {metal} ---\nPrice: {price:.2f} ({change:+.2f}%)\nDealer Facts: {dealer_info}")
        except Exception as e: print(f"❌ {metal} 数据收集失败: {e}")

    if not market_context: return

    # 2. 构造合并 Prompt
    full_prompt = f"你是顶尖宏观交易员。以下是 {date_str} 的贵金属数据：\n\n" + "\n".join(market_context) + \
                  "\n\n请分别为每个品种提供 2 句硬核研判。格式严格如下：\n[Gold] 结论...\n[Silver] 结论...\n[Platinum] 结论...\n[Copper] 结论..."

    # 3. 发起单次 API 请求
    print(f"🚀 正在合并请求发送至 Gemini 2.0-flash...")
    all_analysis = call_gemini_rest_consolidated(full_prompt)
    
    if all_analysis:
        # 4. 解析 AI 返回的内容并分别填入 Notion
        for metal, page_id in notion_pages.items():
            try:
                # 简单正则或字符串切片提取对应金属的结论
                start_marker = f"[{metal}]"
                if start_marker in all_analysis:
                    part = all_analysis.split(start_marker)[1].split("[")[0].strip()
                    requests.patch(f"https://api.notion.com/v1/pages/{page_id}", headers=HEADERS,
                        json={"properties": {"Activity Note": {"rich_text": [{"text": {"content": part}}]}}})
                    print(f"✅ {metal} 深度研判同步成功")
            except Exception as e: print(f"❌ {metal} 写入失败: {e}")

if __name__ == "__main__": run_analysis()
