from app.main import create_app

app = create_app()
for route in app.router.routes:
    if route.path == "/chat/stream":
        print("Route path", route.path)
        print("methods", route.methods)
        print("endpoint", route.endpoint)
        print("query params", [param.name for param in route.dependant.query_params])
