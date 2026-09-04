from datetime import datetime,timezone
from sqlalchemy import Boolean,DateTime,Float,Integer,String,Text,UniqueConstraint
from sqlalchemy.orm import Mapped,mapped_column
from .db import Base
def now(): return datetime.now(timezone.utc)
class Company(Base):
    __tablename__="companies"
    id:Mapped[int]=mapped_column(Integer,primary_key=True); name:Mapped[str]=mapped_column(String(200),unique=True,index=True); slug:Mapped[str]=mapped_column(String(200),unique=True,index=True)
    category:Mapped[str]=mapped_column(String(100),default="Technology"); priority:Mapped[int]=mapped_column(Integer,default=50); career_url:Mapped[str]=mapped_column(String(1000),default=""); source_type:Mapped[str]=mapped_column(String(50),default="generic"); adapter_config:Mapped[str]=mapped_column(Text,default="{}"); enabled:Mapped[bool]=mapped_column(Boolean,default=True); created_at:Mapped[datetime]=mapped_column(DateTime(timezone=True),default=now)
class Job(Base):
    __tablename__="jobs"; __table_args__=(UniqueConstraint("fingerprint",name="uq_job_fingerprint"),)
    id:Mapped[int]=mapped_column(Integer,primary_key=True); company_id:Mapped[int]=mapped_column(Integer,index=True); company_name:Mapped[str]=mapped_column(String(200),index=True); title:Mapped[str]=mapped_column(String(500),index=True); location:Mapped[str]=mapped_column(String(500),default=""); remote:Mapped[bool]=mapped_column(Boolean,default=False); source:Mapped[str]=mapped_column(String(100),default=""); url:Mapped[str]=mapped_column(String(2000),default=""); description:Mapped[str]=mapped_column(Text,default=""); posted_at:Mapped[datetime|None]=mapped_column(DateTime(timezone=True)); posted_at_source:Mapped[str]=mapped_column(String(120),default=""); first_seen_at:Mapped[datetime]=mapped_column(DateTime(timezone=True),default=now); last_seen_at:Mapped[datetime]=mapped_column(DateTime(timezone=True),default=now); fingerprint:Mapped[str]=mapped_column(String(64),index=True)
    score:Mapped[float]=mapped_column(Float,default=0); role_score:Mapped[float]=mapped_column(Float,default=0); technical_score:Mapped[float]=mapped_column(Float,default=0); experience_score:Mapped[float]=mapped_column(Float,default=0); location_score:Mapped[float]=mapped_column(Float,default=0); company_score:Mapped[float]=mapped_column(Float,default=0); industry_score:Mapped[float]=mapped_column(Float,default=0); match_reason:Mapped[str]=mapped_column(Text,default=""); ai_analysis:Mapped[str]=mapped_column(Text,default=""); status:Mapped[str]=mapped_column(String(50),default="new",index=True); saved:Mapped[bool]=mapped_column(Boolean,default=False); applied_at:Mapped[datetime|None]=mapped_column(DateTime(timezone=True)); created_at:Mapped[datetime]=mapped_column(DateTime(timezone=True),default=now); updated_at:Mapped[datetime]=mapped_column(DateTime(timezone=True),default=now,onupdate=now)


class Resume(Base):
    __tablename__="resumes"
    id:Mapped[int]=mapped_column(Integer,primary_key=True)
    name:Mapped[str]=mapped_column(String(300),index=True)
    filename:Mapped[str]=mapped_column(String(500),default="")
    mime_type:Mapped[str]=mapped_column(String(120),default="text/plain")
    content:Mapped[str]=mapped_column(Text,default="")
    is_default:Mapped[bool]=mapped_column(Boolean,default=False,index=True)
    coverage:Mapped[float]=mapped_column(Float,default=0)
    created_at:Mapped[datetime]=mapped_column(DateTime(timezone=True),default=now)
    updated_at:Mapped[datetime]=mapped_column(DateTime(timezone=True),default=now,onupdate=now)

class ResumeVersion(Base):
    __tablename__="resume_versions"
    id:Mapped[int]=mapped_column(Integer,primary_key=True)
    resume_id:Mapped[int]=mapped_column(Integer,index=True)
    label:Mapped[str]=mapped_column(String(300),default="Snapshot")
    content:Mapped[str]=mapped_column(Text,default="")
    source:Mapped[str]=mapped_column(String(80),default="manual")
    created_at:Mapped[datetime]=mapped_column(DateTime(timezone=True),default=now)


class AppSetting(Base):
    __tablename__="app_settings"
    key:Mapped[str]=mapped_column(String(120),primary_key=True)
    value:Mapped[str]=mapped_column(Text,default="")
    updated_at:Mapped[datetime]=mapped_column(DateTime(timezone=True),default=now,onupdate=now)
