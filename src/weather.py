#!/usr/bin/env python3
"""天氣查詢——新北市三重（湯城）。

## 為什麼用 Open-Meteo

免費、**不用申請 API key**、沒有每日額度限制、回傳 JSON。
用需要 key 的服務（OpenWeatherMap 之類）會多一個「key 過期/額度用完就整個壞掉」
的失效點，而且金鑰要另外保管。

## 座標寫死是刻意的

這台機器就架在辦公室，地點不會變。做成可設定只是多一個會設錯的地方。
之後真要換地點，改這兩個數字就好。
"""
import json
import urllib.request

# 新北市三重區湯城園區
LAT, LON = 25.0616, 121.4790
PLACE = '新北市三重'

TIMEOUT = 8

# Open-Meteo 的天氣代碼（WMO）對照。只收錄台灣會遇到的。
WMO = {
    0: '晴朗', 1: '大致晴朗', 2: '多雲時晴', 3: '陰天',
    45: '有霧', 48: '霧凇',
    51: '毛毛雨', 53: '毛毛雨', 55: '毛毛雨較大',
    61: '小雨', 63: '中雨', 65: '大雨',
    66: '凍雨', 67: '凍雨',
    71: '小雪', 73: '中雪', 75: '大雪',
    80: '陣雨', 81: '陣雨較大', 82: '強陣雨',
    95: '雷雨', 96: '雷雨伴冰雹', 99: '強雷雨伴冰雹',
}


def fetch():
    url = (f'https://api.open-meteo.com/v1/forecast?latitude={LAT}&longitude={LON}'
           '&current=temperature_2m,apparent_temperature,relative_humidity_2m,'
           'precipitation,weather_code,wind_speed_10m'
           '&daily=temperature_2m_max,temperature_2m_min,precipitation_probability_max'
           '&timezone=Asia%2FTaipei&forecast_days=1')
    with urllib.request.urlopen(url, timeout=TIMEOUT) as r:
        return json.loads(r.read().decode('utf-8'))


def report():
    """回一段人看的天氣描述。查不到就直說，不要編。"""
    try:
        d = fetch()
    except Exception as e:
        return f'查不到天氣資料（{type(e).__name__}），可能是網路不通。'

    cur = d.get('current') or {}
    day = d.get('daily') or {}
    t = cur.get('temperature_2m')
    feel = cur.get('apparent_temperature')
    rh = cur.get('relative_humidity_2m')
    code = cur.get('weather_code')
    wind = cur.get('wind_speed_10m')
    desc = WMO.get(code, '')

    lines = [f'🌤 {PLACE}　{desc}']
    if t is not None:
        line = f'目前 {t:.0f}°C'
        if feel is not None and abs(feel - t) >= 1:
            line += f'（體感 {feel:.0f}°C）'
        lines.append(line)
    if rh is not None:
        lines.append(f'濕度 {rh:.0f}%')
    try:
        lo = day['temperature_2m_min'][0]
        hi = day['temperature_2m_max'][0]
        lines.append(f'今日 {lo:.0f}~{hi:.0f}°C')
    except (KeyError, IndexError, TypeError):
        pass
    try:
        pop = day['precipitation_probability_max'][0]
        if pop is not None:
            lines.append(f'降雨機率 {pop:.0f}%')
    except (KeyError, IndexError, TypeError):
        pass
    if wind is not None and wind >= 20:
        lines.append(f'⚠ 風速 {wind:.0f} km/h，風大')
    return '　'.join(lines[:2]) + '\n' + '　'.join(lines[2:])


if __name__ == '__main__':
    print(report())
