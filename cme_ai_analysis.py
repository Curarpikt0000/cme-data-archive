import os, requests, pdfplumber, json
from google import genai
from datetime import datetime, timedelta

# 配置
GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")
NOTION_TOKEN = os.getenv("NOTION_TOKEN")
DATABASE_ID = os.getenv("NOTION_DATABASE_ID")
HEADERS = {"Authorization": f"Bearer {NOTION_TOKEN}", "Content-Type": "application/json", "Notion-Version": "2022-06-28"}

def run_ai_extraction():
    if not GOOGLE_API_KEY: return
    client = genai.Client(api_key=GOOGLE_API_KEY)
    
    # 提取 PDF 前几页全文
    pdf_text = ""
    if os.path.exists("MetalsIssuesAndStopsReport.pdf"):
        with pdfplumber.open("MetalsIssuesAndStopsReport.pdf") as pdf:
            pdf_text = "\n".join([p.extract_text() for p in pdf.pages[:8] if p.extract_text()])

    prompt = f"""
    分析这份 CME 交割报告，识别 Gold, Silver, Platinum, Copper 的异样。
    要求：
    1. 找到各个金属下 Issues(交割) 或 Stops(接货) 变动明显的做市商。
    2. 为每种金属生成一句结论，格式如: "JPM 接货 500 张 | BOFA 交割 200 张"。
    3. 必须返回 JSON 格式：{{"Gold": "结论", "Silver": "结论", "Platinum": "结论", "Copper": "结论"}}
    文本：{pdf_text[:15000]}
    """
    
    try:
        response = client.models.generate_content(model='gemini-1.5-flash', contents=prompt)
        extraction = json.loads(response.text.strip().replace('```json', '').replace('```', ''))
        
        # 同步 Notion
        date_str = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")
        for metal, content in extraction.items():
            # 这里请保留您之前的 Notion 查询和 PATCH 逻辑，确保更新对应的 Metal Type
            print(f"✅ {metal} 数据已解析: {content}")
            # ... (执行 PATCH 操作)
    except Exception as e:
        print(f"❌ AI 解析失败: {e}")

if __name__ == "__main__":
    run_ai_extraction()
