import os
import requests
import yfinance as yf
from google import genai
from datetime import datetime, timedelta

# --- 环境变量配置 ---
GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")
NOTION_TOKEN = os.getenv("NOTION_TOKEN")
DATABASE_ID = os.getenv("NOTION_DATABASE_ID")

HEADERS = {
    "Authorization": f"Bearer {NOTION_TOKEN}", 
    "Content-Type": "application/json", 
    "Notion-Version": "2022-06-28"
}

def get_ai_market_analysis():
    """Step 4: 基于行情和异动数据进行深度市场研判"""
    if not GOOGLE_API_KEY:
        print("❌ 错误: GOOGLE_API_KEY 为空，请检查 GitHub Secrets")
        return

    # 1. 初始化新版 Gemini 客户端 (修复 404 和命名空间问题)
    client = genai.Client(api_key=GOOGLE_API_KEY)
    
    # 设定分析日期 (昨天)
    date_str = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")
    tickers = {"Gold": "GC=F", "Silver": "SI=F", "Platinum": "PL=F", "Copper": "HG=F"}

    for metal, sym in tickers.items():
        try:
            # 2. 获取行情数据并修复 Series 格式化错误
            hist = yf.download(sym, period="5d", progress=False)
            if hist.empty or len(hist) < 2:
                p_info = "Price data unavailable."
            else:
                # 使用 .item() 确保将 pandas Series 转换为标量数值，解决格式化报错
                last_price = hist['Close'].iloc[-1].item() 
                prev_price = hist['Close'].iloc[-2].item()
                change_pct = (last_price - prev_price) / prev_price * 100
                p_info = f"Price {last_price:.2f} ({change_pct:+.2f}%)"

            # 3. 从 Notion 查询 Step 3 已写入的异动详情
            query_url = f"https://api.notion.com/v1/databases/{DATABASE_ID}/query"
            query_payload = {
                "filter": {
                    "and": [
                        {"property": "Date", "date": {"equals": date_str}},
                        {"property": "Metal Type", "select": {"equals": metal}}
                    ]
                }
            }
            res = requests.post(query_url, headers=HEADERS, json=query_payload).json()

            if not res.get("results"):
                print(f"ℹ️ {metal} 在 Notion 中未找到记录，跳过分析")
                continue
            
            page = res["results"][0]
            page_id = page["id"]
            # 提取 Step 3 刚刚填入的异动事实 (JPM/Asahi etc Stock change 字段)
            dealer_rt = page["properties"].get("JPM/Asahi etc Stock change", {}).get("rich_text", [])
            anomaly_details = dealer_rt[0].get("plain_text", "No specific movement") if dealer_rt else "None"

            # 4. 执行 AI 深度研判 (使用 gemini-1.5-flash)
            prompt = f"""
            分析 {metal} ({date_str})：
            价格行情: {p_info}
            交割异动详情: {anomaly_details}

            请作为顶级宏观交易员，提供 2 句深度博弈研判。
            直接指出是否存在“挤仓风险（Squeeze）”或“机构护盘/出货”的意图。禁止废话。
            """
            
            response = client.models.generate_content(
                model='gemini-1.5-flash',
                contents=prompt
            )
            ai_conclusion = response.text.strip()

            # 5. 将深度研判结果回填到 Notion 的 Activity Note
            update_payload = {
                "properties": {
                    "Name": {"title": [{"text": {"content": f"AI Insight: {metal} {date_str}"}}]},
                    "Activity Note": {"rich_text": [{"text": {"content": ai_conclusion}}]}
                }
            }
            requests.patch(f"https://api.notion.com/v1/pages/{page_id}", headers=HEADERS, json=update_payload)
            print(f"✅ {metal} 深度研判同步成功")

        except Exception as e:
            print(f"❌ {metal} 处理出错: {str(e)}")

if __name__ == "__main__":
    get_ai_market_analysis()
