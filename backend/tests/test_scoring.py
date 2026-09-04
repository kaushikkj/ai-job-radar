from app.scoring import score_job
def test_good_match():
 s=score_job('Senior Site Reliability Engineer','Hyderabad, India','Kubernetes Terraform AWS Python Prometheus Grafana incident management',100,'Technology')
 assert s.total>=80 and s.location==15
def test_bad_match():
 assert score_job('Marketing Manager','Mumbai, India','Brand campaigns and social media',20,'Retail').total<70
