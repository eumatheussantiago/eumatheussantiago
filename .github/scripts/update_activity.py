import argparse
import math
import re
from datetime import date, timedelta
from html import escape
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import Request, urlopen
import xml.etree.ElementTree as ET


class CalendarParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.cells = {}
        self.tips = {}
        self.target = None
        self.text = []

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == 'td' and attrs.get('data-date'):
            self.cells[attrs['id']] = {
                'date': attrs['data-date'],
                'level': int(attrs['data-level']),
            }
        if tag == 'tool-tip' and attrs.get('for'):
            self.target = attrs['for']
            self.text = []

    def handle_data(self, data):
        if self.target is not None:
            self.text.append(data)

    def handle_endtag(self, tag):
        if tag == 'tool-tip' and self.target is not None:
            self.tips[self.target] = ''.join(self.text).strip()
            self.target = None

    def days(self):
        result = []
        for key, item in self.cells.items():
            label = self.tips.get(key, '')
            match = re.match(r'([\d,]+) contributions?\b', label)
            if label.startswith('No contributions'):
                count = 0
            elif match:
                count = int(match.group(1).replace(',', ''))
            else:
                raise ValueError('Contribution count missing for ' + item['date'])
            if not 0 <= item['level'] <= 4:
                raise ValueError('Unexpected contribution level')
            result.append({**item, 'count': count})
        result.sort(key=lambda item: item['date'])
        if len(result) < 300:
            raise ValueError('Incomplete contribution calendar')
        for previous, current in zip(result, result[1:]):
            if date.fromisoformat(current['date']) - date.fromisoformat(previous['date']) != timedelta(days=1):
                raise ValueError('Contribution calendar is not continuous')
        return result


def download(url):
    request = Request(url, headers={'User-Agent': 'GitHub-Profile-Widgets', 'Accept-Language': 'en-US'})
    with urlopen(request, timeout=25) as response:
        return response.read()


def write_svg(path, content):
    if isinstance(content, str):
        content = content.encode('utf-8')
    root = ET.fromstring(content)
    if root.tag != '{http://www.w3.org/2000/svg}svg':
        raise ValueError('Expected an SVG document')
    if any(element.tag.endswith('script') for element in root.iter()):
        raise ValueError('Unexpected script in SVG')
    temporary = path.with_suffix('.tmp')
    temporary.write_bytes(content)
    temporary.replace(path)


def activity_svg(days, username):
    days = days[-31:]
    width, height = 1000, 340
    left, right, top, bottom = 60, 28, 86, 72
    plot_w, plot_h = width-left-right, height-top-bottom
    maximum = max(1, max(item['count'] for item in days))
    step = max(1, math.ceil(maximum/4))
    maximum = step*4
    points = [(left+i*plot_w/(len(days)-1), top+plot_h*(1-item['count']/maximum)) for i, item in enumerate(days)]
    parts = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width} {height}" role="img" aria-labelledby="title desc">',
        f'<title id="title">{escape(username)} contribution activity</title>',
        f'<desc id="desc">Public GitHub calendar from {days[0]["date"]} to {days[-1]["date"]}. {sum(item["count"] for item in days)} contributions.</desc>',
        '<rect width="1000" height="340" rx="12" fill="#0D1117"/>',
        '<g font-family="DejaVu Sans,Arial,sans-serif">',
        '<text x="500" y="34" text-anchor="middle" fill="#A78BFA" font-size="21" font-weight="600">Contribution Activity</text>',
        f'<text x="500" y="58" text-anchor="middle" fill="#94A3B8" font-size="12">{days[0]["date"]} to {days[-1]["date"]} · public GitHub calendar</text>']
    for tick in range(5):
        value = step*tick
        y = top+plot_h*(1-value/maximum)
        parts += [f'<path d="M{left},{y:.2f}H{width-right}" stroke="#25263D" stroke-width="1"/>',
            f'<text x="{left-14}" y="{y+4:.2f}" text-anchor="end" fill="#94A3B8" font-size="12">{value}</text>']
    coords = ' '.join(f'{x:.2f},{y:.2f}' for x,y in points)
    parts += [f'<polygon points="{left},{top+plot_h} {coords} {width-right},{top+plot_h}" fill="#6D28D9" opacity="0.22"/>',
        f'<polyline points="{coords}" stroke="#818CF8" stroke-width="3" fill="none" stroke-linejoin="round"/>']
    for item,(x,y) in zip(days,points):
        parts.append(f'<circle cx="{x:.2f}" cy="{y:.2f}" r="3.5" fill="#C4B5FD"><title>{item["date"]}: {item["count"]} contributions</title></circle>')
    for i in list(range(0,len(days),5)):
        x,_ = points[i]
        day=date.fromisoformat(days[i]['date'])
        label=day.strftime('%b %d')
        parts.append(f'<text x="{x:.2f}" y="{top+plot_h+27}" text-anchor="middle" fill="#94A3B8" font-size="12">{label}</text>')
    parts += ['<text x="500" y="321" text-anchor="middle" fill="#64748B" font-size="11">Source: github.com/'+escape(username)+'</text></g></svg>']
    return ''.join(parts)


