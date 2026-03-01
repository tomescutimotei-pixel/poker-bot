import asyncio
import os
from functools import wraps
from flask import Flask, render_template_string, jsonify, request, session, redirect, url_for
import asyncpg
import database

app = Flask(__name__)
app.secret_key = os.getenv("DASHBOARD_SECRET_KEY", "change_this_in_production")

ADMIN_USERNAME = os.getenv("DASHBOARD_USER", "admin")
ADMIN_PASSWORD = os.getenv("DASHBOARD_PASS", "kingsriver2024")

# ─── AUTH ─────────────────────────────────────────────
def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not session.get("logged_in"):
            return redirect(url_for("login"))
        return f(*args, **kwargs)
    return decorated

def run_async(coro):
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()

# ─── LOGIN ────────────────────────────────────────────
@app.route("/login", methods=["GET", "POST"])
def login():
    error = None
    if request.method == "POST":
        if (request.form["username"] == ADMIN_USERNAME and
                request.form["password"] == ADMIN_PASSWORD):
            session["logged_in"] = True
            return redirect(url_for("dashboard"))
        error = "Credențiale greșite."
    return render_template_string(LOGIN_HTML, error=error)

@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))

# ─── DASHBOARD ────────────────────────────────────────
@app.route("/")
@login_required
def dashboard():
    return render_template_string(DASHBOARD_HTML)

# ─── API ENDPOINTS ────────────────────────────────────
@app.route("/api/stats")
@login_required
def api_stats():
    stats = run_async(database.get_stats())
    return jsonify(stats)

@app.route("/api/users")
@login_required
def api_users():
    users = run_async(database.get_all_users())
    result = []
    for u in users:
        result.append({
            "telegram_id": u["telegram_id"],
            "gg_username": u["gg_username"],
            "balance": u["balance"],
            "status": u["status"],
            "registered_at": str(u["registered_at"])
        })
    return jsonify(result)

@app.route("/api/transactions")
@login_required
def api_transactions():
    txs = run_async(database.get_all_transactions(100))
    result = []
    for t in txs:
        result.append({
            "id": t["id"],
            "user_id": t["user_id"],
            "gg_username": t["gg_username"],
            "type": t["type"],
            "amount": t["amount"],
            "status": t["status"],
            "created_at": str(t["created_at"])
        })
    return jsonify(result)

@app.route("/api/pending_deposits")
@login_required
def api_pending_deposits():
    txs = run_async(database.get_pending_deposits())
    result = []
    for t in txs:
        result.append({
            "id": t["id"],
            "user_id": t["user_id"],
            "gg_username": t["gg_username"],
            "amount": t["amount"],
            "created_at": str(t["created_at"])
        })
    return jsonify(result)

@app.route("/api/pending_withdrawals")
@login_required
def api_pending_withdrawals():
    txs = run_async(database.get_pending_withdrawals())
    result = []
    for t in txs:
        result.append({
            "id": t["id"],
            "user_id": t["user_id"],
            "gg_username": t["gg_username"],
            "amount": t["amount"],
            "created_at": str(t["created_at"])
        })
    return jsonify(result)

@app.route("/api/update_balance", methods=["POST"])
@login_required
def api_update_balance():
    data = request.json
    telegram_id = int(data["telegram_id"])
    new_balance = float(data["balance"])
    run_async(database.manual_update_balance(telegram_id, new_balance))
    return jsonify({"success": True})

@app.route("/api/approve_transaction", methods=["POST"])
@login_required
def api_approve_transaction():
    data = request.json
    tx_id = int(data["tx_id"])
    user_id = int(data["user_id"])
    amount = float(data["amount"])
    tx_type = data["type"]

    run_async(database.update_transaction_status(tx_id, "completed"))
    if tx_type == "deposit":
        run_async(database.update_balance(user_id, amount))
    elif tx_type == "withdraw":
        run_async(database.update_balance(user_id, -amount))
    return jsonify({"success": True})

@app.route("/api/reject_transaction", methods=["POST"])
@login_required
def api_reject_transaction():
    data = request.json
    tx_id = int(data["tx_id"])
    run_async(database.update_transaction_status(tx_id, "rejected"))
    return jsonify({"success": True})

