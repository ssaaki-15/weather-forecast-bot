"""
YouTube OAuth2 初期セットアップスクリプト
=========================================
初回のみローカルで実行してリフレッシュトークンを取得する。
取得したトークンを GitHub Secrets に登録すれば以降は自動実行される。

使い方：
  1. Google Cloud Console でプロジェクトを作成
  2. YouTube Data API v3 を有効化
  3. OAuth2 クライアントID（デスクトップアプリ用）を作成
  4. クライアントID・シークレットをこのスクリプトに設定して実行
  5. ブラウザで認可 → 表示されたリフレッシュトークンを GitHub Secrets に登録

必要なパッケージ:
  pip install google-auth-oauthlib
"""

import json
import webbrowser
import urllib.parse
import urllib.request
from http.server import HTTPServer, BaseHTTPRequestHandler

# ==============================================================
# ここに Google Cloud Console から取得した値を入力してください
# ==============================================================
CLIENT_ID     = "YOUR_CLIENT_ID.apps.googleusercontent.com"
CLIENT_SECRET = "YOUR_CLIENT_SECRET"
REDIRECT_URI  = "http://localhost:8080/callback"
# ==============================================================

SCOPES = [
    "https://www.googleapis.com/auth/youtube.upload",
    "https://www.googleapis.com/auth/youtube",
]

AUTH_URL   = "https://accounts.google.com/o/oauth2/v2/auth"
TOKEN_URL  = "https://oauth2.googleapis.com/token"

_auth_code = None


class CallbackHandler(BaseHTTPRequestHandler):
    """ローカルサーバーで認可コードを受け取る"""
    def do_GET(self):
        global _auth_code
        params = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
        if "code" in params:
            _auth_code = params["code"][0]
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b"<h2>認証完了！ターミナルに戻ってください。</h2>")
        else:
            self.send_response(400)
            self.end_headers()
            self.wfile.write(b"<h2>認証失敗</h2>")

    def log_message(self, *args):
        pass  # ログ抑制


def main():
    if CLIENT_ID == "YOUR_CLIENT_ID.apps.googleusercontent.com":
        print("❌ CLIENT_ID と CLIENT_SECRET をスクリプト内に設定してから実行してください。")
        return

    # 認可URLを生成
    params = {
        "client_id":     CLIENT_ID,
        "redirect_uri":  REDIRECT_URI,
        "response_type": "code",
        "scope":         " ".join(SCOPES),
        "access_type":   "offline",
        "prompt":        "consent",
    }
    auth_url = f"{AUTH_URL}?{urllib.parse.urlencode(params)}"

    print("\n🌐 ブラウザで YouTube への認可を行います...")
    print(f"   URL: {auth_url}\n")
    webbrowser.open(auth_url)

    # ローカルサーバーで認可コードを受け取る
    print("📡 認可コード待ち受け中（localhost:8080）...")
    server = HTTPServer(("localhost", 8080), CallbackHandler)
    server.handle_request()

    if not _auth_code:
        print("❌ 認可コードの取得に失敗しました。")
        return

    print(f"✅ 認可コード取得: {_auth_code[:20]}...")

    # 認可コード → トークン交換
    body = urllib.parse.urlencode({
        "client_id":     CLIENT_ID,
        "client_secret": CLIENT_SECRET,
        "code":          _auth_code,
        "redirect_uri":  REDIRECT_URI,
        "grant_type":    "authorization_code",
    }).encode("utf-8")

    req = urllib.request.Request(
        TOKEN_URL, data=body, method="POST",
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        token_data = json.loads(resp.read().decode("utf-8"))

    refresh_token = token_data.get("refresh_token", "")
    if not refresh_token:
        print(f"❌ リフレッシュトークン取得失敗: {token_data}")
        return

    print("\n" + "="*60)
    print("🎉 リフレッシュトークンの取得に成功しました！")
    print("="*60)
    print("\n以下の値を GitHub Secrets に登録してください：\n")
    print(f"  YOUTUBE_CLIENT_ID:     {CLIENT_ID}")
    print(f"  YOUTUBE_CLIENT_SECRET: {CLIENT_SECRET}")
    print(f"  YOUTUBE_REFRESH_TOKEN: {refresh_token}")
    print("\n⚠️  リフレッシュトークンは秘密情報です。公開リポジトリにコミットしないでください。")
    print("="*60)

    # ローカルに保存（gitignore で除外すること）
    with open(".youtube_tokens.json", "w") as f:
        json.dump({
            "client_id":     CLIENT_ID,
            "client_secret": CLIENT_SECRET,
            "refresh_token": refresh_token,
        }, f, indent=2)
    print("\n💾 .youtube_tokens.json に保存しました（gitignore に追加してください）")


if __name__ == "__main__":
    main()
