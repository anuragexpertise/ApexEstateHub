def when_ready(server):
    print("✅ EstateHub production server is ready")


def post_fork(server, worker):
    print(f"🔄 Worker {worker.pid} started")
    try:
        from app.services.redis_broker import broker
        broker.start(lambda payload: broker.dispatch_to_listeners(payload))
    except Exception as exc:
        print(f"⚠️  SSE Redis broker not started in worker {worker.pid}: {exc}")


def post_worker_exit(server, worker):
    print(f"🔄 Worker {worker.pid} exited")