# ─── HTML TEMPLATES ───────────────────────────────────
LOGIN_HTML = """<!DOCTYPE html>
<html lang="ro">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>KingsRiver — Admin Login</title>
<link href="https://fonts.googleapis.com/css2?family=Cinzel:wght@600;700&family=Raleway:wght@300;400;500&display=swap" rel="stylesheet">
<style>
  *, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }
  :root {
    --gold: #c9a84c;
    --gold-light: #e8cc7d;
    --dark: #0a0a0f;
    --card: #13131a;
    --border: rgba(201,168,76,0.25);
  }
  body {
    font-family: 'Raleway', sans-serif;
    background: var(--dark);
    min-height: 100vh;
    display: flex;
    align-items: center;
    justify-content: center;
    background-image: radial-gradient(ellipse at 50% 0%, rgba(201,168,76,0.08) 0%, transparent 60%);
  }
  .login-card {
    background: var(--card);
    border: 1px solid var(--border);
    border-radius: 16px;
    padding: 48px 40px;
    width: 380px;
    box-shadow: 0 0 80px rgba(201,168,76,0.06), 0 20px 60px rgba(0,0,0,0.6);
  }
  .logo {
    text-align: center;
    margin-bottom: 36px;
  }
  .logo-icon { font-size: 40px; margin-bottom: 12px; }
  .logo h1 {
    font-family: 'Cinzel', serif;
    color: var(--gold);
    font-size: 20px;
    letter-spacing: 2px;
    text-transform: uppercase;
  }
  .logo p {
    color: rgba(255,255,255,0.35);
    font-size: 11px;
    letter-spacing: 3px;
    text-transform: uppercase;
    margin-top: 4px;
  }
  .divider {
    height: 1px;
    background: linear-gradient(90deg, transparent, var(--gold), transparent);
    margin-bottom: 36px;
    opacity: 0.4;
  }
  label {
    display: block;
    color: rgba(255,255,255,0.5);
    font-size: 11px;
    letter-spacing: 2px;
    text-transform: uppercase;
    margin-bottom: 8px;
  }
  input {
    width: 100%;
    background: rgba(255,255,255,0.04);
    border: 1px solid rgba(255,255,255,0.1);
    border-radius: 8px;
    padding: 12px 16px;
    color: #fff;
    font-family: 'Raleway', sans-serif;
    font-size: 14px;
    margin-bottom: 20px;
    transition: border-color 0.2s;
    outline: none;
  }
  input:focus { border-color: var(--gold); }
  button {
    width: 100%;
    background: linear-gradient(135deg, var(--gold), var(--gold-light));
    border: none;
    border-radius: 8px;
    padding: 14px;
    color: #0a0a0f;
    font-family: 'Cinzel', serif;
    font-size: 13px;
    font-weight: 700;
    letter-spacing: 2px;
    text-transform: uppercase;
    cursor: pointer;
    transition: opacity 0.2s, transform 0.1s;
    margin-top: 4px;
  }
  button:hover { opacity: 0.9; transform: translateY(-1px); }
  button:active { transform: translateY(0); }
  .error {
    background: rgba(220,50,50,0.12);
    border: 1px solid rgba(220,50,50,0.3);
    border-radius: 8px;
    padding: 10px 14px;
    color: #ff6b6b;
    font-size: 13px;
    margin-bottom: 20px;
    text-align: center;
  }
</style>
</head>
<body>
<div class="login-card">
  <div class="logo">
    <div class="logo-icon">🃏</div>
    <h1>KingsRiver</h1>
    <p>Admin Panel</p>
  </div>
  <div class="divider"></div>
  {% if error %}<div class="error">{{ error }}</div>{% endif %}
  <form method="POST">
    <label>Username</label>
    <input type="text" name="username" autocomplete="username" required>
    <label>Parolă</label>
    <input type="password" name="password" autocomplete="current-password" required>
    <button type="submit">Intră în panou</button>
  </form>
</div>
</body>
</html>"""

