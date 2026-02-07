import os
import random
import time
import uuid
from datetime import datetime
from threading import Lock

from flask import Blueprint, Flask, jsonify, redirect, render_template, request, session, url_for
from sqlalchemy import Column, DateTime, Integer, String, create_engine
from sqlalchemy.orm import declarative_base, scoped_session, sessionmaker
from werkzeug.security import check_password_hash, generate_password_hash

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "balloono-dev-secret")
RAW_URL_PREFIX = os.environ.get("URL_PREFIX", "/balloono")
URL_PREFIX = RAW_URL_PREFIX.rstrip("/")
if URL_PREFIX and not URL_PREFIX.startswith("/"):
    URL_PREFIX = f"/{URL_PREFIX}"
BLUEPRINT_PREFIX = URL_PREFIX
main_bp = Blueprint("main", __name__, url_prefix=BLUEPRINT_PREFIX)

DATABASE_URL = os.environ.get("DATABASE_URL", "sqlite:///balloono.db")
engine_kwargs = {}
if DATABASE_URL.startswith("sqlite"):
    engine_kwargs["connect_args"] = {"check_same_thread": False}
engine = create_engine(DATABASE_URL, **engine_kwargs)
SessionLocal = scoped_session(sessionmaker(bind=engine))
Base = declarative_base()


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True)
    username = Column(String(32), unique=True, nullable=False)
    password_hash = Column(String(255), nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    total_score = Column(Integer, default=0)
    games_played = Column(Integer, default=0)
    balloons_placed = Column(Integer, default=0)
    powerups_collected = Column(Integer, default=0)


Base.metadata.create_all(engine)

GAME_WIDTH = 800
GAME_HEIGHT = 600
PLAYER_SPEED = 250.0
BALLOON_MIN_SPEED = 40.0
BALLOON_MAX_SPEED = 90.0
BALLOON_RADIUS = 18
BALLOON_SPAWN_BASE = 0.6
BALLOON_SPAWN_PER_PLAYER = 0.25
PLAYER_COOLDOWN = 0.6
PLAYER_TIMEOUT = 30.0
BALLOON_FUSE = 2.4
BALLOON_BASE_RADIUS = 70
POWERUP_SPAWN_INTERVAL = 12.0
BANANA_SPAWN_INTERVAL = 10.0
BANANA_READY_WINDOW = 10.0
BANANA_SLOW_DURATION = 3.0

ROOMS = {}
ROOMS_LOCK = Lock()

COLOR_POOL = [
    "#ff5d5d",
    "#ffb347",
    "#f9e65c",
    "#6bd4ff",
    "#8b6bff",
    "#6bff95",
]

POWERUP_TYPES = ["speed", "capacity", "strength"]


def _now():
    return time.monotonic()


def _db():
    return SessionLocal()


def _current_user():
    user_id = session.get("user_id")
    if not user_id:
        return None
    db = _db()
    return db.get(User, user_id)


def _new_balloon():
    return {
        "id": uuid.uuid4().hex[:8],
        "x": random.uniform(40, GAME_WIDTH - 40),
        "y": GAME_HEIGHT + BALLOON_RADIUS + random.uniform(0, 80),
        "vy": random.uniform(BALLOON_MIN_SPEED, BALLOON_MAX_SPEED),
        "radius": BALLOON_RADIUS,
        "color": random.choice(COLOR_POOL),
    }


def _new_room(room_id):
    return {
        "id": room_id,
        "players": {},
        "balloons": [],
        "placed_balloons": [],
        "explosions": [],
        "powerups": [],
        "bananas": [],
        "last_update": _now(),
        "spawn_accum": 0.0,
        "powerup_timer": 0.0,
        "banana_timer": 0.0,
    }


def _add_player(room, user):
    player_id = uuid.uuid4().hex[:10]
    room["players"][player_id] = {
        "id": player_id,
        "user_id": user.id,
        "name": user.username,
        "x": GAME_WIDTH / 2,
        "vx": 0.0,
        "score": 0,
        "color": random.choice(COLOR_POOL),
        "last_seen": _now(),
        "last_shot": 0.0,
        "speed_mult": 1.0,
        "balloon_capacity": 1,
        "blast_radius": BALLOON_BASE_RADIUS,
        "banana_ready_until": 0.0,
        "has_banana": False,
        "slow_until": 0.0,
    }
    return player_id


def _cleanup_players(room, now):
    stale = [
        player_id
        for player_id, player in room["players"].items()
        if now - player["last_seen"] > PLAYER_TIMEOUT
    ]
    for player_id in stale:
        room["players"].pop(player_id, None)


def _player_speed(player, now):
    slow_mult = 0.45 if now < player["slow_until"] else 1.0
    return PLAYER_SPEED * player["speed_mult"] * slow_mult


def _spawn_powerup(room):
    powerup_type = random.choice(POWERUP_TYPES)
    room["powerups"].append(
        {
            "id": uuid.uuid4().hex[:8],
            "type": powerup_type,
            "x": random.uniform(50, GAME_WIDTH - 50),
            "y": GAME_HEIGHT - 55,
        }
    )


def _spawn_banana_powerup(room):
    room["powerups"].append(
        {
            "id": uuid.uuid4().hex[:8],
            "type": "banana",
            "x": random.uniform(50, GAME_WIDTH - 50),
            "y": GAME_HEIGHT - 55,
        }
    )


def _apply_powerup(player, powerup_type):
    if powerup_type == "speed":
        player["speed_mult"] += 0.15
    elif powerup_type == "capacity":
        player["balloon_capacity"] += 1
    elif powerup_type == "strength":
        player["blast_radius"] += 12
    elif powerup_type == "banana":
        player["has_banana"] = True
        player["banana_ready_until"] = _now() + BANANA_READY_WINDOW


def _advance_room(room, now):
    dt = max(0.0, min(0.05, now - room["last_update"]))
    room["last_update"] = now

    for player in room["players"].values():
        player["x"] += player["vx"] * _player_speed(player, now) * dt
        player["x"] = max(30, min(GAME_WIDTH - 30, player["x"]))
        if player["has_banana"] and now > player["banana_ready_until"]:
            player["has_banana"] = False

    for balloon in list(room["balloons"]):
        balloon["y"] -= balloon["vy"] * dt
        if balloon["y"] < -BALLOON_RADIUS:
            room["balloons"].remove(balloon)

    room["spawn_accum"] += dt * (
        BALLOON_SPAWN_BASE + BALLOON_SPAWN_PER_PLAYER * len(room["players"])
    )
    while room["spawn_accum"] >= 1.0:
        room["balloons"].append(_new_balloon())
        room["spawn_accum"] -= 1.0

    room["powerup_timer"] += dt
    if room["powerup_timer"] >= POWERUP_SPAWN_INTERVAL:
        _spawn_powerup(room)
        room["powerup_timer"] = 0.0

    room["banana_timer"] += dt
    if room["banana_timer"] >= BANANA_SPAWN_INTERVAL:
        _spawn_banana_powerup(room)
        room["banana_timer"] = 0.0

    for placed in list(room["placed_balloons"]):
        if now - placed["placed_at"] >= placed["fuse"]:
            room["placed_balloons"].remove(placed)
            room["explosions"].append(
                {
                    "id": uuid.uuid4().hex[:8],
                    "x": placed["x"],
                    "y": placed["y"],
                    "radius": placed["radius"],
                    "expires_at": now + 0.4,
                    "player_id": placed["player_id"],
                }
            )

    for explosion in list(room["explosions"]):
        if now > explosion["expires_at"]:
            room["explosions"].remove(explosion)
            continue
        for balloon in list(room["balloons"]):
            dx = explosion["x"] - balloon["x"]
            dy = explosion["y"] - balloon["y"]
            if dx * dx + dy * dy <= (explosion["radius"] + balloon["radius"]) ** 2:
                room["balloons"].remove(balloon)
                shooter = room["players"].get(explosion["player_id"])
                if shooter:
                    shooter["score"] += 1
                    db = _db()
                    user = db.get(User, shooter["user_id"])
                    if user:
                        user.total_score += 1
                        db.commit()

    for powerup in list(room["powerups"]):
        for player in room["players"].values():
            dx = powerup["x"] - player["x"]
            dy = powerup["y"] - (GAME_HEIGHT - 34)
            if dx * dx + dy * dy <= 26**2:
                room["powerups"].remove(powerup)
                _apply_powerup(player, powerup["type"])
                db = _db()
                user = db.get(User, player["user_id"])
                if user:
                    user.powerups_collected += 1
                    db.commit()
                break

    for banana in list(room["bananas"]):
        for player in room["players"].values():
            if player["id"] == banana["player_id"]:
                continue
            dx = banana["x"] - player["x"]
            dy = banana["y"] - (GAME_HEIGHT - 34)
            if dx * dx + dy * dy <= 22**2:
                player["slow_until"] = max(player["slow_until"], now + BANANA_SLOW_DURATION)
                room["bananas"].remove(banana)
                break


def _room_state(room):
    return {
        "roomId": room["id"],
        "width": GAME_WIDTH,
        "height": GAME_HEIGHT,
        "players": list(room["players"].values()),
        "balloons": room["balloons"],
        "placedBalloons": room["placed_balloons"],
        "explosions": room["explosions"],
        "powerups": room["powerups"],
        "bananas": room["bananas"],
        "serverTime": _now(),
    }


@app.route("/")
def root_redirect():
    if BLUEPRINT_PREFIX:
        return redirect(BLUEPRINT_PREFIX + "/")
    return index()


@main_bp.route("/")
def index():
    return render_template("index.html")


@main_bp.route("/join")
def join_redirect():
    return redirect(url_for("main.index"))


@main_bp.post("/api/register")
def api_register():
    data = request.get_json(force=True, silent=True) or {}
    username = (data.get("username") or "").strip().lower()[:32]
    password = (data.get("password") or "").strip()
    if len(username) < 3 or len(password) < 6:
        return jsonify({"error": "invalid_credentials"}), 400

    db = _db()
    if db.query(User).filter(User.username == username).first():
        return jsonify({"error": "user_exists"}), 409
    user = User(username=username, password_hash=generate_password_hash(password))
    db.add(user)
    db.commit()
    session["user_id"] = user.id
    return jsonify({"id": user.id, "username": user.username})


@main_bp.post("/api/login")
def api_login():
    data = request.get_json(force=True, silent=True) or {}
    username = (data.get("username") or "").strip().lower()
    password = (data.get("password") or "").strip()
    db = _db()
    user = db.query(User).filter(User.username == username).first()
    if not user or not check_password_hash(user.password_hash, password):
        return jsonify({"error": "invalid_login"}), 401
    session["user_id"] = user.id
    return jsonify({"id": user.id, "username": user.username})


@main_bp.post("/api/logout")
def api_logout():
    session.clear()
    return jsonify({"ok": True})


@main_bp.get("/api/me")
def api_me():
    user = _current_user()
    if not user:
        return jsonify({"authenticated": False})
    return jsonify(
        {
            "authenticated": True,
            "user": {
                "id": user.id,
                "username": user.username,
                "totalScore": user.total_score,
                "gamesPlayed": user.games_played,
                "balloonsPlaced": user.balloons_placed,
                "powerupsCollected": user.powerups_collected,
            },
        }
    )


@main_bp.route("/api/join", methods=["POST"])
def api_join():
    user = _current_user()
    if not user:
        return jsonify({"error": "unauthorized"}), 401
    data = request.get_json(force=True, silent=True) or {}
    room_id = (data.get("room") or "lobby").strip().lower()[:32]

    with ROOMS_LOCK:
        room = ROOMS.get(room_id)
        if not room:
            room = _new_room(room_id)
            ROOMS[room_id] = room
        user.games_played += 1
        db = _db()
        db.merge(user)
        db.commit()
        player_id = _add_player(room, user)
        room["players"][player_id]["last_seen"] = _now()
        state = _room_state(room)

    return jsonify({"playerId": player_id, "state": state})


@main_bp.route("/api/input", methods=["POST"])
def api_input():
    data = request.get_json(force=True, silent=True) or {}
    room_id = data.get("roomId")
    player_id = data.get("playerId")
    move = data.get("move", 0)
    place_balloon = bool(data.get("placeBalloon"))
    place_banana = bool(data.get("placeBanana"))

    with ROOMS_LOCK:
        room = ROOMS.get(room_id)
        if not room:
            return jsonify({"error": "room_not_found"}), 404
        player = room["players"].get(player_id)
        if not player:
            return jsonify({"error": "player_not_found"}), 404

        now = _now()
        player["last_seen"] = now
        player["vx"] = max(-1.0, min(1.0, float(move)))

        if place_balloon and now - player["last_shot"] >= PLAYER_COOLDOWN:
            active = [
                b for b in room["placed_balloons"] if b["player_id"] == player_id
            ]
            if len(active) < player["balloon_capacity"]:
                player["last_shot"] = now
                room["placed_balloons"].append(
                    {
                        "id": uuid.uuid4().hex[:8],
                        "player_id": player_id,
                        "x": player["x"],
                        "y": GAME_HEIGHT - 45,
                        "placed_at": now,
                        "fuse": BALLOON_FUSE,
                        "radius": player["blast_radius"],
                    }
                )
                db = _db()
                user = db.get(User, player["user_id"])
                if user:
                    user.balloons_placed += 1
                    db.commit()

        if place_banana and player["has_banana"] and now <= player["banana_ready_until"]:
            room["bananas"].append(
                {
                    "id": uuid.uuid4().hex[:8],
                    "player_id": player_id,
                    "x": player["x"],
                    "y": GAME_HEIGHT - 45,
                }
            )
            player["has_banana"] = False

    return jsonify({"ok": True})


@main_bp.route("/api/poll", methods=["GET"])
def api_poll():
    room_id = request.args.get("roomId")
    player_id = request.args.get("playerId")

    with ROOMS_LOCK:
        room = ROOMS.get(room_id)
        if not room:
            return jsonify({"error": "room_not_found"}), 404
        player = room["players"].get(player_id)
        if not player:
            return jsonify({"error": "player_not_found"}), 404

        now = _now()
        player["last_seen"] = now
        _cleanup_players(room, now)
        _advance_room(room, now)
        state = _room_state(room)

    return jsonify(state)


app.register_blueprint(main_bp)


if __name__ == "__main__":
    app.run(debug=True)