def snake_svg(days, dark):
    palette = ['#161B22','#312E81','#4F46E5','#7C3AED','#A78BFA'] if dark else ['#EDE9FE','#DDD6FE','#C4B5FD','#8B5CF6','#6D28D9']
    ink = '#C4B5FD' if dark else '#7C3AED'
    start=date.fromisoformat(days[0]['date'])
    offset=(start.weekday()+1)%7
    columns=math.ceil((len(days)+offset)/7)
    step, pad = 16, 14
    width=columns*step+2*pad
    cells={}
    parts=[f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width} 154" role="img" aria-labelledby="title desc">',
        '<title id="title">GitHub contribution snake</title>',
        f'<desc id="desc">Contribution calendar from {days[0]["date"]} to {days[-1]["date"]}. The snake follows each calendar cell.</desc>']
    for i,item in enumerate(days):
        col,row=divmod(i+offset,7)
        cells[(col,row)]=item
    route=[(col,row) for col in range(columns) for row in (range(7) if col%2==0 else range(6,-1,-1)) if (col,row) in cells]
    for index,(col,row) in enumerate(route):
        item=cells[(col,row)]
        x,y=pad+col*step,pad+row*step
        fraction=min(.965,index/max(1,len(route)-1)*.96)
        parts.append(f'<rect x="{x}" y="{y}" width="11" height="11" rx="2" fill="{palette[item["level"]]}"><title>{item["date"]}: {item["count"]} contributions</title>')
        if item['count']:
            parts.append(f'<animate attributeName="opacity" values="1;1;0.18;0.18;1" keyTimes="0;{fraction:.4f};{fraction+.003:.4f};0.98;1" dur="42s" repeatCount="indefinite"/>')
        parts.append('</rect>')
    coords=[(pad+col*step+5.5,pad+row*step+5.5) for col,row in route]
    path='M'+' L'.join(f'{x},{y}' for x,y in coords)
    length=sum(math.hypot(x2-x1,y2-y1) for (x1,y1),(x2,y2) in zip(coords,coords[1:]))
    parts.append(f'<path d="{path}" fill="none" stroke="{ink}" stroke-width="9" stroke-linecap="round" stroke-linejoin="round" stroke-dasharray="55 {length+55:.1f}"><animate attributeName="stroke-dashoffset" from="55" to="{-length:.1f}" dur="42s" repeatCount="indefinite"/></path>')
    parts.append(f'<text x="{width/2:.1f}" y="146" text-anchor="middle" fill="{ink}" font-family="DejaVu Sans,Arial,sans-serif" font-size="11">Public contributions · {days[0]["date"]} to {days[-1]["date"]}</text></svg>')
    return ''.join(parts)


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--username',default='eumatheussantiago')
    parser.add_argument('--output',default='assets')
    parser.add_argument('--source-html')
    parser.add_argument('--bootstrap-snake',action='store_true')
    parser.add_argument('--prefer-service',action='store_true')
    args=parser.parse_args()
    if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9-]{0,38}',args.username):
        raise ValueError('Invalid GitHub username')
    raw=Path(args.source_html).read_bytes() if args.source_html else download(f'https://github.com/users/{args.username}/contributions')
    calendar=CalendarParser()
    calendar.feed(raw.decode('utf-8'))
    days=calendar.days()
    output=Path(args.output)
    output.mkdir(parents=True,exist_ok=True)
    rendered=None
    if args.prefer_service:
        query=urlencode({'username':args.username,'bg_color':'0D1117','color':'A78BFA','line':'818CF8','point':'C4B5FD','area':'true','area_color':'6D28D9','hide_border':'true','radius':12})
        try:
            candidate=download('https://github-readme-activity-graph.vercel.app/graph?'+query)
            root=ET.fromstring(candidate)
            text=' '.join(root.itertext()).lower()
            if any(term in text for term in ['error','rate limit',"can't fetch"]):
                raise ValueError('Activity service returned an error card')
            if not any('ct-line' in element.attrib.get('class','') for element in root.iter()):
                raise ValueError('Activity service did not return a graph')
            rendered=candidate
        except Exception as error:
            print(f'Using public-calendar fallback: {type(error).__name__}')
    write_svg(output/'activity.svg',rendered if rendered is not None else activity_svg(days,args.username))
    if args.bootstrap_snake:
        write_svg(output/'github-snake.svg',snake_svg(days,False))
        write_svg(output/'github-snake-dark.svg',snake_svg(days,True))
    print(f'Validated {len(days)} calendar days through {days[-1]["date"]}; {sum(item["count"] for item in days[-31:])} contributions in the last 31 days.')


if __name__=='__main__':
    main()
