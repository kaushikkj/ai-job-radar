import re
from datetime import datetime,timezone
from .collectors.base import CollectedJob
def parse_alert(text):
 lines=[x.strip() for x in text.splitlines() if x.strip()]; out=[]
 for i,line in enumerate(lines):
  if not any(k in line.lower() for k in ['engineer','sre','devops','platform','cloud','reliability','database']):continue
  urls=re.findall(r'https?://\S+',line+' '+' '.join(lines[i:i+5]));
  if urls:out.append(CollectedJob(line,lines[i+2] if i+2<len(lines) else '',urls[0].rstrip(').,'),'LinkedIn job alert import', 'LinkedIn Alert',datetime.now(timezone.utc),'remote' in (lines[i+2] if i+2<len(lines) else '').lower()))
 return out[:100]
