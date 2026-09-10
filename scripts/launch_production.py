#!/usr/bin/env python3
"""
Production Launch Script for Financial AI Agent
Coordinates startup of main application stack + monitoring infrastructure
"""
import subprocess
import time
import sys
import requests
from pathlib import Path

def run_command(cmd: str, cwd: str = None) -> tuple[int, str]:
    """Run command and return exit code and output"""
    try:
        result = subprocess.run(
            cmd, shell=True, cwd=cwd, capture_output=True, text=True, timeout=300
        )
        return result.returncode, result.stdout + result.stderr
    except subprocess.TimeoutExpired:
        return -1, "Command timed out"

def check_service_health(name: str, url: str, max_retries: int = 30) -> bool:
    """Check if service is healthy"""
    print(f"🔍 Checking {name} health at {url}")
    
    for attempt in range(max_retries):
        try:
            response = requests.get(url, timeout=5)
            if response.status_code == 200:
                print(f"✅ {name} is healthy")
                return True
        except requests.RequestException:
            pass
        
        if attempt < max_retries - 1:
            print(f"⏳ {name} not ready, retrying in 5s ({attempt + 1}/{max_retries})")
            time.sleep(5)
    
    print(f"❌ {name} failed health check")
    return False

def main():
    print("🚀 Starting Financial AI Agent Production Stack")
    print("=" * 60)
    
    # Check if main application is running
    print("\n1️⃣ Checking main application stack...")
    exit_code, output = run_command("docker-compose ps")
    if "fin_app" not in output or "Up" not in output:
        print("⚠️ Main application not running. Please wait for docker-compose up --build to complete.")
        return 1
    
    # Start monitoring stack
    print("\n2️⃣ Starting monitoring stack...")
    exit_code, output = run_command("docker-compose -f docker-compose.monitoring.yml up -d")
    if exit_code != 0:
        print(f"❌ Failed to start monitoring stack: {output}")
        return 1
    print("✅ Monitoring stack started")
    
    # Wait for services to be ready
    print("\n3️⃣ Waiting for services to be ready...")
    
    services = [
        ("API Server", "http://localhost:8000/health"),
        ("Prometheus", "http://localhost:9090/-/healthy"),
        ("Grafana", "http://localhost:3001/api/health"),
    ]
    
    all_healthy = True
    for name, url in services:
        if not check_service_health(name, url):
            all_healthy = False
    
    if not all_healthy:
        print("\n⚠️ Some services are not healthy. Check logs with:")
        print("   docker-compose logs")
        print("   docker-compose -f docker-compose.monitoring.yml logs")
        return 1
    
    # Show system status
    print("\n4️⃣ System Status")
    print("=" * 40)
    print("🌐 API Server:      http://localhost:8000")
    print("📊 Prometheus:      http://localhost:9090")
    print("📈 Grafana:         http://localhost:3001 (admin/admin123)")
    print("🔧 Node Exporter:   http://localhost:9100")
    print("📈 Redis Exporter:  http://localhost:9121")
    print("🗄️ Postgres Export: http://localhost:9187")
    print("🚨 Alert Manager:   http://localhost:9093")
    
    # Test analytics endpoint
    print("\n5️⃣ Testing Analytics System...")
    try:
        response = requests.get("http://localhost:8000/api/analytics/quality-score", timeout=10)
        if response.status_code == 200:
            data = response.json()
            print(f"✅ Analytics working - Quality Score: {data.get('overall_quality', 'N/A')}%")
        else:
            print(f"⚠️ Analytics endpoint returned {response.status_code}")
    except Exception as e:
        print(f"⚠️ Could not test analytics: {e}")
    
    print("\n🎉 Financial AI Agent Production Stack is READY!")
    print("\n📝 Next Steps:")
    print("   - Open Grafana to view real-time dashboards")
    print("   - Test the API endpoints at http://localhost:8000/docs")
    print("   - Monitor system metrics in Prometheus")
    print("   - Check application logs: docker-compose logs -f")
    
    return 0

if __name__ == "__main__":
    exit(main())