import os, requests, pdfplumber, re
from datetime import datetime, timedelta

NOTION_TOKEN = os.getenv("NOTION_TOKEN")
DATABASE_ID = os.getenv("NOTION_DATABASE_ID")
HEADERS = {"Authorization": f"Bearer {NOTION_TOKEN}", "Content-Type": "application/json", "Notion-Version": "2022-06-28"}

def parse_pdf_robust():
    pdf_path = "MetalsIssuesAndStopsReport.pdf"
    results = {"Gold": [], "Silver": [], "Platinum": [], "Copper": []}
    if not os.path.exists(pdf_path): 
        print("❌ PDF 文件不存在")
        return results

    # 预设匹配关键字（CME PDF 中的标题通常全大写且独立一行）
    targets = {
        "GOLD": "Gold", 
        "SILVER": "Silver", 
        "PLATINUM": "Platinum", 
        "COPPER": "Copper"
    }

    with pdfplumber.open(pdf_path) as pdf:
        for page in pdf.pages[:10]: # 扩大搜索范围到前10页
            text = page.extract_text() or ""
            lines = text.split('\n')
            
            # 确定当前页面属于哪个金属
            current_metal = None
            for line in lines:
                clean_line = line.strip().upper()
                for key, val in targets.items():
                    # 匹配独立的单词 "GOLD" 等，防止误匹配 Goldman Sachs
                    if re.search(rf'\b{key}\b', clean_line) and "ISSUES AND STOPS" in clean_line:
                        current_metal = val
                        break
                if current_metal: break
            
            if not current_metal: continue
            print(f"🔍 正在解析 {current_metal} 页面...")

            # 使用 extract_table 处理表格，增加兼容性配置
            tables = page.extract_tables()
            for table in tables:
                for row in table:
                    # 过滤掉非数据行（表头或太短的行）
                    if not row or len(row) < 4: continue
                    
                    firm_name = str(row[0]).replace('\n', ' ').strip()
                    # 排除表头词汇和统计行
                    if any(x in firm_name.upper() for x in ["FIRM", "TOTAL", "SERVICE", "ISSUES"]): continue
                    
                    # 提取数值并去除逗号
                    issued = str(row[2]).replace(',', '').strip() if row[2] else ""
                    stopped = str(row[3]).replace(',', '').strip() if row[3] else ""

                    acts = []
                    if issued.isdigit() and int(issued) > 0:
                        acts.append(f"{issued} (Issued)")
                    if stopped.isdigit() and int(stopped) > 0:
                        acts.append(f"{stopped} (Stopped)")
                    
                    if acts:
                        entry = f"{firm_name}: {' | '.join(acts)}"
                        results[current_metal].append(entry)
                        print(f"  ✨ 发现变动: {entry}")

    # 合并结果，如果没有数据则保持 "No significant activity."
    return {k: (" | ".join(v) if v else "No significant activity.") for k, v in results.items()}

def run_sync():
    # 注意：CME 数据通常有滞后，确保 date_str 与你 Notion 中的 Date 列一致
    # 如果你是周一跑，抓取周五的数据，请根据实际情况调整 timedelta
    date_str = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")
    print(f"📅 目标同步日期: {date_str}")
    
    movement_data = parse_pdf_robust()
    
    for metal, info in movement_data.items():
        # 查询 Notion
        q_payload = {
            "filter": {
                "and": [
                    {"property": "Date", "date": {"equals": date_str}},
                    {"property": "Metal Type", "select": {"equals": metal}}
                ]
            }
        }
        res = requests.post(f"https://api.notion.com/v1/databases/{DATABASE_ID}/query", headers=HEADERS, json=q_payload).json()
        
        if res.get("results"):
            page_id = res["results"][0]["id"]
            update_payload = {
                "properties": {
                    "JPM/Asahi etc Stock change": {"rich_text": [{"text": {"content": info}}]}
                }
            }
            requests.patch(f"https://api.notion.com/v1/pages/{page_id}", headers=HEADERS, json=update_payload)
            print(f"✅ {metal} 同步成功")
        else:
            print(f"⚠️ Notion 中未找到 {metal} 的记录 ({date_str})")

if __name__ == "__main__":
    run_sync()
