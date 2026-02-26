import os
from sqlalchemy import create_engine, Column, Integer, String, Float, JSON
from sqlalchemy.orm import declarative_base, sessionmaker

# Bruk DATABASE_URL fra miljøvariabel, fall back til lokal Postgres
DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql://tharusan@localhost:5432/brokerdb",
)

engine = create_engine(DATABASE_URL, echo=True, future=True)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)
Base = declarative_base()


class Company(Base):
    __tablename__ = "companies"

    id = Column(Integer, primary_key=True, index=True)
    orgnr = Column(String(9), unique=True, index=True, nullable=False)
    navn = Column(String, index=True)
    organisasjonsform_kode = Column(String(10))
    kommune = Column(String(100))
    land = Column(String(50))
    naeringskode1 = Column(String(20))
    naeringskode1_beskrivelse = Column(String(255))

    regnskapsår = Column(Integer)
    sum_driftsinntekter = Column(Float)
    sum_egenkapital = Column(Float)
    sum_eiendeler = Column(Float)
    equity_ratio = Column(Float)
    risk_score = Column(Integer)

    regnskap_raw = Column(JSON)
    pep_raw = Column(JSON)


def init_db():
    Base.metadata.create_all(bind=engine)
