"""Diagnostic script to test AWS Bedrock connectivity via Bearer token.

Tests 4 layers:
  1. Environment variables loaded correctly
  2. Raw HTTPS connectivity to Bedrock endpoint
  3. Anthropic SDK direct API call (bypassing claude.exe)
  4. Claude Agent SDK query() — the actual path used by the orchestrator
"""

from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path

# Load .env first
from dotenv import load_dotenv
load_dotenv(Path(__file__).resolve().parent / ".env")
os.environ.pop("ANTHROPIC_MODEL", None)


def section(title: str) -> None:
    print(f"\n{'='*60}")
    print(f"  {title}")
    print(f"{'='*60}")


def test_1_env_vars() -> bool:
    """Check that all required env vars are set."""
    section("TEST 1: Environment Variables")
    
    required = {
        "CLAUDE_CODE_USE_BEDROCK": os.environ.get("CLAUDE_CODE_USE_BEDROCK"),
        "AWS_REGION": os.environ.get("AWS_REGION"),
    }
    
    auth_bearer = os.environ.get("AWS_BEARER_TOKEN_BEDROCK")
    auth_key = os.environ.get("AWS_ACCESS_KEY_ID")
    auth_secret = os.environ.get("AWS_SECRET_ACCESS_KEY")
    
    ok = True
    for k, v in required.items():
        status = "✅" if v else "❌ MISSING"
        print(f"  {k} = {v!r}  {status}")
        if not v:
            ok = False
    
    # Auth method
    if auth_bearer:
        print(f"  AWS_BEARER_TOKEN_BEDROCK = {auth_bearer[:20]}...{auth_bearer[-10:]}  ✅ ({len(auth_bearer)} chars)")
        print(f"  Auth method: Bearer token")
    elif auth_key and auth_secret:
        print(f"  AWS_ACCESS_KEY_ID = {auth_key[:8]}...  ✅")
        print(f"  AWS_SECRET_ACCESS_KEY = ***  ✅")
        print(f"  Auth method: IAM keys")
    else:
        print(f"  ❌ No auth method found (need AWS_BEARER_TOKEN_BEDROCK or IAM keys)")
        ok = False
    
    # Check for model env var
    model = os.environ.get("ANTHROPIC_MODEL") or os.environ.get("ANTHROPIC_DEFAULT_SONNET_MODEL")
    if model:
        print(f"  Model override: {model}")
    else:
        print(f"  Model override: (none — SDK will auto-select)")
    
    return ok


def test_2_network_connectivity() -> bool:
    """Test raw HTTPS connectivity to the Bedrock endpoint."""
    section("TEST 2: Network Connectivity to Bedrock")
    
    region = os.environ.get("AWS_REGION", "us-east-2")
    endpoint = f"bedrock-runtime.{region}.amazonaws.com"
    
    import socket
    import ssl
    
    print(f"  Target: {endpoint}:443")
    
    # DNS resolution
    try:
        ip = socket.gethostbyname(endpoint)
        print(f"  DNS resolve: {ip}  ✅")
    except socket.gaierror as e:
        print(f"  DNS resolve: ❌ FAILED — {e}")
        return False
    
    # TCP connection
    try:
        sock = socket.create_connection((endpoint, 443), timeout=10)
        print(f"  TCP connect: ✅")
    except (socket.timeout, ConnectionRefusedError, OSError) as e:
        print(f"  TCP connect: ❌ FAILED — {e}")
        return False
    
    # TLS handshake
    try:
        ctx = ssl.create_default_context()
        with ctx.wrap_socket(sock, server_hostname=endpoint) as ssock:
            print(f"  TLS handshake: ✅ (protocol={ssock.version()})")
            ssock.close()
    except ssl.SSLError as e:
        print(f"  TLS handshake: ❌ FAILED — {e}")
        sock.close()
        return False
    
    return True


