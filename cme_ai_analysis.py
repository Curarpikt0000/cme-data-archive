import os
import requests
import pdfplumber
import yfinance as yf
import google.generativeai as genai
from datetime import datetime, timedelta

# ==========================================
# 1. 配置加载 (从 GitHub Secrets)
# ==========================================
NOTION_TOKEN = os.getenv("NOTION_TOKEN")
DATABASE_ID = os.getenv("NOTION_DATABASE_ID", "2e047eb5fd3c80d89d56e2c1ad066138")
GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")

genai.configure(api_key=GOOGLE_API_KEY)
HEADERS = {
    "Authorization": f"Bearer {NOTION_TOKEN}",
    "Content-Type": "application/json",
    "Notion-Version": "2022-06-28"
}

def extract_pdf_text():
    """提取交割通知 PDF 的文本内容"""
    pdf_path = "MetalsIssuesAndStopsReport.pdf"
    if not os.path.exists(pdf_path):
        return "Warning: Delivery Notice PDF not found."
    try:
        with pdfplumber.open(pdf_path) as pdf:
            # 提取前几页核心交割数据
            content = "\n".join([page.extract_text() for page in pdf.pages[:3] if page.extract_text()])
            return content[:5000] # 限制长度防止 Token 溢出
    except Exception as e:
        return f"PDF Error: {str(e)}"

def get_market_analysis():
    # 当前日期设为 2026-01-11 逻辑
    date_str = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")
    model = genai.GenerativeModel('gemini-1.5-flash')
    tickers = {"Gold": "GC=F", "Silver": "SI=F", "Platinum": "PL=F"}

    print(f"[*] 启动 AI 深度分析流水线: {datetime.now()}")
    pdf_context = extract_pdf_text()

    for metal, ticker in tickers.items():
        # 1. 抓取价格并修复 IndexError
        try:
            data = yf.download(ticker, period="5d")
            if len(data) < 2:
                p_report = "Price data insufficient."
            else:
                change = ((data['Close'].iloc[-1] - data['Close'].iloc[-2]) / data['Close'].iloc[-2]) * 100
                p_report = f"Price: {data['Close'].iloc[-1]:.2f}, Change: {change:+.2f}%"
        except:
            p_report = "Price fetch failed."

        # 2. 构造深度分析提示词 (结合 PDF + AI 知识)
        prompt = f"""
        作为大宗商品分析师，请根据以下信息分析 {metal} 的市场风险与新闻：
        1. 价格动态：{p_report}
        2. 交割报告 (PDF 摘要)：{pdf_context}
        3. 当前时间背景：2026 年 1 月。
        
        请结合 PDF 中的做市商 Issues/Stops 异动，识别是否存在潜在的挤仓(Squeeze)风险、
        主要的空头交割压力或利好新闻。
        
        要求：
        - 逻辑严密，指出具体的风险点。
        - 简明扼要，给出两句核心结论。
        """

        try:
            response = model.generate_content(prompt)
            ai_insight = response.text.strip()

            # 3. 同步至 Notion (修正属性名)
            query_res = requests.post(
                f"https://api.notion.com/v1/databases/{DATABASE_ID}/query",
                headers=HEADERS,
                json={"filter": {"and": [
                    {"property": "Date", "date": {"equals": date_str}},
                    {"property": "Metal Type", "select": {"equals": metal}}
                ]}}
            ).json()

            if query_res.get("results"):
                pid = query_res["results"][0]["id"]
                requests.patch(
                    f"https://api.notion.com/v1/pages/{pid}",
                    headers=HEADERS,
                    json={"properties": {
                        "Name": {"title": [{"text": {"content": f"AI Insight: {metal} {date_str}"}}]},
                        "Activity Note": {"rich_text": [{"text": {"content": ai_insight}}]}
                    }}
                )
                print(f"✅ {metal} AI 分析已同步。")
        except Exception as e:
            print(f"❌ {metal} AI 处理失败: {e}")

if __name__ == "__main__":
    get_market_analysis()
