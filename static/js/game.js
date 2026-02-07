const canvas = document.getElementById("gameCanvas");
const ctx = canvas.getContext("2d");

const authOverlay = document.getElementById("authOverlay");
const authForm = document.getElementById("authForm");
const authTitle = document.getElementById("authTitle");
const authSubmit = document.getElementById("authSubmit");
const authError = document.getElementById("authError");
const toggleAuth = document.getElementById("toggleAuth");
const usernameInput = document.getElementById("usernameInput");
const passwordInput = document.getElementById("passwordInput");
const joinOverlay = document.getElementById("joinOverlay");
const joinForm = document.getElementById("joinForm");
const roomInput = document.getElementById("roomInput");
const roomLabel = document.getElementById("roomLabel");
const statusLabel = document.getElementById("statusLabel");
const userLabel = document.getElementById("userLabel");
const scoreboard = document.getElementById("scoreboard");
const statSpeed = document.getElementById("statSpeed");
const statCapacity = document.getElementById("statCapacity");
const statBlast = document.getElementById("statBlast");
const statBanana = document.getElementById("statBanana");

const inputState = {
  left: false,
  right: false,
  placeBalloon: false,
  placeBanana: false,
};

let playerId = null;
let roomId = null;
let gameState = null;
let lastPoll = 0;
let pollTimer = null;
let inputTimer = null;
let authMode = "login";
let currentUser = null;

function setStatus(text) {
  statusLabel.textContent = text;
}

function normalizeMove() {
  if (inputState.left && !inputState.right) return -1;
  if (inputState.right && !inputState.left) return 1;
  return 0;
}

async function sendInput(forceBalloon = false, forceBanana = false) {
  if (!playerId || !roomId) return;
  const payload = {
    playerId,
    roomId,
    move: normalizeMove(),
    placeBalloon: inputState.placeBalloon || forceBalloon,
    placeBanana: inputState.placeBanana || forceBanana,
  };
  if (forceBalloon) {
    inputState.placeBalloon = false;
  }
  if (forceBanana) {
    inputState.placeBanana = false;
  }
  try {
    await fetch("/api/input", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
  } catch (err) {
    setStatus("Reconnecting…");
  }
}

async function poll() {
  if (!playerId || !roomId) return;
  try {
    const response = await fetch(
      `/api/poll?roomId=${encodeURIComponent(roomId)}&playerId=${encodeURIComponent(
        playerId
      )}`
    );
    if (!response.ok) {
      setStatus("Disconnected");
      return;
    }
    gameState = await response.json();
    lastPoll = Date.now();
    setStatus("Online");
    updateStats(gameState);
  } catch (err) {
    setStatus("Reconnecting…");
  } finally {
    pollTimer = setTimeout(poll, 140);
  }
}

async function joinGame(name, room) {
  setStatus("Joining…");
  const response = await fetch("/api/join", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ room }),
  });
  const data = await response.json();
  playerId = data.playerId;
  roomId = (room || "lobby").toLowerCase();
  gameState = data.state;
  joinOverlay.classList.add("hidden");
  roomLabel.textContent = `Room: ${roomId}`;
  setStatus("Online");
  if (!pollTimer) poll();
  if (!inputTimer) {
    inputTimer = setInterval(() => sendInput(false, false), 120);
  }
}

function resizeCanvas() {
  const rect = canvas.getBoundingClientRect();
  const ratio = window.devicePixelRatio || 1;
  canvas.width = rect.width * ratio;
  canvas.height = rect.height * ratio;
  ctx.setTransform(ratio, 0, 0, ratio, 0, 0);
}

function drawBackground() {
  ctx.fillStyle = "#11152b";
  ctx.fillRect(0, 0, canvas.width, canvas.height);
}

function drawGround(scale) {
  const groundY = canvas.height / scale - 30;
  ctx.fillStyle = "#1d1f38";
  ctx.fillRect(0, groundY, canvas.width / scale, 40);
}

function drawPlayers(state) {
  state.players.forEach((player) => {
    const y = state.height - 34;
    ctx.fillStyle = player.color;
    ctx.fillRect(player.x - 18, y, 36, 16);
    ctx.fillStyle = "#1b1c2f";
    ctx.fillRect(player.x - 8, y - 14, 16, 12);
    if (state.serverTime < player.slow_until) {
      ctx.strokeStyle = "rgba(120, 187, 255, 0.6)";
      ctx.lineWidth = 2;
      ctx.strokeRect(player.x - 20, y - 2, 40, 20);
    }
  });
}

function drawBalloons(state) {
  state.balloons.forEach((balloon) => {
    ctx.beginPath();
    ctx.fillStyle = balloon.color;
    ctx.arc(balloon.x, balloon.y, balloon.radius, 0, Math.PI * 2);
    ctx.fill();
    ctx.strokeStyle = "rgba(255,255,255,0.2)";
    ctx.stroke();
  });
}

function drawPlacedBalloons(state) {
  ctx.fillStyle = "#f7f7f8";
  state.placedBalloons.forEach((placed) => {
    ctx.beginPath();
    ctx.arc(placed.x, placed.y, 10, 0, Math.PI * 2);
    ctx.fill();
  });
}

