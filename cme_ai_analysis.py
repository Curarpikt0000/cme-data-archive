import os
import requests
import yfinance as yf
from datetime import datetime, timedelta

# --- 配置区 ---
GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")
NOTION_TOKEN = os.getenv("NOTION_TOKEN")
DATABASE_ID = os.getenv("NOTION_DATABASE_ID")

HEADERS = {
    "Authorization": f"Bearer {NOTION_TOKEN}",
    "Content-Type": "application/json",
    "Notion-Version": "2022-06-28"
}

def call_gemini_rest_2026(prompt):
    """
    思路：跳过 SDK，直接使用 REST POST 请求。
    2026 年标准：使用 v1beta 接口和 gemini-2.0-flash 模型。
    """
    # 尝试 2026 年最稳健的 2.0-flash 模型
    model_name = "gemini-2.0-flash"
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model_name}:generateContent?key={GOOGLE_API_KEY}"
    
    payload = {
        "contents": [{
            "parts": [{"text": prompt}]
        }],
        "generationConfig": {
            "temperature": 0.7,
            "maxOutputTokens": 200
        }
    }

    try:
        res = requests.post(url, json=payload, timeout=15)
        if res.status_code == 200:
            return res.json()['candidates'][0]['content']['parts'][0]['text'].strip()
        else:
            print(f"⚠️ {model_name} 报错 {res.status_code}: {res.text}")
            # 备选方案：如果 2.0 报错，尝试 1.5-flash-latest (兼容模式)
            url_bak = url.replace(model_name, "gemini-1.5-flash-latest")
            res_bak = requests.post(url_bak, json=payload)
            if res_bak.status_code == 200:
                return res_bak.json()['candidates'][0]['content']['parts'][0]['text'].strip()
            return None
    except Exception as e:
        print(f"❌ REST 请求异常: {e}")
        return None

def run_analysis():
    # 设定分析日期（昨天）
    date_str = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")
    tickers = {"Gold": "GC=F", "Silver": "SI=F", "Platinum": "PL=F", "Copper": "HG=F"}

    print(f"🚀 开始执行 {date_str} 市场博弈研判...")

    for metal, sym in tickers.items():
        try:
            # 1. 获取行情并修复数据类型报错
            hist = yf.download(sym, period="5d", progress=False)
            if hist.empty or len(hist) < 2:
                print(f"⚠️ {metal} 行情数据不足")
                continue
            
            # 使用 .item() 解决 Series format 报错
            curr_p = hist['Close'].iloc[-1].item()
            prev_p = hist['Close'].iloc[-2].item()
            change = (curr_p - prev_p) / prev_p * 100
            price_info = f"Price: {curr_p:.2f} ({change:+.2f}%)"

            # 2. 从 Notion 查询 Step 3 写入的异动事实
            query_url = f"https://api.notion.com/v1/databases/{DATABASE_ID}/query"
            query_payload = {
                "filter": {
                    "and": [
                        {"property": "Date", "date": {"equals": date_str}},
                        {"property": "Metal Type", "select": {"equals": metal}}
                    ]
                }
            }
            query_res = requests.post(query_url, headers=HEADERS, json=query_payload).json()

            if not query_res.get("results"):
                print(f"ℹ️ {metal} 未找到记录")
                continue
            
            page = query_res["results"][0]
            page_id = page["id"]
            
            # 提取详细异动 (JPM etc Stock change) 
            dealer_props = page["properties"].get("JPM/Asahi etc Stock change", {}).get("rich_text", [])
            dealer_info = dealer_props[0]["plain_text"] if dealer_props else "No specific movement data."

            # 3. 构造提示词并调用 AI
            prompt = f"""
            你是一位顶尖的大宗商品宏观交易员。请根据以下数据进行市场博弈研判：
            
            品种: {metal} ({date_str})
            价格变动: {price_info}
            做市商变动事实: {dealer_info}
            
            研判要求：
            1. 直接给出 2 句深度结论，分析机构接货（Stops）或交割（Issues）背后的挤仓风险或护盘意图。
            2. 严禁废话，风格硬核。
            """
            
            analysis = call_gemini_rest_2026(prompt)

            if analysis:
                # 4. 回填至 Notion 的 Activity Note
                update_payload = {
                    "properties": {
                        "Name": {"title": [{"text": {"content": f"AI Insight: {metal} {date_str}"}}]},
                        "Activity Note": {"rich_text": [{"text": {"content": analysis}}]}
                    }
                }
                requests.patch(f"https://api.notion.com/v1/pages/{page_id}", headers=HEADERS, json=update_payload)
                print(f"✅ {metal} 研判成功: {analysis[:30]}...")
            else:
                print(f"❌ {metal} AI 生成失败")

        except Exception as e:
            print(f"❌ {metal} 处理过程中崩溃: {e}")

if __name__ == "__main__":
    run_analysis()
