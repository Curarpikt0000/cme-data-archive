import os
import requests
from datetime import datetime

NOTION_TOKEN = os.getenv("NOTION_TOKEN")
DATABASE_ID = "2e047eb5fd3c80d89d56e2c1ad066138"
GITHUB_REPO = "Curarpikt0000/cme-data-archive"

HEADERS = {
    "Authorization": f"Bearer {NOTION_TOKEN}",
    "Content-Type": "application/json",
    "Notion-Version": "2022-06-28"
}

METALS = {
    "Gold": "Gold_Stocks.xls",
    "Silver": "Silver_stocks.xls",
    "Copper": "Copper_Stocks.xls",
    "Aluminum": "Aluminum_Stocks.xls",
    "Lead": "Lead_Stocks.xls",
    "Zinc": "Zinc_Stocks.xls",
    "PA-PL": "PA-PL_Stck_Rprt.xls"
}

def get_file_property_item(name, url):
    return {"files": [{"name": name, "external": {"url": url}}]}

def sync_to_notion():
    # 确保日期格式和 Notion 一致
    from datetime import timedelta
    # 修正：直接使用 datetime.now()
    date_str = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")
    delivery_url = f"https://raw.githubusercontent.com/{GITHUB_REPO}/main/data/{date_str}/MetalsIssuesAndStopsReport.pdf"

    for metal_type, file_name in METALS.items():
        stock_url = f"https://raw.githubusercontent.com/{GITHUB_REPO}/main/data/{date_str}/{file_name}"
        
        # 1. 查询
        query_data = {
            "filter": {
                "and": [
                    {"property": "Date", "date": {"equals": date_str}},
                    {"property": "Metal Type", "select": {"equals": metal_type}}
                ]
            }
        }
        query_res = requests.post(f"https://api.notion.com/v1/databases/{DATABASE_ID}/query", headers=HEADERS, json=query_data)
        
        # 检查查询是否授权成功
        if query_res.status_code != 200:
            print(f"❌ Query Error: {query_res.status_code} - {query_res.text}")
            continue

        res_json = query_res.json()
        
        # 2. 准备属性 (严格匹配你的 Notion 列名)
        properties = {
            "Stock File": get_file_property_item(file_name, stock_url),
            "Delivery Notice": get_file_property_item("Delivery_Notice.pdf", delivery_url)
        }

        if res_json.get("results"):
            # 更新已有的
            page_id = res_json["results"][0]["id"]
            update_res = requests.patch(f"https://api.notion.com/v1/pages/{page_id}", headers=HEADERS, json={"properties": properties})
            if update_res.status_code == 200:
                print(f"✅ Updated {metal_type}")
            else:
                print(f"❌ Update Failed for {metal_type}: {update_res.text}")
        else:
            # 新建
            new_page = {
                "parent": {"database_id": DATABASE_ID},
                "properties": {
                    "Name": {"title": [{"text": {"content": f"{metal_type} - {date_str}"}}]},
                    "Date": {"date": {"start": date_str}},
                    "Metal Type": {"select": {"name": metal_type}},
                    **properties
                }
            }
            create_res = requests.post("https://api.notion.com/v1/pages", headers=HEADERS, json=new_page)
            if create_res.status_code == 200:
                print(f"✅ Created {metal_type}")
            else:
                print(f"❌ Creation Failed for {metal_type}: {create_res.text}")

if __name__ == "__main__":
    sync_to_notion()
