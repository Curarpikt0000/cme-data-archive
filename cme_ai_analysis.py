import os
import requests
import yfinance as yf
import pdfplumber
from google import genai  # 使用新版 SDK
from datetime import datetime, timedelta

# --- 配置读取 ---
GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")
NOTION_TOKEN = os.getenv("NOTION_TOKEN")
DATABASE_ID = os.getenv("NOTION_DATABASE_ID")

HEADERS = {
    "Authorization": f"Bearer {NOTION_TOKEN}", 
    "Content-Type": "application/json", 
    "Notion-Version": "2022-06-28"
}

def get_ai_analysis():
    if not GOOGLE_API_KEY:
        print("❌ 错误: GOOGLE_API_KEY 为空，请检查 GitHub Secrets 配置")
        return

    # 初始化新版客户端
    client = genai.Client(api_key=GOOGLE_API_KEY)
    
    # 获取分析日期 (昨日)
    date_str = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")
    tickers = {"Gold": "GC=F", "Silver": "SI=F", "Platinum": "PL=F", "Copper": "HG=F"}

    # 1. 提取本地 PDF 内容 (Step 1 下载的文件)
    pdf_text = "No PDF data available."
    pdf_path = "MetalsIssuesAndStopsReport.pdf"
    if os.path.exists(pdf_path):
        try:
            with pdfplumber.open(pdf_path) as pdf:
                pdf_text = "\n".join([p.extract_text() for p in pdf.pages[:3] if p.extract_text()])
        except Exception as e:
            print(f"⚠️ PDF 读取失败: {e}")

    for metal, sym in tickers.items():
        try:
            # 2. 获取行情数据并强制标量化
            hist = yf.download(sym, period="5d", progress=False)
            if hist.empty or len(hist) < 2:
                p_info = "Price unavailable"
            else:
                # 使用 .item() 彻底避免 Series 格式化错误
                last_price = hist['Close'].iloc[-1]
                prev_price = hist['Close'].iloc[-2]
                
                # 处理 MultiIndex 结构下的提取
                if hasattr(last_price, 'item'):
                    last_price = last_price.item()
                    prev_price = prev_price.item()
                
                change_pct = (last_price - prev_price) / prev_price * 100
                p_info = f"Price {last_price:.2f} ({change_pct:+.2f}%)"

            # 3. 从 Notion 查询 Step 3 填入的数据
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
                print(f"ℹ️ {metal} 未找到记录，跳过")
                continue
            
            page = res["results"][0]
            pid = page["id"]
            props = page["properties"]
            
            net_chg = props.get("Net Change", {}).get("number", 0)
            dealer_text = props.get("JPM/Asahi etc Stock change", {}).get("rich_text", [])
            dealers = dealer_text[0]["text"]["content"] if dealer_text else "No dealer info"

            # 4. 调用 AI 进行深度研判
            prompt = f"""
            分析 {metal} ({date_str})：
            - 价格: {p_info}
            - 库存净变动: {net_chg}
            - 关键做市商异动: {dealers}
            - PDF交割摘要: {pdf_text[:800]}

            基于库存流向(Registered/Eligible)和机构搬货逻辑，提供2句硬核研判。
            直接指出是否存在挤仓风险或机构建仓迹象。
            """
            
            response = client.models.generate_content(
                model="gemini-1.5-flash",
                contents=prompt
            )
            ai_insight = response.text.strip()

            # 5. 回填 Notion
            update_payload = {
                "properties": {
                    "Name": {"title": [{"text": {"content": f"AI Insight: {metal} {date_str}"}}]},
                    "Activity Note": {"rich_text": [{"text": {"content": ai_insight}}]}
                }
            }
            requests.patch(f"https://api.notion.com/v1/pages/{pid}", headers=HEADERS, json=update_payload)
            print(f"✅ {metal} AI 分析同步成功")

        except Exception as e:
            print(f"❌ {metal} 处理出错: {str(e)}")

if __name__ == "__main__":
    get_ai_analysis()
