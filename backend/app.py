import json
import os
from datetime import datetime, timedelta, timezone

import psycopg
from fastapi import Depends, FastAPI, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError, jwt
from passlib.context import CryptContext
from pydantic import BaseModel, Field
from psycopg.rows import dict_row

from rules import clean_foreign_names, judge

SECRET = os.environ.get("JWT_SECRET", "herb-process-dev-secret")
DSN = os.environ.get("DATABASE_URL", "postgresql://app:app@localhost:54393/herb")
pwd = CryptContext(schemes=["bcrypt"], deprecated="auto")
security = HTTPBearer(auto_error=False)
USERS = {
    "processor": {"role": "writer", "password_hash": pwd.hash("herb123456")},
    "checker": {"role": "reader", "password_hash": pwd.hash("check123456")},
}

# 初始异物词条：炮制员可在此基础上维护
SEED_FOREIGN_TERMS = ["草屑", "砂粒"]


def connect():
    return psycopg.connect(DSN, row_factory=dict_row)


class LoginIn(BaseModel):
    username: str
    password: str


class StepIn(BaseModel):
    name: str
    temp_c: float
    minutes: float


class BatchIn(BaseModel):
    herb: str = Field(min_length=1, max_length=80)
    steps: list[StepIn]
    # 开炒点名的异物词条原文；至少一项，且必须命中词条表，由业务校验
    foreign_names: list[str] = []


class TermIn(BaseModel):
    text: str = Field(min_length=1, max_length=40)


def current_user(credentials: HTTPAuthorizationCredentials | None = Depends(security)) -> dict:
    if credentials is None:
        raise HTTPException(status_code=401, detail="未登录")
    try:
        payload = jwt.decode(credentials.credentials, SECRET, algorithms=["HS256"])
    except JWTError as exc:
        raise HTTPException(status_code=401, detail="无效令牌") from exc
    if payload.get("sub") not in USERS:
        raise HTTPException(status_code=401, detail="无效令牌")
    return {"username": payload["sub"], "role": payload.get("role")}


def require_writer(user: dict = Depends(current_user)) -> dict:
    if user["role"] != "writer":
        raise HTTPException(status_code=403, detail="仅炮制员可写入记录")
    return user


app = FastAPI(title="饮片炮制记录台")


@app.on_event("startup")
def startup():
    with connect() as conn:
        conn.execute(
            """CREATE TABLE IF NOT EXISTS batches (
                id serial PRIMARY KEY,
                herb text NOT NULL,
                doc jsonb NOT NULL,
                verdict text NOT NULL,
                reason text NOT NULL,
                created_by text NOT NULL,
                created_at timestamptz NOT NULL
            )"""
        )
        conn.execute(
            """CREATE TABLE IF NOT EXISTS foreign_terms (
                id serial PRIMARY KEY,
                text text NOT NULL UNIQUE,
                created_by text NOT NULL,
                created_at timestamptz NOT NULL
            )"""
        )
        term_count = conn.execute("SELECT COUNT(*) AS n FROM foreign_terms").fetchone()["n"]
        if term_count == 0:
            now = datetime.now(timezone.utc)
            for text in SEED_FOREIGN_TERMS:
                conn.execute(
                    """INSERT INTO foreign_terms (text, created_by, created_at)
                       VALUES (%s, %s, %s)""",
                    (text, "processor", now),
                )
        count = conn.execute("SELECT COUNT(*) AS n FROM batches").fetchone()["n"]
        if count == 0:
            now = datetime.now(timezone.utc)
            samples = [
                ("甘草", {"steps": [{"name": "清炒", "temp_c": 120, "minutes": 12}], "foreign_names": ["草屑"]}),
                ("黄芩", {"steps": [{"name": "清炒", "temp_c": 40, "minutes": 12}], "foreign_names": ["砂粒"]}),
            ]
            for herb, doc in samples:
                verdict, reason = judge(doc)
                conn.execute(
                    """INSERT INTO batches (herb, doc, verdict, reason, created_by, created_at)
                       VALUES (%s, %s::jsonb, %s, %s, %s, %s)""",
                    (herb, json.dumps(doc, ensure_ascii=False), verdict, reason, "processor", now),
                )
        conn.commit()


@app.get("/api/health")
def health():
    return {"status": "ok", "service": "herb-process-record"}


@app.post("/api/auth/login")
def login(body: LoginIn):
    user = USERS.get(body.username.strip())
    if not user or not pwd.verify(body.password, user["password_hash"]):
        raise HTTPException(status_code=401, detail="用户名或密码错误")
    exp = datetime.now(timezone.utc) + timedelta(hours=8)
    token = jwt.encode({"sub": body.username.strip(), "role": user["role"], "exp": exp}, SECRET, algorithm="HS256")
    return {"access_token": token, "username": body.username.strip(), "role": user["role"]}


@app.get("/api/batches")
def list_batches(_user: dict = Depends(current_user)):
    with connect() as conn:
        rows = conn.execute("SELECT id, herb, doc, verdict, reason, created_by FROM batches ORDER BY id DESC").fetchall()
    return rows


@app.post("/api/batches", status_code=201)
def create_batch(body: BatchIn, user: dict = Depends(require_writer)):
    with connect() as conn:
        known_texts = {
            r["text"] for r in conn.execute("SELECT text FROM foreign_terms").fetchall()
        }
        try:
            # 零点名拒写；点名原文随即整包写入文书，事后改词条不影响已存点名
            foreign_names = clean_foreign_names(body.foreign_names, known_texts)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        doc = {
            "steps": [s.model_dump() for s in body.steps],
            "foreign_names": foreign_names,
        }
        verdict, reason = judge(doc)
        row = conn.execute(
            """INSERT INTO batches (herb, doc, verdict, reason, created_by, created_at)
               VALUES (%s, %s::jsonb, %s, %s, %s, %s)
               RETURNING id, herb, doc, verdict, reason, created_by""",
            (body.herb.strip(), json.dumps(doc, ensure_ascii=False), verdict, reason, user["username"], datetime.now(timezone.utc)),
        ).fetchone()
        conn.commit()
    return row


@app.get("/api/foreign-terms")
def list_terms(_user: dict = Depends(current_user)):
    # 质检员也能看词条
    with connect() as conn:
        rows = conn.execute(
            "SELECT id, text, created_by FROM foreign_terms ORDER BY id"
        ).fetchall()
    return rows


@app.post("/api/foreign-terms", status_code=201)
def add_term(body: TermIn, user: dict = Depends(require_writer)):
    # 仅炮制员可维护词条，质检员只读
    text = body.text.strip()
    if not text:
        raise HTTPException(status_code=400, detail="词条不能为空")
    with connect() as conn:
        exists = conn.execute(
            "SELECT 1 FROM foreign_terms WHERE text = %s", (text,)
        ).fetchone()
        if exists:
            raise HTTPException(status_code=409, detail="词条已存在")
        row = conn.execute(
            """INSERT INTO foreign_terms (text, created_by, created_at)
               VALUES (%s, %s, %s)
               RETURNING id, text, created_by""",
            (text, user["username"], datetime.now(timezone.utc)),
        ).fetchone()
        conn.commit()
    return row


@app.delete("/api/foreign-terms/{term_id}", status_code=204)
def delete_term(term_id: int, user: dict = Depends(require_writer)):
    with connect() as conn:
        cursor = conn.execute("DELETE FROM foreign_terms WHERE id = %s", (term_id,))
        conn.commit()
    if cursor.rowcount == 0:
        raise HTTPException(status_code=404, detail="词条不存在")
