# import uvicorn

# if __name__ == "__main__":
#     uvicorn.run(
#     "app.main:app",
#     host="127.0.0.1",
#     port=8000,
#     reload=True
#     )

from granian import Granian
from granian.constants import Loops, Interfaces


if __name__ == "__main__":
    Granian(
        target="app.main:app",
        address="127.0.0.1",
        port=8000,
        workers=2,
        loop=Loops.uvloop,
        log_enabled=True,
        interface=Interfaces.ASGI,
        reload=True
    ).serve()