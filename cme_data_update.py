import os
import requests
import pdfplumber
import json
from google import genai
from datetime import datetime, timedelta

# --- 环境变量配置 ---
NOTION_TOKEN = os.getenv("NOTION_TOKEN")
DATABASE_ID = os.getenv("NOTION_DATABASE_ID")
GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")

HEADERS = {
    "Authorization": f"Bearer {NOTION_TOKEN}",
    "Content-Type": "application/json",
    "Notion-Version": "2022-06-28"
}

def get_ai_extraction(pdf_text):
    """
    Step 3 核心逻辑：利用 Gemini AI 从非结构化 PDF 文本中提取异动事实
    """
    if not GOOGLE_API_KEY:
        print("❌ 错误: GOOGLE_API_KEY 未设置")
        return None

    # 初始化新版 Gemini 客户端 (解决 404 路径问题)
    client = genai.Client(api_key=GOOGLE_API_KEY)
    
    prompt = f"""
    你是一个大宗商品数据分析专家。请阅读以下 CME 交割报告文本，并提取 Gold, Silver, Platinum, Copper 的交割异动。
    
    分析要求：
    1. 找到每个品种下具体的做市商 (Firm Name)，以及它们对应的 Issued (交割) 和 Stopped (接货) 数量。
    2. 忽略 "TOTAL" 汇总行。
    3. 为每种金属生成一句事实性结论。
       示例格式: "JPM 接货 500 张 (Stopped) | BOFA 交割 200 张 (Issued)"
    4. 必须严格以 JSON 格式返回，不要包含 Markdown 标签或废话。
       格式要求: {{"Gold": "结论", "Silver": "结论", "Platinum": "结论", "Copper": "结论"}}
    5. 若无显著异动，请填 "No significant activity."。
    
    报告文本：
    {pdf_text[:15000]}
    """
    
    try:
        # 使用新版 SDK 调用 gemini-1.5-flash
        response = client.models.generate_content(
            model='gemini-1.5-flash',
            contents=prompt
        )
        # 清洗可能存在的 Markdown 代码块标签
        clean_json = response.text.strip().replace('```json', '').replace('```', '').strip()
        return json.loads(clean_json)
    except Exception as e:
        print(f"❌ AI 解析 PDF 失败: {e}")
        return None

def run_inventory_update():
    """执行 Notion 同步任务"""
    pdf_path = "MetalsIssuesAndStopsReport.pdf"
    if not os.path.exists(pdf_path):
        print("❌ 错误: 找不到 PDF 文件，请检查 Step 1 是否下载成功")
        return

    # 1. 提取 PDF 文本 (前 8 页通常涵盖了金银铂铜)
    print("📄 正在提取 PDF 文本...")
    with pdfplumber.open(pdf_path) as pdf:
        all_text = "\n".join([p.extract_text() for p in pdf.pages[:8] if p.extract_text()])

    # 2. 调用 AI 提取结构化异动数据
    print("🤖 正在调用 Gemini 分析异动事实...")
    extraction = get_ai_extraction(all_text)
    if not extraction:
        return

    # 3. 同步至 Notion
    # 设定目标日期 (昨天)
    date_str = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")
    print(f"📅 准备更新日期为 {date_str} 的 Notion 记录")

    for metal, conclusion in extraction.items():
        try:
            # 查询 Notion 中对应的条目
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
                print(f"⚠️ {metal} 在 Notion 中未找到 {date_str} 的记录，跳过")
                continue

            page_id = res["results"][0]["id"]

            # 更新 JPM/Asahi etc Stock change 字段
            update_payload = {
                "properties": {
                    "JPM/Asahi etc Stock change": {
                        "rich_text": [{"text": {"content": conclusion}}]
                    }
                }
            }
            requests.patch(f"https://api.notion.com/v1/pages/{page_id}", headers=HEADERS, json=update_payload)
            print(f"✅ {metal} 异动数据更新成功: {conclusion}")

        except Exception as e:
            print(f"❌ {metal} 同步至 Notion 失败: {e}")

if __name__ == "__main__":
    run_inventory_update()