DASHBOARD_HTML = """<!DOCTYPE html>
<html lang="ro">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>KingsRiver — Admin Dashboard</title>
<link href="https://fonts.googleapis.com/css2?family=Cinzel:wght@600;700&family=Raleway:wght@300;400;500;600&display=swap" rel="stylesheet">
<style>
  *, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }
  :root {
    --gold: #c9a84c;
    --gold-light: #e8cc7d;
    --gold-dim: rgba(201,168,76,0.15);
    --dark: #080810;
    --surface: #0f0f18;
    --card: #13131e;
    --card2: #181824;
    --border: rgba(201,168,76,0.18);
    --border-light: rgba(255,255,255,0.06);
    --text: #e8e8f0;
    --text-dim: rgba(232,232,240,0.45);
    --green: #4caf82;
    --red: #e05252;
    --blue: #5280e0;
  }
  body {
    font-family: 'Raleway', sans-serif;
    background: var(--dark);
    color: var(--text);
    min-height: 100vh;
    background-image:
      radial-gradient(ellipse at 80% 0%, rgba(201,168,76,0.05) 0%, transparent 50%),
      radial-gradient(ellipse at 20% 100%, rgba(82,128,224,0.03) 0%, transparent 40%);
  }

  /* ── SIDEBAR ── */
  .sidebar {
    position: fixed;
    left: 0; top: 0; bottom: 0;
    width: 240px;
    background: var(--surface);
    border-right: 1px solid var(--border);
    display: flex;
    flex-direction: column;
    z-index: 100;
  }
  .sidebar-logo {
    padding: 28px 24px;
    border-bottom: 1px solid var(--border);
  }
  .sidebar-logo h1 {
    font-family: 'Cinzel', serif;
    color: var(--gold);
    font-size: 16px;
    letter-spacing: 2px;
  }
  .sidebar-logo p {
    color: var(--text-dim);
    font-size: 10px;
    letter-spacing: 3px;
    text-transform: uppercase;
    margin-top: 3px;
  }
  .nav { flex: 1; padding: 16px 12px; }
  .nav-item {
    display: flex;
    align-items: center;
    gap: 12px;
    padding: 11px 14px;
    border-radius: 8px;
    color: var(--text-dim);
    font-size: 13px;
    font-weight: 500;
    cursor: pointer;
    transition: all 0.15s;
    margin-bottom: 2px;
    border: 1px solid transparent;
  }
  .nav-item:hover { background: rgba(255,255,255,0.04); color: var(--text); }
  .nav-item.active {
    background: var(--gold-dim);
    color: var(--gold);
    border-color: rgba(201,168,76,0.2);
  }
  .nav-icon { font-size: 16px; width: 20px; text-align: center; }
  .badge {
    margin-left: auto;
    background: var(--red);
    color: #fff;
    border-radius: 10px;
    font-size: 10px;
    font-weight: 700;
    padding: 2px 7px;
    min-width: 18px;
    text-align: center;
  }
  .sidebar-footer {
    padding: 16px 12px;
    border-top: 1px solid var(--border);
  }
  .logout-btn {
    display: flex;
    align-items: center;
    gap: 10px;
    padding: 10px 14px;
    border-radius: 8px;
    color: var(--text-dim);
    font-size: 13px;
    cursor: pointer;
    text-decoration: none;
    transition: color 0.15s;
  }
  .logout-btn:hover { color: var(--red); }

  /* ── MAIN ── */
  .main { margin-left: 240px; padding: 32px; min-height: 100vh; }
  .page { display: none; }
  .page.active { display: block; }

  /* ── PAGE HEADER ── */
  .page-header { margin-bottom: 28px; }
  .page-header h2 {
    font-family: 'Cinzel', serif;
    font-size: 22px;
    color: var(--text);
    margin-bottom: 4px;
  }
  .page-header p { color: var(--text-dim); font-size: 13px; }

  /* ── STATS GRID ── */
  .stats-grid {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
    gap: 16px;
    margin-bottom: 28px;
  }
  .stat-card {
    background: var(--card);
    border: 1px solid var(--border-light);
    border-radius: 12px;
    padding: 20px;
    position: relative;
    overflow: hidden;
  }
  .stat-card::before {
    content: '';
    position: absolute;
    top: 0; left: 0; right: 0;
    height: 2px;
    background: linear-gradient(90deg, var(--gold), transparent);
  }
  .stat-label {
    color: var(--text-dim);
    font-size: 11px;
    letter-spacing: 2px;
    text-transform: uppercase;
    margin-bottom: 10px;
  }
  .stat-value {
    font-size: 28px;
    font-weight: 600;
    color: var(--text);
    line-height: 1;
  }
  .stat-value.gold { color: var(--gold); }
  .stat-value.green { color: var(--green); }
  .stat-value.red { color: var(--red); }
  .stat-icon {
    position: absolute;
    right: 16px; top: 16px;
    font-size: 24px;
    opacity: 0.2;
  }

  /* ── TABLE ── */
  .table-card {
    background: var(--card);
    border: 1px solid var(--border-light);
    border-radius: 12px;
    overflow: hidden;
    margin-bottom: 20px;
  }
  .table-header {
    padding: 16px 20px;
    border-bottom: 1px solid var(--border-light);
    display: flex;
    align-items: center;
    justify-content: space-between;
  }
  .table-header h3 { font-size: 14px; font-weight: 600; }
  .table-search {
    background: rgba(255,255,255,0.04);
    border: 1px solid var(--border-light);
    border-radius: 6px;
    padding: 7px 12px;
    color: var(--text);
    font-family: 'Raleway', sans-serif;
    font-size: 12px;
    width: 200px;
    outline: none;
  }
  .table-search:focus { border-color: var(--gold); }
  table { width: 100%; border-collapse: collapse; }
  th {
    background: rgba(255,255,255,0.02);
    padding: 11px 16px;
    text-align: left;
    font-size: 10px;
    letter-spacing: 2px;
    text-transform: uppercase;
    color: var(--text-dim);
    font-weight: 600;
    border-bottom: 1px solid var(--border-light);
  }
  td {
    padding: 12px 16px;
    font-size: 13px;
    border-bottom: 1px solid rgba(255,255,255,0.03);
    vertical-align: middle;
  }
  tr:last-child td { border-bottom: none; }
  tr:hover td { background: rgba(255,255,255,0.02); }

  /* ── BADGES ── */
  .pill {
    display: inline-block;
    padding: 3px 10px;
    border-radius: 20px;
    font-size: 11px;
    font-weight: 600;
    letter-spacing: 0.5px;
  }
  .pill-green { background: rgba(76,175,130,0.15); color: var(--green); }
  .pill-red { background: rgba(224,82,82,0.15); color: var(--red); }
  .pill-yellow { background: rgba(201,168,76,0.15); color: var(--gold); }
  .pill-blue { background: rgba(82,128,224,0.15); color: var(--blue); }

  /* ── BUTTONS ── */
  .btn {
    display: inline-flex;
    align-items: center;
    gap: 6px;
    padding: 6px 14px;
    border-radius: 6px;
    font-size: 12px;
    font-weight: 600;
    cursor: pointer;
    border: none;
    transition: all 0.15s;
    font-family: 'Raleway', sans-serif;
  }
  .btn-gold { background: linear-gradient(135deg, var(--gold), var(--gold-light)); color: #0a0a0f; }
  .btn-gold:hover { opacity: 0.88; }
  .btn-green { background: rgba(76,175,130,0.18); color: var(--green); border: 1px solid rgba(76,175,130,0.3); }
  .btn-green:hover { background: rgba(76,175,130,0.28); }
  .btn-red { background: rgba(224,82,82,0.15); color: var(--red); border: 1px solid rgba(224,82,82,0.3); }
  .btn-red:hover { background: rgba(224,82,82,0.25); }
  .btn-ghost { background: transparent; color: var(--text-dim); border: 1px solid var(--border-light); }
  .btn-ghost:hover { color: var(--text); border-color: rgba(255,255,255,0.15); }
  .btn-sm { padding: 4px 10px; font-size: 11px; }

  /* ── MODAL ── */
  .modal-overlay {
    position: fixed; inset: 0;
    background: rgba(0,0,0,0.75);
    display: none;
    align-items: center;
    justify-content: center;
    z-index: 999;
    backdrop-filter: blur(4px);
  }
  .modal-overlay.show { display: flex; }
  .modal {
    background: var(--card2);
    border: 1px solid var(--border);
    border-radius: 14px;
    padding: 32px;
    width: 400px;
    box-shadow: 0 20px 60px rgba(0,0,0,0.7);
  }
  .modal h3 {
    font-family: 'Cinzel', serif;
    color: var(--gold);
    margin-bottom: 20px;
    font-size: 16px;
  }
  .modal label {
    display: block;
    color: var(--text-dim);
    font-size: 11px;
    letter-spacing: 2px;
    text-transform: uppercase;
    margin-bottom: 6px;
    margin-top: 14px;
  }
  .modal input {
    width: 100%;
    background: rgba(255,255,255,0.04);
    border: 1px solid var(--border-light);
    border-radius: 8px;
    padding: 10px 14px;
    color: var(--text);
    font-family: 'Raleway', sans-serif;
    font-size: 14px;
    outline: none;
  }
  .modal input:focus { border-color: var(--gold); }
  .modal-actions { display: flex; gap: 10px; margin-top: 24px; justify-content: flex-end; }

  /* ── TOAST ── */
  .toast {
    position: fixed;
    bottom: 24px; right: 24px;
    background: var(--card2);
    border: 1px solid var(--border);
    border-radius: 10px;
    padding: 14px 20px;
    font-size: 13px;
    z-index: 9999;
    transform: translateY(100px);
    opacity: 0;
    transition: all 0.3s;
    max-width: 300px;
  }
  .toast.show { transform: translateY(0); opacity: 1; }
  .toast.success { border-color: rgba(76,175,130,0.5); color: var(--green); }
  .toast.error { border-color: rgba(224,82,82,0.5); color: var(--red); }

  /* ── PENDING SECTION ── */
  .pending-grid {
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: 16px;
    margin-bottom: 20px;
  }
  @media (max-width: 900px) { .pending-grid { grid-template-columns: 1fr; } }

  /* ── REFRESH ── */
  .refresh-btn {
    background: rgba(255,255,255,0.04);
    border: 1px solid var(--border-light);
    border-radius: 6px;
    padding: 6px 12px;
    color: var(--text-dim);
    font-size: 12px;
    cursor: pointer;
    font-family: 'Raleway', sans-serif;
    transition: color 0.15s;
  }
  .refresh-btn:hover { color: var(--text); }
  .spinning { animation: spin 1s linear infinite; display: inline-block; }
  @keyframes spin { to { transform: rotate(360deg); } }

  /* ── EMPTY STATE ── */
  .empty-state {
    text-align: center;
    padding: 40px;
    color: var(--text-dim);
    font-size: 13px;
  }
  .empty-state .icon { font-size: 32px; margin-bottom: 12px; }

  /* ── LOADING ── */
  .skeleton {
    background: linear-gradient(90deg, rgba(255,255,255,0.04) 25%, rgba(255,255,255,0.08) 50%, rgba(255,255,255,0.04) 75%);
    background-size: 200% 100%;
    animation: shimmer 1.5s infinite;
    border-radius: 4px;
    height: 14px;
  }
  @keyframes shimmer { to { background-position: -200% 0; } }
</style>
</head>
<body>

<!-- SIDEBAR -->
<div class="sidebar">
  <div class="sidebar-logo">
    <h1>🃏 KingsRiver</h1>
    <p>Admin Panel</p>
  </div>
  <nav class="nav">
    <div class="nav-item active" onclick="showPage('overview')">
      <span class="nav-icon">📊</span> Overview
    </div>
    <div class="nav-item" onclick="showPage('pending')">
      <span class="nav-icon">⏳</span> Pending
      <span class="badge" id="pending-badge" style="display:none">0</span>
    </div>
    <div class="nav-item" onclick="showPage('users')">
      <span class="nav-icon">👥</span> Utilizatori
    </div>
    <div class="nav-item" onclick="showPage('transactions')">
      <span class="nav-icon">💳</span> Tranzacții
    </div>
  </nav>
  <div class="sidebar-footer">
    <a href="/logout" class="logout-btn">
      <span>🚪</span> Ieșire
    </a>
  </div>
</div>

<!-- MAIN -->
<main class="main">

  <!-- OVERVIEW PAGE -->
  <div class="page active" id="page-overview">
    <div class="page-header">
      <h2>Overview</h2>
      <p>Situația generală a clubului</p>
    </div>
    <div class="stats-grid" id="stats-grid">
      <div class="stat-card">
        <div class="stat-icon">👥</div>
        <div class="stat-label">Total Utilizatori</div>
        <div class="stat-value" id="stat-users">—</div>
      </div>
      <div class="stat-card">
        <div class="stat-icon">💰</div>
        <div class="stat-label">Sold Total Cumulat</div>
        <div class="stat-value gold" id="stat-balance">—</div>
      </div>
      <div class="stat-card">
        <div class="stat-icon">📈</div>
        <div class="stat-label">Volum Azi</div>
        <div class="stat-value green" id="stat-volume">—</div>
      </div>
      <div class="stat-card">
        <div class="stat-icon">⏳</div>
        <div class="stat-label">Depuneri Pending</div>
        <div class="stat-value" id="stat-pdep" style="color:var(--gold)">—</div>
      </div>
      <div class="stat-card">
        <div class="stat-icon">🔄</div>
        <div class="stat-label">Retrageri Pending</div>
        <div class="stat-value red" id="stat-pwit">—</div>
      </div>
    </div>
  </div>

  <!-- PENDING PAGE -->
  <div class="page" id="page-pending">
    <div class="page-header" style="display:flex;align-items:center;justify-content:space-between">
      <div>
        <h2>Tranzacții Pending</h2>
        <p>Depuneri și retrageri care necesită acțiune</p>
      </div>
      <button class="refresh-btn" onclick="loadPending()">↻ Refresh</button>
    </div>
    <div class="pending-grid">
      <div>
        <div class="table-card">
          <div class="table-header">
            <h3>💰 Depuneri în așteptare</h3>
          </div>
          <table>
            <thead>
              <tr>
                <th>GG User</th>
                <th>Sumă</th>
                <th>Data</th>
                <th>Acțiuni</th>
              </tr>
            </thead>
            <tbody id="pending-deposits-body">
              <tr><td colspan="4" class="empty-state"><div class="icon">⏳</div>Se încarcă...</td></tr>
            </tbody>
          </table>
        </div>
      </div>
      <div>
        <div class="table-card">
          <div class="table-header">
            <h3>💸 Retrageri în așteptare</h3>
          </div>
          <table>
            <thead>
              <tr>
                <th>GG User</th>
                <th>Sumă</th>
                <th>Data</th>
                <th>Acțiuni</th>
              </tr>
            </thead>
            <tbody id="pending-withdrawals-body">
              <tr><td colspan="4" class="empty-state"><div class="icon">⏳</div>Se încarcă...</td></tr>
            </tbody>
          </table>
        </div>
      </div>
    </div>
  </div>

  <!-- USERS PAGE -->
  <div class="page" id="page-users">
    <div class="page-header">
      <h2>Utilizatori</h2>
      <p>Toți membrii înregistrați ai clubului</p>
    </div>
    <div class="table-card">
      <div class="table-header">
        <h3>Membri</h3>
        <input class="table-search" placeholder="Caută utilizator..." oninput="filterTable('users-body', this.value)">
      </div>
      <table>
        <thead>
          <tr>
            <th>Telegram ID</th>
            <th>GG Username</th>
            <th>Sold (USDT)</th>
            <th>Status</th>
            <th>Înregistrat</th>
            <th>Acțiuni</th>
          </tr>
        </thead>
        <tbody id="users-body">
          <tr><td colspan="6" class="empty-state"><div class="icon">⏳</div>Se încarcă...</td></tr>
        </tbody>
      </table>
    </div>
  </div>

  <!-- TRANSACTIONS PAGE -->
  <div class="page" id="page-transactions">
    <div class="page-header">
      <h2>Tranzacții</h2>
      <p>Istoricul complet al depunerilor și retragerilor</p>
    </div>
    <div class="table-card">
      <div class="table-header">
        <h3>Toate tranzacțiile</h3>
        <input class="table-search" placeholder="Caută..." oninput="filterTable('tx-body', this.value)">
      </div>
      <table>
        <thead>
          <tr>
            <th>#</th>
            <th>GG User</th>
            <th>Tip</th>
            <th>Sumă</th>
            <th>Status</th>
            <th>Data</th>
          </tr>
        </thead>
        <tbody id="tx-body">
          <tr><td colspan="6" class="empty-state"><div class="icon">⏳</div>Se încarcă...</td></tr>
        </tbody>
      </table>
    </div>
  </div>

</main>

<!-- EDIT BALANCE MODAL -->
<div class="modal-overlay" id="balance-modal">
  <div class="modal">
    <h3>✏️ Editează Sold</h3>
    <label>Telegram ID</label>
    <input type="text" id="edit-tg-id" readonly>
    <label>GG Username</label>
    <input type="text" id="edit-gg-name" readonly>
    <label>Sold Nou (USDT)</label>
    <input type="number" id="edit-balance-val" step="0.01" min="0" placeholder="0.00">
    <div class="modal-actions">
      <button class="btn btn-ghost" onclick="closeModal('balance-modal')">Anulează</button>
      <button class="btn btn-gold" onclick="saveBalance()">Salvează</button>
    </div>
  </div>
</div>

<!-- DEPOSIT AMOUNT MODAL -->
<div class="modal-overlay" id="deposit-amount-modal">
  <div class="modal">
    <h3>💰 Confirmă Depunere</h3>
    <p style="color:var(--text-dim);font-size:13px;margin-bottom:16px">Introdu suma primită efectiv de la utilizator.</p>
    <label>GG Username</label>
    <input type="text" id="dep-gg-name" readonly>
    <label>Suma Primită (USDT)</label>
    <input type="number" id="dep-amount-val" step="0.01" min="0.01" placeholder="0.00">
    <input type="hidden" id="dep-tx-id">
    <input type="hidden" id="dep-user-id">
    <div class="modal-actions">
      <button class="btn btn-ghost" onclick="closeModal('deposit-amount-modal')">Anulează</button>
      <button class="btn btn-gold" onclick="confirmDepositAmount()">Confirmă</button>
    </div>
  </div>
</div>

<!-- TOAST -->
<div class="toast" id="toast"></div>

<script>
// ── NAVIGATION ─────────────────────────────
const pages = ['overview','pending','users','transactions'];

function showPage(name) {
  pages.forEach(p => {
    document.getElementById('page-'+p).classList.remove('active');
    document.querySelectorAll('.nav-item').forEach((el, i) => {
      if (el.onclick && el.onclick.toString().includes(pages[i])) el.classList.remove('active');
    });
  });
  document.getElementById('page-'+name).classList.add('active');
  document.querySelectorAll('.nav-item').forEach(el => {
    if (el.onclick && el.onclick.toString().includes("'"+name+"'")) el.classList.add('active');
  });

  if (name === 'overview') loadStats();
  if (name === 'pending') loadPending();
  if (name === 'users') loadUsers();
  if (name === 'transactions') loadTransactions();
}

// ── TOAST ──────────────────────────────────
function showToast(msg, type='success') {
  const t = document.getElementById('toast');
  t.textContent = msg;
  t.className = 'toast show ' + type;
  setTimeout(() => t.className = 'toast', 3200);
}

// ── MODAL ──────────────────────────────────
function openModal(id) { document.getElementById(id).classList.add('show'); }
function closeModal(id) { document.getElementById(id).classList.remove('show'); }

// ── FILTER TABLE ───────────────────────────
function filterTable(tbodyId, query) {
  const q = query.toLowerCase();
  document.querySelectorAll('#'+tbodyId+' tr').forEach(row => {
    row.style.display = row.textContent.toLowerCase().includes(q) ? '' : 'none';
  });
}

// ── FORMAT ─────────────────────────────────
function fDate(str) {
  if (!str) return '—';
  return new Date(str).toLocaleDateString('ro-RO', {
    day: '2-digit', month: '2-digit', year: 'numeric',
    hour: '2-digit', minute: '2-digit'
  });
}
function fNum(n) { return parseFloat(n).toFixed(2); }

// ── STATS ──────────────────────────────────
async function loadStats() {
  const r = await fetch('/api/stats');
  const d = await r.json();
  document.getElementById('stat-users').textContent = d.total_users;
  document.getElementById('stat-balance').textContent = fNum(d.total_balance) + ' USDT';
  document.getElementById('stat-volume').textContent = fNum(d.volume_today) + ' USDT';
  document.getElementById('stat-pdep').textContent = d.pending_deposits;
  document.getElementById('stat-pwit').textContent = d.pending_withdrawals;

  const total = d.pending_deposits + d.pending_withdrawals;
  const badge = document.getElementById('pending-badge');
  badge.textContent = total;
  badge.style.display = total > 0 ? '' : 'none';
}

// ── PENDING ────────────────────────────────
async function loadPending() {
  const [dRes, wRes] = await Promise.all([
    fetch('/api/pending_deposits'), fetch('/api/pending_withdrawals')
  ]);
  const deposits = await dRes.json();
  const withdrawals = await wRes.json();

  const depBody = document.getElementById('pending-deposits-body');
  if (deposits.length === 0) {
    depBody.innerHTML = '<tr><td colspan="4"><div class="empty-state"><div class="icon">✅</div>Nicio depunere în așteptare</div></td></tr>';
  } else {
    depBody.innerHTML = deposits.map(t => `
      <tr>
        <td><strong>${t.gg_username}</strong><br><span style="color:var(--text-dim);font-size:11px">${t.user_id}</span></td>
        <td><span class="pill pill-yellow">${fNum(t.amount)} USDT</span></td>
        <td style="color:var(--text-dim);font-size:12px">${fDate(t.created_at)}</td>
        <td>
          <button class="btn btn-green btn-sm" onclick="openDepositApprove(${t.id}, ${t.user_id}, '${t.gg_username}')">✓ Confirmă</button>
          <button class="btn btn-red btn-sm" style="margin-top:4px" onclick="rejectTx(${t.id}, 'deposit')">✗ Respinge</button>
        </td>
      </tr>
    `).join('');
  }

  const witBody = document.getElementById('pending-withdrawals-body');
  if (withdrawals.length === 0) {
    witBody.innerHTML = '<tr><td colspan="4"><div class="empty-state"><div class="icon">✅</div>Nicio retragere în așteptare</div></td></tr>';
  } else {
    witBody.innerHTML = withdrawals.map(t => `
      <tr>
        <td><strong>${t.gg_username}</strong><br><span style="color:var(--text-dim);font-size:11px">${t.user_id}</span></td>
        <td><span class="pill pill-red">${fNum(t.amount)} USDT</span></td>
        <td style="color:var(--text-dim);font-size:12px">${fDate(t.created_at)}</td>
        <td>
          <button class="btn btn-green btn-sm" onclick="approveTx(${t.id}, ${t.user_id}, ${t.amount}, 'withdraw')">✓ Aprobă</button>
          <button class="btn btn-red btn-sm" style="margin-top:4px" onclick="rejectTx(${t.id}, 'withdraw')">✗ Respinge</button>
        </td>
      </tr>
    `).join('');
  }
}

// ── USERS ──────────────────────────────────
async function loadUsers() {
  const r = await fetch('/api/users');
  const users = await r.json();
  const body = document.getElementById('users-body');

  if (users.length === 0) {
    body.innerHTML = '<tr><td colspan="6"><div class="empty-state"><div class="icon">👥</div>Niciun utilizator înregistrat</div></td></tr>';
    return;
  }

  body.innerHTML = users.map(u => `
    <tr>
      <td><code style="font-size:12px;color:var(--text-dim)">${u.telegram_id}</code></td>
      <td><strong>${u.gg_username || '—'}</strong></td>
      <td><span style="color:var(--gold);font-weight:600">${fNum(u.balance)} USDT</span></td>
      <td><span class="pill ${u.status === 'active' ? 'pill-green' : 'pill-red'}">${u.status}</span></td>
      <td style="color:var(--text-dim);font-size:12px">${fDate(u.registered_at)}</td>
      <td>
        <button class="btn btn-ghost btn-sm" onclick="openBalanceEdit(${u.telegram_id}, '${u.gg_username}', ${u.balance})">
          ✏️ Editează Sold
        </button>
      </td>
    </tr>
  `).join('');
}

// ── TRANSACTIONS ───────────────────────────
async function loadTransactions() {
  const r = await fetch('/api/transactions');
  const txs = await r.json();
  const body = document.getElementById('tx-body');

  if (txs.length === 0) {
    body.innerHTML = '<tr><td colspan="6"><div class="empty-state"><div class="icon">💳</div>Nicio tranzacție</div></td></tr>';
    return;
  }

  body.innerHTML = txs.map(t => {
    const typePill = t.type === 'deposit'
      ? '<span class="pill pill-green">💰 Depunere</span>'
      : '<span class="pill pill-red">💸 Retragere</span>';
    const statusPill = {
      pending: '<span class="pill pill-yellow">Pending</span>',
      completed: '<span class="pill pill-green">Completat</span>',
      rejected: '<span class="pill pill-red">Respins</span>'
    }[t.status] || t.status;

    return `
      <tr>
        <td style="color:var(--text-dim);font-size:12px">#${t.id}</td>
        <td><strong>${t.gg_username}</strong></td>
        <td>${typePill}</td>
        <td style="font-weight:600">${fNum(t.amount)} USDT</td>
        <td>${statusPill}</td>
        <td style="color:var(--text-dim);font-size:12px">${fDate(t.created_at)}</td>
      </tr>
    `;
  }).join('');
}

// ── BALANCE EDIT ───────────────────────────
function openBalanceEdit(tgId, ggName, balance) {
  document.getElementById('edit-tg-id').value = tgId;
  document.getElementById('edit-gg-name').value = ggName;
  document.getElementById('edit-balance-val').value = balance;
  openModal('balance-modal');
}

async function saveBalance() {
  const tgId = document.getElementById('edit-tg-id').value;
  const balance = document.getElementById('edit-balance-val').value;

  const r = await fetch('/api/update_balance', {
    method: 'POST',
    headers: {'Content-Type':'application/json'},
    body: JSON.stringify({telegram_id: tgId, balance: balance})
  });

  if ((await r.json()).success) {
    closeModal('balance-modal');
    showToast('✅ Sold actualizat cu succes!');
    loadUsers();
    loadStats();
  } else {
    showToast('❌ Eroare la actualizare', 'error');
  }
}

// ── DEPOSIT APPROVE ────────────────────────
function openDepositApprove(txId, userId, ggName) {
  document.getElementById('dep-tx-id').value = txId;
  document.getElementById('dep-user-id').value = userId;
  document.getElementById('dep-gg-name').value = ggName;
  document.getElementById('dep-amount-val').value = '';
  openModal('deposit-amount-modal');
}

async function confirmDepositAmount() {
  const txId = parseInt(document.getElementById('dep-tx-id').value);
  const userId = parseInt(document.getElementById('dep-user-id').value);
  const amount = parseFloat(document.getElementById('dep-amount-val').value);

  if (!amount || amount <= 0) {
    showToast('⚠️ Introdu o sumă validă', 'error');
    return;
  }

  const r = await fetch('/api/approve_transaction', {
    method: 'POST',
    headers: {'Content-Type':'application/json'},
    body: JSON.stringify({tx_id: txId, user_id: userId, amount: amount, type: 'deposit'})
  });

  if ((await r.json()).success) {
    closeModal('deposit-amount-modal');
    showToast('✅ Depunere confirmată și sold actualizat!');
    loadPending();
    loadStats();
  } else {
    showToast('❌ Eroare', 'error');
  }
}

async function approveTx(txId, userId, amount, type) {
  if (!confirm(`Confirmi aprobarea de ${fNum(amount)} USDT?`)) return;
  const r = await fetch('/api/approve_transaction', {
    method: 'POST',
    headers: {'Content-Type':'application/json'},
    body: JSON.stringify({tx_id: txId, user_id: userId, amount: amount, type: type})
  });
  if ((await r.json()).success) {
    showToast('✅ Tranzacție aprobată!');
    loadPending(); loadStats();
  } else {
    showToast('❌ Eroare', 'error');
  }
}

async function rejectTx(txId, type) {
  if (!confirm('Ești sigur că vrei să respingi această tranzacție?')) return;
  const r = await fetch('/api/reject_transaction', {
    method: 'POST',
    headers: {'Content-Type':'application/json'},
    body: JSON.stringify({tx_id: txId})
  });
  if ((await r.json()).success) {
    showToast('Tranzacție respinsă.', 'error');
    loadPending(); loadStats();
  } else {
    showToast('❌ Eroare', 'error');
  }
}

// ── CLOSE MODAL ON OUTSIDE CLICK ───────────
document.querySelectorAll('.modal-overlay').forEach(overlay => {
  overlay.addEventListener('click', e => {
    if (e.target === overlay) overlay.classList.remove('show');
  });
});

// ── INIT ───────────────────────────────────
loadStats();
setInterval(loadStats, 30000); // refresh stats every 30s
</script>
</body>
</html>"""

if __name__ == "__main__":
    port = int(os.getenv("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False)
