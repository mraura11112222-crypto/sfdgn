"""
=============================================================
  MATEMATIK O'YIN BACKEND  — bitta main.py
  FastAPI + PostgreSQL (Neon) + SQLAlchemy (async)

  O'rnatish:
    pip install fastapi uvicorn sqlalchemy asyncpg psycopg2-binary

  Ishga tushirish:
    python main.py

  DB: Neon PostgreSQL (SSL + channel_binding)
=============================================================

ENDPOINTLAR:
  GET  /                         — API ma'lumoti
  POST /game/start               — yangi o'yin sessiyasi
  GET  /game/{session_id}        — sessiya holati
  POST /game/{session_id}/answer — javob yuborish
  GET  /game/{session_id}/hint   — maslahat olish
  POST /game/{session_id}/skip   — savolni o'tkazib yuborish
  GET  /game/{session_id}/history— savol tarixi
  DELETE /game/{session_id}      — sessiyani tugatish
  GET  /leaderboard              — eng yaxshi natijalar
  POST /leaderboard              — natijani saqlash
  GET  /stats                    — umumiy statistika
  GET  /question/random          — bitta tasodifiy savol
=============================================================
"""

import random, math, uuid, time, json
from datetime import datetime
from typing import Optional, Literal
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Depends
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from sqlalchemy import (
    text, Column, String, Integer, Float, Boolean,
    DateTime, JSON, create_engine
)
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, Session

import uvicorn

# ─────────────────────────────────────────────
#  DATABASE ULANISH
# ─────────────────────────────────────────────
DATABASE_URL = (
    "postgresql://neondb_owner:npg_VDSncpbaeN16"
    "@ep-noisy-dream-aqm9uc86-pooler.c-8.us-east-1.aws.neon.tech"
    "/neondb?sslmode=require&channel_binding=require"
)

engine = create_engine(
    DATABASE_URL,
    connect_args={"sslmode": "require"},
    pool_pre_ping=True,
    pool_size=5,
    max_overflow=10,
)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)
Base = declarative_base()


# ─────────────────────────────────────────────
#  DB MODELLARI (JADVALLAR)
# ─────────────────────────────────────────────
class GameSession(Base):
    __tablename__ = "game_sessions"

    session_id        = Column(String, primary_key=True)
    player_name       = Column(String, nullable=False)
    game_type         = Column(String, nullable=False)
    difficulty        = Column(String, nullable=False)
    total_questions   = Column(Integer, nullable=False)
    time_limit        = Column(Integer, nullable=True)
    started_at        = Column(Float, nullable=False)
    current_q_started = Column(Float, nullable=False)
    current_index     = Column(Integer, default=1)
    score             = Column(Integer, default=0)
    correct           = Column(Integer, default=0)
    incorrect         = Column(Integer, default=0)
    skipped           = Column(Integer, default=0)
    hint_used         = Column(Boolean, default=False)
    status            = Column(String, default="active")   # active | finished
    current_question  = Column(JSON, nullable=True)        # joriy savol JSON


class QuestionHistory(Base):
    __tablename__ = "question_history"

    id           = Column(Integer, primary_key=True, autoincrement=True)
    session_id   = Column(String, nullable=False, index=True)
    question     = Column(String, nullable=False)
    your_answer  = Column(Float, nullable=True)
    correct_ans  = Column(Float, nullable=False)
    is_correct   = Column(Boolean, nullable=False)
    points       = Column(Integer, default=0)
    time_taken   = Column(Float, default=0)
    hint_used    = Column(Boolean, default=False)
    skipped      = Column(Boolean, default=False)
    created_at   = Column(DateTime, default=datetime.utcnow)


class Leaderboard(Base):
    __tablename__ = "leaderboard"

    id          = Column(Integer, primary_key=True, autoincrement=True)
    player_name = Column(String, nullable=False)
    score       = Column(Integer, nullable=False)
    correct     = Column(Integer, nullable=False)
    total       = Column(Integer, nullable=False)
    accuracy    = Column(Float, nullable=False)
    difficulty  = Column(String, nullable=False)
    game_type   = Column(String, nullable=False)
    created_at  = Column(DateTime, default=datetime.utcnow)


