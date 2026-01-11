import os
import requests
import pdfplumber
from datetime import datetime, timedelta

# --- 配置区 ---
NOTION_TOKEN = os.getenv("NOTION_TOKEN")
DATABASE_ID = os.getenv("NOTION_DATABASE_ID")
HEADERS = {
    "Authorization": f"Bearer {NOTION_TOKEN}",
    "Content-Type": "application/json",
    "Notion-Version": "2022-06-28"
}

def parse_issues_stops():
    """解析 PDF 中的做市商及其变动数量"""
    results = {"Gold": [], "Silver": [], "Platinum": [], "Copper": []}
    pdf_path = "MetalsIssuesAndStopsReport.pdf"
    
    if not os.path.exists(pdf_path):
        print("❌ 未找到 PDF 文件")
        return results

    # 映射 PDF 中的关键词到我们的分类
    metal_map = {"GOLD": "Gold", "SILVER": "Silver", "PLATINUM": "Platinum", "COPPER": "Copper"}

    with pdfplumber.open(pdf_path) as pdf:
        for page in pdf.pages[:5]:  # 通常前几页包含所有主要品种
            tables = page.extract_tables()
            text = page.extract_text() or ""
            
            # 确定当前页面属于哪个金属品种
            current_metal = None
            for key, val in metal_map.items():
                if key in text.upper():
                    current_metal = val
                    break
            
            if not current_metal: continue

            for table in tables:
                for row in table:
                    # 典型的 CME 报表行格式: [Firm Name, Firm #, Issues, Stops]
                    # 我们过滤掉表头和空行，只取有数值的行
                    if not row or len(row) < 4: continue
                    
                    firm_name = str(row[0]).strip()
                    issues = str(row[2]).strip().replace(',', '')
                    stops = str(row[3]).strip().replace(',', '')

                    # 逻辑：如果 Issues 或 Stops 有数字，则记录
                    change_parts = []
                    if issues.isdigit() and int(issues) > 0:
                        change_parts.append(f"{issues} (Issued)")
                    if stops.isdigit() and int(stops) > 0:
                        change_parts.append(f"{stops} (Stopped)")
                    
                    if change_parts and firm_name not in ["TOTAL", "Firm Name"]:
                        # 格式化为: "JPM: 100 (Issued) | 50 (Stopped)"
                        results[current_metal].append(f"{firm_name}: {' | '.join(change_parts)}")

    # 将数组转化为字符串
    return {k: (" | ".join(v) if v else "No significant activity.") for k, v in results.items()}

def update_notion_inventory():
    date_str = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")
    movement_data = parse_issues_stops()
    
    for metal, dealer_info in movement_data.items():
        try:
            # 1. 查询当天的 Notion 页面
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
                print(f"ℹ️ {metal} {date_str} 记录尚未在 Notion 创建，跳过")
                continue

            pid = res["results"][0]["id"]

            # 2. 更新做市商异动字段 (JPM/Asahi etc Stock change)
            update_payload = {
                "properties": {
                    "JPM/Asahi etc Stock change": {
                        "rich_text": [{"text": {"content": dealer_info}}]
                    }
                }
            }
            requests.patch(f"https://api.notion.com/v1/pages/{pid}", headers=HEADERS, json=update_payload)
            print(f"✅ {metal} 已成功写入异动: {dealer_info}")

        except Exception as e:
            print(f"❌ {metal} 更新失败: {e}")

if __name__ == "__main__":
    update_notion_inventory()
