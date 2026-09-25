# app/routes/web.py — NEW FILE
from flask import Blueprint, redirect, jsonify, render_template_string

web_bp = Blueprint('web', __name__)

@web_bp.route('/')
def index():
    return redirect('/dashboard/')

@web_bp.route('/health')
def health():
    try:
        from database.db_manager import db
        if db.is_healthy():
            return jsonify({'status': 'ok', 'db': 'connected'})
        else:
            return jsonify({'status': 'error', 'db': 'disconnected'}), 503
    except Exception as e:
        return jsonify({'status': 'error', 'db': str(e)}), 500


_MASTER_LOGIN_HTML = """
<!DOCTYPE html>
<html>
<head>
    <title>Master Admin Login — EstateHub</title>
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css" rel="stylesheet">
    <link href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.0/css/all.min.css" rel="stylesheet">
    <style>
        body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); min-height: 100vh; display: flex; align-items: center; justify-content: center; margin: 0; padding: 20px; }
        .login-card { background: #fff; border-radius: 16px; box-shadow: 0 20px 60px rgba(0,0,0,0.15); padding: 40px; width: 100%; max-width: 420px; }
        .login-header { text-align: center; margin-bottom: 32px; }
        .login-header .icon { width: 64px; height: 64px; border-radius: 16px; background: linear-gradient(135deg, #c96a19, #e67e22); display: flex; align-items: center; justify-content: center; margin: 0 auto 16px; }
        .login-header .icon i { font-size: 28px; color: #fff; }
        .login-header h2 { font-weight: 700; color: #15304f; margin: 0 0 8px; }
        .login-header p { color: #7d8ea3; margin: 0; font-size: 14px; }
        .form-label { font-weight: 600; font-size: 13px; color: #2c3e50; margin-bottom: 6px; display: block; }
        .form-control { border-radius: 10px; padding: 12px 16px; font-size: 14px; border: 1px solid #e2e8f0; transition: border-color 0.2s, box-shadow 0.2s; }
        .form-control:focus { border-color: #c96a19; box-shadow: 0 0 0 3px rgba(201,106,25,0.15); outline: none; }
        .btn-master { background: linear-gradient(135deg, #c96a19, #e67e22); border: none; border-radius: 10px; padding: 14px; font-weight: 600; font-size: 14px; color: #fff; width: 100%; transition: transform 0.1s, box-shadow 0.2s; }
        .btn-master:hover { transform: translateY(-1px); box-shadow: 0 8px 24px rgba(201,106,25,0.3); color: #fff; }
        .btn-master:active { transform: translateY(0); }
        .back-link { display: block; text-align: center; margin-top: 20px; color: #7d8ea3; text-decoration: none; font-size: 13px; }
        .back-link:hover { color: #c96a19; }
        .alert { border-radius: 10px; font-size: 13px; }
    </style>
</head>
<body>
    <div class="login-card">
        <div class="login-header">
            <div class="icon"><i class="fas fa-crown"></i></div>
            <h2>Master Admin Login</h2>
            <p>Enter your credentials to access the master dashboard</p>
        </div>
        <form method="POST" action="/auth/login" id="master-login-form">
            <input type="hidden" name="method" value="password">
            <div class="mb-3">
                <label class="form-label" for="email">Email Address</label>
                <input type="email" class="form-control" id="email" name="email" placeholder="admin@estatehub.com" required autocomplete="email">
            </div>
            <div class="mb-4">
                <label class="form-label" for="password">Password</label>
                <input type="password" class="form-control" id="password" name="password" placeholder="Enter your password" required autocomplete="current-password">
            </div>
            <button type="submit" class="btn-master"><i class="fas fa-sign-in-alt me-2"></i>Login as Master Admin</button>
        </form>
        <a href="/dashboard/" class="back-link"><i class="fas fa-arrow-left me-1"></i>Back to Society Login</a>
    </div>
    <script>
        document.getElementById('master-login-form').addEventListener('submit', async function(e) {
            e.preventDefault();
            const btn = this.querySelector('button[type=submit]');
            const originalText = btn.innerHTML;
            btn.disabled = true;
            btn.innerHTML = '<i class="fas fa-spinner fa-spin me-2"></i>Signing in...';
            
            const formData = new FormData(this);
            const data = Object.fromEntries(formData);
            
            try {
                const response = await fetch('/auth/login', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify(data)
                });
                const result = await response.json();
                if (result.success) {
                    window.location.href = result.redirect || '/dashboard/master';
                } else {
                    alert(result.message || 'Login failed');
                    btn.disabled = false;
                    btn.innerHTML = originalText;
                }
            } catch (err) {
                alert('Network error — please try again');
                btn.disabled = false;
                btn.innerHTML = originalText;
            }
        });
    </script>
</body>
</html>
"""

@web_bp.route('/master-login')
def master_login():
    return render_template_string(_MASTER_LOGIN_HTML)