def test_3_anthropic_sdk() -> bool:
    """Test direct Anthropic SDK call to Bedrock."""
    section("TEST 3: Anthropic SDK → Bedrock (direct API)")
    
    try:
        import anthropic
        print(f"  anthropic SDK version: {anthropic.__version__}")
    except ImportError:
        print(f"  ❌ anthropic package not installed")
        return False
    
    region = os.environ.get("AWS_REGION", "us-east-2")
    bearer = os.environ.get("AWS_BEARER_TOKEN_BEDROCK")
    access_key = os.environ.get("AWS_ACCESS_KEY_ID")
    secret_key = os.environ.get("AWS_SECRET_ACCESS_KEY")
    
    # Try to create a Bedrock client
    try:
        if bearer:
            # Bearer token auth — use AnthropicBedrock with session token approach
            # The SDK wants AWS credentials, not a bearer token directly.
            # Let's try the standard approach first.
            print(f"  Attempting: AnthropicBedrock with Bearer token...")
            
            # Check if anthropic has BedrockBearerToken or similar
            # Try the standard Bedrock client with session_token
            client = anthropic.AnthropicBedrock(
                aws_region=region,
                aws_session_token=bearer,
                aws_access_key="BEDROCK_BEARER",  # placeholder for bearer auth
                aws_secret_key="BEDROCK_BEARER",   # placeholder for bearer auth
            )
        elif access_key and secret_key:
            print(f"  Attempting: AnthropicBedrock with IAM keys...")
            client = anthropic.AnthropicBedrock(
                aws_region=region,
                aws_access_key=access_key,
                aws_secret_key=secret_key,
            )
        else:
            print(f"  ❌ No auth credentials available")
            return False
        
        # Try a minimal completion
        # Use cross-region inference profile format
        models_to_try = [
            "us.anthropic.claude-sonnet-4-20250514-v1:0",
            "us.anthropic.claude-3-5-sonnet-20241022-v2:0",
            "us.anthropic.claude-3-7-sonnet-20250219-v1:0",
            "anthropic.claude-3-5-sonnet-20241022-v2:0",
            "anthropic.claude-3-sonnet-20240229-v1:0",
        ]
        
        for model_id in models_to_try:
            try:
                print(f"  Trying model: {model_id}...")
                response = client.messages.create(
                    model=model_id,
                    max_tokens=10,
                    messages=[{"role": "user", "content": "Say 'hello'"}],
                )
                text = response.content[0].text if response.content else "(empty)"
                print(f"  ✅ Response: {text}")
                print(f"  Model used: {model_id}")
                print(f"  Usage: input={response.usage.input_tokens}, output={response.usage.output_tokens}")
                return True
            except Exception as e:
                err = str(e)
                if len(err) > 150:
                    err = err[:150] + "..."
                print(f"    ❌ {type(e).__name__}: {err}")
                continue
        
        print(f"  ❌ All models failed")
        return False
        
    except Exception as e:
        print(f"  ❌ Client creation failed: {type(e).__name__}: {e}")
        return False


def test_3b_anthropic_sdk_direct_bearer() -> bool:
    """Test Anthropic SDK with direct Bearer token in Authorization header."""
    section("TEST 3b: Anthropic SDK → Bedrock (raw Bearer header)")
    
    bearer = os.environ.get("AWS_BEARER_TOKEN_BEDROCK")
    if not bearer:
        print("  ⏭️ Skipping — no bearer token")
        return False
    
    region = os.environ.get("AWS_REGION", "us-east-2")
    
    try:
        import httpx
        import json as _json
        
        endpoint = f"https://bedrock-runtime.{region}.amazonaws.com"
        
        models_to_try = [
            "us.anthropic.claude-sonnet-4-20250514-v1:0",
            "us.anthropic.claude-3-5-sonnet-20241022-v2:0",
            "us.anthropic.claude-3-7-sonnet-20250219-v1:0",
            "anthropic.claude-3-5-sonnet-20241022-v2:0",
        ]
        
        for model_id in models_to_try:
            try:
                url = f"{endpoint}/model/{model_id}/invoke"
                headers = {
                    "Authorization": f"Bearer {bearer}",
                    "Content-Type": "application/json",
                    "Accept": "application/json",
                }
                body = {
                    "anthropic_version": "bedrock-2023-05-31",
                    "max_tokens": 10,
                    "messages": [{"role": "user", "content": "Say hello"}],
                }
                
                print(f"  POST {url[:80]}...")
                resp = httpx.post(url, headers=headers, json=body, timeout=30)
                print(f"  Status: {resp.status_code}")
                
                if resp.status_code == 200:
                    data = resp.json()
                    text = data.get("content", [{}])[0].get("text", "(empty)")
                    print(f"  ✅ Response: {text}")
                    return True
                else:
                    body_text = resp.text[:200]
                    print(f"    ❌ {resp.status_code}: {body_text}")
                    
            except Exception as e:
                print(f"    ❌ {type(e).__name__}: {e}")
        
        return False
        
    except ImportError:
        print("  ❌ httpx not installed, skipping raw test")
        return False


