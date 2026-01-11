import pandas as pd
import numpy as np
import yfinance as yf
from datetime import datetime, timedelta

class CME_AI_Analyzer:
    def __init__(self, ticker_list=["GC=F", "SI=F", "PL=F"]):
        """
        初始化 CME 贵金属 AI 分析器
        GC=F: Gold, SI=F: Silver, PL=F: Platinum
        """
        self.tickers = ticker_list
        self.market_data = {}

    def fetch_data(self, period="60d"):
        """获取期货基础数据及成交量/持仓量（模拟持仓量趋势）"""
        print(f"[*] 正在从 CME 市场接口提取数据: {datetime.now()}")
        for ticker in self.tickers:
            data = yf.download(ticker, period=period, interval="1d")
            # 逻辑计算：波动率 (ATR 简化版)
            data['Volatility'] = (data['High'] - data['Low']) / data['Close']
            # 逻辑计算：5日均量
            data['Vol_MA5'] = data['Volume'].rolling(window=5).mean()
            self.market_data[ticker] = data
        return self.market_data

    def run_logic_chain(self, ticker):
        """
        核心逻辑链条评估: [价格] + [成交量] + [持仓量]
        """
        df = self.market_data[ticker].iloc[-1]
        prev_df = self.market_data[ticker].iloc[-2]
        
        price_change = (df['Close'] - prev_df['Close']) / prev_df['Close']
        vol_surge = df['Volume'] > df['Vol_MA5'] * 1.2  # 成交量超过均值20%
        
        # 逻辑链判定
        signal = "NEUTRAL"
        logic_reason = ""
        
        if price_change > 0.01 and vol_surge:
            signal = "STRONG_BULLISH"
            logic_reason = "价格上涨且成交量显著放大，显示机构资金积极入场（Aggressive Buying）。"
        elif price_change < -0.01 and vol_surge:
            signal = "STRONG_BEARISH"
            logic_reason = "价格下跌且放量，反映市场出现恐慌性抛售或主动性杀跌。"
        elif abs(price_change) < 0.005 and vol_surge:
            signal = "ACCUMULATION"
            logic_reason = "价格震荡但成交量激增，通常为大机构在特定区间进行吸筹或派发。"
            
        return {
            "Ticker": ticker,
            "Price_Change": f"{price_change:.2%}",
            "Signal": signal,
            "Logic": logic_reason,
            "Volatility_Index": f"{df['Volatility']:.4f}"
        }

    def generate_ai_summary(self, logic_results):
        """
        AI 洞察总结（此处模拟调用 LLM API）
        """
        print("\n[AI Market Insights - CME Analysis Summary]")
        print("-" * 50)
        for res in logic_results:
            summary = f"针对 {res['Ticker']}：{res['Logic']} 当前波动率系数为 {res['Volatility_Index']}。"
            print(f"> {summary}")
        
        print("\n[Next Step Suggestion]")
        print("建议密切关注 COMEX 库存变动及 CVOL 指数偏度，确认是否有挤仓风险。")

if __name__ == "__main__":
    analyzer = CME_AI_Analyzer()
    analyzer.fetch_data()
    
    all_results = []
    for t in ["GC=F", "SI=F"]:
        all_results.append(analyzer.run_logic_chain(t))
        
    analyzer.generate_ai_summary(all_results)
