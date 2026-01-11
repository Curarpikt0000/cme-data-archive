import os
import requests
import pandas as pd
import yfinance as yf
from datetime import datetime

class CME_AI_Analyzer:
    def __init__(self):
        # 1. 初始化配置与凭据 (从 GitHub Secrets 读取)
        self.cme_client_id = os.getenv("CME_CLIENT_ID", "api_chao")
        self.cme_client_secret = os.getenv("CME_CLIENT_SECRET")
        self.notion_token = os.getenv("NOTION_TOKEN")
        self.notion_db_id = os.getenv("NOTION_DATABASE_ID")
        
        self.tickers = ["GC=F", "SI=F", "PL=F"] # 金, 银, 铂
        self.market_data = {}

    def get_cme_oauth_token(self):
        """ 通过 OAuth 2.0 获取 CME 访问令牌"""
        if not self.cme_client_secret:
            print("[!] 未检测到 CME_CLIENT_SECRET，跳过 API 验证。")
            return None
        
        auth_url = "https://auth.cmegroup.com/as/token.oauth2"
        payload = {
            'grant_type': 'client_credentials',
            'client_id': self.cme_client_id,
            'client_secret': self.cme_client_secret
        }
        try:
            r = requests.post(auth_url, data=payload, timeout=10)
            return r.json().get('access_token')
        except Exception as e:
            print(f"[!] CME Token 获取失败: {e}")
            return None

    def fetch_market_data(self):
        """抓取数据并修复 MultiIndex 索引问题"""
        print(f"[*] 启动数据抓取流水线: {datetime.now()}")
        for ticker in self.tickers:
            # auto_adjust 确保价格字段统一
            df = yf.download(ticker, period="60d", interval="1d", auto_adjust=True)
            
            # 健壮性修复：如果 yfinance 返回多级索引，则展平它
            if isinstance(df.columns, pd.MultiIndex):
                df.columns = df.columns.get_level_values(0)
            
            # 计算量化指标
            df['Volatility'] = (df['High'] - df['Low']) / df['Close']
            df['Vol_MA5'] = df['Volume'].rolling(window=5).mean()
            self.market_data[ticker] = df.dropna()
        return self.market_data

    def analyze_logic_chain(self, ticker):
        """核心逻辑链条：价格 + 成交量 + 波动率"""
        df = self.market_data.get(ticker)
        
        # 默认返回结构，防止 KeyError
        report = {
            "Ticker": ticker,
            "Price_Change": "0.00%",
            "Signal": "NEUTRAL",
            "Logic": "持平或波动过小，无显著信号。",
            "Vol_Idx": "0.0000"
        }

        if df is None or len(df) < 2:
            report["Logic"] = "数据源缺失，请检查网络。"
            return report

        # 转换为标量，彻底解决 ValueError
        last_row = df.iloc[-1]
        prev_row = df.iloc[-2]
        
        p_now = float(last_row['Close'])
        p_prev = float(prev_row['Close'])
        v_now = float(last_row['Volume'])
        v_ma5 = float(last_row['Vol_MA5'])
        
        p_change = (p_now - p_prev) / p_prev
        vol_surge = v_now > (v_ma5 * 1.2) # 成交量突增20%

        # 逻辑判定
        if p_change > 0.01 and vol_surge:
            report.update({"Signal": "STRONG_BULLISH", "Logic": "价升量增：机构资金入场，趋势极强。"})
        elif p_change < -0.01 and vol_surge:
            report.update({"Signal": "STRONG_BEARISH", "Logic": "价跌量增：恐慌性抛售，下行压力大。"})
        
        report["Price_Change"] = f"{p_change:.2%}"
        report["Vol_Idx"] = f"{float(last_row['Volatility']):.4f}"
        return report

    def sync_to_notion(self, report):
        """ 同步至 Notion 数据库"""
        if not self.notion_token or not self.notion_db_id:
            print(f"[!] {report['Ticker']} 分析完成，但未配置 Notion 环境变量，仅本地打印。")
            return

        url = "https://api.notion.com/v1/pages"
        headers = {
            "Authorization": f"Bearer {self.notion_token}",
            "Notion-Version": "2022-06-28",
            "Content-Type": "application/json"
        }
        
        # 映射 Ticker 到 Notion 的 'Metal Type' 列
        metal_map = {"GC=F": "Gold", "SI=F": "Silver", "PL=F": "Platinum"}
        
        payload = {
            "parent": {"database_id": self.notion_db_id},
            "properties": {
                "Ad Name": {"title": [{"text": {"content": f"AI Insight: {report['Ticker']}"}}]},
                "Metal Type": {"select": {"name": metal_map.get(report['Ticker'], "Other")}},
                "Date": {"date": {"start": datetime.now().strftime("%Y-%m-%d")}},
                "Activity Note": {"rich_text": [{"text": {"content": f"[{report['Signal']}] {report['Logic']}"}}]},
                "Volatility Index": {"number": float(report['Vol_Idx'])}
            }
        }
        
        try:
            res = requests.post(url, json=payload, headers=headers)
            if res.status_code == 200:
                print(f"[√] {report['Ticker']} 成功同步至 Notion。")
            else:
                print(f"[×] Notion 同步失败: {res.text}")
        except Exception as e:
            print(f"[!] 请求 Notion API 异常: {e}")

if __name__ == "__main__":
    bot = CME_AI_Analyzer()
    
    # 步骤 1: 获取 CME Token (为后续扩展官方 API 预留)
    bot.get_cme_oauth_token()
    
    # 步骤 2: 抓取与分析
    bot.fetch_market_data()
    
    print("\n[AI Market Analysis Report]")
    for ticker in bot.tickers:
        analysis = bot.analyze_logic_chain(ticker)
        print(f"> {analysis['Ticker']} [{analysis['Signal']}]: {analysis['Logic']}")
        
        # 步骤 3: 推送至 Notion
        bot.sync_to_notion(analysis)