def test_4_claude_sdk() -> bool:
    """Test the actual Claude Agent SDK query() path."""
    section("TEST 4: Claude Agent SDK query()")
    
    try:
        import claude_agent_sdk
        print(f"  claude_agent_sdk version: {claude_agent_sdk.__version__}")
    except (ImportError, AttributeError) as e:
        print(f"  ❌ claude_agent_sdk import failed: {e}")
        return False
    
    try:
        from claude_agent_sdk import ClaudeAgentOptions, query
        print(f"  Imports: ClaudeAgentOptions, query ✅")
    except ImportError as e:
        print(f"  ❌ Cannot import ClaudeAgentOptions/query: {e}")
        return False
    
    # Check for bundled CLI
    bundled = Path(sys.prefix) / "lib" / "site-packages" / "claude_agent_sdk" / "_bundled" / "claude.exe"
    if bundled.exists():
        print(f"  Bundled CLI: {bundled} ✅ ({bundled.stat().st_size / 1024 / 1024:.1f} MB)")
    else:
        # Try alternative paths
        alt = Path(claude_agent_sdk.__file__).parent / "_bundled" / "claude.exe"
        if alt.exists():
            print(f"  Bundled CLI: {alt} ✅ ({alt.stat().st_size / 1024 / 1024:.1f} MB)")
        else:
            print(f"  ❌ Bundled CLI not found at {bundled} or {alt}")
            # Try to find it
            sdk_root = Path(claude_agent_sdk.__file__).parent
            print(f"  SDK root: {sdk_root}")
            for f in sdk_root.rglob("claude*"):
                print(f"    Found: {f}")
    
    # Try a simple query
    print(f"\n  Running query() with minimal prompt (timeout 30s)...")
    print(f"  ENV: CLAUDE_CODE_USE_BEDROCK={os.environ.get('CLAUDE_CODE_USE_BEDROCK')}")
    print(f"  ENV: AWS_REGION={os.environ.get('AWS_REGION')}")
    
    options = ClaudeAgentOptions(
        system_prompt="You are a test assistant. Reply with exactly: TEST_OK",
        max_turns=1,
        permission_mode="acceptEdits",
    )
    
    async def _run_query():
        messages = []
        async for msg in query(prompt="Say TEST_OK", options=options):
            messages.append(msg)
            msg_type = type(msg).__name__
            print(f"  📨 {msg_type}: {str(msg)[:100]}")
        return messages
    
    try:
        # Run with timeout
        if os.name == "nt":
            asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())
        
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            messages = loop.run_until_complete(
                asyncio.wait_for(_run_query(), timeout=30)
            )
            if messages:
                print(f"  ✅ Received {len(messages)} messages")
                return True
            else:
                print(f"  ❌ No messages received (query returned nothing)")
                return False
        except asyncio.TimeoutError:
            print(f"  ❌ TIMEOUT after 30s — claude.exe is not responding")
            print(f"     This is the same issue causing 'Failed to fetch' in the UI")
            return False
        finally:
            loop.close()
    
    except Exception as e:
        print(f"  ❌ {type(e).__name__}: {e}")
        import traceback
        traceback.print_exc()
        return False


def main():
    print("=" * 60)
    print("  FREESTYLE-02 BEDROCK CONNECTIVITY DIAGNOSTIC")
    print("=" * 60)
    
    results = {}
    
    results["env"] = test_1_env_vars()
    results["network"] = test_2_network_connectivity()
    results["anthropic_sdk"] = test_3_anthropic_sdk()
    results["bearer_raw"] = test_3b_anthropic_sdk_direct_bearer()
    results["claude_sdk"] = test_4_claude_sdk()
    
    section("SUMMARY")
    for name, ok in results.items():
        status = "✅ PASS" if ok else "❌ FAIL"
        print(f"  {name:20s} {status}")
    
    # Diagnosis
    print()
    if results["env"] and results["network"] and not results["anthropic_sdk"] and not results["bearer_raw"]:
        print("  📋 DIAGNOSIS: Network OK but authentication failing.")
        print("     → Bearer token may be expired or format is wrong.")
        print("     → Try regenerating the token.")
    elif results["env"] and results["network"] and (results["anthropic_sdk"] or results["bearer_raw"]) and not results["claude_sdk"]:
        print("  📋 DIAGNOSIS: Bedrock API works directly but claude.exe CLI fails.")
        print("     → The bundled claude.exe doesn't support Bearer token auth,")
        print("       or has a Windows subprocess issue.")
        print("     → SOLUTION: Rewrite orchestrator to use anthropic SDK directly.")
    elif results["env"] and not results["network"]:
        print("  📋 DIAGNOSIS: Cannot reach Bedrock endpoint.")
        print("     → Check VPN/proxy/firewall settings.")
    elif all(results.values()):
        print("  📋 DIAGNOSIS: Everything works! The issue may be transient.")
    else:
        print("  📋 DIAGNOSIS: Multiple failures. Check individual test output above.")


if __name__ == "__main__":
    main()
