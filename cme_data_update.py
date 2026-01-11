import os, requests, pdfplumber, json
from google import genai
from datetime import datetime, timedelta

NOTION_TOKEN = os.getenv("NOTION_TOKEN")
DATABASE_ID = os.getenv("NOTION_DATABASE_ID")
GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")
HEADERS = {"Authorization": f"Bearer {NOTION_TOKEN}", "Content-Type": "application/json", "Notion-Version": "2022-06-28"}

def get_ai_extraction(pdf_text):
    """使用新版 SDK 提取 PDF 中的交割异动"""
    if not GOOGLE_API_KEY:
        print("❌ 错误: GOOGLE_API_KEY 为空")
        return None
    
    # 初始化新版客户端
    client = genai.Client(api_key=GOOGLE_API_KEY)
    
    prompt = f"""
    分析这份 CME 交割报告，提取 Gold, Silver, Platinum, Copper 的异动。
    要求：
    1. 识别每个品种下具体的做市商 (Firm Name) 及其 Issued 和 Stopped 数量。
    2. 生成一句简洁的结论。示例: "JPM 接货 500 张 (Stopped) | BOFA 交割 200 张 (Issued)"。
    3. 必须返回 JSON 格式，不要有 Markdown。
       格式: {{"Gold": "结论", "Silver": "结论", "Platinum": "结论", "Copper": "结论"}}
    4. 若无显著异动填 "No significant activity."。
    
    报告文本：
    {pdf_text[:15000]}
    """
    
    try:
        # 新版 SDK 调用方式
        response = client.models.generate_content(
            model='gemini-1.5-flash',
            contents=prompt
        )
        clean_json = response.text.replace('```json', '').replace('```', '').strip()
        return json.loads(clean_json)
    except Exception as e:
        print(f"❌ AI 解析失败: {e}")
        return None

def run_step_3():
    pdf_path = "MetalsIssuesAndStopsReport.pdf"
    if not os.path.exists(pdf_path): return

    with pdfplumber.open(pdf_path) as pdf:
        # 提取前 8 页文本
        all_text = "\n".join([p.extract_text() for p in pdf.pages[:8] if p.extract_text()])

    print("🤖 正在利用 AI 分析 PDF 异动结论...")
    extraction = get_ai_extraction(all_text)
    if not extraction: return

    date_str = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")
    for metal, conclusion in extraction.items():
        q = requests.post(f"https://api.notion.com/v1/databases/{DATABASE_ID}/query", headers=HEADERS,
            json={"filter": {"and": [{"property": "Date", "date": {"equals": date_str}},
                                   {"property": "Metal Type", "select": {"equals": metal}}]}}).json()
        
        if q.get("results"):
            pid = q["results"][0]["id"]
            requests.patch(f"https://api.notion.com/v1/pages/{pid}", headers=HEADERS,
                json={"properties": {"JPM/Asahi etc Stock change": {"rich_text": [{"text": {"content": conclusion}}]}}})
            print(f"✅ {metal} 同步成功: {conclusion}")

if __name__ == "__main__":
    run_step_3()
