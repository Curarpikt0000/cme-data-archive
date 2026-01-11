import os
import requests
import yfinance as yf
import pdfplumber
import google.generativeai as genai
from datetime import datetime, timedelta

# --- 配置区 ---
NOTION_TOKEN = os.getenv("NOTION_TOKEN")
DATABASE_ID = os.getenv("NOTION_DATABASE_ID", "2e047eb5fd3c80d89d56e2c1ad066138")
genai.configure(api_key=os.getenv("GOOGLE_API_KEY"))
HEADERS = {
    "Authorization": f"Bearer {NOTION_TOKEN}", 
    "Content-Type": "application/json", 
    "Notion-Version": "2022-06-28"
}

def get_ai_analysis():
    # 设定分析日期（通常为昨天的数据）
    date_str = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")
    model = genai.GenerativeModel('gemini-1.5-flash')
    tickers = {"Gold": "GC=F", "Silver": "SI=F", "Platinum": "PL=F", "Copper": "HG=F"}

    # 1. 提取 PDF 交割细节
    pdf_text = ""
    pdf_path = "MetalsIssuesAndStopsReport.pdf"
    if os.path.exists(pdf_path):
        try:
            with pdfplumber.open(pdf_path) as pdf:
                # 仅提取前3页关键信息防止 Token 过长
                pdf_text = "\n".join([p.extract_text() for p in pdf.pages[:3] if p.extract_text()])
        except Exception as e:
            print(f"⚠️ PDF 读取失败: {e}")

    # 2. 遍历金属品种分析
    for metal, sym in tickers.items():
        try:
            # 获取价格数据
            hist = yf.download(sym, period="5d", progress=False)
            
            if len(hist) < 2: 
                p_info = "Price data unavailable."
            else:
                # 【核心修复】：使用 .item() 确保获取的是纯数值而非 Series
                # 处理 yfinance 可能返回的多级索引
                last_price = hist['Close'].iloc[-1]
                prev_price = hist['Close'].iloc[-2]
                
                # 如果是 Series (多级索引情况)，转为标量
                if hasattr(last_price, 'item'):
                    last_price = last_price.item()
                    prev_price = prev_price.item()
                
                change_pct = (last_price - prev_price) / prev_price * 100
                p_info = f"Price {last_price:.2f} ({change_pct:+.2f}%)"

            # 3. 从 Notion 获取库存和商家信息
            query_payload = {
                "filter": {
                    "and": [
                        {"property": "Date", "date": {"equals": date_str}},
                        {"property": "Metal Type", "select": {"equals": metal}}
                    ]
                }
            }
            q_res = requests.post(
                f"https://api.notion.com/v1/databases/{DATABASE_ID}/query", 
                headers=HEADERS, 
                json=query_payload
            ).json()

            if not q_res.get("results"):
                print(f"ℹ️ {metal} 在 Notion 中未找到 {date_str} 的记录，跳过")
                continue
            
            page = q_res["results"][0]
            pid = page["id"]
            props = page["properties"]
            
            # 安全获取数值
            net_chg = props.get("Net Change", {}).get("number", 0)
            dealers_list = props.get("JPM/Asahi etc Stock change", {}).get("rich_text", [])
            dealers = dealers_list[0]["text"]["content"] if dealers_list else "No significant dealer movement"

            # 4. 调用 AI 进行研判
            prompt = f"""
            作为资深大宗商品分析师，请分析 {metal} 在 {date_str} 的表现：
            价格动态: {p_info}
            库存净变动: {net_chg}
            关键做市商/仓库异动: {dealers}
            交割报告原文摘要: {pdf_text[:1000]}
            
            要求：结合库存流向（Registered/Eligible 转换）和商家接货/出货逻辑，给出 2 句深度研判。
            直接指出是否存在“挤仓风险（Squeeze）”或“机构看涨/看跌情绪”。禁止废话。
            """
            
            response = model.generate_content(prompt)
            ai_insight = response.text.strip()
            
            # 5. 回填信息到 Notion
            update_payload = {
                "properties": {
                    "Name": {"title": [{"text": {"content": f"AI Insight: {metal} {date_str}"}}]},
                    "Activity Note": {"rich_text": [{"text": {"content": ai_insight}}]}
                }
            }
            requests.patch(f"https://api.notion.com/v1/pages/{pid}", headers=HEADERS, json=update_payload)
            print(f"✅ {metal} AI 分析同步成功")

        except Exception as e:
            print(f"❌ {metal} 处理过程中出错: {str(e)}")

if __name__ == "__main__":
    get_ai_analysis()
