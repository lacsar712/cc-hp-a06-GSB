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

from rules import judge

SECRET = os.environ.get("JWT_SECRET", "herb-process-dev-secret")
DSN = os.environ.get("DATABASE_URL", "postgresql://app:app@localhost:54393/herb")
pwd = CryptContext(schemes=["bcrypt"], deprecated="auto")
security = HTTPBearer(auto_error=False)
USERS = {
    "processor": {"role": "writer", "password_hash": pwd.hash("herb123456")},
    "checker": {"role": "reader", "password_hash": pwd.hash("check123456")},
}


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
    foreign_named: list[str] = Field(default_factory=list)


class TermIn(BaseModel):
    term: str = Field(min_length=1, max_length=40)


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
                term text NOT NULL UNIQUE,
                created_by text NOT NULL,
                created_at timestamptz NOT NULL
            )"""
        )
        term_count = conn.execute("SELECT COUNT(*) AS n FROM foreign_terms").fetchone()["n"]
        if term_count == 0:
            now = datetime.now(timezone.utc)
            for term in ["草屑", "砂粒"]:
                conn.execute(
                    "INSERT INTO foreign_terms (term, created_by, created_at) VALUES (%s, %s, %s)",
                    (term, "processor", now),
                )
        count = conn.execute("SELECT COUNT(*) AS n FROM batches").fetchone()["n"]
        if count == 0:
            now = datetime.now(timezone.utc)
            samples = [
                ("甘草", {"steps": [{"name": "清炒", "temp_c": 120, "minutes": 12}], "foreign_named": ["草屑"]}),
                ("黄芩", {"steps": [{"name": "清炒", "temp_c": 40, "minutes": 12}], "foreign_named": ["砂粒"]}),
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


@app.get("/api/terms")
def list_terms(_user: dict = Depends(current_user)):
    with connect() as conn:
        rows = conn.execute("SELECT id, term, created_by, created_at FROM foreign_terms ORDER BY id").fetchall()
    return rows


@app.post("/api/terms", status_code=201)
def create_term(body: TermIn, user: dict = Depends(require_writer)):
    term = body.term.strip()
    if not term:
        raise HTTPException(status_code=400, detail="词条不能为空")
    with connect() as conn:
        exists = conn.execute("SELECT 1 FROM foreign_terms WHERE term = %s", (term,)).fetchone()
        if exists:
            raise HTTPException(status_code=400, detail="词条已存在")
        row = conn.execute(
            """INSERT INTO foreign_terms (term, created_by, created_at)
               VALUES (%s, %s, %s) RETURNING id, term, created_by, created_at""",
            (term, user["username"], datetime.now(timezone.utc)),
        ).fetchone()
        conn.commit()
    return row


@app.put("/api/terms/{term_id}")
def update_term(term_id: int, body: TermIn, user: dict = Depends(require_writer)):
    term = body.term.strip()
    if not term:
        raise HTTPException(status_code=400, detail="词条不能为空")
    with connect() as conn:
        clash = conn.execute(
            "SELECT 1 FROM foreign_terms WHERE term = %s AND id <> %s", (term, term_id)
        ).fetchone()
        if clash:
            raise HTTPException(status_code=400, detail="词条已存在")
        row = conn.execute(
            "UPDATE foreign_terms SET term = %s WHERE id = %s RETURNING id, term, created_by, created_at",
            (term, term_id),
        ).fetchone()
        if row is None:
            raise HTTPException(status_code=404, detail="词条不存在")
        conn.commit()
    return row


@app.delete("/api/terms/{term_id}", status_code=204)
def delete_term(term_id: int, user: dict = Depends(require_writer)):
    with connect() as conn:
        row = conn.execute("DELETE FROM foreign_terms WHERE id = %s RETURNING id", (term_id,)).fetchone()
        if row is None:
            raise HTTPException(status_code=404, detail="词条不存在")
        conn.commit()


@app.post("/api/batches", status_code=201)
def create_batch(body: BatchIn, user: dict = Depends(require_writer)):
    named = list(dict.fromkeys(t.strip() for t in body.foreign_named if t.strip()))
    if not named:
        raise HTTPException(status_code=400, detail="零点名拒写：开炒至少点名一项异物词条")
    with connect() as conn:
        valid = {r["term"] for r in conn.execute("SELECT term FROM foreign_terms").fetchall()}
        unknown = [t for t in named if t not in valid]
        if unknown:
            raise HTTPException(status_code=400, detail=f"点名了词条表外的异物：{'、'.join(unknown)}")
        doc = {"steps": [s.model_dump() for s in body.steps], "foreign_named": named}
        verdict, reason = judge(doc)
        row = conn.execute(
            """INSERT INTO batches (herb, doc, verdict, reason, created_by, created_at)
               VALUES (%s, %s::jsonb, %s, %s, %s, %s)
               RETURNING id, herb, doc, verdict, reason, created_by""",
            (body.herb.strip(), json.dumps(doc, ensure_ascii=False), verdict, reason, user["username"], datetime.now(timezone.utc)),
        ).fetchone()
        conn.commit()
    return row
