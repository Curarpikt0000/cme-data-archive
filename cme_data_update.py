import os, requests, pdfplumber, json
import google.generativeai as genai
from datetime import datetime, timedelta

# 环境配置
NOTION_TOKEN = os.getenv("NOTION_TOKEN")
DATABASE_ID = os.getenv("NOTION_DATABASE_ID")
GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")
HEADERS = {"Authorization": f"Bearer {NOTION_TOKEN}", "Content-Type": "application/json", "Notion-Version": "2022-06-28"}

def get_ai_extraction(pdf_text):
    """调用 Gemini AI 分析 PDF 文本提取异动"""
    if not GOOGLE_API_KEY: 
        print("❌ 错误: GOOGLE_API_KEY 为空")
        return None
    
    genai.configure(api_key=GOOGLE_API_KEY)
    # 修复 404: 确保模型名称标准
    model = genai.GenerativeModel('gemini-1.5-flash')
    
    prompt = f"""
    你是一个贵金属数据专家。请分析以下 CME 报告文本，并提取 Gold, Silver, Platinum, Copper 的异动数据。
    
    要求：
    1. 找到每个品种下的做市商 (Firm Name)，以及它们对应的 Issued (交割) 和 Stopped (接货) 数量。
    2. 忽略 "TOTAL" 汇总行。
    3. 结论必须是 JSON 格式，键为 "Gold", "Silver", "Platinum", "Copper"。
    4. 值示例: "JPM: 500 (Issued) | BOFA: 200 (Stopped)"。若无显著异动填 "No significant activity."。
    
    报告文本：
    {pdf_text[:15000]}
    """
    
    try:
        response = model.generate_content(prompt)
        # 清洗 JSON 字符串，防止 Markdown 干扰
        res_text = response.text.replace('```json', '').replace('```', '').strip()
        return json.loads(res_text)
    except Exception as e:
        print(f"❌ AI 提取数据失败: {e}")
        return None

def run_step_3():
    pdf_path = "MetalsIssuesAndStopsReport.pdf"
    if not os.path.exists(pdf_path): 
        print("❌ 找不到 PDF 文件")
        return

    # 1. 提取 PDF 文本
    with pdfplumber.open(pdf_path) as pdf:
        all_text = "\n".join([p.extract_text() for p in pdf.pages[:8] if p.extract_text()])

    # 2. 调用 AI 提取数据
    print("🤖 正在利用 AI 解析 PDF 异动数据...")
    # 修复逻辑: 确保函数名一致
    extraction = get_ai_extraction(all_text)
    if not extraction: return

    # 3. 同步至 Notion
    date_str = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")
    for metal, info in extraction.items():
        q_payload = {"filter": {"and": [{"property": "Date", "date": {"equals": date_str}},
                                       {"property": "Metal Type", "select": {"equals": metal}}]}}
        res = requests.post(f"https://api.notion.com/v1/databases/{DATABASE_ID}/query", headers=HEADERS, json=q_payload).json()
        
        if res.get("results"):
            pid = res["results"][0]["id"]
            requests.patch(f"https://api.notion.com/v1/pages/{pid}", headers=HEADERS,
                           json={"properties": {"JPM/Asahi etc Stock change": {"rich_text": [{"text": {"content": info}}]}}})
            print(f"✅ {metal} 已更新异动数据: {info}")

if __name__ == "__main__":
    run_step_3()
