# 米国株 買い場シグナル（ntfy版）

5分ごとに市場を監視し、Level 4・5だけntfyへ通知します。

## 条件

Level 5:
- VIX >= 35
- または ZVIX >= 2 かつ Fear & Greed <= 10 かつ S&P500 5日騰落率 <= -4%

Level 4:
- ZVIX >= 2 かつ S&P500 5日騰落率 <= -4%
- または VIX >= 30 かつ Fear & Greed <= 15%

同じLevelは連続通知しません。Level 4→5は再通知します。

## GitHub Secret

Settings → Secrets and variables → Actions → New repository secret

Name: NTFY_TOPIC
Value: ntfyで購読したトピック名
