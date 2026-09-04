import json
from .config import settings
def analyze_job(title,company,location,description,score):
 if not settings.openai_api_key:return None
 try:
  from openai import OpenAI
  c=OpenAI(api_key=settings.openai_api_key)
  prompt=f'''Analyze this job for a software/SRE engineer with 5.6 years experience. Target Senior SRE, DevOps, Platform, Cloud, Backend/Infrastructure and DBRE roles. Skills: Python, FastAPI, AWS, GCP, Azure, Kubernetes, Docker, Terraform, ArgoCD, GitOps, CI/CD, Prometheus, Grafana, Datadog, databases, Kafka, REST, automation. Return ONLY JSON: fit_score 0-100, verdict APPLY/CONSIDER/SKIP, strengths array, gaps array, why_apply string. Company: {company}\nTitle: {title}\nLocation: {location}\nInitial score: {score}\nJD: {description[:12000]}'''
  r=c.responses.create(model=settings.openai_model,input=prompt); return json.dumps(json.loads(r.output_text))
 except Exception as e:
  message = str(e)
  if "401" in message or "invalid_api_key" in message or "Incorrect API key" in message:
   return json.dumps({"status":"unavailable","message":"AI analysis unavailable. Add a valid OPENAI_API_KEY in .env and restart the backend."})
  return json.dumps({"status":"unavailable","message":"AI analysis unavailable right now. The job match score is still available."})