function drawExplosions(state) {
  state.explosions.forEach((explosion) => {
    ctx.beginPath();
    ctx.strokeStyle = "rgba(255, 210, 92, 0.6)";
    ctx.lineWidth = 3;
    ctx.arc(explosion.x, explosion.y, explosion.radius, 0, Math.PI * 2);
    ctx.stroke();
  });
}

function drawPowerups(state) {
  state.powerups.forEach((powerup) => {
    ctx.beginPath();
    if (powerup.type === "speed") {
      ctx.fillStyle = "#6bd4ff";
    } else if (powerup.type === "capacity") {
      ctx.fillStyle = "#6bff95";
    } else if (powerup.type === "strength") {
      ctx.fillStyle = "#ffb347";
    } else {
      ctx.fillStyle = "#f9e65c";
    }
    ctx.arc(powerup.x, powerup.y, 12, 0, Math.PI * 2);
    ctx.fill();
  });
}

function drawBananas(state) {
  state.bananas.forEach((banana) => {
    ctx.fillStyle = "#f4d13d";
    ctx.fillRect(banana.x - 8, banana.y - 4, 16, 8);
  });
}

function updateScoreboard(state) {
  scoreboard.innerHTML = "";
  const sorted = [...state.players].sort((a, b) => b.score - a.score);
  sorted.forEach((player) => {
    const item = document.createElement("li");
    const name = document.createElement("span");
    name.textContent = player.name;
    name.style.color = player.color;
    const score = document.createElement("span");
    score.textContent = String(player.score);
    item.append(name, score);
    scoreboard.appendChild(item);
  });
}

function render() {
  resizeCanvas();
  drawBackground();
  if (!gameState) {
    requestAnimationFrame(render);
    return;
  }
  const scale = canvas.clientWidth / gameState.width;
  ctx.save();
  ctx.scale(scale, scale);
  drawGround(scale);
  drawBalloons(gameState);
  drawPlacedBalloons(gameState);
  drawExplosions(gameState);
  drawPowerups(gameState);
  drawBananas(gameState);
  drawPlayers(gameState);
  ctx.restore();
  updateScoreboard(gameState);
  requestAnimationFrame(render);
}

function handleKey(event, isDown) {
  if (event.repeat) return;
  switch (event.key) {
    case "ArrowLeft":
    case "a":
    case "A":
      inputState.left = isDown;
      break;
    case "ArrowRight":
    case "d":
    case "D":
      inputState.right = isDown;
      break;
    case " ":
      if (isDown) {
        inputState.placeBalloon = true;
        sendInput(true, false);
      }
      break;
    case "b":
    case "B":
      if (isDown) {
        inputState.placeBanana = true;
        sendInput(false, true);
      }
      break;
    default:
      return;
  }
  sendInput(false, false);
}

function setAuthMode(mode) {
  authMode = mode;
  if (mode === "login") {
    authTitle.textContent = "Log in";
    authSubmit.textContent = "Log in";
    toggleAuth.textContent = "Create account";
  } else {
    authTitle.textContent = "Create account";
    authSubmit.textContent = "Register";
    toggleAuth.textContent = "Back to login";
  }
  authError.textContent = "";
}

async function checkAuth() {
  const response = await fetch("/api/me");
  const data = await response.json();
  if (data.authenticated) {
    currentUser = data.user;
    userLabel.textContent = data.user.username;
    authOverlay.classList.add("hidden");
    joinOverlay.classList.remove("hidden");
  } else {
    authOverlay.classList.remove("hidden");
    joinOverlay.classList.add("hidden");
  }
}

function updateStats(state) {
  const me = state.players.find((player) => player.id === playerId);
  if (!me) return;
  statSpeed.textContent = `${me.speed_mult.toFixed(2)}x`;
  statCapacity.textContent = `${me.balloon_capacity}`;
  statBlast.textContent = `${Math.round(me.blast_radius)}`;
  if (me.has_banana) {
    const seconds = Math.max(0, me.banana_ready_until - state.serverTime);
    statBanana.textContent = `Ready (${seconds.toFixed(1)}s)`;
  } else {
    statBanana.textContent = "None";
  }
}

authForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  authError.textContent = "";
  const username = usernameInput.value.trim();
  const password = passwordInput.value;
  if (!username || !password) {
    authError.textContent = "Enter username and password.";
    return;
  }
  const endpoint = authMode === "login" ? "/api/login" : "/api/register";
  const response = await fetch(endpoint, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ username, password }),
  });
  const data = await response.json();
  if (!response.ok) {
    authError.textContent = data.error || "Unable to sign in.";
    return;
  }
  currentUser = data;
  userLabel.textContent = data.username;
  authOverlay.classList.add("hidden");
  joinOverlay.classList.remove("hidden");
});

toggleAuth.addEventListener("click", () => {
  setAuthMode(authMode === "login" ? "register" : "login");
});

joinForm.addEventListener("submit", (event) => {
  event.preventDefault();
  joinGame("", roomInput.value.trim() || "lobby");
});

window.addEventListener("keydown", (event) => handleKey(event, true));
window.addEventListener("keyup", (event) => handleKey(event, false));
window.addEventListener("resize", resizeCanvas);

render();
setAuthMode("login");
checkAuth();