class GlobalStats(Base):
    __tablename__ = "global_stats"

    id                       = Column(Integer, primary_key=True, default=1)
    total_games              = Column(Integer, default=0)
    total_questions_answered = Column(Integer, default=0)
    total_correct            = Column(Integer, default=0)
    total_incorrect          = Column(Integer, default=0)


# ─────────────────────────────────────────────
#  DB TAYYORLASH — BARCHA JADVALLARNI O'CHIRIB QAYTA YARATISH
# ─────────────────────────────────────────────
def init_db():
    print("⚡ Barcha jadvallar o'chirilmoqda...")
    Base.metadata.drop_all(bind=engine)
    print("✅ O'chirildi. Yangi jadvallar yaratilmoqda...")
    Base.metadata.create_all(bind=engine)

    # global_stats boshlang'ich qatori
    with SessionLocal() as db:
        stats = db.query(GlobalStats).filter_by(id=1).first()
        if not stats:
            db.add(GlobalStats(id=1))
            db.commit()
    print("✅ DB tayyor!")


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


# ─────────────────────────────────────────────
#  APP
# ─────────────────────────────────────────────
@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    yield

app = FastAPI(
    title="Matematik O'yin API",
    description="FastAPI + Neon PostgreSQL",
    version="2.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


# ─────────────────────────────────────────────
#  PYDANTIC MODELLARI
# ─────────────────────────────────────────────
class StartGameRequest(BaseModel):
    player_name: str = "O'yinchi"
    game_type: Literal["arithmetic", "algebra", "geometry", "sequence", "fraction", "mixed"] = "mixed"
    difficulty: Literal["easy", "medium", "hard", "extreme"] = "medium"
    total_questions: int = 10
    time_limit_seconds: Optional[int] = None


class AnswerRequest(BaseModel):
    answer: float


class LeaderboardEntry(BaseModel):
    player_name: str
    score: int
    correct: int
    total: int
    difficulty: str
    game_type: str


# ─────────────────────────────────────────────
#  SAVOL GENERATORLARI
# ─────────────────────────────────────────────
def _rng(difficulty: str) -> tuple:
    return {"easy": (1,10), "medium": (1,50), "hard": (1,200), "extreme": (1,1000)}.get(difficulty, (1,50))


def gen_arithmetic(difficulty: str) -> dict:
    lo, hi = _rng(difficulty)
    op = random.choice(["+", "-", "*", "/"])
    a = random.randint(lo, hi)
    b = random.randint(lo, hi)
    if op == "/":
        b = random.randint(1, max(1, hi // 2))
        a = b * random.randint(1, max(1, hi // b))
        answer = a / b
    elif op == "*" and difficulty in ("easy", "medium"):
        a = random.randint(lo, min(hi, 20))
        b = random.randint(lo, min(hi, 20))
        answer = a * b
    else:
        answer = a+b if op=="+" else a-b if op=="-" else a*b
    op_name = {"+":'qoshish', "-":'ayirish', "*":'kopaytirish', "/":'bolish'}[op]
    return {
        "type": "arithmetic",
        "question": f"{a} {op} {b} = ?",
        "answer": round(answer, 4),
        "hints": [f"Birinchi son: {a}", f"Ikkinchi son: {b}", f"Amal: {op_name}"],
        "explanation": f"{a} {op} {b} = {round(answer,4)}",
    }


def gen_algebra(difficulty: str) -> dict:
    lo, hi = _rng(difficulty)
    a = random.randint(1, max(2, hi // 5))
    b = random.randint(-hi, hi)
    x = random.randint(lo, hi)
    c = a * x + b
    q = f"{a}x + {b} = {c}   (x = ?)" if b >= 0 else f"{a}x - {abs(b)} = {c}   (x = ?)"
    return {
        "type": "algebra",
        "question": q,
        "answer": float(x),
        "hints": [f"{a}x = {c} - ({b}) = {c-b}", f"x = {c-b} / {a}"],
        "explanation": f"{a}*{x} + {b} = {c}",
    }


def gen_geometry(difficulty: str) -> dict:
    lo, hi = _rng(difficulty)
    shapes = ["kvadrat", "tortburchak", "uchburchak", "doira"]
    if difficulty in ("hard", "extreme"):
        shapes += ["trapeziya", "parallelogram"]
    shape = random.choice(shapes)
    task  = random.choice(["yuza", "perimetr"])

    if shape == "kvadrat":
        a = random.randint(lo, hi)
        if task == "yuza":
            return {"type":"geometry","question":f"Tomoni {a} bo'lgan kvadratning yuzasi?","answer":float(a*a),"hints":[f"a={a}","S = a*a"],"explanation":f"S = {a}*{a} = {a*a}"}
        else:
            return {"type":"geometry","question":f"Tomoni {a} bo'lgan kvadratning perimetri?","answer":float(4*a),"hints":[f"a={a}","P = 4*a"],"explanation":f"P = 4*{a} = {4*a}"}
    elif shape == "tortburchak":
        a,b = random.randint(lo,hi), random.randint(lo,hi)
        if task == "yuza":
            return {"type":"geometry","question":f"Tomonlari {a} va {b} bo'lgan to'rtburchak yuzasi?","answer":float(a*b),"hints":[f"a={a},b={b}","S=a*b"],"explanation":f"S={a}*{b}={a*b}"}
        else:
            return {"type":"geometry","question":f"Tomonlari {a} va {b} bo'lgan to'rtburchak perimetri?","answer":float(2*(a+b)),"hints":[f"a={a},b={b}","P=2(a+b)"],"explanation":f"P=2*({a}+{b})={2*(a+b)}"}
    elif shape == "uchburchak":
        a = random.randint(lo,hi)
        if task == "yuza":
            h = random.randint(lo,hi)
            ans = round(0.5*a*h, 2)
            return {"type":"geometry","question":f"Asosi {a}, balandligi {h} uchburchak yuzasi?","answer":ans,"hints":[f"a={a},h={h}","S=0.5*a*h"],"explanation":f"S=0.5*{a}*{h}={ans}"}
        else:
            b,c = random.randint(lo,hi), random.randint(lo,hi)
            return {"type":"geometry","question":f"Tomonlari {a},{b},{c} uchburchak perimetri?","answer":float(a+b+c),"hints":[f"a={a},b={b},c={c}","P=a+b+c"],"explanation":f"P={a}+{b}+{c}={a+b+c}"}
    elif shape == "doira":
        r = random.randint(lo, max(lo, hi//3))
        if task == "yuza":
            ans = round(math.pi*r*r, 4)
            return {"type":"geometry","question":f"Radiusi {r} doira yuzasi? (pi=3.14159)","answer":ans,"hints":[f"r={r}","S=pi*r^2"],"explanation":f"S=pi*{r}^2={ans}"}
        else:
            ans = round(2*math.pi*r, 4)
            return {"type":"geometry","question":f"Radiusi {r} doira aylanasi?","answer":ans,"hints":[f"r={r}","C=2*pi*r"],"explanation":f"C=2*pi*{r}={ans}"}
    elif shape == "trapeziya":
        a,b,h = random.randint(lo,hi),random.randint(lo,hi),random.randint(lo,hi)
        ans = round(0.5*(a+b)*h, 2)
        return {"type":"geometry","question":f"Asoslari {a},{b}, balandligi {h} trapeziya yuzasi?","answer":ans,"hints":[f"a={a},b={b},h={h}","S=(a+b)/2*h"],"explanation":f"S=({a}+{b})/2*{h}={ans}"}
    else:
        a,h = random.randint(lo,hi),random.randint(lo,hi)
        return {"type":"geometry","question":f"Asosi {a}, balandligi {h} parallelogramm yuzasi?","answer":float(a*h),"hints":[f"a={a},h={h}","S=a*h"],"explanation":f"S={a}*{h}={a*h}"}


def gen_sequence(difficulty: str) -> dict:
    lo, hi = _rng(difficulty)
    t = random.choice(["arith","geo","squares","fib"])
    if t == "arith":
        s,step,n = random.randint(lo,hi),random.randint(1,max(1,hi//10)),random.randint(4,7)
        seq = [s+i*step for i in range(n)]
        return {"type":"sequence","question":f"Keyingi son: {', '.join(map(str,seq))}, ?","answer":float(s+n*step),"hints":[f"Farq: {step}"],"explanation":f"Arifmetik ketma-ketlik, d={step}"}
    elif t == "geo":
        s,r,n = random.randint(1,max(1,hi//20)),random.randint(2,4),random.randint(4,6)
        seq = [s*(r**i) for i in range(n)]
        return {"type":"sequence","question":f"Keyingi son: {', '.join(map(str,seq))}, ?","answer":float(s*(r**n)),"hints":[f"Nisbat: {r}"],"explanation":f"Geometrik ketma-ketlik, q={r}"}
    elif t == "squares":
        s = random.randint(1,5)
        seq = [(s+i)**2 for i in range(5)]
        return {"type":"sequence","question":f"Keyingi son: {', '.join(map(str,seq))}, ?","answer":float((s+5)**2),"hints":["Kvadratlar ketma-ketligi"],"explanation":f"n^2 ketma-ketligi"}
    else:
        a,b = random.randint(1,5),random.randint(1,5)
        seq = [a,b]
        for _ in range(4): seq.append(seq[-1]+seq[-2])
        return {"type":"sequence","question":f"Keyingi son: {', '.join(map(str,seq))}, ?","answer":float(seq[-1]+seq[-2]),"hints":["Har bir son = oldingi ikkitasining yig'indisi"],"explanation":"Fibonachchi tipidagi ketma-ketlik"}


def gen_fraction(difficulty: str) -> dict:
    lo, hi = _rng(difficulty)
    op = random.choice(["+","-","*","/"])
    d1,d2 = random.randint(2,min(hi,10)),random.randint(2,min(hi,10))
    n1,n2 = random.randint(1,d1-1),random.randint(1,d2-1)
    f1,f2 = n1/d1, n2/d2
    if op=="+" : ans=round(f1+f2,6); q=f"{n1}/{d1} + {n2}/{d2} = ?"
    elif op=="-":
        if f1<f2: n1,d1,n2,d2,f1,f2=n2,d2,n1,d1,f2,f1
        ans=round(f1-f2,6); q=f"{n1}/{d1} - {n2}/{d2} = ?"
    elif op=="*": ans=round(f1*f2,6); q=f"{n1}/{d1} x {n2}/{d2} = ?"
    else: ans=round(f1/f2,6); q=f"{n1}/{d1} / {n2}/{d2} = ?"
    return {"type":"fraction","question":q,"answer":ans,"hints":[f"{n1}/{d1}={round(f1,4)}",f"{n2}/{d2}={round(f2,4)}"],"explanation":f"Javob: {ans}"}


GENERATORS = {"arithmetic":gen_arithmetic,"algebra":gen_algebra,"geometry":gen_geometry,"sequence":gen_sequence,"fraction":gen_fraction}


def generate_question(game_type: str, difficulty: str) -> dict:
    fn = random.choice(list(GENERATORS.values())) if game_type == "mixed" else GENERATORS[game_type]
    q = fn(difficulty)
    q["question_id"] = str(uuid.uuid4())[:8]
    return q


# ─────────────────────────────────────────────
#  BALL TIZIMI
# ─────────────────────────────────────────────
DIFF_MULT = {"easy":1,"medium":2,"hard":4,"extreme":8}

def calc_score(difficulty: str, time_taken: float, hint_used: bool) -> int:
    mult  = DIFF_MULT.get(difficulty, 1)
    speed = max(0, 1 - time_taken/60)
    hint  = 0.5 if hint_used else 1.0
    return max(10, int(100 * mult * (0.5 + 0.5*speed) * hint))


# ─────────────────────────────────────────────
#  ENDPOINTLAR
# ─────────────────────────────────────────────

@app.get("/", tags=["Umumiy"])
def root():
    return {
        "title": "Matematik O'yin API v2 (PostgreSQL)",
        "version": "2.0.0",
        "game_types": list(GENERATORS.keys()) + ["mixed"],
        "difficulties": ["easy","medium","hard","extreme"],
        "docs": "/docs",
    }


# ── O'YIN BOSHLASH ─────────────────────────────
@app.post("/game/start", tags=["O'yin"])
def start_game(req: StartGameRequest, db: Session = Depends(get_db)):
    if not 1 <= req.total_questions <= 100:
        raise HTTPException(400, "total_questions 1–100 bo'lishi kerak")

    session_id = str(uuid.uuid4())
    first_q    = generate_question(req.game_type, req.difficulty)
    now        = time.time()

    session = GameSession(
        session_id        = session_id,
        player_name       = req.player_name,
        game_type         = req.game_type,
        difficulty        = req.difficulty,
        total_questions   = req.total_questions,
        time_limit        = req.time_limit_seconds,
        started_at        = now,
        current_q_started = now,
        current_index     = 1,
        score             = 0,
        correct           = 0,
        incorrect         = 0,
        skipped           = 0,
        hint_used         = False,
        status            = "active",
        current_question  = first_q,
    )
    db.add(session)

    stats = db.query(GlobalStats).filter_by(id=1).first()
    if stats:
        stats.total_games += 1
    db.commit()

    return {
        "session_id":      session_id,
        "player_name":     req.player_name,
        "difficulty":      req.difficulty,
        "game_type":       req.game_type,
        "total_questions": req.total_questions,
        "question_number": 1,
        "question":        first_q["question"],
        "question_type":   first_q["type"],
        "time_limit":      req.time_limit_seconds,
    }


# ── SESSIYA HOLATI ─────────────────────────────
@app.get("/game/{session_id}", tags=["O'yin"])
def get_session(session_id: str, db: Session = Depends(get_db)):
    s = db.query(GameSession).filter_by(session_id=session_id).first()
    if not s:
        raise HTTPException(404, "Sessiya topilmadi")

    elapsed   = time.time() - s.started_at
    remaining = None
    if s.time_limit:
        remaining = max(0, s.time_limit - elapsed)
        if remaining == 0 and s.status == "active":
            s.status = "finished"
            db.commit()

    return {
        "session_id":      session_id,
        "player_name":     s.player_name,
        "status":          s.status,
        "score":           s.score,
        "correct":         s.correct,
        "incorrect":       s.incorrect,
        "skipped":         s.skipped,
        "question_number": s.current_index,
        "total_questions": s.total_questions,
        "current_question": s.current_question["question"] if s.status=="active" and s.current_question else None,
        "elapsed_seconds": round(elapsed, 1),
        "time_remaining":  round(remaining, 1) if remaining is not None else None,
        "accuracy":        round(s.correct / max(1, s.correct+s.incorrect) * 100, 1),
    }


# ── JAVOB YUBORISH ─────────────────────────────
@app.post("/game/{session_id}/answer", tags=["O'yin"])
def submit_answer(session_id: str, req: AnswerRequest, db: Session = Depends(get_db)):
    s = db.query(GameSession).filter_by(session_id=session_id).first()
    if not s:
        raise HTTPException(404, "Sessiya topilmadi")
    if s.status != "active":
        raise HTTPException(400, "O'yin tugagan")

    if s.time_limit and time.time() - s.started_at > s.time_limit:
        s.status = "finished"
        db.commit()
        raise HTTPException(400, "Vaqt tugadi!")

    q           = s.current_question
    correct_ans = q["answer"]
    time_taken  = time.time() - s.current_q_started
    tolerance   = max(0.01, abs(correct_ans) * 0.001)
    is_correct  = abs(req.answer - correct_ans) <= tolerance

    if is_correct:
        pts = calc_score(s.difficulty, time_taken, s.hint_used)
        s.score   += pts
        s.correct += 1
        msg = f"To'g'ri! +{pts} ball"
    else:
        pts = 0
        s.incorrect += 1
        msg = f"Noto'g'ri. To'g'ri javob: {correct_ans}"

    # tarix
    hist = QuestionHistory(
        session_id  = session_id,
        question    = q["question"],
        your_answer = req.answer,
        correct_ans = correct_ans,
        is_correct  = is_correct,
        points      = pts,
        time_taken  = round(time_taken, 2),
        hint_used   = s.hint_used,
        skipped     = False,
    )
    db.add(hist)

    # global stats
    stats = db.query(GlobalStats).filter_by(id=1).first()
    if stats:
        stats.total_questions_answered += 1
        if is_correct: stats.total_correct   += 1
        else:          stats.total_incorrect += 1

    # o'yin tugadimi?
    if s.current_index >= s.total_questions:
        s.status = "finished"
        db.commit()
        return {
            "result": "correct" if is_correct else "incorrect",
            "message": msg, "explanation": q["explanation"],
            "points_earned": pts, "total_score": s.score,
            "game_over": True, "final_score": s.score,
            "correct": s.correct, "total": s.total_questions,
            "accuracy": round(s.correct / s.total_questions * 100, 1),
        }

    s.current_index   += 1
    s.hint_used        = False
    s.current_q_started = time.time()
    next_q = generate_question(s.game_type, s.difficulty)
    s.current_question = next_q
    db.commit()

    return {
        "result": "correct" if is_correct else "incorrect",
        "message": msg, "explanation": q["explanation"],
        "points_earned": pts, "total_score": s.score,
        "game_over": False,
        "next_question": next_q["question"],
        "next_question_type": next_q["type"],
        "question_number": s.current_index,
    }


# ── MASLAHAT ──────────────────────────────────
@app.get("/game/{session_id}/hint", tags=["O'yin"])
def get_hint(session_id: str, db: Session = Depends(get_db)):
    s = db.query(GameSession).filter_by(session_id=session_id).first()
    if not s: raise HTTPException(404, "Sessiya topilmadi")
    if s.status != "active": raise HTTPException(400, "O'yin tugagan")
    s.hint_used = True
    db.commit()
    return {"hints": s.current_question.get("hints",[]), "warning": "Maslahat uchun ball x0.5"}


# ── SAVOLNI O'TKAZIB YUBORISH ─────────────────
@app.post("/game/{session_id}/skip", tags=["O'yin"])
def skip_question(session_id: str, db: Session = Depends(get_db)):
    s = db.query(GameSession).filter_by(session_id=session_id).first()
    if not s: raise HTTPException(404, "Sessiya topilmadi")
    if s.status != "active": raise HTTPException(400, "O'yin tugagan")

    q = s.current_question
    s.skipped += 1
    db.add(QuestionHistory(
        session_id=session_id, question=q["question"],
        your_answer=None, correct_ans=q["answer"],
        is_correct=False, points=0, time_taken=0,
        hint_used=False, skipped=True,
    ))

    if s.current_index >= s.total_questions:
        s.status = "finished"
        db.commit()
        return {"game_over": True, "final_score": s.score}

    s.current_index    += 1
    s.hint_used         = False
    s.current_q_started = time.time()
    next_q = generate_question(s.game_type, s.difficulty)
    s.current_question = next_q
    db.commit()

    return {
        "skipped": True,
        "correct_answer": q["answer"],
        "explanation": q["explanation"],
        "next_question": next_q["question"],
        "question_number": s.current_index,
    }


# ── TARIX ──────────────────────────────────────
@app.get("/game/{session_id}/history", tags=["O'yin"])
def get_history(session_id: str, db: Session = Depends(get_db)):
    s = db.query(GameSession).filter_by(session_id=session_id).first()
    if not s: raise HTTPException(404, "Sessiya topilmadi")
    rows = db.query(QuestionHistory).filter_by(session_id=session_id).all()
    history = [
        {"question":r.question,"your_answer":r.your_answer,"correct":r.correct_ans,
         "is_correct":r.is_correct,"points":r.points,"time_taken":r.time_taken,
         "hint_used":r.hint_used,"skipped":r.skipped}
        for r in rows
    ]
    return {"history": history, "total": len(history)}


# ── SESSIYANI TUGATISH ─────────────────────────
@app.delete("/game/{session_id}", tags=["O'yin"])
def end_session(session_id: str, db: Session = Depends(get_db)):
    s = db.query(GameSession).filter_by(session_id=session_id).first()
    if not s: raise HTTPException(404, "Sessiya topilmadi")
    score = s.score
    db.delete(s)
    db.commit()
    return {"message": "Sessiya tugatildi", "final_score": score}


# ── LEADERBOARD ────────────────────────────────
@app.get("/leaderboard", tags=["Leaderboard"])
def get_leaderboard(limit: int = 10, db: Session = Depends(get_db)):
    rows = db.query(Leaderboard).order_by(Leaderboard.score.desc()).limit(limit).all()
    data = [
        {"rank": i+1, "player_name":r.player_name, "score":r.score,
         "correct":r.correct, "total":r.total, "accuracy":r.accuracy,
         "difficulty":r.difficulty, "game_type":r.game_type,
         "date": r.created_at.strftime("%Y-%m-%d %H:%M") if r.created_at else ""}
        for i, r in enumerate(rows)
    ]
    total = db.query(Leaderboard).count()
    return {"leaderboard": data, "total_entries": total}


@app.post("/leaderboard", tags=["Leaderboard"])
def save_leaderboard(entry: LeaderboardEntry, db: Session = Depends(get_db)):
    record = Leaderboard(
        player_name = entry.player_name,
        score       = entry.score,
        correct     = entry.correct,
        total       = entry.total,
        accuracy    = round(entry.correct / max(1, entry.total) * 100, 1),
        difficulty  = entry.difficulty,
        game_type   = entry.game_type,
    )
    db.add(record)
    db.commit()
    db.refresh(record)
    rank = db.query(Leaderboard).filter(Leaderboard.score > entry.score).count() + 1
    return {"message": "Saqlandi!", "rank": rank, "id": record.id}


# ── STATISTIKA ─────────────────────────────────
@app.get("/stats", tags=["Statistika"])
def get_stats(db: Session = Depends(get_db)):
    s = db.query(GlobalStats).filter_by(id=1).first()
    if not s:
        return {"total_games":0,"total_questions_answered":0,"total_correct":0,"total_incorrect":0,"accuracy":0}
    total = s.total_questions_answered
    active = db.query(GameSession).filter_by(status="active").count()
    return {
        "total_games":              s.total_games,
        "total_questions_answered": total,
        "total_correct":            s.total_correct,
        "total_incorrect":          s.total_incorrect,
        "accuracy":                 round(s.total_correct / max(1, total) * 100, 1),
        "active_sessions":          active,
    }


# ── TASODIFIY SAVOL ────────────────────────────
@app.get("/question/random", tags=["Savol"])
def random_question(
    game_type: Literal["arithmetic","algebra","geometry","sequence","fraction","mixed"] = "mixed",
    difficulty: Literal["easy","medium","hard","extreme"] = "medium",
):
    q = generate_question(game_type, difficulty)
    return {"question":q["question"],"type":q["type"],"hints":q["hints"],"answer":q["answer"],"explanation":q["explanation"]}


# ─────────────────────────────────────────────
#  ISHGA TUSHIRISH
# ─────────────────────────────────────────────
if __name__ == "__main__":
    print("=" * 55)
    print("  Matematik O'yin Backend (PostgreSQL) ishga tushmoqda")
    print("  http://localhost:8000")
    print("  API hujjati: http://localhost:8000/docs")
    print("=" * 55)
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)