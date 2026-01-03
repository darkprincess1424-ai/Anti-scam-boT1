from flask import Flask, jsonify, request
import datetime
import threading
import os
import sys
import logging
from functools import wraps

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

app = Flask(__name__)

# Глобальные переменные для мониторинга состояния
bot_status = {
    "bot_alive": False,
    "last_activity": None,
    "total_requests": 0,
    "error_count": 0,
    "start_time": datetime.datetime.utcnow().isoformat()
}

# Декоратор для логирования запросов
def log_request(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        bot_status["total_requests"] += 1
        logger.info(f"Health check request from {request.remote_addr}")
        return f(*args, **kwargs)
    return decorated_function

@app.route('/')
@log_request
def home():
    """Главная страница для проверки работы"""
    return jsonify({
        "service": "Telegram Bot",
        "status": "running",
        "uptime": str(datetime.datetime.utcnow() - datetime.datetime.fromisoformat(bot_status["start_time"])),
        "timestamp": datetime.datetime.utcnow().isoformat()
    })

@app.route('/health')
@log_request
def health():
    """Основной health-check endpoint для мониторинга"""
    health_data = {
        "status": "healthy",
        "service": "telegram-bot",
        "timestamp": datetime.datetime.utcnow().isoformat(),
        "version": os.environ.get("VERSION", "1.0.0"),
        "environment": os.environ.get("ENVIRONMENT", "production"),
        "metrics": {
            "total_requests": bot_status["total_requests"],
            "error_count": bot_status["error_count"],
            "uptime_seconds": (
                datetime.datetime.utcnow() - 
                datetime.datetime.fromisoformat(bot_status["start_time"])
            ).total_seconds(),
            "bot_alive": bot_status["bot_alive"],
            "last_activity": bot_status["last_activity"]
        },
        "dependencies": {
            "telegram_api": "ok",  # Можно добавить реальные проверки
            "database": "ok"       # если есть БД
        }
    }
    
    # Проверка критических компонентов
    issues = []
    
    # Проверка памяти (пример)
    try:
        import psutil
        memory_percent = psutil.virtual_memory().percent
        health_data["metrics"]["memory_percent"] = memory_percent
        if memory_percent > 90:
            issues.append("high_memory_usage")
    except ImportError:
        pass
    
    # Проверка диска
    try:
        import psutil
        disk_percent = psutil.disk_usage('/').percent
        health_data["metrics"]["disk_percent"] = disk_percent
        if disk_percent > 90:
            issues.append("high_disk_usage")
    except ImportError:
        pass
    
    if issues:
        health_data["status"] = "degraded"
        health_data["issues"] = issues
    
    # Проверка бота
    if not bot_status["bot_alive"]:
        health_data["status"] = "unhealthy"
        health_data["issues"] = ["bot_not_running"]
    
    status_code = 200 if health_data["status"] == "healthy" else 503
    
    return jsonify(health_data), status_code

@app.route('/health/live')
@log_request
def liveness():
    """Liveness probe для Kubernetes/Render"""
    return jsonify({"status": "alive"}), 200

@app.route('/health/ready')
@log_request
def readiness():
    """Readiness probe"""
    if bot_status["bot_alive"]:
        return jsonify({"status": "ready"}), 200
    else:
        return jsonify({"status": "not_ready"}), 503

@app.route('/metrics')
@log_request
def metrics():
    """Prometheus-совместимые метрики"""
    from prometheus_client import generate_latest, Counter, Gauge, Histogram
    
    # Создаем метрики
    REQUEST_COUNT = Counter('http_requests_total', 'Total HTTP requests')
    REQUEST_COUNT.inc(bot_status["total_requests"])
    
    BOT_STATUS = Gauge('bot_status', 'Bot status (1=alive, 0=dead)')
    BOT_STATUS.set(1 if bot_status["bot_alive"] else 0)
    
    UPTIME = Gauge('service_uptime_seconds', 'Service uptime in seconds')
    UPTIME.set(
        (datetime.datetime.utcnow() - 
         datetime.datetime.fromisoformat(bot_status["start_time"])
        ).total_seconds()
    )
    
    return generate_latest(), 200, {'Content-Type': 'text/plain'}

@app.route('/info')
@log_request
def info():
    """Информация о сервисе"""
    return jsonify({
        "name": "Telegram Bot",
        "description": "AI-powered Telegram bot",
        "repository": "https://github.com/YOUR_USERNAME/YOUR_REPO",
        "author": "Your Name",
        "endpoints": [
            "/health",
            "/health/live",
            "/health/ready",
            "/metrics",
            "/info"
        ]
    })

@app.route('/status/update', methods=['POST'])
def update_status():
    """Эндпоинт для обновления статуса бота (вызывается из bot.py)"""
    data = request.json
    if data and 'alive' in data:
        bot_status["bot_alive"] = data['alive']
        bot_status["last_activity"] = datetime.datetime.utcnow().isoformat()
        logger.info(f"Bot status updated: alive={data['alive']}")
    
    return jsonify({"success": True})

def start_flask_server(port=5000):
    """Запуск Flask сервера"""
    logger.info(f"Starting Flask health-check server on port {port}")
    app.run(host='0.0.0.0', port=port, debug=False, use_reloader=False)

# Глобальная функция для запуска
def run_health_check():
    """Функция для импорта и запуска из bot.py"""
    flask_thread = threading.Thread(
        target=start_flask_server,
        daemon=True,
        kwargs={'port': int(os.environ.get('PORT', 5000))}
    )
    flask_thread.start()
    logger.info("Health-check server thread started")
    return flask_thread

if __name__ == '__main__':
    # Запуск напрямую для тестирования
    port = int(os.environ.get('PORT', 5000))
    start_flask_server(port)
